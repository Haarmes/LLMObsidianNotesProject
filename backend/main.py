"""
Managed RAG backend
===================

FastAPI backend that combines the managed RAG demo with the web app integration
pattern:

* Azure AI Search provides retrieved context from an indexed document store.
* Azure OpenAI generates the final answer.
* /chat returns a full JSON response.
* /chat/stream streams token chunks over SSE.

The frontend can keep the same request shape used by the example app:

{
  "message": "...",
  "history": [{"role": "user"|"assistant", "content": "..."}],
  "session_id": "session-abc123"
}
"""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_community.retrievers import AzureAISearchRetriever
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

load_dotenv()


# ─── Configuration ───────────────────────────────────────────────────────────

AZURE_SEARCH_SERVICE_NAME = os.environ["AZURE_SEARCH_SERVICE_NAME"]
AZURE_SEARCH_INDEX_NAME = os.environ["AZURE_SEARCH_INDEX_NAME"]
AZURE_SEARCH_API_KEY = os.environ["AZURE_SEARCH_API_KEY"]
AZURE_SEARCH_CONTENT_FIELD = os.getenv("AZURE_SEARCH_CONTENT_FIELD", "content")
AZURE_SEARCH_TOP_K = int(os.getenv("AZURE_SEARCH_TOP_K", "3"))

AZURE_OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_OPENAI_API_KEY = os.environ["AZURE_OPENAI_API_KEY"]
AZURE_OPENAI_DEPLOYMENT = os.environ["AZURE_OPENAI_DEPLOYMENT"]
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")


# ─── Services ────────────────────────────────────────────────────────────────

retriever = AzureAISearchRetriever(
    service_name=AZURE_SEARCH_SERVICE_NAME,
    index_name=AZURE_SEARCH_INDEX_NAME,
    api_key=AZURE_SEARCH_API_KEY,
    content_key=AZURE_SEARCH_CONTENT_FIELD,
    top_k=AZURE_SEARCH_TOP_K,
)

llm = AzureChatOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_API_KEY,
    azure_deployment=AZURE_OPENAI_DEPLOYMENT,
    api_version=AZURE_OPENAI_API_VERSION,
    temperature=0,
)


# ─── App setup ───────────────────────────────────────────────────────────────

