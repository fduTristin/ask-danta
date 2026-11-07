export type SourceMode = 'auto' | 'web' | 'all';
export type Source = { id: string; source?: 'web' | 'campus'; title: string; url?: string; snippet: string; published_at: string | null; is_mock: boolean; truncated: boolean; page_read?: boolean; page_truncated?: boolean; hole_id?: number; floor_id?: number; thread_read?: boolean; redacted?: boolean };
export type ProgressStep = { id: string; label: string; detail?: string; tool?: string; status: 'running' | 'complete' | 'error' | 'notice' | 'interrupted'; started_ms: number; duration_ms?: number };
export type Progress = { started_at: number; elapsed_ms: number; status: 'running' | 'complete' | 'error' | 'incomplete' | 'interrupted'; steps: ProgressStep[] };
export type Message = { role: 'user' | 'assistant'; content: string; sources?: Source[]; warnings?: string[]; end_reason?: string; status?: string; progress?: Progress };
export type Summary = { session_id: string; title: string; updated_at: string; busy: boolean; source_preference: SourceMode; interrupted: boolean };
export type Session = Summary & { messages: Message[]; sources: Source[]; pending_question: string | null; progress?: Progress | null };
export type Health = { stage: number; model: { configured: boolean }; search: { is_mock: boolean }; campus: { tools_enabled: boolean; credentials_present: boolean; auth_state: string } };

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export async function api<T>(path: string, method = 'GET', data?: unknown): Promise<T> {
  const response = await fetch(path, {
    method, headers: data === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data), signal: AbortSignal.timeout(12_000), cache: 'no-store',
  });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(typeof body?.detail === 'string' ? body.detail : body?.error?.message || '操作失败，请稍后重试。', response.status);
  if (!body) throw new Error('服务返回异常，请检查连接后重试。');
  return body as T;
}

export const errorText = (error: unknown) => error instanceof Error ? error.message : '暂时无法连接，请稍后重试。';
