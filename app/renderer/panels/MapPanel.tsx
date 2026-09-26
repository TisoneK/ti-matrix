/*
 * The map: what the run believes about the world, drawn as it learned it.
 *
 * The engine never shows a run the maze (`maze.py` is explicit about it), so this is not a map with
 * hidden parts — it is the *belief*, cell by cell, in the order it arrived. Anything unexplored is void.
 *
 * Three overlays carry the rest of the story, and each one answers a question you cannot ask of the run's
 * prose: the heat overlay surfaces loops (a cell visited four times is thrashing), the ghost trail marks
 * the cells it walked into and left behind, and the path shows only the branch the live state still
 * stands on. They are toggles, not decorations: an unreadable map is a map with everything switched on.
 *
 * Hovering a cell opens it in the inspector below — the same shared cursor the ledger and the tree use, so
 * pointing at a wall here and clicking a row there are the same act.
 */

import { useMemo, useState } from "react";
import { MazeKnowledge, KnownCell, boundsOf, cellKey, parseCellKey, statsOf } from "../core/knowledge";
import { Decision, EngineEventFrame } from "../core/types";
import { Chip, IconButton } from "../ui/controls";
import { Empty, PaneBody, PaneHead, Readouts } from "../ui/atoms";
import { WorldSurface } from "./WorldSurface";

const PITCH = 20;
const GAP = 1.6;

export interface MapFocus {
  cell: string | null;
  onFocus: (cell: string | null) => void;
  onPin: (cell: string | null) => void;
}

export function MapPanel({ knowledge, decisions, world, events, focus, liveStep, hoverCell }: {
  knowledge: MazeKnowledge;
  decisions: Decision[];
  world: string;
  events: EngineEventFrame[];
  focus: MapFocus;
  liveStep: number;
  /** The cell the shared cursor is over — a ledger row or tree node elsewhere in the window. */
  hoverCell?: string | null;
}) {
  const [heat, setHeat] = useState(false);
  const [ghost, setGhost] = useState(true);
  const [path, setPath] = useState(true);
  const [zoom, setZoom] = useState(1);

  const stats = useMemo(() => statsOf(knowledge), [knowledge]);
  const bounds = useMemo(() => boundsOf(knowledge), [knowledge]);
  // A world with no grid is not a world with no picture: prose has structure, so the same surface that
  // draws squares for the maze draws what the run read for everything else.
  if (world !== "maze") {
    return (
      <section className="pane" aria-label="the world">
        <WorldSurface world={world} events={events} decisions={decisions} />
      </section>
    );
  }

  return (
    <section className="pane" aria-label="the map">
      <PaneHead title="Map" sub={stats.coverage === null ? "reading the grid…" : `${Math.round(stats.coverage * 100)}% of the floor seen`}>
        <Chip label="heat" pressed={heat} onClick={() => setHeat((v) => !v)}
              title="recolour explored cells by how many times the run stepped on them" />
        <Chip label="ghost" pressed={ghost} onClick={() => setGhost((v) => !v)}
              title="mark the cells it entered and left behind" />
        <Chip label="path" pressed={path} onClick={() => setPath((v) => !v)}
              title="draw the branch the live state still stands on" />
        <span className="pane-sub">{zoom}×</span>
        <IconButton label="zoom out" onClick={() => setZoom((z) => Math.max(0.6, +(z - 0.2).toFixed(1)))}>−</IconButton>
        <IconButton label="zoom in" onClick={() => setZoom((z) => Math.min(3, +(z + 0.2).toFixed(1)))}>+</IconButton>
      </PaneHead>

      <PaneBody>
        {bounds === null ? (
          <Empty eyebrow="the world" title="Nothing seen yet">
            The map fills in as the run looks around. Start a run, or drag the scrubber forward.
          </Empty>
        ) : (
          <div className="mapwrap">
            <MapSvg knowledge={knowledge} bounds={bounds} heat={heat} ghost={ghost} showPath={path}
                    zoom={zoom} focus={focus} hoverCell={hoverCell} />
          </div>
        )}
      </PaneBody>

      <div className="legend" aria-label="what the map's colours mean">
        <span className="legend-item"><i className="swatch dark" />unexplored</span>
        <span className="legend-item"><i className="swatch cell" />a cell it knows</span>
        <span className="legend-item"><i className="swatch wall" />wall</span>
        <span className="legend-item"><i className="swatch live" />where it stands</span>
        {ghost ? <span className="legend-item"><i className="swatch gone" />walked into, then left</span> : null}
        {heat ? <span className="legend-item"><i className="swatch hot" />visited more than once</span> : null}
        <span className="legend-item"><i className="swatch exit" />the exit, once seen</span>
      </div>

      <div className="inspector">
        <div className="inspector-grid map-zones">
          <div className="inspector-zone">
            <CellInspector cell={focus.cell} knowledge={knowledge} />
          </div>
          <div className="inspector-zone">
            <h4>Coverage</h4>
            {/* Three, not five. "Cells seen" is the pane head's own percentage and "step" is in the
                transport a few pixels below, so keeping them here cost a second, ragged row of numbers to
                say nothing new — and a strip of five small figures under a map is the exact texture this
                panel is trying not to have. What is left is what only this strip says. */}
            <Readouts items={[
              { label: "walked", value: stats.entered },
              { label: "revisited", value: stats.revisits, tone: stats.revisits > 0 ? "neg" : undefined },
              { label: "left behind", value: stats.abandoned },
            ]} />
          </div>
          <div className="inspector-zone">
            <h4>Last thing it saw</h4>
            {decisions.length === 0
              ? <p className="mono inspector-none">—</p>
              : <p className="mono inspector-quote" title={lastEvidence(decisions)}>{lastEvidence(decisions)}</p>}
          </div>
        </div>
      </div>
    </section>
  );
}