app = FastAPI(title="Managed RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Rate limiting ───────────────────────────────────────────────────────────

RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW = 60
request_timestamps: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(session_id: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    request_timestamps[session_id] = [t for t in request_timestamps[session_id] if t > window_start]
    if len(request_timestamps[session_id]) >= RATE_LIMIT_REQUESTS:
        return False
    request_timestamps[session_id].append(now)
    return True


# ─── Request / response models ───────────────────────────────────────────────


class ChatTurn(BaseModel):
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Conversation text")


class ChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = Field(default_factory=list)
    session_id: str = "default"
    verify_with_notes: bool = False


class VerificationResult(BaseModel):
    is_supported: bool
    reason: str


# ─── Helpers ────────────────────────────────────────────────────────────────


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Simple placeholder estimate for frontend usage display."""
    input_cost_per_m = 0.10
    output_cost_per_m = 0.40
    return (input_tokens / 1_000_000) * input_cost_per_m + (output_tokens / 1_000_000) * output_cost_per_m


def approximate_token_count(text: str) -> int:
    return max(1, len(text.split())) if text.strip() else 0


def build_context(query: str) -> list[str]:
    documents = retriever.invoke(query)
    return [document.page_content for document in documents]


def build_messages(history: list[ChatTurn], query: str, context: list[str]) -> list[Any]:
    context_block = "\n\n---\n\n".join(context) if context else "No relevant context was retrieved."
    messages: list[Any] = [
        SystemMessage(
            content=(
                "You are assistant that helps person learn by making quizzes based on provided notes/context. "
                "don't answer questions that are not about learning and topics of the notes "
            )
        ),
        SystemMessage(content=f"Retrieved context:\n\n{context_block}"),
    ]

    for turn in history:
        if turn.role == "assistant":
            messages.append(AIMessage(content=turn.content))
        else:
            messages.append(HumanMessage(content=turn.content))

    messages.append(HumanMessage(content=query))
    return messages


def build_usage(prompt_text: str, answer_text: str) -> dict[str, Any]:
    input_tokens = approximate_token_count(prompt_text)
    output_tokens = approximate_token_count(answer_text)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": estimate_cost(input_tokens, output_tokens),
    }


def render_prompt(query: str, history: list[ChatTurn], context: list[str]) -> str:
    history_block = "\n".join(f"{turn.role}: {turn.content}" for turn in history) if history else "(no prior history)"
    context_block = "\n\n---\n\n".join(context) if context else "(no retrieved context)"
    return f"History:\n{history_block}\n\nContext:\n{context_block}\n\nQuestion:\n{query}"


def generate_answer(query: str, history: list[ChatTurn], context: list[str]) -> tuple[str, dict[str, Any]]:
    messages = build_messages(history, query, context)
    response = llm.invoke(messages)
    answer_text = response.content if isinstance(response.content, str) else str(response.content)
    usage = build_usage(render_prompt(query, history, context), answer_text)
    return answer_text, usage


def verify_answer_with_context(query: str, answer: str, context: list[str]) -> VerificationResult:
    """Run a second LLM call that checks whether the answer is supported by retrieved notes."""
    context_block = "\n\n---\n\n".join(context) if context else "No context was retrieved."
    verification_messages = [
        SystemMessage(
            content=(
                "You are a strict fact-checker. "
                "Decide whether the assistant answer is supported by the provided notes/context only. "
                "Return JSON with keys: is_supported (boolean), reason (string). "
                "Keep reason concise in one sentence."
            )
        ),
        HumanMessage(
            content=(
                f"Question:\n{query}\n\n"
                f"Assistant answer:\n{answer}\n\n"
                f"Notes/context:\n{context_block}"
            )
        ),
    ]

    verification_response = llm.invoke(verification_messages)
    verification_text = (
        verification_response.content
        if isinstance(verification_response.content, str)
        else str(verification_response.content)
    )

    try:
        parsed = json.loads(verification_text)
        is_supported = bool(parsed.get("is_supported", False))
        reason = str(parsed.get("reason", "No reason provided by verification model.")).strip()
        return VerificationResult(is_supported=is_supported, reason=reason or "No reason provided by verification model.")
    except json.JSONDecodeError:
        fallback_supported = "supported" in verification_text.lower() and "not supported" not in verification_text.lower()
        return VerificationResult(
            is_supported=fallback_supported,
            reason=f"Unstructured verifier output: {verification_text[:220]}",
        )


# ─── Endpoints ───────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    if not check_rate_limit(request.session_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a moment.")

    context = build_context(request.message)
    answer_text, usage = generate_answer(request.message, request.history, context)
    verification: VerificationResult | None = None
    if request.verify_with_notes:
        verification = verify_answer_with_context(request.message, answer_text, context)

    return {
        "response": answer_text,
        "context": context,
        "usage": usage,
        "verification": verification.model_dump() if verification else None,
    }


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    if not check_rate_limit(request.session_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a moment.")

    context = build_context(request.message)
    messages = build_messages(request.history, request.message, context)

    def generate():
        answer_parts: list[str] = []
        for chunk in llm.stream(messages):
            chunk_text = getattr(chunk, "content", "") or ""
            if not chunk_text:
                continue
            answer_parts.append(chunk_text)
            event = json.dumps({"type": "text", "content": chunk_text})
            yield f"data: {event}\n\n"

        answer_text = "".join(answer_parts)
        usage = build_usage(render_prompt(request.message, request.history, context), answer_text)
        verification: VerificationResult | None = None
        if request.verify_with_notes:
            verification = verify_answer_with_context(request.message, answer_text, context)

        done_event = json.dumps(
            {
                "type": "done",
                "usage": usage,
                "context": context,
                "verification": verification.model_dump() if verification else None,
            }
        )
        yield f"data: {done_event}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
