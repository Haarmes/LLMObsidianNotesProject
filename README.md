# Obsidian Notes Quiz Demo

## Project Description

This is a full-stack web application that generates quiz questions and answers based on your indexed notes and documents. Upload your study materials to Azure, and the app will create contextually aware quiz questions using an LLM. You can toggle **streaming mode** to see answers appear token-by-token, and enable **fact-checking** to verify whether answers are actually supported by your notes.

**Key features:**
- Real-time streaming responses from the LLM
- Automatic fact-checking against retrieved notes
- Session-based rate limiting (20 requests per 60 seconds)
- Token usage and cost estimation display
- Dark purple/black themed UI

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        React Frontend                            │
│                  (localhost:3000 / :5173)                         │
│  • Quiz input & chat interface                                   │
│  • Streaming SSE decoder                                         │
│  • Real-time token display                                       │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                    HTTP/POST (JSON)
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend                                │
│                 (localhost:8000)                                  │
│  • /chat — non-streaming endpoint                                │
│  • /chat/stream — Server-Sent Events streaming                   │
│  • Rate limiting & session tracking                              │
│  • Verification (second LLM call)                                │
└────────┬──────────────────────────────────┬──────────────────────┘
         │                                  │
         ▼                                  ▼
   ┌──────────────────────┐    ┌──────────────────────────┐
   │  Azure AI Search     │    │   Azure OpenAI           │
   │  (Retrieval/RAG)     │    │  (LLM Generation &       │
   │                      │    │   Fact-checking)         │
   │  • Vector search     │    │                          │
   │  • Semantic ranking  │    │  • gpt-4o-mini           │
   │  • Chunked docs      │    │  • Temperature: 0        │
   └──────────────────────┘    └──────────────────────────┘
```

**Data Flow:**
1. User inputs a question in the React frontend.
2. Frontend sends `{ message, history, session_id, verify_with_notes }` to backend.
3. Backend retrieves relevant document chunks from Azure AI Search.
4. Backend generates an answer using Azure OpenAI (optionally with streaming).
5. If `verify_with_notes=true`, backend runs a second LLM call to fact-check.
6. Response streams back via SSE or JSON; frontend updates the UI in real-time.

---

## Technical Choices

### Frontend Stack
- **React 19** — Component-based UI framework; straightforward state management for chat history.
- **Create React App (CRA)** — Zero-config build setup with built-in linting and testing.
- **CSS Grid/Flexbox** — Layout without heavy dependencies; purple/black theme applied via CSS variables.

### Backend Stack
- **FastAPI 0.115** — Modern async Python web framework; auto-generated OpenAPI docs; built-in CORS support.
- **Uvicorn** — ASGI server for running FastAPI with streaming support (SSE).
- **LangChain** — Simplifies Azure AI Search integration and LLM chaining.
  - `AzureAISearchRetriever` — Managed RAG (Azure handles chunking, embedding, indexing).
  - `AzureChatOpenAI` — Direct interface to Azure OpenAI deployment.

### AI/ML Services
- **Azure AI Search** — Managed vector database + semantic ranking; eliminates need to self-host Chroma/Weaviate.
- **Azure OpenAI** — Enterprise-grade LLM access; ensures data stays within Azure region; cost predictable.

### Why These Choices?
- **Managed RAG (Azure AI Search)** — No need to build embedding pipelines or manage vector DBs locally.
- **Streaming SSE** — Provides real-time feedback; better UX than waiting for full response.
- **Fact-verification** — Second LLM call ensures generated answers are grounded in notes.
- **Python + FastAPI** — Rapid backend development; async support for streaming; easy Azure SDK integration.
- **React** — Familiar, component-based front-end; SSE/fetch API for streaming.

---

## Setup & Running Instructions

### Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- **Azure account** with:
  - Azure AI Search resource (Free or Standard tier)
  - Azure AI Foundry hub with deployed LLM models
  - Storage account with indexed documents

### Step 1: Clone the Repository

```bash
git clone <your-repo-url>
cd FinalProject-LLM
```

### Step 2: Backend Setup

#### 2.1 Create and Activate Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

#### 2.2 Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

#### 2.3 Set Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Azure AI Search
AZURE_SEARCH_SERVICE_NAME=my-search-service
AZURE_SEARCH_INDEX_NAME=my-index
AZURE_SEARCH_API_KEY=your-search-api-key
AZURE_SEARCH_CONTENT_FIELD=content
AZURE_SEARCH_TOP_K=3

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://my-hub.openai.azure.com/
AZURE_OPENAI_API_KEY=your-openai-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

**Where to find these values:**
- Search service details: Azure Portal → AI Search resource → Settings → Keys
- OpenAI details: Azure Portal → AI Foundry project → Models + endpoints → Deployments

#### 2.4 Start the Backend Server

```bash
cd backend
uvicorn main:app --reload
```

Server runs on `http://localhost:8000`. Verify: `curl http://localhost:8000/health`

### Step 3: Frontend Setup

#### 3.1 Install Dependencies

```bash
cd frontend/my-app
npm install
```

#### 3.2 Start the Development Server

```bash
npm start
```

Frontend runs on `http://localhost:3000` (CRA default).

### Step 4: Use the App

1. Open `http://localhost:3000` in your browser.
2. Type a quiz question (e.g., "What is the capital of France?").
3. Toggle **Streaming** to see real-time token generation.
4. Toggle **Fact check** to verify answers against your notes.
5. View token usage and estimated cost below the header.

---
#### Known limitations
This is currently locally running application. it does not support multiple users and does not support file uploading. The quizzes are determined based on notes so if there is low amount of notes the quiz is not gonna be good or LLM refuses to make them

#### AI tools used in development 
I used copilot on VScode to come up with the code. also used previous example codes from day 7 and 9 examples