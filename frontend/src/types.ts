export interface Source {
  id: string;
  source: string;
  content: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
}

export type ChatEvent =
  | { event: "meta"; data: { conversation_id: string } }
  | { event: "sources"; data: { sources: Source[] } }
  | { event: "token"; data: { text: string } }
  | { event: "done"; data: { conversation_id: string } }
  | { event: "error"; data: { message: string } };
