import { useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy, Link, X } from 'lucide-react';
import type { Message, Source } from './api';
import { RunProgress } from './RunProgress';

type MarkdownNode = { type: string; value?: string; url?: string; children?: MarkdownNode[] };
// Transform plain text citations only; never rewrite code or an existing link.
function citations() {
  return (tree: MarkdownNode) => {
    const visit = (node: MarkdownNode) => {
      if (!node.children || ['link', 'code', 'inlineCode', 'image'].includes(node.type)) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text') { visit(child); return [child]; }
        const text = child.value || '';
        const parts: MarkdownNode[] = [];
        let offset = 0;
        for (const match of text.matchAll(/\[([WC]\d+)\]/g)) {
          parts.push({ type: 'text', value: text.slice(offset, match.index) });
          parts.push({ type: 'link', url: `#citation-${match[1]}`, children: [{ type: 'text', value: match[1] }] });
          offset = match.index! + match[0].length;
        }
        parts.push({ type: 'text', value: text.slice(offset) });
        return parts;
      });
    };
    visit(tree);
  };
}

function webUrl(url?: string) {
  try { const value = new URL(url || ''); return ['https:', 'http:'].includes(value.protocol) ? value.href : undefined; }
  catch { return undefined; }
}

export function Answer({ message, index }: { message: Message; index: number }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string>();
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState('');
  const panel = useRef<HTMLDivElement>(null);
  const article = useRef<HTMLElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const sources = message.sources || [];
  function showSources(id?: string, trigger?: HTMLElement) {
    returnTo.current = trigger || null;
    setSelected(id); setOpen(true);
    requestAnimationFrame(() => {
      const target = id ? panel.current?.querySelector<HTMLElement>(`[data-source="${id}"]`) : panel.current;
      target?.scrollIntoView({ block: 'nearest' }); target?.focus({ preventScroll: true });
    });
  }
  function closeSources() {
    setOpen(false);
    // Markdown renderers may replace an inline citation node during state changes.
    requestAnimationFrame(() => {
      const target = selected ? article.current?.querySelector<HTMLElement>(`[data-citation="${selected}"]`) : returnTo.current;
      target?.focus({ preventScroll: true }); target?.scrollIntoView({ block: 'nearest' });
    });
  }
  async function copy() {
    try { await navigator.clipboard.writeText(message.content); setCopied(true); setCopyError(''); }
    catch { setCopyError('无法自动复制，请选中回答后复制。'); }
  }
  return <article className="message assistant" ref={article}>
    <div className="assistant-label"><img src="/danta-logo.webp" alt="" />问问旦挞</div>
    {message.progress && <RunProgress progress={message.progress} />}
    <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm, citations]} skipHtml components={{
      a: ({ href, children }) => {
        const id = href?.match(/^#citation-([WC]\d+)$/)?.[1];
        if (id) return sources.some(source => source.id === id)
          ? <button type="button" className="citation" data-citation={id} aria-label={`查看引用 ${id}`} onClick={event => showSources(id, event.currentTarget)}>{children}</button>
          : <span>[{children}]</span>;
        const safe = webUrl(href);
        return safe ? <a href={safe} target="_blank" rel="noreferrer noopener">{children}</a> : <span>{children}</span>;
      },
      img: ({ alt }) => <span>{alt ? `[图片：${alt}]` : '[图片]'}</span>,
      table: ({ children }) => <div className="table-scroll"><table>{children}</table></div>,
    }}>{message.content}</ReactMarkdown></div>
    {message.end_reason === 'budget' && <p className="notice">本轮已达到处理时限，仍有未核实的信息。</p>}
    {message.end_reason === 'error' && <p className="notice">本轮资料未完成核对，请结合下方提示继续确认。</p>}
    {!!message.warnings?.length && <p className="notice">{[...new Set(message.warnings)].join(' ')}</p>}
    <div className="answer-actions"><button type="button" onClick={() => void copy()} aria-label={copied ? '已复制回答' : '复制回答'} title="复制回答">{copied ? <Check /> : <Copy />}<span>{copied ? '已复制' : '复制'}</span></button>
      {!!sources.length && <button type="button" aria-expanded={open} aria-controls={`sources-${index}`} onClick={event => open ? closeSources() : showSources(undefined, event.currentTarget)}><Link />来源 {sources.length}</button>}</div>
    {copyError && <p role="status" className="notice">{copyError}</p>}
    {open && <div className="answer-sources" id={`sources-${index}`} ref={panel} tabIndex={-1} aria-label="本回答引用来源"><div className="source-heading"><strong>本回答的依据</strong><button type="button" aria-label="收起来源并返回回答" onClick={closeSources}><X /></button></div>{sources.map(source => <SourceCard key={source.id} source={source} selected={selected === source.id} />)}</div>}
  </article>;
}

function SourceCard({ source, selected }: { source: Source; selected: boolean }) {
  const url = !source.is_mock && source.source !== 'campus' ? webUrl(source.url) : undefined;
  return <section className={`source-card ${selected ? 'selected' : ''}`} data-source={source.id} tabIndex={-1}>
    <div className="source-kind">{source.id} · {source.source === 'campus' ? '树洞经验' : source.is_mock ? '合成样例' : '公开网页'} · {source.published_at || '日期未知'}</div>
    <strong>{source.source === 'campus' ? `树洞 #${source.hole_id} · 楼层 ID ${source.floor_id}` : url ? <a href={url} target="_blank" rel="noreferrer noopener">{source.title}</a> : source.title}</strong>
    <p>{source.snippet}</p>
    <small>{source.source === 'campus' ? '个人经验，不代表官方规定；未确认已读完整帖子。' : source.page_read ? source.page_truncated ? '已读取部分网页正文。' : '已读取网页文本。' : '当前依据为搜索摘要。'}{source.truncated ? ' 内容已截断。' : ''}{source.redacted ? ' 已做基础脱敏。' : ''}</small>
  </section>;
}
