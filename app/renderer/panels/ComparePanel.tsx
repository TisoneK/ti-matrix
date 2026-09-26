/*
 * Compare: the same seed, two runs, one screen.
 *
 * This is the panel the tool was missing. A single run tells you what happened; two runs of the same world
 * tell you whether the model, the budget or the seed is doing the work — which is the evidence anyone needs
 * before trusting a configuration with more autonomy than they are watching.
 *
 * The two runs are the same three panels as the Run view, driven by one cursor so "step" advances both.
 * Where the worlds are the same size the maps are drawn as one overlay, because the interesting question
 * is not "what did A look like" but "where did they go differently" — and that question is answered by two
 * trails on one maze.
 */

import { useMemo, useState } from "react";
import { Decision, RunArtifact } from "../core/types";
import { modelLabel } from "../core/models";
import { outcomeLabel } from "../core/format";
import { MazeKnowledge, boundsOf, parseCellKey } from "../core/knowledge";
import { project } from "../core/project";
import { Confidence, Empty, Flags, PaneBody, PaneHead, Sparkline } from "../ui/atoms";
import { Button, Chip } from "../ui/controls";

const PITCH = 18;
const GAP = 1.4;

export function ComparePanel({ left, right, onPick, onExit }: {
  left: RunArtifact | null;
  right: RunArtifact | null;
  onPick: (side: "left" | "right") => void;
  onExit: () => void;
}) {
  // Null means "the end of both runs", which is where a comparison starts: two finished runs, held against
  // each other. Stepping or rewinding pins the cursor, exactly as the run view's scrubber does.
  const [pin, setPin] = useState<number | null>(null);
  const [overlay, setOverlay] = useState(true);

  const full = useMemo(() => ({
    a: left ? project(left.events, Number.MAX_SAFE_INTEGER) : null,
    b: right ? project(right.events, Number.MAX_SAFE_INTEGER) : null,
  }), [left, right]);
  const steps = Math.max(full.a?.decisions.length ?? 0, full.b?.decisions.length ?? 0);
  const cursor = pin === null ? Math.max(0, steps - 1) : Math.max(0, Math.min(pin, steps - 1));
  const stepBoth = (delta: number) => setPin(Math.max(0, Math.min(cursor + delta, Math.max(0, steps - 1))));

  const a = useMemo(() => (left ? project(left.events, cursor) : null), [left, cursor]);
  const b = useMemo(() => (right ? project(right.events, cursor) : null), [right, cursor]);

  if (!left || !right) {
    return (
      <section className="pane" aria-label="compare">
        <PaneHead title="Compare" sub="two runs, side by side" />
        <PaneBody pad>
          <Empty eyebrow="side by side" title={!left && !right ? "Pick two runs" : "Pick one more run"}>
            Choose two saved runs — the same seed against two models is the comparison worth making — and
            this view puts their maps, trees and decisions under one cursor.
          </Empty>
          <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 16 }}>
            <Button onClick={() => onPick("left")}>{left ? `left: ${left.name}` : "choose the left run"}</Button>
            <Button onClick={() => onPick("right")}>{right ? `right: ${right.name}` : "choose the right run"}</Button>
          </div>
        </PaneBody>
      </section>
    );
  }

  const sameShape = sameWorldShape(a!.knowledge, b!.knowledge);

  return (
    <section className="pane compare" aria-label="compare">
      <div className="compare-pick">
        <span className="pane-title">Compare</span>
        <button type="button" className="pick" onClick={() => onPick("left")}><span className="dot a" />{left.name}</button>
        <button type="button" className="pick" onClick={() => onPick("right")}><span className="dot b" />{right.name}</button>
        {sameShape ? (
          <Chip label="overlay the maps" pressed={overlay} onClick={() => setOverlay((v) => !v)}
                title="draw both runs on one grid — only possible when they read the same world" />
        ) : (
          <span className="warn">different world sizes — maps are shown apart</span>
        )}
        <span className="spacer" />
        <span className="pane-sub">step {Math.min(cursor + 1, steps)}/{steps}</span>
        <Chip label="step both" pressed={false} onClick={() => stepBoth(1)}
              title="advance the shared cursor by one decision" />
        <Chip label="back" pressed={false} onClick={() => stepBoth(-1)} title="step both back" />
        <Chip label="to the start" pressed={false} onClick={() => setPin(0)} title="both runs, before their first decision" />
        <Chip label="to the end" pressed={false} onClick={() => setPin(null)} title="both runs as they finished" />
        <Button size="sm" onClick={onExit}>leave compare</Button>
      </div>

      <Scorecard a={left} b={right} atA={a!} atB={b!} />

      <div className={`compare-body ${sameShape && overlay ? "overlay" : ""}`}>
        {sameShape && overlay ? (
          <div className="compare-col">
            <div className="overlay-legend">
              <span><i className="dot a" />{modelLabel(left.model) || "left"} — step {Math.min(cursor + 1, a!.decisions.length)}/{a!.decisions.length}</span>
              <span><i className="dot b" />{modelLabel(right.model) || "right"} — step {Math.min(cursor + 1, b!.decisions.length)}/{b!.decisions.length}</span>
              <span className="dim">lighter squares are the union of what both have seen</span>
            </div>
            <PaneBody>
              <OverlayMap a={a!.knowledge} b={b!.knowledge} />
            </PaneBody>
            <div className="inspector">
              <div className="inspector-grid">
                <Column title={`${modelLabel(left.model) || "left"} at this step`} decision={a!.at} />
                <Column title={`${modelLabel(right.model) || "right"} at this step`} decision={b!.at} />
              </div>
            </div>
          </div>
        ) : (
          <>
            <Column2 title={modelLabel(left.model) || "left"} accent="a" artifact={left} decisions={a!.decisions} at={a!.at}
                     knowledge={a!.knowledge} cursor={cursor} />
            <Column2 title={modelLabel(right.model) || "right"} accent="b" artifact={right} decisions={b!.decisions} at={b!.at}
                     knowledge={b!.knowledge} cursor={cursor} />
          </>
        )}
      </div>
    </section>
  );
}

