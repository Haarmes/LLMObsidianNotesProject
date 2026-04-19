import { useState } from 'react';
import ChatInput from './components/ChatInput';
import MessageList from './components/MessageList';
import UsageBar from './components/UsageBar';
import './App.css';

const API_BASE = 'http://localhost:8000';
const SESSION_ID = `session-${Math.random().toString(36).slice(2, 9)}`;

function App() {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingEnabled, setStreamingEnabled] = useState(true);
  const [verificationEnabled, setVerificationEnabled] = useState(false);
  const [lastVerification, setLastVerification] = useState(null);
  const [lastUsage, setLastUsage] = useState(null);
  const [error, setError] = useState(null);

  async function sendMessage(text) {
    if (!text.trim() || isStreaming) return;

    setError(null);
    const userMsg = { role: 'user', content: text };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setLastVerification(null);
    setIsStreaming(true);

    const history = messages;

    try {
      if (streamingEnabled) {
        await streamResponse(text, history, updatedMessages);
      } else {
        await fetchResponse(text, history, updatedMessages);
      }
    } catch (err) {
      setError(err.message || 'Something went wrong while sending the message.');
    } finally {
      setIsStreaming(false);
    }
  }

  async function streamResponse(message, history, currentMessages) {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        history,
        session_id: SESSION_ID,
        verify_with_notes: verificationEnabled,
      }),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || `Server error: ${response.status}`);
    }

    const assistantIndex = currentMessages.length;
    setMessages([...currentMessages, { role: 'assistant', content: '' }]);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';

      for (const event of events) {
        if (!event.startsWith('data: ')) continue;
        const data = JSON.parse(event.slice(6));

        if (data.type === 'text') {
          fullText += data.content;

          setMessages((prev) => {
            const updated = [...prev];
            updated[assistantIndex] = { role: 'assistant', content: fullText };
            return updated;
          });
        } else if (data.type === 'done') {
          setLastUsage(data.usage);
          setLastVerification(data.verification || null);
        }
      }
    }
  }

  async function fetchResponse(message, history, currentMessages) {
    const response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        history,
        session_id: SESSION_ID,
        verify_with_notes: verificationEnabled,
      }),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || `Server error: ${response.status}`);
    }

    const data = await response.json();
    setMessages([...currentMessages, { role: 'assistant', content: data.response }]);
    setLastUsage(data.usage);
    setLastVerification(data.verification || null);
  }

  function clearChat() {
    setMessages([]);
    setLastUsage(null);
    setLastVerification(null);
    setError(null);
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-title">
          <h1>Obsidian Notes quiz Demo</h1>
          <span className="session-id">Session: {SESSION_ID}</span>
        </div>
        <div className="header-controls">
          <label className="streaming-toggle">
            <input
              type="checkbox"
              checked={streamingEnabled}
              onChange={(e) => setStreamingEnabled(e.target.checked)}
              disabled={isStreaming}
            />
            <span>Streaming</span>
          </label>
          <label className="streaming-toggle">
            <input
              type="checkbox"
              checked={verificationEnabled}
              onChange={(e) => setVerificationEnabled(e.target.checked)}
              disabled={isStreaming}
            />
            <span>fact check</span>
          </label>
          <button onClick={clearChat} className="btn-clear" disabled={isStreaming}>
            Clear chat
          </button>
        </div>
      </header>

      <ChatInput onSend={sendMessage} disabled={isStreaming} />

      {lastUsage && <UsageBar usage={lastUsage} />}

      {lastVerification && (
        <div className={`verification-banner ${lastVerification.is_supported ? 'ok' : 'warn'}`}>
          <strong>{lastVerification.is_supported ? 'Verified' : 'Potential mismatch'}:</strong>{' '}
          {lastVerification.reason}
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      <MessageList messages={messages} isStreaming={isStreaming} />
    </div>
  );
}

export default App;
