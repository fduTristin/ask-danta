import { useEffect, useRef, useState } from 'react';
import { Bot, Globe, SlidersHorizontal, UserRound } from 'lucide-react';
import { Modal } from './Modal';
import { CampusLogin } from './CampusLogin';
import { api, errorText } from './api';
import type { Health, RuntimeSettings } from './api';

type Category = 'account' | 'model' | 'search' | 'advanced';
type Secret = 'model_api_key' | 'search_api_key';
const categories = [
  { id: 'model', title: '模型', icon: Bot }, { id: 'search', title: '网页搜索', icon: Globe },
  { id: 'account', title: '账号', icon: UserRound }, { id: 'advanced', title: '高级', icon: SlidersHorizontal },
] as const;

export function SettingsPanel({ health, busy, initialCategory = 'model', close, onSaved }: {
  health: Health | null; busy: boolean; initialCategory?: Category; close: () => void; onSaved: () => Promise<void>;
}) {
  const [category, setCategory] = useState<Category>(initialCategory);
  const [saved, setSaved] = useState<RuntimeSettings | null>(null);
  const [draft, setDraft] = useState<RuntimeSettings | null>(null);
  const [keys, setKeys] = useState<Partial<Record<Secret, string>>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loginBusy, setLoginBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const submitting = useRef(false);
  const dirty = JSON.stringify(saved) !== JSON.stringify(draft) || Object.keys(keys).length > 0;

  async function load() {
    setLoading(true); setError('');
    try { const value = await api<RuntimeSettings>('/api/settings'); setSaved(value); setDraft(value); }
    catch (cause) { setError(errorText(cause)); }
    finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  function update<K extends keyof RuntimeSettings>(name: K, value: RuntimeSettings[K]) {
    setDraft(previous => previous ? { ...previous, [name]: value } : previous); setNotice('');
  }
  function changeKey(name: Secret, value: string) {
    setKeys(previous => { const next = { ...previous }; if (value) next[name] = value; else delete next[name]; return next; });
    setNotice('');
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft || !saved || !dirty || busy || submitting.current) return;
    submitting.current = true; setSaving(true); setError(''); setNotice('');
    const changes: Record<string, unknown> = { ...keys };
    for (const name of Object.keys(draft) as (keyof RuntimeSettings)[]) {
      if (draft[name] !== saved[name]) changes[name] = draft[name];
    }
    try {
      const value = await api<RuntimeSettings>('/api/settings', 'PATCH', changes);
      setSaved(value); setDraft(value); setKeys({}); setNotice('设置已保存');
      await onSaved();
    } catch (cause) { setError(errorText(cause)); }
    finally { submitting.current = false; setSaving(false); }
  }
  function secretField(name: Secret, label: string) {
    const configured = !!saved?.[`${name}_configured`];
    const clearing = keys[name] === '';
    return <div className="settings-secret">
      <div className="secret-heading"><label htmlFor={name}>{label}</label><span className="setting-status">{clearing ? '保存后清除' : configured ? '已配置' : '未配置'}</span></div>
      <div className="secret-input"><input id={name} type="password" autoComplete="new-password" maxLength={8192} value={keys[name] ?? ''} placeholder={configured ? '留空保留现有密钥' : '输入 API Key'} onChange={event => changeKey(name, event.target.value)} />
        {configured && <button type="button" onClick={() => { if (clearing) changeKey(name, ''); else { setKeys(previous => ({ ...previous, [name]: '' })); setNotice(''); } }} aria-label={`${clearing ? '撤销清除' : '清除'}${label}`}>{clearing ? '撤销' : '清除'}</button>}
      </div>
    </div>;
  }
  function numberField(name: keyof RuntimeSettings, label: string, min: number, max: number, nullable = false) {
    return <label className="setting-row" key={name}><span>{label}</span><input type="number" min={min} max={max} step={name.endsWith('_seconds') ? 'any' : 1} required={!nullable} value={String(draft?.[name] ?? '')} placeholder={nullable ? '跟随通用超时' : undefined} onChange={event => update(name, event.target.value === '' && nullable ? null : event.target.value === '' ? '' : Number(event.target.value))} /></label>;
  }

  return <Modal title="设置" className="settings-modal" close={close} locked={saving || loginBusy}>
    <div className="settings-layout">
      <nav className="settings-nav" aria-label="设置分类">{categories.map(item => <button key={item.id} type="button" aria-current={category === item.id ? 'page' : undefined} onClick={() => { setCategory(item.id); setNotice(''); }}><item.icon />{item.title}</button>)}</nav>
      <div className="settings-content">
        <h3>{categories.find(item => item.id === category)?.title}</h3>
        {category === 'account' ? <CampusLogin enabled={!!health} loginSupported={(health?.stage || 0) >= 3} credentialsPresent={!!health?.campus.tools_enabled} onLoggedIn={onSaved} onBusyChange={setLoginBusy} /> : <>
          {loading && <p className="help" role="status">正在读取设置…</p>}
          {!loading && !draft && <button onClick={() => void load()}>重新加载设置</button>}
          {draft && <form id="settings-form" onSubmit={event => void save(event)}>
            <fieldset disabled={saving}>
              {category === 'model' && <div className="settings-fields">
                <label>接口地址<input type="url" required maxLength={2048} value={draft.model_base_url} placeholder="https://api.deepseek.com" onChange={event => update('model_base_url', event.target.value)} /></label>
                <p className="help">使用兼容 Chat Completions 的接口地址。</p>
                <label>模型名称<input required maxLength={200} value={draft.model_name} onChange={event => update('model_name', event.target.value)} /></label>
                {secretField('model_api_key', '模型 API Key')}
                <label className="setting-row"><span>深度思考</span><input type="checkbox" checked={draft.model_thinking === 'enabled'} onChange={event => update('model_thinking', event.target.checked ? 'enabled' : 'disabled')} /></label>
                {draft.model_thinking === 'enabled' && <label className="setting-row"><span>思考强度</span><select value={draft.model_reasoning_effort} onChange={event => update('model_reasoning_effort', event.target.value as RuntimeSettings['model_reasoning_effort'])}><option value="low">低</option><option value="high">高</option><option value="max">最高</option></select></label>}
                {numberField('model_max_tokens', '最大输出 Token 数', 256, 32768)}
              </div>}
              {category === 'search' && <div className="settings-fields">
                <label className="setting-row"><span>搜索服务</span><select value={draft.search_provider} onChange={event => update('search_provider', event.target.value as RuntimeSettings['search_provider'])}><option value="mock">合成样例</option><option value="tavily">Tavily</option></select></label>
                {draft.search_provider === 'mock' && <p className="help">合成样例仅用于演示，不会检索真实网页。</p>}
                {secretField('search_api_key', 'Tavily API Key')}
                <label className="setting-row"><span>搜索深度</span><select value={draft.search_depth} onChange={event => update('search_depth', event.target.value as RuntimeSettings['search_depth'])}><option value="basic">基础</option><option value="advanced">深入</option></select></label>
                {numberField('search_max_results', '每次搜索结果数', 1, 10)}
              </div>}
              {category === 'advanced' && <div className="settings-fields">
                <label className="setting-row"><span>答案核对<small>生成后核对证据，可能增加等待时间。</small></span><input type="checkbox" checked={draft.answer_review_enabled} onChange={event => update('answer_review_enabled', event.target.checked)} /></label>
                {numberField('model_timeout_seconds', '模型超时（秒）', 0.1, 300)}
                {numberField('request_budget_seconds', '单轮总时限（秒）', 0.1, 600)}
                {numberField('http_timeout_seconds', '通用请求超时（秒）', 0.1, 120)}
                {numberField('search_timeout_seconds', '搜索超时（秒）', 0.1, 120, true)}
                {numberField('max_tool_calls', '每轮工具调用上限', 1, 30)}
                {numberField('max_campus_pages', '树洞分页上限', 1, 20)}
                {numberField('search_max_snippet_chars', '网页摘要字数上限', 100, 10000)}
                {numberField('campus_max_content_chars', '树洞正文字数上限', 100, 12000)}
              </div>}
            </fieldset>
          </form>}
        </>}
        {error && <p className="inline-error" role="alert">{error}</p>}
      </div>
    </div>
    <div className="settings-footer"><p className="help" role="status">{notice || (busy ? '回答完成或停止后可保存设置。' : dirty ? '有未保存的更改' : '设置仅保存在本机。')}</p>{category !== 'account' && <button type="submit" form="settings-form" className="primary" disabled={!dirty || saving || busy || !draft}>{saving ? '保存中…' : '保存'}</button>}</div>
  </Modal>;
}
