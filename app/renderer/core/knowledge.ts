/*
 * What a run believes about the world, read back out of the observations it was given.
 *
 * A run is never shown the map — `ti_matrix/adapters/maze.py` decides that — so the only source is what
 * the probes actually said. This file folds those sentences into knowledge, and invents nothing:
 *
 *     cell 1,1 — open: south, east · THIS IS THE EXIT        (a cell the run stood in)
 *     from 1,1 east: cell 2,1 — open: west, south             (a step the world confirmed)
 *     a wall blocks north from 1,1                            (a step the world refused)
 *     3,1 has not been entered — a run learns a cell by…      (a neighbour that exists, unwalked)
 *     a 11x9 grid holding 41 cells; a run enters at 1,1       (the world's own dimensions)
 *
 * Nothing is drawn until something was observed, which is the point: the map is a record of belief, so an
 * unexplored corridor stays dark until the run's own eyes reach it.
 *
 * Maze coordinates are the drawing's own coordinates — `cell 1,1` is the point (1,1) in the world's textual
 * map, walls included — so a cell's openings land directly on the points between cells, and the whole thing
 * renders as a grid without any rescaling or double-width bookkeeping.
 */

import { EngineEventFrame } from "./types";
import { Probe, probesOf } from "./worlds/probe";

export type Dir = "north" | "south" | "east" | "west";

const DELTA: Record<Dir, readonly [number, number]> = {
  north: [0, -1], south: [0, 1], east: [1, 0], west: [-1, 0],
};
const OPPOSITE: Record<Dir, Dir> = { north: "south", south: "north", east: "west", west: "east" };
const DIRECTIONS: Dir[] = ["north", "east", "south", "west"];

const isDir = (v: string): v is Dir => v === "north" || v === "south" || v === "east" || v === "west";

export interface KnownCell {
  x: number;
  y: number;
  /** The world listed this cell's openings — only then is an absent direction known to be a wall. */
  described: boolean;
  open: Set<Dir>;
  exit?: boolean;
  start?: boolean;
  /** The run stood here. */
  entered?: boolean;
  /** How many times the run stepped onto it. */
  visits: number;
  /** The first event seq that revealed anything about this cell. */
  seenAt: number;
}

export interface MazeKnowledge {
  cells: Map<string, KnownCell>;
  /** Points known to be solid, in the drawing's own coordinates (walls and pillars). */
  walls: Set<string>;
  /** Points known to be walkable — cells and the corridors between them. */
  floor: Set<string>;
  /** Corridors something said were passable: a step that landed, or a cell that listed the way out. */
  openCorridors: Set<string>;
  grid: { width: number; height: number; floors: number } | null;
  start: string | null;
  exit: string | null;
  /** Where the run stands now — null for a run that never stepped anywhere. */
  current: string | null;
  /** Cells the run has entered, in the order it first entered them. */
  entered: string[];
  /** Corridors actually walked. A fan probes several at once, so these are edges, not one long trail. */
  steps: [string, string][];
  /** The path the live state stands on — the last `trail` the engine reported, as cells. */
  livePath: string[];
  /** Cells it went into and is no longer standing on: the ghost trail. Brightest thrash first. */
  abandoned: string[];
  /** How much of the world is known, 0..1 — null until the grid's own size was read. */
  coverage: number | null;
}

export const cellKey = (x: number, y: number): string => `${x},${y}`;

export const parseCellKey = (key: string): [number, number] => {
  const [x, y] = key.split(",");
  return [Number(x), Number(y)];
};

export const emptyKnowledge = (): MazeKnowledge => ({
  cells: new Map(),
  walls: new Set(),
  floor: new Set(),
  openCorridors: new Set(),
  grid: null,
  start: null,
  exit: null,
  current: null,
  entered: [],
  steps: [],
  livePath: [],
  abandoned: [],
  coverage: null,
});

const ensure = (k: MazeKnowledge, x: number, y: number, seq: number): KnownCell => {
  const key = cellKey(x, y);
  let cell = k.cells.get(key);
  if (!cell) {
    cell = { x, y, described: false, open: new Set<Dir>(), visits: 0, seenAt: seq };
    k.cells.set(key, cell);
  }
  k.floor.add(key);
  k.walls.delete(key);
  return cell;
};

/** `open: south, east` / `open: nothing — this cell is sealed` — only the direction words count. */
const setOpen = (k: MazeKnowledge, cell: KnownCell, listed: string): void => {
  cell.described = true;
  for (const word of listed.split(",").map((w) => w.trim())) {
    if (!isDir(word)) continue;
    cell.open.add(word);
    const [dx, dy] = DELTA[word];
    const corridor = cellKey(cell.x + dx, cell.y + dy);
    k.floor.add(corridor);
    k.openCorridors.add(corridor);
    k.walls.delete(corridor);
  }
};

