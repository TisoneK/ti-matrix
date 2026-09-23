/* Buttons, chips and the settings fields — the pieces a person clicks. */

import { ReactNode } from "react";
import { WorldField } from "../protocol";

export function Button({ children, onClick, variant = "plain", disabled, title, type = "button" }: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "plain" | "primary" | "ghost" | "mini";
  disabled?: boolean;
  title?: string;
  type?: "button" | "submit";
}) {
  return (
    <button type={type} className={`btn ${variant}`} onClick={onClick} disabled={disabled} title={title}>
      {children}
    </button>
  );
}

export function Chip({ children, on, onClick, title }: {
  children: ReactNode;
  on?: boolean;
  onClick?: () => void;
  title?: string;
}) {
  return (
    <button type="button" className={`chip${on ? " on" : ""}`} aria-pressed={on} onClick={onClick} title={title}>
      {children}
    </button>
  );
}

/** A theme is any set of named things a person picks one of: worlds, scopes, log kinds. */
export function ChipRow<T extends string>({ items, value, onChange }: {
  items: readonly { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="tools">
      {items.map((it) => (
        <Chip key={it.id} on={it.id === value} onClick={() => onChange(it.id)}>{it.label}</Chip>
      ))}
    </div>
  );
}

const DIRECTORY_FIELDS = new Set(["root", "project"]);

export function Field({ field, value, onChange, onPick }: {
  field: WorldField;
  value: string | boolean;
  onChange: (value: string | boolean) => void;
  onPick: () => void;
}) {
  if (field.kind === "checkbox") {
    return (
      <label className="check">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {field.label}
      </label>
    );
  }
  const id = `field-${field.name}`;
  return (
    <div className="field">
      <label className="label" htmlFor={id}>{field.label}</label>
      <span className="inputrow">
        <input id={id} type="text" value={String(value)} placeholder={field.placeholder ?? ""}
               spellCheck={false} onChange={(e) => onChange(e.target.value)} />
        {DIRECTORY_FIELDS.has(field.name) ? (
          <Button variant="mini" onClick={onPick} title="choose a directory">…</Button>
        ) : null}
      </span>
    </div>
  );
}