/* ── the numbers, side by side ──────────────────────────────────────────── */

function Scorecard({ a, b, atA, atB }: {
  a: RunArtifact;
  b: RunArtifact;
  atA: ReturnType<typeof project>;
  atB: ReturnType<typeof project>;
}) {
  const trustA = atA.trust.trend;
  const trustB = atB.trust.trend;
  const rows: { label: string; x: string | number; y: string | number; delta?: string }[] = [
    { label: "seed", x: a.seed ?? "—", y: b.seed ?? "—" },
    { label: "ended", x: outcomeLabel(a.outcome.settled, a.outcome.reason),
      y: outcomeLabel(b.outcome.settled, b.outcome.reason) },
    { label: "decisions", x: atA.decisions.length, y: atB.decisions.length, delta: diff(atA.decisions.length, atB.decisions.length) },
    { label: "retreats", x: count(atA.decisions, "backtrack"), y: count(atB.decisions, "backtrack") },
    { label: "surprises", x: countFlag(atA.decisions, "surprise"), y: countFlag(atB.decisions, "surprise") },
    { label: "mean belief", x: `${Math.round(atA.trust.mean * 100)}%`, y: `${Math.round(atB.trust.mean * 100)}%` },
    { label: "trend", x: trustA, y: trustB },
    { label: "cells seen", x: atA.knowledge.cells.size, y: atB.knowledge.cells.size, delta: diff(atA.knowledge.cells.size, atB.knowledge.cells.size) },
  ];
  return (
    <dl className="scorecard">
      {rows.map((r) => (
        <div className="cell" key={r.label}>
          <dt>{r.label}</dt>
          <dd>
            <span className="a">{r.x}</span>
            <span className="dim"> / </span>
            <span className="b">{r.y}</span>
            {r.delta ? <span className="delta">{r.delta}</span> : null}
          </dd>
        </div>
      ))}
      <div className="cell">
        <dt>belief over the run</dt>
        <dd style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <Sparkline curve={atA.trust} width={96} height={22} />
          <Sparkline curve={atB.trust} width={96} height={22} />
        </dd>
      </div>
    </dl>
  );
}