const lastEvidence = (decisions: Decision[]): string => {
  for (let i = decisions.length - 1; i >= 0; i -= 1) {
    if (decisions[i].evidence) return decisions[i].evidence;
  }
  return "nothing yet";
};

/**
 * The grid itself. Coordinates are the world's own — a cell at (1,1) is drawn at (1,1) — so a passage
 * between two cells lands exactly where the world says it is, and the drawing needs no rescaling.
 */
function MapSvg({ knowledge, bounds, heat, ghost, showPath, zoom, focus, hoverCell }: {
  knowledge: MazeKnowledge;
  bounds: { minX: number; maxX: number; minY: number; maxY: number };
  heat: boolean;
  ghost: boolean;
  showPath: boolean;
  zoom: number;
  focus: MapFocus;
  hoverCell?: string | null;
}) {
  const cols = bounds.maxX - bounds.minX + 1;
  const rows = bounds.maxY - bounds.minY + 1;
  const w = cols * PITCH;
  const h = rows * PITCH;
  const px = (x: number): number => (x - bounds.minX) * PITCH;
  const py = (y: number): number => (y - bounds.minY) * PITCH;
  const centre = (key: string): [number, number] => {
    const [x, y] = parseCellKey(key);
    return [px(x) + PITCH / 2, py(y) + PITCH / 2];
  };

  const ghosts = new Set(ghost ? knowledge.abandoned : []);

  const points: string[] = [];
  for (let y = bounds.minY; y <= bounds.maxY; y += 1) {
    for (let x = bounds.minX; x <= bounds.maxX; x += 1) {
      points.push(cellKey(x, y));
    }
  }

  const pathLine = showPath && knowledge.livePath.length > 1
    ? knowledge.livePath.map((k) => centre(k).join(",")).join(" ")
    : null;

  const hovered = focus.cell;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height="100%" preserveAspectRatio="xMidYMid meet" role="img"
         aria-label={`the maze as the run has learned it: ${knowledge.cells.size} cells seen, ${knowledge.abandoned.length} left behind`}>
      <g transform={`translate(${(w * (1 - zoom)) / 2} ${(h * (1 - zoom)) / 2}) scale(${zoom})`}>
        {points.map((key) => {
          const [x, y] = parseCellKey(key);
          const cell = knowledge.cells.get(key);
          const isWall = knowledge.walls.has(key);
          const kind = cell ? "cell" : isWall ? "wall" : "unknown";
          const classes = ["drawn"];
          if (kind === "cell") classes.push("cell-floor");
          else if (kind === "wall") classes.push("cell-wall");
          else classes.push("cell-unknown");
          if (cell && heat && cell.visits > 1) classes.push(`revisit-${Math.min(3, cell.visits - 1)}`);
          if (ghosts.has(key)) classes.push("cell-ghost");
          if (hoverCell && key === hoverCell) classes.push("cell-peek");
          if (cell?.exit) classes.push("cell-exit");
          else if (cell?.start) classes.push("cell-start");
          return (
            <rect
              key={key}
              className={classes.join(" ")}
              x={px(x) + GAP / 2}
              y={py(y) + GAP / 2}
              width={PITCH - GAP}
              height={PITCH - GAP}
              rx={kind === "unknown" ? 0 : 3}
              onMouseEnter={() => focus.onFocus(key)}
              onMouseLeave={() => focus.onFocus(null)}
              onClick={() => focus.onPin(hovered === key ? null : key)}
            >
              <title>{describePoint(key, cell, isWall)}</title>
            </rect>
          );
        })}

      {pathLine ? <polyline className="trail" points={pathLine} /> : null}

      {knowledge.start ? (
        <circle className="marker-start" cx={centre(knowledge.start)[0]} cy={centre(knowledge.start)[1]} r={PITCH * 0.3} />
      ) : null}

      {knowledge.exit ? (
        <>
          <rect className="cell-exit" x={px(parseCellKey(knowledge.exit)[0]) + GAP / 2} y={py(parseCellKey(knowledge.exit)[1]) + GAP / 2}
                width={PITCH - GAP} height={PITCH - GAP} rx={3} opacity={0.35} />
          <circle className="marker-exit" cx={centre(knowledge.exit)[0]} cy={centre(knowledge.exit)[1]} r={PITCH * 0.34} />
        </>
      ) : null}

      {knowledge.current ? (
        <g>
          <circle className="agent-halo" cx={centre(knowledge.current)[0]} cy={centre(knowledge.current)[1]} r={PITCH * 0.42} />
          <circle className="agent" cx={centre(knowledge.current)[0]} cy={centre(knowledge.current)[1]} r={Math.max(3, PITCH * 0.19)} />
        </g>
      ) : null}

      {hovered ? (
        <rect className="node-selected" x={px(parseCellKey(hovered)[0]) + GAP / 2} y={py(parseCellKey(hovered)[1]) + GAP / 2}
              width={PITCH - GAP} height={PITCH - GAP} rx={3} />
      ) : null}

      <rect className="map-frame" x={0.5} y={0.5} width={w - 1} height={h - 1} />
      </g>
    </svg>
  );
}

