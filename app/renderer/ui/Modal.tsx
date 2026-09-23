/*
 * A dialog shell — used by the settings panel and the confirmer alike.
 *
 * Escape closes it and focus moves inside, so a keyboard can always get out of one.
 */

import { ReactNode, useEffect, useRef } from "react";

export function Modal({ title, onClose, children, footer, tone }: {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  tone?: "warn";
}) {
  const box = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    box.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`dialog${tone ? ` ${tone}` : ""}`} role="dialog" aria-modal="true"
           aria-labelledby="modal-title" tabIndex={-1} ref={box}>
        <header className="dialog-head">
          <h2 id="modal-title">{title}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="close">✕</button>
        </header>
        <div className="dialog-body">{children}</div>
        {footer ? <footer className="dialog-foot">{footer}</footer> : null}
      </div>
    </div>
  );
}
