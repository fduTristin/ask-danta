import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { X } from 'lucide-react';

export function Modal({ title, children, close, drawer = false, locked = false, className = '' }: { title: string; children: ReactNode; close: () => void; drawer?: boolean; locked?: boolean; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    const dialog = ref.current!;
    dialog.showModal();
    return () => { dialog.close(); if (trigger?.isConnected) trigger.focus({ preventScroll: true }); };
  }, []);
  return <dialog ref={ref} className={`${drawer ? 'drawer' : 'modal'} ${className}`} aria-label={title} onCancel={event => { event.preventDefault(); if (!locked) close(); }} onClick={event => { if (event.target === event.currentTarget && !locked) close(); }}>
    <div className="modal-heading"><h2>{title}</h2><button type="button" onClick={close} disabled={locked} aria-label={`关闭${title}`}><X /></button></div>{children}
  </dialog>;
}