/** One cell, in words — the map's own answer to "what do you know about here?". */
function describePoint(key: string, cell: KnownCell | undefined, isWall: boolean): string {
  if (cell) {
    const ways = [...cell.open].sort().join(", ") || "nothing";
    const bits = [`cell ${key}`, `open: ${ways}`];
    if (cell.visits > 0) bits.push(`walked ${cell.visits}×`);
    if (cell.exit) bits.push("THIS IS THE EXIT");
    return bits.join(" · ");
  }
  if (isWall) return `${key} — solid`;
  return `${key} — not seen`;
}

function CellInspector({ cell, knowledge }: { cell: string | null; knowledge: MazeKnowledge }) {
  if (!cell) {
    return (
      <>
        <h4>Cell</h4>
        <p className="inspector-none">Hover a square to read it; click to keep it here.</p>
      </>
    );
  }
  const known = knowledge.cells.get(cell);
  const wall = knowledge.walls.has(cell);
  return (
    <>
      <h4>Cell {cell}</h4>
      {known ? (
        <ul>
          <li>open: {[...known.open].sort().join(", ") || "nothing — sealed"}</li>
          <li>walked {known.visits} time{known.visits === 1 ? "" : "s"}{known.entered ? "" : " (looked at, never entered)"}</li>
          <li>first seen at event {known.seenAt}</li>
        </ul>
      ) : wall ? (
        <p className="mono">solid — the world refused a step into it.</p>
      ) : (
        <p className="mono">never observed. The map is dark here because the run has not looked, not because it is empty.</p>
      )}
    </>
  );
}
