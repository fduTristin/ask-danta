import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';

type Source = { id: string; source?: 'web' | 'campus'; title: string; url?: string; snippet: string; published_at: string | null; is_mock: boolean; truncated: boolean; page_read?: boolean; page_truncated?: boolean; hole_id?: number; floor_id?: number; thread_read?: boolean; redacted?: boolean };
type Plan = { questions: string[]; gaps: string[]; next_action: string; sources: string[] };
type Message = { role: 'user' | 'assistant'; content: string; sources?: Source[]; warnings?: string[]; skill?: string; plan?: Plan; end_reason?: string; source_mode?: string };
type Session = { session_id: string; messages: Message[]; sources: Source[]; busy: boolean };
type StreamEvent = {
  type: string; call_id?: string; name?: string; message?: Message | string;
  error?: { message: string }; session_sources?: Source[];
  allowed_sources?: string[]; skill_loaded?: string;
  result?: { query?: string; source_id?: string; title?: string; is_mock?: boolean; results?: Source[]; thread?: { id: number }; skill?: string; plan?: Plan; remaining_campus_pages?: number };
};

function Sources({ sources, label }: { sources: Source[]; label: string }) {
  if (!sources.length) return null;
  return <details className="source-details"><summary>{label} · {sources.length}</summary>{sources.map(source => <div className="chat-source" key={source.id}><strong>[{source.id}] </strong>{source.source === 'campus' ? <span>树洞 #{source.hole_id} · 楼层 ID {source.floor_id}</span> : source.is_mock ? <span>{source.title}（合成样例）</span> : <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>}<small>{source.published_at || '日期未知'} · {source.source === 'campus' ? source.thread_read ? '已读取帖子上下文（部分楼层）' : '搜索命中楼层' : source.page_read ? source.page_truncated ? '已读取部分正文' : '已读取网页文本' : '搜索摘要'}{source.truncated ? ' · 内容已截断' : ''}{source.redacted ? ' · 已做基础脱敏' : ''}</small>{source.source === 'campus' && <small>个人经验，不代表官方规定；未确认已读完整帖子。</small>}<p>{source.source === 'campus' ? '楼层正文' : '搜索摘要'}：{source.snippet}</p></div>)}</details>;
}

async function api<T>(path: string, method = 'GET'): Promise<T> {
  const response = await fetch(path, { method, signal: AbortSignal.timeout(10_000) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message || body.detail || '请求失败，请稍后重试。');
  return body;
}

export function Chat({ enabled, isMock, campusReady, onAuthChange }: { enabled: boolean; isMock: boolean; campusReady: boolean; onAuthChange: () => Promise<void> }) {
  const [session, setSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionSources, setSessionSources] = useState<Source[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const [sourcePreference, setSourcePreference] = useState(() => {
    const saved = sessionStorage.getItem('campus-source-preference');
    return saved === 'web' || saved === 'all' ? saved : 'auto';
  });
  const sourceMode = sourcePreference === 'auto' ? campusReady ? 'all' : 'web' : sourcePreference;

  function install(value: Session) {
    setSession(value); setMessages(value.messages); setSessionSources(value.sources);
    sessionStorage.setItem('campus-session', value.session_id);
  }

  useEffect(() => {
    let active = true;
    async function restore() {
      try {
        const id = sessionStorage.getItem('campus-session');
        if (!id) return;
        const response = await fetch(`/api/sessions/${id}`, { signal: AbortSignal.timeout(10_000) });
        if (response.status === 404) { sessionStorage.removeItem('campus-session'); return; }
        if (!response.ok) throw new Error('无法恢复会话，请重试或新建会话。');
        const value: Session = await response.json();
        if (active) install(value);
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : '无法恢复会话。'); }
      finally { if (active) setReady(true); }
    }
    void restore();
    return () => { active = false; controller.current?.abort(); };
  }, []);

  async function changeSession(clear: boolean) {
    setBusy(true); setError('');
    try {
      install(await api<Session>(clear && session ? `/api/sessions/${session.session_id}/clear` : '/api/sessions', 'POST'));
      setProgress([]); setInput('');
    } catch (cause) { setError(cause instanceof Error ? cause.message : '会话操作失败。'); }
    finally { setBusy(false); }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!ready || busy || !input.trim()) return;
    const question = input.trim();
    const previous = messages;
    setBusy(true); setError(''); setProgress([]);
    const abort = new AbortController();
    controller.current = abort;
    let completed = false;
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    let currentId = session?.session_id;
    try {
      const current = session || await api<Session>('/api/sessions', 'POST');
      currentId = current.session_id;
      if (!session) install(current);
      setMessages([...previous, { role: 'user', content: question }]);
      const response = await fetch(`/api/sessions/${current.session_id}/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question, source_mode: sourceMode }), signal: abort.signal,
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error?.message || data.detail || '对话请求失败。');
      }
      if (!response.body) throw new Error('浏览器不支持响应流。');
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      function accept(frame: string) {
        const data = frame.split('\n').filter(line => line.startsWith('data: ')).map(line => line.slice(6)).join('\n');
        if (!data) return;
        const item: StreamEvent = JSON.parse(data);
        let note = '';
        if (item.type === 'start') note = `本轮来源：${item.allowed_sources?.includes('campus') ? '公开网页 + 树洞' : '仅公开网页'} · 已加载 ${item.skill_loaded}`;
        if (item.type === 'model_start' || item.type === 'budget' || item.type === 'review_start' || item.type === 'source_notice') note = String(item.message);
        if (item.type === 'tool_start') note = `开始工具：${item.name}`;
        if (item.type === 'tool_complete' && item.result) {
          if (item.name === 'plan_research' && item.result.plan) note = `调研计划：${item.result.plan.questions.join('；')} · 证据缺口：${item.result.plan.gaps.join('；') || '无'} · 下一步：${item.result.plan.next_action}`;
          else if (item.name === 'read_campus_thread') note = `已读取树洞 #${item.result.thread?.id}：${item.result.results?.length || 0} 条楼层 · 剩余 ${item.result.remaining_campus_pages} 页预算`;
          else if (item.name === 'search_campus_posts') note = `树洞搜索完成：${item.result.query} · ${item.result.results?.length || 0} 条楼层 · 剩余 ${item.result.remaining_campus_pages} 页预算`;
          else note = item.name === 'read_web' ? `已读取网页：${item.result.source_id} · ${item.result.title}` : `${item.result.is_mock ? '合成样例' : '搜索完成'}：${item.result.query} · ${item.result.results?.length || 0} 条来源`;
        }
        if (item.type === 'tool_error') note = `工具失败：${item.error?.message}`;
        if (item.type === 'error') note = item.error?.message || '本轮出现错误。';
        if (note) setProgress(items => [...items, note]);
        if (item.type === 'final' && typeof item.message === 'object') {
          setMessages([...previous, { role: 'user', content: question }, item.message]);
          setSessionSources(item.session_sources || []);
          setInput(''); completed = true;
        }
      }
      while (true) {
        const chunk = await reader.read();
        buffer += decoder.decode(chunk.value, { stream: !chunk.done });
        let boundary: number;
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          accept(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 2);
        }
        if (chunk.done) break;
      }
      if (!completed) throw new Error('连接已结束但未收到最终回答，请重试。');
    } catch (cause) {
      if (!completed) setMessages(previous);
      // The server may have committed just before a disconnect. Restore its
      // authoritative history so the next turn cannot hide a completed answer.
      if (currentId) {
        try { install(await api<Session>(`/api/sessions/${currentId}`)); }
        catch { /* Keep the last locally known history if offline. */ }
      }
      setError(abort.signal.aborted ? '已停止。本轮未完成的内容不会写入会话；输入已保留。' : cause instanceof Error ? cause.message : '对话失败。');
    } finally {
      await reader?.cancel().catch(() => undefined);
      reader?.releaseLock();
      controller.current = null; setBusy(false);
      void onAuthChange();
    }
  }

  return <section className="chat-section" aria-labelledby="chat-title">
    <div className="section-heading"><h2 id="chat-title">和研究助手聊一聊</h2><div className="session-actions"><button className="text-button" disabled={busy || !ready} onClick={() => void changeSession(false)}>新建会话</button><button className="text-button" disabled={busy || !ready || !session} onClick={() => void changeSession(true)}>清空会话</button></div></div>
    <p className="help">支持追问并沿用本会话的条件。按允许的数据源检索，复杂问题应用校园调研流程。</p>
    <div className="source-selector"><label htmlFor="source-mode">本轮允许的数据源</label><select id="source-mode" value={sourcePreference} disabled={busy} onChange={event => { setSourcePreference(event.target.value); sessionStorage.setItem('campus-source-preference', event.target.value); }}><option value="auto">自动（{campusReady ? '公开网页 + 树洞' : '仅公开网页'}）</option><option value="web">仅公开网页</option><option value="all">公开网页 + 树洞</option></select><small>{sourceMode === 'all' ? '允许将检索到的树洞正文发送给模型，用于回答当前问题。' : '不请求树洞，也不把此前的树洞资料和相关回答发送给模型。'}{sourceMode === 'all' && !campusReady ? ' 当前凭据不可用，将说明限制并使用网页。' : ''}</small></div>
    {!enabled && <p className="notice">填写本地 MODEL_API_KEY 并重启服务后即可对话，网页搜索仍可单独试用。</p>}
    {isMock && <p className="notice">搜索处于合成样例模式，不能用于实际办事结论。对话仍会调用真实模型。</p>}
    <div className="conversation" aria-live="polite" aria-busy={busy}>
      {!messages.length && <p className="empty">例如：查找复旦大学研究生在读证明的官方办理说明。<br /><small>随后可以继续问：“我在江湾校区，有哪些注意事项？”</small></p>}
      {messages.map((message, index) => <article key={index} className={`message ${message.role}`}><span className="message-role">{message.role === 'user' ? '你' : '研究助手'}{message.skill ? ` · ${message.skill}` : ''}</span><p className="message-content">{message.content}</p>{message.plan && <details className="source-details"><summary>调研问题与证据缺口</summary><p>{message.plan.questions.join('；')}</p><p>待核实：{message.plan.gaps.join('；') || '未记录缺口'}</p></details>}{message.end_reason && <small>结束原因：{message.end_reason === 'budget' ? '达到预算' : message.end_reason === 'error' ? '处理失败，资料未完成核对' : '已生成回答（证据充分性见正文）'}</small>}{!!message.warnings?.length && <p className="notice">{[...new Set(message.warnings)].join(' ')}</p>}<Sources sources={message.sources || []} label="本回答引用" /></article>)}
    </div>
    <Sources sources={sessionSources} label="会话累计检索（不一定支持本回答）" />
    {!!progress.length && <ol className="tool-progress" aria-label="本轮调用进度" aria-live="polite">{progress.map((item, index) => <li key={index}>{item}</li>)}</ol>}
    {error && <p className="error" role="alert">{error}</p>}
    <form onSubmit={send}><label htmlFor="message">你的问题或追问</label><textarea id="message" rows={3} maxLength={8000} value={input} onChange={event => setInput(event.target.value)} placeholder="说明你想了解的问题、校区或其他条件…" required disabled={busy} /><div className="composer-actions"><small>{sourceMode === 'all' ? '公开网页 + 树洞' : '仅公开网页'} · 会话保存在服务内存中</small>{busy ? <button type="button" className="text-button" onClick={() => controller.current?.abort()}>停止回答</button> : <button type="submit" disabled={!ready || !enabled || !input.trim()}>发送</button>}</div></form>
  </section>;
}
