/* Read-only display pieces: the status pill, the run's meters, key/value records, and counts. */

import { ReactNode } from "react";
import { Status } from "../protocol";

export function Pill({ status }: { status: Status }) {
  return <span className={`pill s-${status}`} role="status">{status}</span>;
}

export function Meters({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <div className="meters">
      {items.map((m) => <span key={m.label}><b>{m.value}</b> {m.label}</span>)}
    </div>
  );
}

/** A record the world handed over as `- **Key:** value` lines, or a row of plain pairs. */
export function KeyValues({ pairs, dense }: { pairs: [string, string][]; dense?: boolean }) {
  if (pairs.length === 0) return null;
  return (
    <dl className={`kv${dense ? " dense" : ""}`}>
      {pairs.map(([k, v], i) => (
        <div className="kv-row" key={`${k}-${i}`}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Count({ n, one, many }: { n: number; one: string; many?: string }) {
  return <>{n} {n === 1 ? one : (many ?? `${one}s`)}</>;
}

/** A hairline bar, for a number that is a fraction of something (a score, a share of the budget). */
export function Bar({ value, tone }: { value: number; tone?: "ok" | "warn" | "bad" }) {
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <span className={`bar${tone ? ` ${tone}` : ""}`} role="img" aria-label={`${Math.round(clamped * 100)}%`}>
      <i style={{ width: `${clamped * 100}%` }} />
    </span>
  );
}