const count = (ds: Decision[], kind: Decision["kind"]): number => ds.filter((d) => d.kind === kind).length;
const countFlag = (ds: Decision[], flag: string): number => ds.filter((d) => d.flags.includes(flag as Decision["flags"][number])).length;
const diff = (x: number, y: number): string => {
  const d = x - y;
  return d === 0 ? "" : d > 0 ? `+${d} left` : `+${-d} right`;
};

/* ── one run, as a column ───────────────────────────────────────────────── */

function Column2({ title, accent, artifact, decisions, at, knowledge, cursor }: {
  title: string;
  accent: "a" | "b";
  artifact: RunArtifact;
  decisions: Decision[];
  at: Decision | null;
  knowledge: MazeKnowledge;
  cursor: number;
}) {
  const bounds = boundsOf(knowledge);
  return (
    <div className="compare-col">
      <PaneHead title={title || "run"} sub={`${artifact.events.length} events · step ${Math.min(cursor + 1, decisions.length)}/${decisions.length}`} />
      <PaneBody>
        {bounds ? <SingleMap knowledge={knowledge} accent={accent} /> : <Empty title="Nothing seen at this step">{artifact.world}</Empty>}
      </PaneBody>
      <div className="inspector">
        <div className="inspector-grid">
          <Column title="this step" decision={at} />
          <Column title="last evidence" decision={lastWithEvidence(decisions, cursor)} />
        </div>
      </div>
    </div>
  );
}

function Column({ title, decision }: { title: string; decision: Decision | null }) {
  if (!decision) return <div><h4>{title}</h4><p className="dim">—</p></div>;
  return (
    <div>
      <h4>{title}</h4>
      <p>
        <span className="mono">{decision.index + 1}. {decision.move ?? decision.kind}</span>
        {decision.kind === "move" || decision.kind === "done"
          ? <> <Confidence value={decision.confidence} /></> : null}
        {" "}<Flags flags={decision.flags} />
      </p>
      {decision.evidence ? <p className="mono dim" style={{ marginTop: 3 }}>{decision.evidence}</p> : null}
    </div>
  );
}

const lastWithEvidence = (decisions: Decision[], cursor: number): Decision | null => {
  for (let i = Math.min(cursor, decisions.length - 1); i >= 0; i -= 1) {
    if (decisions[i].evidence) return decisions[i];
  }
  return null;
};

/* ── the two maps ───────────────────────────────────────────────────────── */

const sameWorldShape = (a: MazeKnowledge, b: MazeKnowledge): boolean =>
  a.grid !== null && b.grid !== null && a.grid.width === b.grid.width && a.grid.height === b.grid.height;

function SingleMap({ knowledge, accent }: { knowledge: MazeKnowledge; accent: "a" | "b" }) {
  const bounds = boundsOf(knowledge)!;
  const w = (bounds.maxX - bounds.minX + 1) * PITCH;
  const h = (bounds.maxY - bounds.minY + 1) * PITCH;
  return (
    <div className="mapwrap">
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img"
           aria-label={`${accent} map: ${knowledge.cells.size} cells seen`}>
        <Grid knowledge={knowledge} bounds={bounds} />
        <Trail knowledge={knowledge} bounds={bounds} accent={accent} />
      </svg>
    </div>
  );
}

/**
 * Both runs on one grid. The squares are either agent's knowledge — which is itself informative, because
 * the cells only one of them ever saw are exactly the divergence — and each trail is drawn in its own
 * colour over it.
 */