const toolOf = (move: string): string => (/^\s*(\w+)\s*\(/.exec(move)?.[1] ?? "").toLowerCase();

const DESCRIBED = /cell (\d+),(\d+) — open: ([a-z, ]*)/g;
const STEPPED = /from (\d+),(\d+) ([a-z]+):/;
const WALL_BLOCKS = /a wall blocks ([a-z]+) from (\d+),(\d+)/;
const NOT_ENTERED = /(\d+),(\d+) has not been entered/;
const NOT_A_CELL = /not a cell of this maze: '([^']*)'/;
const ENTERS_AT = /a run enters at (\d+),(\d+)/;
const GRID_SIZE = /a (\d+)x(\d+) grid holding (\d+) cells/;

/**
 * Mark a point solid. Two strengths, because two different things are being said: a wall the world
 * reported when a step was refused is a fact, while "the cell listed its openings and this was not one of
 * them" is an inference — and an inference never overrides a corridor something else established. The
 * world is allowed to contradict itself (an engine may be driven against a hand-written maze that does),
 * so the precedence has to be stated rather than left to the order events arrive in.
 */
const markWall = (k: MazeKnowledge, x: number, y: number, strength: "observed" | "inferred"): void => {
  const key = cellKey(x, y);
  // A cell the run has described is a cell, whatever an earlier refusal left behind.
  if (k.cells.get(key)?.described) return;
  if (strength === "inferred" && k.openCorridors.has(key)) return;
  k.walls.add(key);
  k.floor.delete(key);
  k.openCorridors.delete(key);
};

/** One `probe`, folded in. Events arrive in the order they happened, and so do their consequences. */
export function applyProbe(k: MazeKnowledge, probe: Probe): void {
  const { move, ok, excerpt, seq } = probe;
  const tool = toolOf(move);
  const described = [...excerpt.matchAll(DESCRIBED)];
  const stepped = STEPPED.exec(excerpt);

  if (ok) {
    if (tool === "grid") {
      const m = GRID_SIZE.exec(excerpt);
      if (m) k.grid = { width: Number(m[1]), height: Number(m[2]), floors: Number(m[3]) };
      const at = ENTERS_AT.exec(excerpt);
      if (at) {
        const cell = ensure(k, Number(at[1]), Number(at[2]), seq);
        cell.start = true;
        k.start = cellKey(cell.x, cell.y);
      }
      revisit(k);
      return;
    }

    // A step names where it came from before it says where it landed.
    if (stepped && isDir(stepped[3])) {
      const from = ensure(k, Number(stepped[1]), Number(stepped[2]), seq);
      from.open.add(stepped[3]);
      const [dx, dy] = DELTA[stepped[3]];
      const corridor = cellKey(from.x + dx, from.y + dy);
      k.floor.add(corridor);
      k.openCorridors.add(corridor);
    }

    const last = described[described.length - 1];
    if (!last) {
      revisit(k);
      return;
    }
    const cell = ensure(k, Number(last[1]), Number(last[2]), seq);
    setOpen(k, cell, last[3]);
    if (tool === "entry") {
      cell.start = true;
      k.start = cellKey(cell.x, cell.y);
    }
    if (/THIS IS THE EXIT/.test(excerpt)) {
      cell.exit = true;
      k.exit = cellKey(cell.x, cell.y);
    }
    // A described cell with openings: everything it did not list is solid. This is what makes the map fill
    // in as a maze rather than as a drift of unconnected rooms.
    for (const dir of DIRECTIONS) {
      if (cell.open.has(dir)) continue;
      const [dx, dy] = DELTA[dir];
      markWall(k, cell.x + dx, cell.y + dy, "inferred");
    }

    if (stepped && isDir(stepped[3])) {
      // The far side opens back the way it was entered — the world said so by letting the step happen.
      cell.open.add(OPPOSITE[stepped[3]]);
      cell.entered = true;
      cell.visits += 1;
      k.current = cellKey(cell.x, cell.y);
      const landed = k.current;
      if (!k.entered.includes(landed)) k.entered.push(landed);
      const left = cellKey(Number(stepped[1]), Number(stepped[2]));
      if (left !== landed && !k.steps.some(([a, b]) => (a === left && b === landed) || (a === landed && b === left))) {
        k.steps.push([left, landed]);
      }
    }
    revisit(k);
    return;
  }

  // A failed probe is a fact too, and each failure names the same thing a different way.
  const blocked = WALL_BLOCKS.exec(excerpt);
  if (blocked && isDir(blocked[1])) {
    const [dx, dy] = DELTA[blocked[1]];
    markWall(k, Number(blocked[2]) + dx, Number(blocked[3]) + dy, "observed");
    revisit(k);
    return;
  }
  const unentered = NOT_ENTERED.exec(excerpt);
  if (unentered) {
    // It exists and it is open; the run simply has not walked it. Knowing a cell is there is not knowing
    // the cell — so it stays floor with nothing said about its openings.
    ensure(k, Number(unentered[1]), Number(unentered[2]), seq);
    revisit(k);
    return;
  }
  const refused = NOT_A_CELL.exec(excerpt);
  if (refused) {
    const nums = /^(\d+),(\d+)$/.exec(refused[1].trim().replace(/[<>[\]]/g, ""));
    if (nums) markWall(k, Number(nums[1]), Number(nums[2]), "observed");
  }
  revisit(k);
}

