export type SourceKind = 'research' | 'url' | 'note';
export type ResearchStatus = 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled' | 'ready';

export interface SourceItem {
  key: string;
  kind: SourceKind;
  id: number | string;
  title: string;
  status: ResearchStatus;
  created_at?: string;
}

export interface ChatSession {
  id: number;
  project_id: number;
  type: 'chat' | 'research';
  query: string;
  status: ResearchStatus;
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  created_at: string;
  session_count: number;
  sources: SourceItem[];
  chats: ChatSession[];
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface SessionDetail {
  id?: number;
  type?: 'chat' | 'research';
  query?: string;
  report_md?: string;
  messages?: ChatMessage[];
  data_sources?: string[];
  kind?: SourceKind;
  title?: string;
  content?: string;
}
