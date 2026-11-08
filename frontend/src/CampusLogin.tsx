import { useRef, useState } from 'react';

type Props = {
  enabled: boolean;
  loginSupported: boolean;
  credentialsPresent: boolean;
  onLoggedIn: () => Promise<void>;
  onBusyChange?: (busy: boolean) => void;
};

export function CampusLogin({ enabled, loginSupported, credentialsPresent, onLoggedIn, onBusyChange }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const submitting = useRef(false);

  async function login(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current || !enabled || !loginSupported) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const email = String(data.get('email') || '').trim();
    const password = String(data.get('password') || '');
    if (!email || !password) return;
    submitting.current = true;
    setBusy(true); setError(''); setSuccess('');
    onBusyChange?.(true);
    // Clear the visible field immediately; credentials never enter chat state,
    // localStorage or sessionStorage. Only the login request contains them.
    (form.elements.namedItem('password') as HTMLInputElement).value = '';
    try {
      const response = await fetch('/api/campus/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        signal: AbortSignal.timeout(100_000), cache: 'no-store',
      });
      if (response.status === 404) {
        throw new Error('当前后端没有树洞登录接口，请重启项目的前后端服务，再点击“重新检查”。');
      }
      const result = await response.json().catch(() => null);
      if (!result) {
        throw new Error('登录服务未返回有效响应，请确认后端服务已启动且前端连接到正确端口。');
      }
      if (!response.ok || result.authenticated !== true) {
        throw new Error(result.error?.message || '登录失败，请稍后重试。');
      }
      form.reset();
      setOpen(false);
      setSuccess('已登录');
      await onLoggedIn();
    } catch (cause) {
      setError(cause instanceof Error && cause.name === 'Error'
        ? cause.message : '未能完成登录，请检查后端连接后重试。');
    } finally {
      submitting.current = false;
      setBusy(false);
      onBusyChange?.(false);
    }
  }

  return (
    <div className="campus-login">
      <div className="section-heading">
        <div><strong>树洞</strong><small className="account-status">{credentialsPresent ? '已登录' : '未登录'}</small></div>
        <button className="text-button" type="button" disabled={!enabled || !loginSupported || busy}
          aria-expanded={open} aria-controls="campus-login-form"
          onClick={() => { setOpen(!open); setError(''); setSuccess(''); }}>
          {open ? '取消' : credentialsPresent ? '重新登录' : '登录树洞'}
        </button>
      </div>
      {enabled && !loginSupported && <p className="error" role="alert">当前连接的是旧版后端，尚不支持树洞登录。请重启项目的前后端服务，再点击“重新检查”。这不是账号或密码错误。</p>}
      {open && <form id="campus-login-form" onSubmit={login} autoComplete="off" aria-busy={busy}>
        <div className="login-fields">
          <div><label htmlFor="campus-email">树洞邮箱</label><input id="campus-email" name="email" type="email" autoComplete="username" required maxLength={320} disabled={busy} /></div>
          <div><label htmlFor="campus-password">树洞密码</label><input id="campus-password" name="password" type="password" required maxLength={1024} disabled={busy} /></div>
          <button type="submit" disabled={busy || !enabled || !loginSupported}>{busy ? '正在登录…' : '登录'}</button>
        </div>
      </form>}
      {error && <p className="error" role="alert">{error}</p>}
      {success && <p className="login-success" role="status">{success}</p>}
    </div>
  );
}