/**
 * The path the live state stands on, from the engine's own `trail`.
 *
 * A trail entry is an action label (`step(cell=1,1, direction=east)`), and the trail is the sequence of
 * applied actions — so the cells it visited are recoverable exactly, with no guessing about which way it
 * went. Actions that read rather than walk are skipped: they moved the run's knowledge, not its feet.
 */
export function applyTrail(k: MazeKnowledge, trail: string[]): void {
  const path: string[] = [];
  let at: string | null = k.start;
  for (const label of trail) {
    if (toolOf(label) !== "step") continue;
    const args = /\((.*)\)\s*$/.exec(label)?.[1] ?? "";
    const cell = /cell=([^,)]+),([^,)]+)/.exec(args);
    const dir = /direction=([a-z]+)/.exec(args)?.[1] ?? "";
    if (!cell || !isDir(dir)) continue;
    const from = cellKey(Number(cell[1]), Number(cell[2]));
    if (path.length === 0) {
      at = from;
      path.push(from);
    } else if (from !== at) {
      // It walked out of a cell it was not recorded as standing in: follow the world, and show the gap by
      // putting both points on the path rather than gluing over it.
      path.push(from);
    }
    const [dx, dy] = DELTA[dir];
    const [fx, fy] = parseCellKey(from);
    at = cellKey(fx + dx, fy + dy);
    path.push(at);
  }
  k.livePath = path;
  if (at) k.current = at;
  revisit(k);
}

/** Derived summaries, recomputed on every fold so no caller has to remember to ask for them. */
function revisit(k: MazeKnowledge): void {
  const live = new Set(k.livePath);
  k.abandoned = k.entered
    .filter((c) => !live.has(c))
    .sort((a, b) => (k.cells.get(b)?.visits ?? 0) - (k.cells.get(a)?.visits ?? 0));
  k.coverage = k.grid && k.grid.floors > 0 ? k.cells.size / k.grid.floors : null;
}

/** Fold a run's prefix into what it believed at that moment — the whole basis of the scrubber. */
export function readKnowledge(events: EngineEventFrame[], upto = events.length): MazeKnowledge {
  const k = emptyKnowledge();
  const uptoClamped = Math.max(0, Math.min(upto, events.length));
  for (const probe of probesOf(events.slice(0, uptoClamped))) applyProbe(k, probe);
  for (let i = uptoClamped - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.kind === "state" && Array.isArray(e["trail"])) {
      applyTrail(k, (e["trail"] as unknown[]).map(String));
      break;
    }
  }
  return k;
}

export interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/**
 * The box the map should draw: the world's own dimensions once it was read, otherwise only what has been
 * seen, always with a ring of margin so the unknown has an edge to be dark at.
 */
export function boundsOf(k: MazeKnowledge): Bounds | null {
  if (k.grid) return { minX: -1, maxX: k.grid.width, minY: -1, maxY: k.grid.height };
  if (k.floor.size === 0 && k.walls.size === 0) return null;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const key of [...k.floor, ...k.walls]) {
    const [x, y] = parseCellKey(key);
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  return { minX: minX - 1, maxX: maxX + 1, minY: minY - 1, maxY: maxY + 1 };
}

/** Cells the run walked more than once — the shortest possible statement of "it went in circles". */
export function revisitedCells(k: MazeKnowledge): KnownCell[] {
  return [...k.cells.values()].filter((c) => c.visits > 1).sort((a, b) => b.visits - a.visits);
}

export interface MazeStats {
  entered: number;
  known: number;
  revisits: number;
  abandoned: number;
  coverage: number | null;
  exitSeen: boolean;
}

export function statsOf(k: MazeKnowledge): MazeStats {
  return {
    entered: k.entered.length,
    known: k.cells.size,
    revisits: revisitedCells(k).length,
    abandoned: k.abandoned.length,
    coverage: k.coverage,
    exitSeen: k.exit !== null,
  };
}
