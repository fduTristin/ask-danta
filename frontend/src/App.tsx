import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Ellipsis, PanelLeft, Pencil, Settings2, Square, SquarePen, Trash2 } from 'lucide-react';
import { Answer } from './Answer';
import { CampusLogin } from './CampusLogin';
import { Modal } from './Modal';
import { SourcePicker } from './SourcePicker';
import { api, ApiError, errorText } from './api';
import type { Health, Message, Session, SourceMode, Summary } from './api';

type Action = { kind: 'rename' | 'delete' | 'clear' | 'switch'; target?: Summary; nextId?: string };
type Run = { controller: AbortController; id?: string; done: Promise<void> };
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [connectionError, setConnectionError] = useState('');
  const [list, setList] = useState<Summary[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const sessionRef = useRef<Session | null>(null);
  const [input, setInput] = useState('');
  const inputRef = useRef('');
  const drafts = useRef(new Map<string, string>());
  const [mode, setMode] = useState<SourceMode>('auto');
  const [busy, setBusy] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState('');
  const run = useRef<Run | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [working, setWorking] = useState(false);
  const actionLock = useRef(false);
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 760px)').matches);
  const [sidebar, setSidebar] = useState(() => !window.matchMedia('(max-width: 760px)').matches);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [consent, setConsent] = useState(false);
  const [consentMode, setConsentMode] = useState<SourceMode>('all');
  const [action, setAction] = useState<Action | null>(null);
  const [rename, setRename] = useState('');
  const [menu, setMenu] = useState<string>();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const [showLatest, setShowLatest] = useState(false);
  const activeBusy = busy || !!session?.busy;
  const enabled = !!health?.model.configured && health.stage >= 6;
  const campusReady = !!health?.campus.tools_enabled;
  const effectiveMode = mode === 'auto' ? campusReady ? 'all' : 'web' : mode;
  const messages = session?.messages || [];
  const hasConversation = messages.length > 0 || !!pendingQuestion || !!session?.pending_question;

  function editInput(value: string) { inputRef.current = value; setInput(value); }
  function install(value: Session | null, restoreDraft = false) {
    sessionRef.current = value; setSession(value);
    if (value) localStorage.setItem('danta-current-session', value.session_id);
    else localStorage.removeItem('danta-current-session');
    if (restoreDraft) {
      setMode(value?.source_preference || 'auto');
      editInput(drafts.current.get(value?.session_id || 'new') ?? value?.pending_question ?? '');
      nearBottom.current = true; setShowLatest(false);
      requestAnimationFrame(() => bottom.current?.scrollIntoView({ block: 'end' }));
    }
  }
  async function refreshList() { const result = await api<{ sessions: Summary[] }>('/api/sessions'); setList(result.sessions); }
  async function refreshHealth() {
    try { const value = await api<Health>('/api/health'); setHealth(value); setConnectionError(''); }
    catch { setHealth(null); setConnectionError('暂时无法连接服务，请确认项目已启动后重试。'); }
  }
  async function load() {
    if (ready) drafts.current.set(sessionRef.current?.session_id || 'new', inputRef.current);
    setError(''); setReady(false);
    await refreshHealth();
    try {
      await refreshList();
      const id = localStorage.getItem('danta-current-session') || sessionStorage.getItem('campus-session');
      if (id) {
        try {
          const value = await api<Session>(`/api/sessions/${id}`);
          const previous = sessionRef.current;
          if (previous?.session_id === id && value.messages.length > previous.messages.length) {
            const question = value.messages.at(-2);
            if (question?.role === 'user' && question.content === inputRef.current.trim()) drafts.current.delete(id);
            setInfo('已恢复最新回答，请查看后再继续提问。');
          }
          install(value, true);
        }
        catch (cause) {
          if (cause instanceof ApiError && cause.status === 404) { install(null, true); sessionStorage.removeItem('campus-session'); }
          else throw cause;
        }
      }
    } catch (cause) { setError(errorText(cause)); }
    finally { setReady(true); }
  }
  useEffect(() => {
    void load();
    const media = window.matchMedia('(max-width: 760px)');
    const resize = () => { setMobile(media.matches); setSidebar(!media.matches); };
    media.addEventListener('change', resize);
    return () => { media.removeEventListener('change', resize); run.current?.controller.abort(); };
  }, []);
  // A restored tab may observe a request that is still running in another tab.
  useEffect(() => {
    if (!session?.busy || busy) return;
    let alive = true;
    const id = session.session_id;
    const timer = window.setInterval(() => {
      void api<Session>(`/api/sessions/${id}`).then(value => {
        if (alive && sessionRef.current?.session_id === id) {
          const previous = sessionRef.current;
          const question = value.messages.at(-2);
          if (value.messages.length > previous.messages.length && question?.role === 'user' && question.content === inputRef.current.trim()) {
            editInput(''); drafts.current.delete(id); setInfo('已恢复最新回答，请查看后再继续提问。');
          }
          install(value);
          if (!value.busy) void refreshList().catch(() => {});
        }
      }).catch(cause => { if (alive) setError(errorText(cause)); });
    }, 1200);
    return () => { alive = false; window.clearInterval(timer); };
  }, [session?.session_id, session?.busy, busy]);
  useLayoutEffect(() => {
    const element = textarea.current;
    if (element) { element.style.height = 'auto'; element.style.height = `${Math.min(element.scrollHeight, 180)}px`; }
  }, [input]);
  useLayoutEffect(() => {
    if (nearBottom.current) bottom.current?.scrollIntoView({ block: 'end' });
    else setShowLatest(true);
  }, [messages.length, pendingQuestion, busy]);
  useEffect(() => {
    const viewport = window.visualViewport;
    const resize = () => document.documentElement.style.setProperty('--app-height', `${viewport?.height ?? window.innerHeight}px`);
    resize(); viewport?.addEventListener('resize', resize);
    return () => viewport?.removeEventListener('resize', resize);
  }, []);

  async function synchronize(id: string): Promise<Session> {
    for (let attempt = 0; attempt < 40; attempt++) {
      const value = await api<Session>(`/api/sessions/${id}`);
      if (!value.busy) return value;
      await delay(150);
    }
    throw new Error('当前回答仍在结束处理中，请稍后重试；不会切换或重复发送。');
  }
  async function stop() {
    const currentRun = run.current;
    const id = currentRun?.id || sessionRef.current?.session_id;
    if (id) await api(`/api/sessions/${id}/cancel`, 'POST');
    currentRun?.controller.abort();
    if (currentRun) await currentRun.done;
    if (id) install(await synchronize(id));
  }
  async function switchTo(id?: string) {
    if (actionLock.current) return;
    actionLock.current = true; setWorking(true); setError('');
    drafts.current.set(sessionRef.current?.session_id || 'new', inputRef.current);
    try {
      if (run.current || sessionRef.current?.busy) await stop();
      install(id ? await api<Session>(`/api/sessions/${id}`) : null, true);
      setPendingQuestion(''); setInfo(''); setMenu(undefined);
      if (mobile) setSidebar(false);
      setAction(null);
    } catch (cause) { setError(errorText(cause)); }
    finally { actionLock.current = false; setWorking(false); }
  }
  function navigate(id?: string) {
    if (id && id === sessionRef.current?.session_id) { if (mobile) setSidebar(false); return; }
    if (activeBusy) { setAction({ kind: 'switch', nextId: id }); if (mobile) setSidebar(false); }
    else void switchTo(id);
  }

  async function executeTurn(currentRun: Run, question: string) {
    let id = sessionRef.current?.session_id;
    const beforeCount = sessionRef.current?.messages.length || 0;
    let finalReceived = false;
    let failure = '';
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      const value = sessionRef.current || await api<Session>('/api/sessions', 'POST');
      id = value.session_id; currentRun.id = id;
      if (!sessionRef.current) install(value);
      drafts.current.delete('new');
      if (currentRun.controller.signal.aborted) throw new Error('已停止');
      const response = await fetch(`/api/sessions/${id}/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question, source_mode: effectiveMode, source_preference: mode }),
        signal: currentRun.controller.signal,
      });
      if (!response.ok) { const result = await response.json().catch(() => null); throw new Error(typeof result?.detail === 'string' ? result.detail : result?.error?.message || '发送失败，请稍后重试。'); }
      void refreshList().catch(() => {});
      if (!response.body) throw new Error('浏览器未能读取回答，请重试。');
      reader = response.body.getReader();
      const decoder = new TextDecoder(); let buffer = '';
      function accept(frame: string) {
        const data = frame.split('\n').filter(line => line.startsWith('data: ')).map(line => line.slice(6)).join('\n');
        if (!data) return;
        const item = JSON.parse(data) as { type: string; message?: Message; error?: { message?: string } };
        if (item.type === 'error') failure = item.error?.message || '本轮未完成，请重试。';
        if (item.type === 'final' && item.message) finalReceived = true;
      }
      while (true) {
        const chunk = await reader.read(); buffer += decoder.decode(chunk.value, { stream: !chunk.done });
        let boundary: number;
        while ((boundary = buffer.indexOf('\n\n')) !== -1) { accept(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 2); }
        if (chunk.done) { if (buffer.trim()) accept(buffer); break; }
      }
      if (!finalReceived) throw new Error(failure || '连接中断，正在核对已保存的回答。');
    } catch (cause) { failure = currentRun.controller.signal.aborted ? '已停止，问题已保留。' : errorText(cause); }
    finally {
      await reader?.cancel().catch(() => {}); reader?.releaseLock();
      if (id) {
        try {
          const value = await synchronize(id);
          const committed = value.messages.length > beforeCount;
          install(value);
          if (committed) { editInput(''); drafts.current.delete(id); setError(''); setInfo(''); }
          else { editInput(question); drafts.current.set(id, question); setError(currentRun.controller.signal.aborted ? '' : failure); setInfo(currentRun.controller.signal.aborted ? '已停止，问题已保留，可修改后重新发送。' : ''); }
        } catch (cause) { setError(`${errorText(cause)} 请先重新检查会话，再发送问题。`); editInput(question); }
      } else { setError(failure); editInput(question); }
      setPendingQuestion(''); setBusy(false); run.current = null;
      await refreshList().catch(() => {}); void refreshHealth();
    }
  }
  async function send() {
    if (run.current || actionLock.current || activeBusy || !ready || !enabled || !input.trim()) return;
    // Reconcile with the server before sending, especially after a lost final event.
    actionLock.current = true; setWorking(true); setError(''); setInfo('');
    try {
      if (sessionRef.current) {
        const latest = await api<Session>(`/api/sessions/${sessionRef.current.session_id}`);
        if (latest.messages.length !== sessionRef.current.messages.length) {
          const question = latest.messages.at(-2);
          if (latest.messages.length > sessionRef.current.messages.length && question?.role === 'user' && question.content === inputRef.current.trim()) {
            editInput(''); drafts.current.delete(latest.session_id);
          }
          install(latest); setInfo('已恢复最新回答，请查看后再继续提问。'); return;
        }
        if (latest.busy) { install(latest); setInfo('这段对话仍在回答，可以等待或停止。'); return; }
      }
      if (effectiveMode === 'all' && !localStorage.getItem('danta-campus-consent')) { setConsentMode(mode); setConsent(true); return; }
      setBusy(true); setPendingQuestion(input.trim()); nearBottom.current = true;
      const currentRun: Run = { controller: new AbortController(), id: sessionRef.current?.session_id, done: Promise.resolve() };
      run.current = currentRun;
      currentRun.done = executeTurn(currentRun, input.trim());
    } catch (cause) { setError(errorText(cause)); }
    finally { actionLock.current = false; setWorking(false); }
  }
  async function changeMode(next: SourceMode, consented = false) {
    if (activeBusy || actionLock.current) return;
    if (next === 'all' && !campusReady) { setSettingsOpen(true); if (mobile) setSidebar(false); setInfo('登录树洞后，可在这里启用校内经验检索。'); return; }
    if ((next === 'all' || next === 'auto' && campusReady) && !consented && !localStorage.getItem('danta-campus-consent')) { setConsentMode(next); setConsent(true); return; }
    actionLock.current = true; setWorking(true);
    try { if (sessionRef.current) install(await api<Session>(`/api/sessions/${sessionRef.current.session_id}`, 'PATCH', { source_preference: next })); setMode(next); setError(''); }
    catch (cause) { setError(errorText(cause)); }
    finally { actionLock.current = false; setWorking(false); }
  }
  async function performAction() {
    if (!action || actionLock.current) return;
    if (action.kind === 'switch') { await switchTo(action.nextId); return; }
    actionLock.current = true; setWorking(true); setError('');
    const target = action.target || sessionRef.current;
    try {
      if (!target) return;
      const id = target.session_id;
      if (action.kind === 'rename') {
        const value = await api<Session>(`/api/sessions/${id}`, 'PATCH', { title: rename.trim() });
        if (sessionRef.current?.session_id === id) install(value);
      } else if (action.kind === 'delete') {
        await api(`/api/sessions/${id}`, 'DELETE'); drafts.current.delete(id);
        if (sessionRef.current?.session_id === id) install(null, true);
      } else {
        install(await api<Session>(`/api/sessions/${id}/clear`, 'POST')); editInput(''); drafts.current.delete(id); setInfo('');
      }
      await refreshList(); setAction(null); setMenu(undefined);
    } catch (cause) { setError(errorText(cause)); }
    finally { actionLock.current = false; setWorking(false); }
  }
  function beginAction(kind: 'rename' | 'delete', target: Summary) { setRename(target.title); setAction({ kind, target }); setMenu(undefined); if (mobile) setSidebar(false); }
  const sidebarContent = <>
    <div className="brand"><img src="/danta-logo.webp" alt="旦挞小猫 Logo" /><strong>问问旦挞</strong></div>
    <button className="new-chat" onClick={() => navigate()} disabled={working || !ready}><SquarePen />新对话</button>
    <nav className="history" aria-label="历史会话"><p className="history-label">最近对话</p>{!list.length && <p className="history-empty">开始聊天后，对话会保存在这里。</p>}{list.map(item => <div className={`history-row ${session?.session_id === item.session_id ? 'selected' : ''}`} key={item.session_id}>
      <button className="history-title" aria-current={session?.session_id === item.session_id ? 'page' : undefined} title={item.title} onClick={() => navigate(item.session_id)} disabled={working}><span>{item.title}</span>{item.busy && <small aria-label="正在回答">…</small>}</button>
      <button className="history-more" aria-label={`管理对话：${item.title}`} aria-expanded={menu === item.session_id} onClick={() => setMenu(menu === item.session_id ? undefined : item.session_id)} disabled={working}><Ellipsis /></button>
      {menu === item.session_id && <div className="history-menu"><button onClick={() => beginAction('rename', item)}><Pencil />重命名</button><button onClick={() => beginAction('delete', item)}><Trash2 />删除</button></div>}
    </div>)}</nav>
    <button className="settings-button" onClick={() => { setSettingsOpen(true); if (mobile) setSidebar(false); }}><Settings2 />设置</button>
  </>;

  return <div className={`app ${sidebar && !mobile ? '' : 'sidebar-closed'}`}>
    {!mobile && sidebar && <aside className="sidebar">{sidebarContent}</aside>}
    {mobile && sidebar && <Modal title="历史会话" drawer close={() => setSidebar(false)}>{sidebarContent}</Modal>}
    <main className="main">
      <header className="topbar"><button title={sidebar ? '收起历史会话' : '展开历史会话'} aria-label={sidebar ? '收起历史会话' : '展开历史会话'} aria-expanded={sidebar} onClick={() => setSidebar(!sidebar)}><PanelLeft /></button><span>问问旦挞</span>{(!sidebar || mobile) && <button aria-label="新对话" title="新对话" onClick={() => navigate()} disabled={working}><SquarePen /></button>}</header>
      <div className={`chat-layout ${hasConversation ? '' : 'empty-layout'}`}>
        <div className="messages-scroll" ref={scroll} onScroll={() => { const node = scroll.current!; nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 100; setShowLatest(!nearBottom.current); }}>
          <div className="messages" aria-label="对话内容">
            {!hasConversation && <div className="welcome"><img src="/danta-logo.webp" alt="" /><h1>今天，有什么校园问题？</h1></div>}
            {messages.map((message, index) => message.role === 'user' ? <article className="message user" key={`${session?.session_id}-${index}`}><p>{message.content}</p></article> : <Answer key={`${session?.session_id}-${index}`} message={message} index={index} />)}
            {pendingQuestion && <article className="message user pending"><p>{pendingQuestion}</p></article>}
            {activeBusy && <div className="waiting" role="status"><img src="/danta-logo.webp" alt="" />正在回答…</div>}
            {session?.interrupted && !activeBusy && <p className="notice interrupted">上次回答未完成，问题已恢复到输入框，可修改后重新发送。</p>}
            <div ref={bottom} />
          </div>
        </div>
        <div className="composer-region">
          {showLatest && hasConversation && <button className="back-latest" onClick={() => { nearBottom.current = true; bottom.current?.scrollIntoView({ block: 'end' }); setShowLatest(false); }}><ArrowDown />回到最新</button>}
          {(connectionError || health && health.stage < 6) && <div className="inline-error" role="alert">{connectionError || '请重启后端以启用新版历史会话功能。'}<button onClick={() => void load()} disabled={working || busy}>重新检查</button></div>}
          {health && !health.model.configured && <p className="notice">配置模型密钥并重启服务后即可开始对话。</p>}
          {health?.search.is_mock && <p className="notice">当前搜索使用合成样例，不能作为实际办事依据。</p>}
          {error && !action && <div className="inline-error" role="alert">{error}{input.trim() && enabled && <button onClick={() => void send()} disabled={activeBusy || working}>重试</button>}<button onClick={() => void load()} disabled={busy || working}>重新检查</button></div>}
          {info && <p className="notice" role="status">{info}</p>}
          <form className="composer" onSubmit={event => { event.preventDefault(); void send(); }}>
            <textarea ref={textarea} rows={1} aria-label="你的问题或追问" placeholder="向旦挞提问…" maxLength={8000} value={input} disabled={activeBusy || working || !ready} onChange={event => editInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); void send(); } }} />
            <div className="composer-bar"><SourcePicker value={mode} campusReady={campusReady} disabled={activeBusy || working || !ready} onChange={next => void changeMode(next)} />
              {activeBusy ? <button type="button" className="send" aria-label="停止回答" title="停止回答" disabled={working} onClick={() => { setWorking(true); void stop().catch(cause => setError(errorText(cause))).finally(() => setWorking(false)); }}><Square /></button> : <button type="submit" className="send" aria-label="发送" title="发送（Enter）" disabled={!enabled || !ready || working || !input.trim()}><ArrowUp /></button>}
            </div>
          </form>
          {effectiveMode === 'all' && !campusReady && <p className="notice">树洞暂不可用，本轮将说明限制并使用网页。<button onClick={() => setSettingsOpen(true)}>重新登录</button></p>}
        </div>
      </div>
    </main>
    {settingsOpen && <Modal title="设置" close={() => setSettingsOpen(false)}><h3>树洞账号</h3><CampusLogin enabled={!!health} loginSupported={(health?.stage || 0) >= 3} credentialsPresent={!!health?.campus.credentials_present} onLoggedIn={refreshHealth} /><p className="help">启用树洞后，检索到的相关片段会交给模型用于回答。聊天记录与引用保存在本机。</p><div className="settings-history"><h3>当前对话</h3><p className="help">清空将删除本段对话的消息与引用，保留历史条目。</p><button className="danger" disabled={!session || activeBusy} onClick={() => { setSettingsOpen(false); setAction({ kind: 'clear' }); }}>清空当前对话</button></div></Modal>}
    {consent && <Modal title="启用树洞检索" close={() => setConsent(false)}><p>允许把检索到的相关树洞片段发送给已配置的模型，用于回答你的问题。回答及必要引用片段会保存在本机聊天记录中。</p><div className="modal-actions"><button onClick={() => setConsent(false)}>取消</button><button className="primary" onClick={() => { localStorage.setItem('danta-campus-consent', '1'); setConsent(false); void changeMode(consentMode, true); }}>允许使用</button></div></Modal>}
    {action && <Modal title={action.kind === 'rename' ? '重命名对话' : action.kind === 'delete' ? '删除对话' : action.kind === 'clear' ? '清空当前对话' : '停止并切换对话'} close={() => setAction(null)} locked={working}>
      <form onSubmit={event => { event.preventDefault(); void performAction(); }}>
        {action.kind === 'rename' ? <label>对话名称<input autoFocus value={rename} maxLength={80} required onChange={event => setRename(event.target.value)} /></label> : <p>{action.kind === 'switch' ? '切换会停止当前回答。已保存的消息和未发送的问题会留在原会话。' : '这段对话的消息与引用将从本机删除，操作无法撤销。'}</p>}
        {error && <p className="inline-error" role="alert">{error}</p>}
        <div className="modal-actions"><button type="button" disabled={working} onClick={() => setAction(null)}>取消</button><button type="submit" className={action.kind === 'delete' || action.kind === 'clear' ? 'danger' : 'primary'} disabled={working || action.kind === 'rename' && !rename.trim()}>{working ? '处理中…' : action.kind === 'rename' ? '保存名称' : action.kind === 'switch' ? '停止并切换' : '确认删除'}</button></div>
      </form>
    </Modal>}
  </div>;
}
