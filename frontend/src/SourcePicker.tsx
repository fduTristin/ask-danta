import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Globe, MessagesSquare, SlidersHorizontal } from 'lucide-react';
import type { SourceMode } from './api';

type Props = { value: SourceMode; campusReady: boolean; disabled: boolean; onChange: (value: SourceMode) => void };
type Placement = { left: number; top: number; width: number; maxHeight: number };

export function SourcePicker({ value, campusReady, disabled, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const initialIndex = useRef(0);
  const id = useId();
  const options = [
    { value: 'auto' as const, label: '自动选择', description: campusReady ? '当前可使用网页与树洞' : '当前使用网页，登录后可用树洞', icon: SlidersHorizontal },
    { value: 'web' as const, label: '仅网页', description: '查找公开信息与官方资料', icon: Globe },
    { value: 'all' as const, label: '网页 + 树洞', description: campusReady ? '同时参考校内讨论与同学经验' : '登录树洞，补充同学的校园经验', icon: MessagesSquare },
  ];
  const selected = options.find(option => option.value === value)!;
  const label = value === 'auto' ? `自动（${campusReady ? '网页 + 树洞' : '仅网页'}）` : selected.label;
  const Icon = selected.icon;
  const visible = open && !disabled;

  function close(restoreFocus = false) {
    setOpen(false); setPlacement(null);
    if (restoreFocus) trigger.current?.focus({ preventScroll: true });
  }
  function show(last = false) {
    initialIndex.current = last ? options.length - 1 : options.findIndex(option => option.value === value);
    setPlacement(null); setOpen(true);
  }
  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useLayoutEffect(() => {
    if (!visible) return;
    const position = () => {
      const anchor = trigger.current!;
      const popup = menu.current!;
      const rect = anchor.getBoundingClientRect();
      const viewport = window.visualViewport;
      const leftEdge = viewport?.offsetLeft || 0;
      const topEdge = viewport?.offsetTop || 0;
      const width = Math.min(292, (viewport?.width || window.innerWidth) - 24);
      const height = viewport?.height || window.innerHeight;
      popup.style.width = `${width}px`;
      const above = rect.top - topEdge - 22;
      const below = topEdge + height - rect.bottom - 22;
      const upwards = above >= popup.scrollHeight || above > below;
      const maxHeight = Math.max(80, upwards ? above : below);
      setPlacement({
        left: Math.max(leftEdge + 12, Math.min(rect.left, leftEdge + (viewport?.width || window.innerWidth) - width - 12)),
        top: upwards ? rect.top - 10 - Math.min(popup.scrollHeight, maxHeight) : rect.bottom + 10,
        width, maxHeight,
      });
    };
    position();
    window.addEventListener('resize', position);
    window.visualViewport?.addEventListener('resize', position);
    window.visualViewport?.addEventListener('scroll', position);
    const observer = new ResizeObserver(position);
    const composer = trigger.current?.closest('form');
    if (composer) observer.observe(composer);
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) close();
    };
    document.addEventListener('pointerdown', outside);
    return () => {
      window.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('scroll', position);
      document.removeEventListener('pointerdown', outside);
      observer.disconnect();
    };
  }, [visible]);
  useLayoutEffect(() => {
    if (visible && placement) menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]')[initialIndex.current]?.focus({ preventScroll: true });
  }, [visible, !!placement]);

  return <>
    <button ref={trigger} type="button" className="source-trigger" disabled={disabled} title={label} aria-label={`搜索范围：${label}`} aria-haspopup="menu" aria-expanded={visible} aria-controls={visible ? id : undefined}
      onClick={() => visible ? close() : show()} onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); show(event.key === 'ArrowUp'); }
      }}><Icon aria-hidden="true" /><span>{value === 'auto' ? '自动' : selected.label}</span><ChevronDown className="source-chevron" aria-hidden="true" /></button>
    {visible && createPortal(<div ref={menu} id={id} className="source-menu" role="menu" aria-label="搜索范围" style={{ ...placement, visibility: placement ? 'visible' : 'hidden' }} onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); return; }
      // Return to the trigger before the browser moves focus to the next control.
      if (event.key === 'Tab') { close(true); return; }
      const items = Array.from(menu.current!.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]'));
      const index = items.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === 'ArrowDown' ? (index + 1) % items.length : event.key === 'ArrowUp' ? (index + items.length - 1) % items.length : event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : -1;
      if (next >= 0) { event.preventDefault(); items[next].focus(); }
    }}>
      <p className="source-menu-heading">搜索范围</p>
      {options.map(option => <button key={option.value} type="button" className="source-option" role="menuitemradio" aria-label={option.label} aria-describedby={`${id}-${option.value}`} aria-checked={value === option.value} tabIndex={-1} onClick={() => { close(true); onChange(option.value); }}>
        <option.icon className="source-option-icon" aria-hidden="true" /><span className="source-option-copy"><strong>{option.label}</strong><small id={`${id}-${option.value}`}>{option.description}</small></span><Check className="source-option-check" aria-hidden="true" />
      </button>)}
      <p className="source-menu-footnote">用于本段对话，随时可以切换</p>
    </div>, document.body)}
  </>;
}
