/*
 * The interactive primitives: a button, a chip, a modal.
 *
 * Kept apart from the display atoms because these are the ones with behaviour — and the ones an
 * accessibility pass has to look at. Every one of them is reachable and operable from the keyboard, and
 * every one of them carries an accessible name.
 */

import { KeyboardEvent as ReactKeyboardEvent, ReactNode, useEffect, useRef } from "react";

export function Button({ children, onClick, variant = "plain", disabled = false, title, type = "button", size }:
  {
    children: ReactNode;
    onClick?: () => void;
    variant?: "plain" | "primary" | "ghost" | "danger";
    disabled?: boolean;
    title?: string;
    type?: "button" | "submit";
    size?: "sm";
  }) {
  return (
    <button type={type} className={`btn ${variant === "plain" ? "" : variant} ${size === "sm" ? "sm" : ""}`}
            onClick={onClick} disabled={disabled} title={title}
            aria-label={typeof children === "string" ? undefined : title}>
      {children}
    </button>
  );
}

export function IconButton({ label, onClick, disabled = false, children }:
  { label: string; onClick?: () => void; disabled?: boolean; children: ReactNode }) {
  return (
    <button type="button" className="btn ghost icon" onClick={onClick} disabled={disabled} title={label} aria-label={label}>
      {children}
    </button>
  );
}

/** A toggle chip. `aria-pressed` carries the state; the label says what it toggles, never "on"/"off". */
export function Chip({ label, pressed, onClick, swatch, title }:
  { label: string; pressed: boolean; onClick: () => void; swatch?: string; title?: string }) {
  return (
    <button type="button" className="pick" aria-pressed={pressed} onClick={onClick} title={title ?? label}>
      {swatch ? <span className={`swatch ${swatch}`} aria-hidden="true" /> : null}
      {label}
    </button>
  );
}

export function Tab({ label, selected, onClick, count }:
  { label: string; selected: boolean; onClick: () => void; count?: number }) {
  return (
    <button type="button" className="tab" role="tab" aria-selected={selected} onClick={onClick}>
      {label}
      {count !== undefined ? <span className="count">{count}</span> : null}
    </button>
  );
}

/**
 * A modal that behaves: focus moves into it, Escape closes it, and Tab cycles inside it. The confirmer is
 * the reason this exists — it blocks a run, so it has to be answerable without a mouse.
 */
export function Modal({ title, onClose, children, footer }: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const first = box.current?.querySelector<HTMLElement>("[data-autofocus], button, input, select, textarea");
    first?.focus();
  }, []);

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
    if (e.key !== "Tab" || !box.current) return;
    const focusable = [...box.current.querySelectorAll<HTMLElement>("button, input, select, textarea, [href]")]
      .filter((el) => !el.hasAttribute("disabled"));
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  return (
    <div className="scrim" onKeyDown={onKeyDown}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-title" ref={box}>
        <div className="dialog-head">
          <h3 id="dlg-title">{title}</h3>
        </div>
        <div className="dialog-body">{children}</div>
        <div className="dialog-foot">{footer}</div>
      </div>
    </div>
  );
}