function OverlayMap({ a, b }: { a: MazeKnowledge; b: MazeKnowledge }) {
  const bounds = useMemo(() => unionBounds(a, b)!, [a, b]);
  const w = (bounds.maxX - bounds.minX + 1) * PITCH;
  const h = (bounds.maxY - bounds.minY + 1) * PITCH;
  return (
    <div className="mapwrap">
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img"
           aria-label={`both runs on one grid: ${a.cells.size} and ${b.cells.size} cells seen`}>
        <Grid knowledge={merge(a, b)} bounds={bounds} />
        <Trail knowledge={a} bounds={bounds} accent="a" />
        <Trail knowledge={b} bounds={bounds} accent="b" />
      </svg>
    </div>
  );
}

/** Squares either run has seen, so the overlay shows every cell anything observed. */
function merge(a: MazeKnowledge, b: MazeKnowledge): MazeKnowledge {
  const cells = new Map(a.cells);
  for (const [key, cell] of b.cells) if (!cells.has(key)) cells.set(key, cell);
  const walls = new Set(a.walls);
  for (const key of b.walls) if (!cells.has(key)) walls.add(key);
  const floor = new Set([...a.floor, ...b.floor]);
  return { ...a, cells, walls, floor };
}

function unionBounds(a: MazeKnowledge, b: MazeKnowledge) {
  const x = boundsOf(a);
  const y = boundsOf(b);
  if (!x) return y;
  if (!y) return x;
  return {
    minX: Math.min(x.minX, y.minX), maxX: Math.max(x.maxX, y.maxX),
    minY: Math.min(x.minY, y.minY), maxY: Math.max(x.maxY, y.maxY),
  };
}

function Grid({ knowledge, bounds }: { knowledge: MazeKnowledge; bounds: { minX: number; maxX: number; minY: number; maxY: number } }) {
  const out = [];
  for (let y = bounds.minY; y <= bounds.maxY; y += 1) {
    for (let x = bounds.minX; x <= bounds.maxX; x += 1) {
      const key = `${x},${y}`;
      const known = knowledge.cells.has(key) || knowledge.floor.has(key);
      const wall = knowledge.walls.has(key);
      out.push(
        <rect key={key}
              className={known ? "cell-floor" : wall ? "cell-wall" : "cell-unknown"}
              x={(x - bounds.minX) * PITCH + GAP / 2} y={(y - bounds.minY) * PITCH + GAP / 2}
              width={PITCH - GAP} height={PITCH - GAP} rx={known || wall ? 3 : 0} />,
      );
    }
  }
  return <g>{out}</g>;
}

function Trail({ knowledge, bounds, accent }: { knowledge: MazeKnowledge; bounds: { minX: number; maxX: number; minY: number; maxY: number }; accent: "a" | "b" }) {
  const centre = (key: string): string => {
    const [x, y] = parseCellKey(key);
    return `${(x - bounds.minX) * PITCH + PITCH / 2},${(y - bounds.minY) * PITCH + PITCH / 2}`;
  };
  return (
    <g>
      {knowledge.livePath.length > 1 ? (
        <polyline className={accent === "a" ? "trail" : "trail-b"} points={knowledge.livePath.map(centre).join(" ")} />
      ) : null}
      {knowledge.abandoned.map((key) => (
        <circle key={key} className={accent === "a" ? "ghost-dot-a" : "ghost-dot-b"}
                cx={centre(key).split(",")[0]} cy={centre(key).split(",")[1]} r={PITCH * 0.22} />
      ))}
      {knowledge.current ? (
        <>
          <circle className={accent === "a" ? "agent-halo" : "agent-b-halo"} cx={centre(knowledge.current).split(",")[0]}
                  cy={centre(knowledge.current).split(",")[1]} r={PITCH * 0.42} />
          <circle className={accent === "a" ? "agent" : "agent-b"} cx={centre(knowledge.current).split(",")[0]}
                  cy={centre(knowledge.current).split(",")[1]} r={Math.max(2.5, PITCH * 0.19)} />
        </>
      ) : null}
    </g>
  );
}
