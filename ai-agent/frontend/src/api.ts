import type { ChatMessage, Project, SessionDetail, SourceKind } from './types';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ ok: boolean; user: string }>('/api/health'),
  listProjects: () => request<Project[]>('/api/projects'),
  createProject: (name: string) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ name }) }),
  deleteProject: (projectId: number) =>
    request<{ ok: boolean }>(`/api/projects/${projectId}`, { method: 'DELETE' }),
  addUrl: (projectId: number, url: string) =>
    request<Project>(`/api/projects/${projectId}/urls`, { method: 'POST', body: JSON.stringify({ url }) }),
  addNote: (projectId: number, title: string, content: string) =>
    request<Project>(`/api/projects/${projectId}/notes`, { method: 'POST', body: JSON.stringify({ title, content }) }),
  startResearch: (projectId: number, query: string) =>
    request<{ session_id: number; project: Project }>(`/api/projects/${projectId}/research`, {
      method: 'POST',
      body: JSON.stringify({ query }),
    }),
  cancelResearch: (sessionId: number) =>
    request<{ ok: boolean }>(`/api/sessions/${sessionId}/cancel`, { method: 'POST' }),
  deleteSession: (sessionId: number) =>
    request<{ ok: boolean }>(`/api/sessions/${sessionId}`, { method: 'DELETE' }),
  deleteSource: (projectId: number, kind: SourceKind, id: number | string) =>
    request<Project>(`/api/projects/${projectId}/sources`, {
      method: 'DELETE',
      body: JSON.stringify({ kind, id }),
    }),
  getSession: (sessionId: number) => request<SessionDetail>(`/api/sessions/${sessionId}`),
  getSourceDetail: (projectId: number, kind: SourceKind, id: number | string) =>
    request<SessionDetail>(`/api/projects/${projectId}/sources/${kind}/${encodeURIComponent(String(id))}`),
  chat: (projectId: number, message: string, sourceKeys: string[], messages: ChatMessage[]) =>
    request<{ answer: string; session_id: number; project: Project }>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, message, source_keys: sourceKeys, messages }),
    }),
};
