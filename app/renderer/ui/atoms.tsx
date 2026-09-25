/*
 * The small things every panel is built from.
 *
 * All of them are dumb: they take values and draw them. Nothing here reads an event, knows a world, or
 * holds state — which is what keeps the panels free to be about the run instead of about layout.
 */

import { ReactNode, useId } from "react";
import { Flag } from "../core/types";
import { FLAGS } from "../core/flags";
import { curvePath, TrustCurve } from "../core/trust";
import { Status } from "../protocol";

/* ── panes ──────────────────────────────────────────────────────────────── */

export function Pane({ children, className = "", label }: { children: ReactNode; className?: string; label?: string }) {
  return (
    <section className={`pane ${className}`} aria-label={label}>
      {children}
    </section>
  );
}

export function PaneHead({ title, sub, children }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <header className="pane-head">
      <h3 className="pane-title">{title}</h3>
      {sub !== undefined && sub !== null && sub !== "" ? <span className="pane-sub">{sub}</span> : null}
      <span className="spacer" />
      {children}
    </header>
  );
}

export function PaneBody({ children, className = "", scroll = false, pad = false }:
  { children: ReactNode; className?: string; scroll?: boolean; pad?: boolean }) {
  return <div className={`pane-body ${scroll ? "scroll" : ""} ${pad ? "pad" : ""} ${className}`}>{children}</div>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <p className="big">{title}</p>
      {children ? <p className="small">{children}</p> : null}
    </div>
  );
}

/* ── readouts ───────────────────────────────────────────────────────────── */

export interface Readout {
  label: string;
  value: ReactNode;
  tone?: "pos" | "neg";
}

