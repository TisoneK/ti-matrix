/*
 * The ops console: the run as an instrument panel.
 *
 * The Run view answers "what did it believe and why"; this answers "how is it doing, right now" — the same
 * projection read as telemetry. A row of gauges, a column of signals, the candidate orbit at the centre,
 * and the feed with the current fan's belief spread beside it.
 *
 * Every readout here is a real engine fact or an honestly-labelled proxy, never a decoration dressed as a
 * measurement. Two substitutions were made on purpose from the first draft of this panel, and both are
 * noted where they are drawn: "active agents" became **candidates live** (this engine is a beam of one, so
 * there are no agents to count), and "throughput" became **retreats** (a token rate is not a number
 * `builtin` can produce — it spends none — so the gauge reads a fact that exists for every run).
 */

import { useMemo } from "react";
import { Decision } from "../core/types";
import { curvePath, TrustCurve } from "../core/trust";
import { finalAnswerOf } from "../core/decisions";
import { pct } from "../core/format";
import { Empty, PaneBody, PaneHead } from "../ui/atoms";
import { CandidateRadar } from "./CandidateRadar";
import { fanOf, feedLines, formatMs } from "./LiveTrace";

const CW = 340; // the signal charts' own coordinate width
const CH = 54;

export function OpsConsole({ decisions, trust, cursor, live, tokens }: {
  decisions: Decision[];
  trust: TrustCurve;
  cursor: number;
  live?: boolean;
  /** Total tokens, when the run reported usage. `builtin` spends none, so it stays undefined there. */
  tokens?: number | null;
}) {
  const fan = useMemo(() => fanOf(decisions, cursor), [decisions, cursor]);
  const answer = useMemo(() => finalAnswerOf(decisions), [decisions]);
  const lines = useMemo(() => feedLines(decisions), [decisions]);
  const backtracks = useMemo(() => decisions.filter((d) => d.kind === "backtrack").length, [decisions]);
  const open = fan ? fan.options.filter((o) => !o.chosen && o.ok === undefined).length : 0;

  // The cumulative retreats, as a step line — a run that never retreats draws flat along the floor, which
  // is itself the readout: a straight line is the fact.
  const retreatPath = useMemo(() => {
    if (decisions.length === 0) return "";
    let n = 0;
    const counts = decisions.map((d) => { if (d.kind === "backtrack") n += 1; return n; });
    const max = Math.max(1, n);
    return counts.map((c, i) => {
      const x = 4 + (i / Math.max(1, decisions.length - 1)) * (CW - 8);
      const y = CH - 4 - (c / max) * (CH - 10);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(" ");
  }, [decisions]);

  const beliefLine = useMemo(() => curvePath(trust, CW, CH, 4), [trust]);
  const bars = trust.points.slice(-24);
  const latest = lines[0];

  return (
    <main className="console">
      <div className="console-kpis">
        <Kpi value={trust.mean} tone="ice" label="belief"
             sub={trust.points.length === 0 ? "no scored move yet" : `${trust.trend} · ${pct(trust.mean)}`} />
        <Kpi value={clamp01(decisions.length === 0 ? 0 : decisions[decisions.length - 1].confidence)} tone="violet"
             label="last decision" sub={decisions.length === 0 ? "—" : pct(decisions[decisions.length - 1].confidence)} />
        <Kpi value={fan && fan.options.length ? open / fan.options.length : 0} tone="ice" label="candidates live"
             sub={fan ? `${open} of ${fan.options.length} open` : "none proposed"} />
        <Kpi value={decisions.length ? backtracks / decisions.length : 0} tone="amber" label="retreats"
             sub={decisions.length ? `${backtracks} of ${decisions.length} turns` : "none yet"} />
      </div>

      <div className="console-cols">
        <section className="pane" aria-label="signals">
          <PaneHead title="Signals" sub="belief · retreats" />
          <PaneBody className="console-body">
            <div className="sig">
              <div className="sig-lbl"><span>belief over the run</span><b>{trust.points.length === 0 ? "—" : trust.trend}</b></div>
              {beliefLine ? (
                <svg className="sig-chart" viewBox={`0 0 ${CW} ${CH}`} preserveAspectRatio="none" role="img"
                     aria-label={`belief across ${trust.points.length} scored moves, mean ${pct(trust.mean)}`}>
                  <path className="sig-area" d={`${beliefLine} L${CW - 4} ${CH} L4 ${CH} Z`} />
                  <path className="sig-line" d={beliefLine} />
                </svg>
              ) : <p className="sig-none">A move is not scored until the evaluator returns one; the curve starts there.</p>}
              <div className="scan"><i /></div>
            </div>

            <div className="sig">
              <div className="sig-lbl"><span>retreats · cumulative</span><b>{backtracks}</b></div>
              {retreatPath ? (
                <svg className="sig-chart" viewBox={`0 0 ${CW} ${CH}`} preserveAspectRatio="none" role="img"
                     aria-label={`${backtracks} retreats across the run`}>
                  <path className="sig-line" d={retreatPath} />
                </svg>
              ) : <p className="sig-none">Nothing to plot yet.</p>}
            </div>

            <div className="sig" style={{ marginBottom: 0 }}>
              <div className="sig-lbl"><span>belief · per move</span><b>{bars.length}</b></div>
              {bars.length === 0 ? (
                <p className="sig-none">Each bar is one move's evaluated score.</p>
              ) : (
                <div className="eq" role="img" aria-label="each recent move's evaluated belief">
                  {bars.map((p) => (
                    <i key={p.index} style={{ height: `${Math.max(6, p.confidence * 100)}%` }}
                       className={p.confidence < 0.5 ? "low" : p.confidence >= 0.85 ? "high" : ""}
                       title={`step ${p.index + 1} — believed ${pct(p.confidence)}`} />
                  ))}
                </div>
              )}
            </div>

            {/* The one number the first draft invented and this one does not: tokens exist only for a
                hosted run, and `builtin` spends none — so it is printed as a fact when there is one and
                said to be absent when there is not, rather than animated as a rate. */}
            <p className="sig-note">
              {tokens === undefined || tokens === null
                ? "token spend: unavailable — this run spent none (built-in rules)"
                : `token spend: ${tokens.toLocaleString()}`}
            </p>
          </PaneBody>
        </section>

        <section className="pane" aria-label="state orbit">
          <PaneHead title="State orbit"
                    sub={fan ? `${fan.options.length} weighed · step ${fan.index + 1} of ${decisions.length}` : "no candidates"} />
          <PaneBody className="trace-body">
            {fan ? <CandidateRadar decision={fan} live={!!live} /> : (
              <Empty eyebrow="the search" title="Nothing weighed yet">
                The candidates the run is choosing between appear here, and drop out as the world answers.
              </Empty>
            )}
            {answer ? (
              <div className={`answer-band ${answer.verified ? "on" : "held"}`}>
                <span className="lbl">{answer.verified ? "answer" : "best from what it read"}</span>
                <span className="answer-text">{answer.text}</span>
              </div>
            ) : null}
          </PaneBody>
        </section>

        <section className="pane" aria-label="state feed">
          <PaneHead title="State feed"
                    sub={decisions.length === 0 ? undefined : `${decisions.length} turn${decisions.length === 1 ? "" : "s"} · newest first`} />
          <PaneBody className="feedwrap">
            {lines.length === 0 ? (
              <Empty eyebrow="the feed" title="Nothing yet">
                Every turn lands here as it happens.
              </Empty>
            ) : (
              <ol className="feed">
                {lines.slice(0, 60).map((line) => (
                  <li key={line.key} className={`feed-line ${line.tone}`}>
                    <span className="t">{formatMs(line.tMs)}</span>
                    <span className="body">{line.text}</span>
                  </li>
                ))}
              </ol>
            )}
            <Distribution fan={fan} />
          </PaneBody>
        </section>
      </div>

      {/* The closing ticker: the run's own headlines, oldest to newest, in one line. The margin at either
          end is a seam so the loop does not jump — the second copy is `aria-hidden`. */}
      <div className="ticker" aria-hidden={lines.length === 0}>
        <span className="ticker-run">
          {latest ? decisions.slice(-12).map((d) => d.headline).join("   →   ") : "no run on screen — start one to see its trace"}
        </span>
      </div>
    </main>
  );
}

/** One gauge, one real number. The ring is the whole reading; the figure in the middle is the exact value. */
function Kpi({ value, label, sub, tone }: { value: number; label: string; sub: string; tone: "ice" | "violet" | "amber" }) {
  const size = 52, r = (size - 12) / 2, c = 2 * Math.PI * r, v = clamp01(value);
  return (
    <div className="kpi">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${Math.round(v * 100)} percent`}>
        <circle className="kpi-ring-bg" cx={size / 2} cy={size / 2} r={r} />
        <circle className={`kpi-ring-fg ${tone}`} cx={size / 2} cy={size / 2} r={r}
                strokeDasharray={c} strokeDashoffset={c - c * v}
                transform={`rotate(-90 ${size / 2} ${size / 2})`} />
        <text className="kpi-val" x={size / 2} y={size / 2 + 4} textAnchor="middle">{Math.round(v * 100)}</text>
      </svg>
      <div className="kpi-lbl">{label}<b>{sub}</b></div>
    </div>
  );
}

/**
 * The current fan's belief, as one bar. Each candidate's share of the weight, so a fan where one option
 * runs away with it and a fan that is still genuinely split look different at a glance — which is the
 * question the radar's single centre number cannot answer.
 */
function Distribution({ fan }: { fan: Decision | null }) {
  const options = fan?.options ?? [];
  if (options.length === 0) return null;
  const total = options.reduce((s, o) => s + (o.progress ?? 0), 0);
  const even = total === 0;
  return (
    <div className="dist">
      <div className="dist-lbl">
        candidate belief {even ? <em>unweighted — nothing scored yet</em> : <em>share of {options.length}</em>}
      </div>
      <div className="dist-bar" role="img" aria-label={`${options.length} candidates and their share of belief`}>
        {options.map((o, i) => {
          const w = even ? 100 / options.length : Math.max(3, ((o.progress ?? 0) / total) * 100);
          const cls = o.chosen ? "chosen" : o.ok === false ? "refused" : "";
          return (
            <i key={o.fp || i} className={cls} style={{ width: `${w}%` }} title={`${o.label} — ${even ? "unscored" : pct(o.progress ?? 0)}`} />
          );
        })}
      </div>
    </div>
  );
}

const clamp01 = (n: number): number => (Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0);
