import { useState } from 'react';
import { Check, Copy, Pencil, RotateCcw } from 'lucide-react';

export function UserMessage({ content, disabled, failed = false, onSend }: {
  content: string; disabled: boolean; failed?: boolean; onSend: (text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState('');
  async function copy() {
    try { await navigator.clipboard.writeText(content); setCopied(true); setCopyError(''); }
    catch { setCopyError('无法自动复制，请选中消息后复制。'); }
  }
  return <article className={`message user${failed ? ' failed' : ''}`}>
    {editing ? <form className="message-editor" onSubmit={event => { event.preventDefault(); if (draft.trim() && !disabled) onSend(draft.trim()); }}>
      <textarea aria-label="编辑消息" autoFocus value={draft} maxLength={8000} disabled={disabled} onChange={event => setDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Escape') setEditing(false); }} />
      {!failed && <small>在当前对话中重新回答；这条问题及其后的内容将被替换。</small>}
      <div className="message-edit-actions"><button type="button" disabled={disabled} onClick={() => setEditing(false)}>取消</button><button className="primary" disabled={disabled || !draft.trim()}>发送修改</button></div>
    </form> : <><p>{content}</p><div className="message-actions">
      <button type="button" aria-label={copied ? '已复制消息' : '复制消息'} title="复制消息" onClick={() => void copy()}>{copied ? <Check /> : <Copy />}</button>
      <button type="button" aria-label="编辑并重新发送" title="编辑并重新发送" disabled={disabled} onClick={() => { setDraft(content); setEditing(true); }}><Pencil /></button>
      {failed && <button type="button" disabled={disabled} onClick={() => onSend(content)}><RotateCcw />重新发送</button>}
    </div></>}
    {copyError && <small role="status">{copyError}</small>}
  </article>;
}