export function Readouts({ items }: { items: Readout[] }) {
  // Nothing to measure means no list at all, not an empty one: an empty <dl> still takes its gap in
  // the rail, which leaves a hole where the numbers were and reads as a layout bug.
  if (items.length === 0) return null;
  return (
    <dl className="readouts">
      {items.map((r) => (
        <div className="readout" key={r.label}>
          <dt>{r.label}</dt>
          <dd className={r.tone ?? ""}>{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Badge({ children, tone = "", title }: {
  children: ReactNode;
  tone?: "" | "ok" | "fail" | "warn";
  /** The engine's own word for this, when the badge shows a plainer one — kept reachable, not shown. */
  title?: string;
}) {
  return <span className={`badge ${tone}`} title={title}>{children}</span>;
}

/* ── the marks ──────────────────────────────────────────────────────────── */

/**
 * A flag's mark: its own shape at 10×10, tinted by the stylesheet. Shape carries the meaning and colour
 * reinforces it, so the five kinds stay distinguishable without relying on hue.
 */
export function FlagMark({ flag, size = 10, title }: { flag: Flag; size?: number; title?: string }) {
  const spec = FLAGS[flag];
  return (
    <svg className="flagmark" data-flag={flag} width={size} height={size} viewBox="0 0 10 10"
         role="img" aria-label={spec.label} style={{ color: "inherit" }}>
      <title>{title ?? `${spec.label} — ${spec.claim}`}</title>
      <path d={spec.path} fill={spec.filled ? "currentColor" : "none"}
            stroke="currentColor" strokeWidth={spec.filled ? 0 : 1.4} strokeLinejoin="round" />
    </svg>
  );
}

export function Flags({ flags, order }: { flags: Flag[]; order?: Flag[] }) {
  const list = order ? order.filter((f) => flags.includes(f)).concat(flags.filter((f) => !order.includes(f))) : flags;
  return (
    <span className="row-marks">
      {list.map((f) => <FlagMark key={f} flag={f} />)}
    </span>
  );
}

/**
 * A confidence bar. The number is the evaluator's own score for the move, so it is drawn as belief rather
 * than as a percentage of anything — amber, with the low and high ends tinted because "it went anyway on
 * 0.3" is the row you scan for.
 */
export function Confidence({ value, showNumber = true }: { value: number; showNumber?: boolean }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const tone = value < 0.5 ? "low" : value >= 0.85 ? "high" : "";
  return (
    <>
      <span className={`conf ${tone}`} role="img" aria-label={`believed ${pct}%`}>
        <i style={{ width: `${pct}%` }} />
      </span>
      {showNumber ? <span className="conf-num">{pct}%</span> : null}
    </>
  );
}

/* ── the wordmark ───────────────────────────────────────────────────────── */

/**
 * One word, two colours: `Ti` in the accent, `Matrix` in ink.
 *
 * It used to be set as two words — "TI MATRIX" uppercased in the rail, "Ti Matrix" beside a boxed
 * glyph elsewhere — which read as a two-word phrase rather than a name, and said it twice wherever
 * the glyph appeared next to it. One component so the rail, the welcome and anything after them
 * cannot drift apart on it.
 */
export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`wordmark ${className}`}>
      <b>Ti</b>Matrix
    </span>
  );
}

/* ── status ─────────────────────────────────────────────────────────────── */

/* "Sidecar" is what this process is called in the codebase, and for a while it was what the window
   called it too — "reaching the sidecar", "sidecar gone". It is a deployment-pattern name: it tells a
   reader nothing unless they already know the architecture, and the same thing was being called "the
   engine" three strings away. One word, and it is the one a person can act on. */
const STATUS_TEXT: Record<Status, string> = {
  connecting: "starting the engine",
  // "idle" was shown for four different situations — nothing run yet, a run that had just succeeded,
  // a run that had failed, and a saved run opened from the library — because all four are `ready` to
  // the socket. It is also a machine's word for "no work queued", which is never what a person wants
  // to know. The rail now says how the run ended; this is only the case where there is no run at all.
  ready: "ready",
  running: "running",
  reconnecting: "reconnecting…",
  crashed: "engine stopped",
};

/**
 * The lamp says what the machine is doing; `tone` lets the caller say how the *run* ended, which is a
 * different fact and the one a person wants once a run is over. `Status` stays the socket's own
 * vocabulary — it should not learn about runs — so the colour is overridden rather than the state.
 */
export function StatusLamp({ status, detail, tone }: {
  status: Status;
  detail?: string;
  tone?: "ok" | "warn" | "bad";
}) {
  return (
    <span className="status">
      <span className="lamp" data-state={tone ?? status} aria-hidden="true" />
      <span>{detail ?? STATUS_TEXT[status]}</span>
    </span>
  );
}

/* ── the trust sparkline ────────────────────────────────────────────────── */

/**
 * The run's confidence over time, small enough to sit in a header. The mean is a dashed line across it, so
 * the shape reads against the run's own average rather than against zero.
 */
export function Sparkline({ curve, width = 132, height = 26 }:
  { curve: TrustCurve; width?: number; height?: number }) {
  if (curve.points.length === 0) return null;
  const line = curvePath(curve, width, height, 3);
  const area = `${line} L${width - 3} ${height} L3 ${height} Z`;
  const meanY = height - 3 - curve.mean * (height - 6);
  const last = curve.points[curve.points.length - 1];
  const step = curve.points.length > 1 ? (width - 6) / (curve.points.length - 1) : 0;
  const lastX = 3 + (curve.points.length - 1) * step;
  const lastY = height - 3 - last.confidence * (height - 6);
  return (
    <svg className="trust-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`}
         role="img" aria-label={`confidence over the run, mean ${Math.round(curve.mean * 100)} percent, ${curve.trend}`}>
      <title>{`mean ${Math.round(curve.mean * 100)}% · ${curve.trend}`}</title>
      <path className="area" d={area} />
      <line className="mean" x1={0} x2={width} y1={meanY} y2={meanY} />
      <path className="line" d={line} />
      <circle cx={lastX} cy={lastY} r={2.2} />
    </svg>
  );
}

/* ── a labelled field, used by the config drawer ────────────────────────── */

export interface FieldProps {
  id: string;
  "aria-describedby"?: string;
}

/**
 * A labelled control.
 *
 * The label is wired by `for`/`id` rather than wrapping the control, and the hint sits outside it: a label
 * that contains an input *and* the explanation reads the explanation out as part of the control's name,
 * which turns "Model" into "Model the name the endpoint knows it by". The hint becomes a description
 * instead, which is what it is.
 *
 * The children are a function of the props to spread, so the control and its label cannot drift apart.
 */
export function Field({ label, hint, children }:
  { label: string; hint?: string; children: (props: FieldProps) => ReactNode }) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      {children({ id, "aria-describedby": hintId })}
      {hint ? <span className="hint" id={hintId}>{hint}</span> : null}
    </div>
  );
}

/** A field that holds something other than a control — a button, say — so it must not be a label. */
export function Fieldset({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="hint">{hint}</span> : null}
    </div>
  );
}
