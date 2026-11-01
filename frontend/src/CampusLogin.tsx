import { useRef, useState } from 'react';

type Props = {
  enabled: boolean;
  credentialsPresent: boolean;
  onLoggedIn: () => Promise<void>;
};

export function CampusLogin({ enabled, credentialsPresent, onLoggedIn }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const submitting = useRef(false);

  async function login(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const email = String(data.get('email') || '').trim();
    const password = String(data.get('password') || '');
    if (!email || !password) return;
    submitting.current = true;
    setBusy(true); setError(''); setSuccess('');
    // Clear the visible field immediately; credentials never enter chat state,
    // localStorage or sessionStorage. Only the login request contains them.
    (form.elements.namedItem('password') as HTMLInputElement).value = '';
    try {
      const response = await fetch('/api/campus/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        signal: AbortSignal.timeout(100_000), cache: 'no-store',
      });
      const result = await response.json();
      if (!response.ok || result.authenticated !== true) {
        throw new Error(result.error?.message || '登录失败，请稍后重试。');
      }
      form.reset();
      setOpen(false);
      setSuccess('登录成功，凭据已保存在本机。树洞对话功能将在第四步开放。');
      await onLoggedIn();
    } catch (cause) {
      setError(cause instanceof Error && cause.name === 'Error'
        ? cause.message : '未能完成登录，请检查后端连接后重试。');
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="campus-login">
      <div className="section-heading">
        <p className="help">使用你的树洞账号登录，凭据仅保存在这台电脑。</p>
        <button className="text-button" type="button" disabled={!enabled || busy}
          aria-expanded={open} aria-controls="campus-login-form"
          onClick={() => { setOpen(!open); setError(''); setSuccess(''); }}>
          {open ? '收起登录' : credentialsPresent ? '重新登录树洞' : '登录树洞'}
        </button>
      </div>
      {open && <form id="campus-login-form" onSubmit={login} autoComplete="off" aria-busy={busy}>
        <p className="help" id="campus-login-help">邮箱和密码将经本机后端发送至树洞认证服务（auth.fduhole.com）。密码不会保存，也不会发送给模型。</p>
        <div className="login-fields">
          <div><label htmlFor="campus-email">树洞邮箱</label><input id="campus-email" name="email" type="email" required maxLength={320} disabled={busy} aria-describedby="campus-login-help" /></div>
          <div><label htmlFor="campus-password">树洞密码</label><input id="campus-password" name="password" type="password" required maxLength={1024} disabled={busy} /></div>
          <button type="submit" disabled={busy || !enabled}>{busy ? '正在登录…' : '登录并保存凭据'}</button>
        </div>
      </form>}
      {error && <p className="error" role="alert">{error}</p>}
      {success && <p className="login-success" role="status">{success}</p>}
    </div>
  );
}
