import { useEffect, useId, useState } from 'react';
import { Check, ChevronDown, CircleAlert, LoaderCircle, Minus } from 'lucide-react';
import type { Progress } from './api';

function duration(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

export function RunProgress({ progress, active = false }: { progress?: Progress | null; active?: boolean }) {
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(Date.now);
  const [mountedAt] = useState(Date.now);
  const panelId = useId();
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
  const steps = progress?.steps || [];
  const elapsed = active ? Math.max(progress?.elapsed_ms || 0, now - (progress?.started_at || mountedAt)) : progress?.elapsed_ms || 0;
  const current = [...steps].reverse().find(step => step.status === 'running');
  const label = active ? current?.label || (steps.length ? '正在处理资料' : '正在连接，准备回答')
    : progress?.status === 'interrupted' ? '回答已停止' : progress?.status === 'incomplete' || progress?.status === 'error' ? '本轮处理未完整完成' : '已完成回答';
  const toolCount = steps.filter(step => step.tool).length;
  return <section className={`run-progress${active ? ' is-active' : ''}`} aria-label="回答执行记录">
    <button type="button" className="progress-toggle" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
      {active ? <LoaderCircle className="progress-spinner" /> : progress?.status === 'complete' ? <Check /> : <CircleAlert />}
      <span className="progress-label" role={active ? 'status' : undefined}>{label}</span>
      <span className="progress-time">{duration(elapsed)}</span><ChevronDown className={open ? 'is-open' : ''} />
    </button>
    {!open && active && <div className="progress-hint">{toolCount ? `已调用 ${toolCount} 次工具 · ` : ''}展开查看执行步骤</div>}
    {open && <div id={panelId} className="progress-panel">
      {!steps.length && <p className="progress-empty">请求已发出，等待服务返回执行状态。</p>}
      <ol className="progress-steps">{steps.map(step => <li key={step.id} className={`progress-step step-${step.status}`}>
        <span className="step-icon" aria-label={{ running: '进行中', complete: '已完成', error: '失败', notice: '提示', interrupted: '已停止' }[step.status]}>
          {step.status === 'running' ? <LoaderCircle className="progress-spinner" /> : step.status === 'complete' ? <Check /> : step.status === 'interrupted' ? <Minus /> : <CircleAlert />}
        </span>
        <div className="step-content"><span>{step.label}</span>{step.detail && <p>{step.detail}</p>}</div>
        <span className="step-time">{duration(step.duration_ms ?? (step.status === 'running' ? elapsed - step.started_ms : 0))}</span>
      </li>)}</ol>
      <p className="progress-footnote">显示实际执行步骤与工具状态</p>
    </div>}
    {active && elapsed >= 20000 && <p className="progress-slow">检索与核对可能需要一些时间，你可以随时停止回答。</p>}
  </section>;
}
