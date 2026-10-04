import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { getConversations, getMessages, sendChat } from "./api/chat";
import type { Conversation, Message } from "./types";

const STUDENT_STORAGE_KEY = "course-ai-student-id";

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
}

export default function App() {
  const [studentId, setStudentId] = useState(() => localStorage.getItem(STUDENT_STORAGE_KEY) || "");
  const [studentInput, setStudentInput] = useState(studentId);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!studentId) return;
    const controller = new AbortController();
    void getConversations(studentId, controller.signal)
      .then(setConversations)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      });
    return () => controller.abort();
  }, [studentId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  function applyStudent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = studentInput.trim();
    if (!value) {
      setError("Enter a student ID to start.");
      return;
    }
    localStorage.setItem(STUDENT_STORAGE_KEY, value);
    setStudentId(value);
    setConversationId(null);
    setMessages([]);
    setConversations([]);
    setError("");
    if (value === studentId) {
      void getConversations(value).then(setConversations).catch((reason: unknown) => setError(errorMessage(reason)));
    }
  }

  function newChat() {
    setConversationId(null);
    setMessages([]);
    setDraft("");
    setError("");
    inputRef.current?.focus();
  }

  async function openConversation(id: string) {
    if (busy || loadingHistory) return;
    setLoadingHistory(true);
    setError("");
    try {
      const history = await getMessages(studentId, id);
      setConversationId(id);
      setMessages(history);
      setDraft("");
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoadingHistory(false);
    }
  }

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || busy || loadingHistory) return;
    if (!studentId) {
      setError("Enter and save a student ID first.");
      return;
    }
    const assistantId = crypto.randomUUID();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError("");
    setDraft("");
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: "user", content: text },
      { id: assistantId, role: "assistant", content: "" },
    ]);

    try {
      await sendChat({
        studentId,
        request: { message: text, conversation_id: conversationId || undefined },
        signal: controller.signal,
        onEvent(streamEvent) {
          if (streamEvent.event === "meta") setConversationId(streamEvent.data.conversation_id);
          if (streamEvent.event === "token") {
            const token = streamEvent.data.text;
            setMessages((current) => current.map((item) => item.id === assistantId
              ? { ...item, content: item.content + token } : item));
          }
          if (streamEvent.event === "sources") {
            const sources = streamEvent.data.sources;
            setMessages((current) => current.map((item) => item.id === assistantId
              ? { ...item, sources } : item));
          }
        },
      });
    } catch (reason) {
      setError(controller.signal.aborted ? "Response stopped." : errorMessage(reason));
      setMessages((current) => current.filter((item) => item.id !== assistantId || item.content));
    } finally {
      setBusy(false);
      abortRef.current = null;
      void getConversations(studentId).then(setConversations).catch(() => undefined);
    }
  }

  function composerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" onClick={(event) => event.preventDefault()}>
          <span className="brand-mark" aria-hidden="true">C</span>
          <span>Course AI<small>Your study companion</small></span>
        </a>
        <button className="new-chat" onClick={newChat} disabled={busy || loadingHistory}>
          <span aria-hidden="true">＋</span> New conversation
        </button>
        <form className="identity-form" onSubmit={applyStudent}>
          <label htmlFor="student-id">Student ID · local demo</label>
          <div className="identity-row">
            <input id="student-id" value={studentInput} maxLength={128}
              onChange={(event) => setStudentInput(event.target.value)}
              placeholder="Enter your student ID" disabled={busy || loadingHistory} />
            <button type="submit" disabled={busy || loadingHistory}>Save</button>
          </div>
        </form>
        <div className="history-label">Conversations</div>
        <nav className="history" aria-label="Conversation history">
          {!conversations.length && <p className="history-empty">Your conversations will appear here.</p>}
          {conversations.map((item) => (
            <button key={item.id} className={item.id === conversationId ? "history-item active" : "history-item"}
              onClick={() => void openConversation(item.id)} disabled={busy || loadingHistory}>
              <span aria-hidden="true">◌</span><span>{item.title}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer"><span className="status-dot" />Built for learning</div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div><span className="eyebrow">YOUR CLASSROOM, CONNECTED</span><h1>Study space</h1></div>
          <span className="session-label">{busy ? "Generating response…" : studentId ? "Ready to study" : "Set your student ID"}</span>
        </header>
        <section className="message-area" aria-label="Chat messages" aria-busy={busy || loadingHistory}>
          {loadingHistory && <p className="loading-history" role="status">Loading conversation…</p>}
          {!messages.length && !loadingHistory && (
            <div className="welcome">
              <div className="welcome-icon" aria-hidden="true">✦</div>
              <span className="eyebrow">A LITTLE CLARITY GOES A LONG WAY</span>
              <h2>What are we learning today?</h2>
              <p>Work through a difficult concept, explore your course materials, or find a new way to understand an idea.</p>
              <div className="suggestions">
                {["Explain a concept step by step", "Help me practice with an example", "Summarize the key ideas"].map((prompt) => (
                  <button key={prompt} onClick={() => { setDraft(prompt); inputRef.current?.focus(); }}>
                    {prompt}<span aria-hidden="true">↗</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="messages">
            {messages.map((item) => (
              <article key={item.id} className={`message message-${item.role}`}>
                <div className="message-avatar" aria-hidden="true">{item.role === "user" ? "Y" : "✦"}</div>
                <div className="message-body">
                  <div className="message-author">{item.role === "user" ? "You" : "Course AI"}</div>
                  <div className="message-content">{item.content || <span className="thinking" role="status">Thinking…</span>}</div>
                  {!!item.sources?.length && (
                    <details className="sources">
                      <summary>Course sources ({item.sources.length})</summary>
                      {item.sources.map((source, index) => (
                        <div className="source" key={source.id}>
                          <strong>[{index + 1}] {source.source}</strong><p>{source.content}</p>
                        </div>
                      ))}
                    </details>
                  )}
                </div>
              </article>
            ))}
            <div ref={bottomRef} />
          </div>
        </section>
        <div className="composer-area">
          {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label="Dismiss message">×</button></div>}
          <form className="composer" onSubmit={(event) => void submit(event)}>
            <label className="sr-only" htmlFor="message">Your message</label>
            <textarea id="message" ref={inputRef} rows={2} value={draft} maxLength={5000}
              onChange={(event) => setDraft(event.target.value)} onKeyDown={composerKeyDown}
              placeholder="Ask a question about your course…" disabled={busy || loadingHistory} />
            <div className="composer-bottom">
              <span>Enter to send · Shift + Enter for a new line</span>
              {busy ? <button type="button" className="send-button" onClick={() => abortRef.current?.abort()}>Stop ■</button>
                : <button type="submit" className="send-button" disabled={!draft.trim() || loadingHistory}>Send ↑</button>}
            </div>
          </form>
          <p className="composer-note">AI can make mistakes. Check important answers against your course materials.</p>
        </div>
      </main>
    </div>
  );
}
