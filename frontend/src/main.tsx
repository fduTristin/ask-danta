import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import './style.css';

type Health = {
  status: string;
  model: { name: string; configured: boolean; available: boolean };
  search: { provider: string; configured: boolean; is_mock: boolean };
  campus: { credentials_present: boolean; available: boolean };
};
type SearchResponse = {
  query: string; provider: string; is_mock: boolean; notice: string;
  results: { title: string; url: string; snippet: string; published_at: string | null; truncated: boolean }[];
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...options, signal: AbortSignal.timeout(130_000) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || '请求失败，请检查输入或稍后重试。');
  return data;
}

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState('');
  const [checking, setChecking] = useState(false);
  const [query, setQuery] = useState('复旦大学 校园办事指南');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<SearchResponse | null>(null);

  async function checkHealth() {
    setChecking(true);
    setHealthError('');
    try { setHealth(await request<Health>('/api/health')); }
    catch { setHealth(null); setHealthError('未连接到后端，请确认启动终端中的服务仍在运行。'); }
    finally { setChecking(false); }
  }
  useEffect(() => { void checkHealth(); }, []);

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !query.trim()) return;
    setBusy(true); setError(''); setResult(null);
    try {
      setResult(await request<SearchResponse>('/api/search', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() }),
      }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '搜索失败，请稍后重试。');
    } finally { setBusy(false); }
  }

  return (
    <div className="workspace">
      <aside>
        <a className="brand" href="/">校内信息<br /><strong>研究助手</strong></a>
        <p className="intro">从正式通知到校园经验，<br />让每一条建议有据可查。</p>
        <div className="stage"><span>当前进度</span><h2>建立项目与配置</h2><p>第一步 / 共六步</p></div>
        <p className="scope">当前可以检查服务状态、试用网页搜索。多轮对话将在下一步接入，树洞检索尚未开放。</p>
        <footer>Campus Agent<br />本机开发环境</footer>
      </aside>
      <main>
        <header><div><p className="eyebrow">开发工作台</p><h1>先让信息来源就绪。</h1></div><span className="local">仅本机运行</span></header>
        <section aria-labelledby="service-title" className="services">
          <div className="section-heading"><h2 id="service-title">服务状态</h2><button className="text-button" onClick={() => void checkHealth()} disabled={checking}>{checking ? '检查中…' : '重新检查'}</button></div>
          {healthError && <p role="alert" className="error">{healthError}</p>}
          <dl className="status-list">
            <div><dt>后端服务</dt><dd><span className={`dot ${health ? 'ready' : ''}`} />{health ? '已连接' : checking ? '连接中' : '未连接'}</dd></div>
            <div><dt>DeepSeek 模型</dt><dd>{health?.model.configured ? '已配置 · 待接入对话' : '待配置'}<small>{health?.model.name || 'DeepSeek'}</small></dd></div>
            <div><dt>网页搜索</dt><dd>{health ? health.search.is_mock ? '离线样例' : health.search.configured ? 'Tavily · 已配置，待实际检索' : 'Tavily · 缺少密钥' : '等待后端'}<small>{health?.search.is_mock ? '未访问网络' : '仅使用公开网页'}</small></dd></div>
            <div><dt>树洞检索</dt><dd>尚未接入<small>{health?.campus.credentials_present ? '检测到凭据文件，尚未验证' : '不影响当前启动'}</small></dd></div>
          </dl>
        </section>
        <section className="search-section" aria-labelledby="search-title">
          <div className="section-heading"><h2 id="search-title">试一次网页搜索</h2><span className="tag">{health ? health.search.is_mock ? '样例模式' : 'Tavily' : '等待连接'}</span></div>
          <p className="help">输入关键词，检查搜索结果和来源展示。</p>
          {health?.search.is_mock && <p className="notice">当前返回固定合成样例，与关键词无关。切换真实搜索后，才能用结果回答实际问题。</p>}
          <form onSubmit={search}>
            <label htmlFor="query">搜索关键词</label>
            <div className="search-bar"><input id="query" value={query} onChange={event => setQuery(event.target.value)} maxLength={500} required placeholder="例如：复旦大学 校园办事指南" /><button type="submit" disabled={busy || !health || !health.search.configured || !query.trim()}>{busy ? '搜索中…' : health?.search.is_mock ? '查看样例' : '搜索网页'}</button></div>
          </form>
          <div aria-live="polite" aria-busy={busy}>
            {error && <p role="alert" className="error">{error}</p>}
            {busy && <p className="empty">正在获取结果…</p>}
            {!result && !busy && !error && <div className="empty"><span className="source-icon" aria-hidden="true">⌕</span><p>来源会显示在这里</p><small>保留原始链接；未提供的日期显示为未知。</small></div>}
            {result && <div className="results"><p className="result-note">{result.notice}</p><p className="query-label">检索词：{result.query}</p>{result.results.length === 0 && <p className="empty">没有找到相关结果，可以换一个关键词。</p>}{result.results.map(item => <article key={item.url}><div className="source-meta">{result.is_mock ? '合成样例' : '公开网页'}<span>{item.published_at || '日期未知'}</span></div><h3>{result.is_mock ? item.title : <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>}</h3><p>{item.snippet}</p>{item.truncated && <small>摘要已截断，请查看原文。</small>}<small className="source-url">{result.is_mock ? '示例地址，不是真实来源：' : ''}{item.url}</small></article>)}</div>}
          </div>
        </section>
        <p className="footnote">配置保存在本地 .env。页面不会展示 API Key，也不会读取树洞凭据内容。</p>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
