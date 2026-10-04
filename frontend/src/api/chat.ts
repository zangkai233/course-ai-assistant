import type { ChatEvent, ChatRequest, Conversation, Message } from "../types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000")
  .replace(/\/+$/, "");

async function checkResponse(response: Response): Promise<void> {
  if (response.ok) return;
  let message = `Request failed (${response.status}).`;
  try {
    const body = await response.json() as { detail?: unknown };
    if (typeof body.detail === "string") message = body.detail;
  } catch {
    // Retain the status message if the server returned a non-JSON error.
  }
  throw new Error(message);
}

export async function getConversations(
  studentId: string,
  signal?: AbortSignal,
): Promise<Conversation[]> {
  const response = await fetch(`${API_BASE_URL}/api/conversations`, {
    headers: { "X-Student-ID": studentId },
    signal,
  });
  await checkResponse(response);
  return response.json() as Promise<Conversation[]>;
}

export async function getMessages(
  studentId: string,
  conversationId: string,
): Promise<Message[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/conversations/${encodeURIComponent(conversationId)}/messages`,
    { headers: { "X-Student-ID": studentId } },
  );
  await checkResponse(response);
  return response.json() as Promise<Message[]>;
}

function parseEvent(frame: string): ChatEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (!data.length || !["meta", "sources", "token", "done", "error"].includes(event)) {
    return null;
  }
  return { event, data: JSON.parse(data.join("\n")) } as ChatEvent;
}

export async function sendChat(options: {
  studentId: string;
  request: ChatRequest;
  signal: AbortSignal;
  onEvent: (event: ChatEvent) => void;
}): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Student-ID": options.studentId,
    },
    body: JSON.stringify(options.request),
    signal: options.signal,
  });
  await checkResponse(response);
  if (!response.body) throw new Error("Streaming is unavailable in this browser.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;

  function dispatch(frame: string): void {
    const event = parseEvent(frame);
    if (!event) return;
    options.onEvent(event);
    if (event.event === "done") completed = true;
    if (event.event === "error") throw new Error(event.data.message);
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let boundary = /\r?\n\r?\n/.exec(buffer);
      while (boundary) {
        dispatch(buffer.slice(0, boundary.index));
        buffer = buffer.slice(boundary.index + boundary[0].length);
        boundary = /\r?\n\r?\n/.exec(buffer);
      }
      if (done) break;
    }
    if (buffer.trim()) dispatch(buffer);
    if (!completed) throw new Error("The response stream ended early. Please try again.");
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
