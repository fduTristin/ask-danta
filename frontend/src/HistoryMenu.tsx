import { useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Ellipsis, Pencil, Trash2 } from 'lucide-react';

type Props = {
  title: string; open: boolean; disabled: boolean;
  onOpenChange: (open: boolean) => void;
  onAction: (action: 'rename' | 'delete') => void;
};

export function HistoryMenu({ title, open, disabled, onOpenChange, onAction }: Props) {
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const initialIndex = useRef(0);
  const id = useId();
  const [placement, setPlacement] = useState<{ left: number; top: number; width: number; maxHeight: number } | null>(null);
  const visible = open && !disabled;

  function close(restoreFocus = false) {
    onOpenChange(false);
    if (restoreFocus) trigger.current?.focus({ preventScroll: true });
  }
  function show(last = false) {
    initialIndex.current = last ? 1 : 0;
    setPlacement(null); onOpenChange(true);
  }
  useLayoutEffect(() => {
    if (!visible) return;
    const position = () => {
      const rect = trigger.current!.getBoundingClientRect();
      const viewport = window.visualViewport;
      const left = (viewport?.offsetLeft || 0) + 8;
      const top = (viewport?.offsetTop || 0) + 8;
      const right = left + (viewport?.width || window.innerWidth) - 16;
      const bottom = top + (viewport?.height || window.innerHeight) - 16;
      const width = Math.min(184, right - left);
      const maxHeight = bottom - top;
      const height = Math.min(menu.current!.scrollHeight, maxHeight);
      setPlacement({
        left: Math.max(left, Math.min(rect.right + 8 + width <= right ? rect.right + 8 : rect.right - width, right - width)),
        top: Math.max(top, Math.min(rect.top - 6, bottom - height)), width, maxHeight,
      });
    };
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) close();
    };
    const scrolled = (event: Event) => { if (!menu.current?.contains(event.target as Node)) close(true); };
    position();
    document.addEventListener('pointerdown', outside);
    document.addEventListener('scroll', scrolled, true);
    window.addEventListener('resize', position);
    window.visualViewport?.addEventListener('resize', position);
    window.visualViewport?.addEventListener('scroll', position);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('scroll', scrolled, true);
      window.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('scroll', position);
    };
  }, [visible]);
  useLayoutEffect(() => {
    if (visible && placement) menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')[initialIndex.current]?.focus({ preventScroll: true });
  }, [visible, !!placement]);

  return <>
    <button ref={trigger} type="button" className="history-more" aria-label={`管理对话：${title}`} aria-haspopup="menu" aria-expanded={visible} aria-controls={visible ? id : undefined} disabled={disabled}
      onClick={() => visible ? close(true) : show()} onKeyDown={event => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); show(event.key === 'ArrowUp'); }
      }}><Ellipsis /></button>
    {visible && createPortal(<div ref={menu} id={id} className="history-menu" role="menu" aria-label={`对话操作：${title}`} style={{ ...placement, visibility: placement ? 'visible' : 'hidden' }} onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); return; }
      if (event.key === 'Tab') { close(true); return; }
      const items = Array.from(menu.current!.querySelectorAll<HTMLButtonElement>('[role="menuitem"]'));
      const index = items.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === 'ArrowDown' ? (index + 1) % items.length : event.key === 'ArrowUp' ? (index + items.length - 1) % items.length : event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : -1;
      if (next >= 0) { event.preventDefault(); items[next].focus(); }
    }}>
      <button type="button" role="menuitem" tabIndex={-1} onClick={() => { close(true); onAction('rename'); }}><Pencil />重命名</button>
      <button type="button" role="menuitem" tabIndex={-1} className="history-delete" onClick={() => { close(true); onAction('delete'); }}><Trash2 />删除</button>
    </div>, trigger.current?.closest('dialog') || document.body)}
  </>;
}
