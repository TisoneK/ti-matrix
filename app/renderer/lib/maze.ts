/*
 * What a run knows about the maze, read back out of the observations it was given.
 *
 * A run is never shown the map (see `ti_matrix/adapters/maze.py`), so the map here is exactly what the
 * probes reported and nothing more: a cell appears only once a probe stood in it or a wall blocked a step
 * into it. The world's own sentences are the source — `cell 1,1 — open: south, east · THIS IS THE EXIT`,
 * `from 1,1 east: cell 2,1 — open: west`, `a wall blocks north from 1,1` — so this file parses the text
 * the engine actually received rather than any private shape.
 */

export type Dir = "north" | "south" | "east" | "west";

const DELTA: Record<Dir, [number, number]> = { north: [0, -1], south: [0, 1], east: [1, 0], west: [-1, 0] };
const OPPOSITE: Record<Dir, Dir> = { north: "south", south: "north", east: "west", west: "east" };

const isDir = (v: string): v is Dir => v === "north" || v === "south" || v === "east" || v === "west";

export interface KnownCell {
  x: number;
  y: number;
  wall: boolean;
  open: Set<Dir>;
  /** True once the world has listed this cell's openings — only then is a missing side known to be a wall. */
  described?: boolean;
  exit?: boolean;
  start?: boolean;
  current?: boolean;
}

export interface MazeKnowledge {
  cells: Map<string, KnownCell>;
  exit: string | null;
  start: string | null;
  current: string | null;
  grid: { width: number; height: number; floors: number } | null;
  /** Cells the run has entered, in the order it first entered them. */
  entered: string[];
  /** Corridors it actually walked: [from, to] for every step the world confirmed. A fan probes several at
   *  once, so these are edges, not one continuous trail — drawing them as a single path would lie. */
  steps: [string, string][];
}

export const cellKey = (x: number, y: number): string => `${x},${y}`;

export const emptyKnowledge = (): MazeKnowledge => ({
  cells: new Map(),
  exit: null,
  start: null,
  current: null,
  grid: null,
  entered: [],
  steps: [],
});

const ensure = (k: MazeKnowledge, x: number, y: number): KnownCell => {
  const key = cellKey(x, y);
  let cell = k.cells.get(key);
  if (!cell) {
    cell = { x, y, wall: false, open: new Set<Dir>() };
    k.cells.set(key, cell);
  }
  return cell;
};

// "open: south, east" / "open: nothing — this cell is sealed" — only the direction words count.
const setOpen = (cell: KnownCell, listed: string): void => {
  cell.described = true;
  for (const word of listed.split(",").map((w) => w.trim())) {
    if (isDir(word)) cell.open.add(word);
  }
};

// The move arrives as the engine labels it: `step(cell=1,1, direction=east)`, `look(cell=<1,1>)`, `entry()`.
const toolOf = (move: string): string => (/^\s*(\w+)\s*\(/.exec(move)?.[1] ?? "").toLowerCase();

const DESCRIBED = /cell (\d+),(\d+) — open: ([a-z, ]*)/g;
const STEPPED = /from (\d+),(\d+) (\w+):/;
const WALL_BLOCKS = /a wall blocks (\w+) from (\d+),(\d+)/;
const NOT_ENTERED = /(\d+),(\d+) has not been entered/;
const NOT_A_CELL = /not a cell of this maze: '([^']*)'/;
const ENTERS_AT = /a run enters at (\d+),(\d+)/;
const GRID_SIZE = /a (\d+)x(\d+) grid holding (\d+) cells/;

/** One `probe` event folded into what is known. Order matters: events arrive in the order they happened. */
export function applyProbe(k: MazeKnowledge, move: string, ok: boolean, excerpt: string): void {
  const tool = toolOf(move);
  const described = [...excerpt.matchAll(DESCRIBED)];
  const stepped = STEPPED.exec(excerpt);

  if (ok) {
    if (tool === "grid") {
      const m = GRID_SIZE.exec(excerpt);
      if (m) k.grid = { width: Number(m[1]), height: Number(m[2]), floors: Number(m[3]) };
      const at = ENTERS_AT.exec(excerpt);
      if (at) ensure(k, Number(at[1]), Number(at[2])).start = true;
      return;
    }

    // A step says where it came from before it says where it landed.
    if (stepped && isDir(stepped[3])) ensure(k, Number(stepped[1]), Number(stepped[2])).open.add(stepped[3]);

    const last = described[described.length - 1];
    if (!last) return;
    const cell = ensure(k, Number(last[1]), Number(last[2]));
    setOpen(cell, last[3]);
    if (tool === "entry") {
      cell.start = true;
      k.start = cellKey(cell.x, cell.y);
    }
    if (/THIS IS THE EXIT/.test(excerpt)) {
      cell.exit = true;
      k.exit = cellKey(cell.x, cell.y);
    }
    if (stepped && isDir(stepped[3])) {
      cell.open.add(OPPOSITE[stepped[3]]); // the far side opens back the way it was entered
      for (const other of k.cells.values()) delete other.current;
      cell.current = true;
      k.current = cellKey(cell.x, cell.y);
      const landed = cellKey(cell.x, cell.y);
      if (!k.entered.includes(landed)) k.entered.push(landed);
      const left = cellKey(Number(stepped[1]), Number(stepped[2]));
      if (left !== landed && !k.steps.some(([a, b]) => (a === left && b === landed) || (a === landed && b === left))) {
        k.steps.push([left, landed]);
      }
    }
    return;
  }

  // A failed probe is a fact too, and each failure names the same thing a different way.
  const blocked = WALL_BLOCKS.exec(excerpt);
  if (blocked && isDir(blocked[1])) {
    const from = ensure(k, Number(blocked[2]), Number(blocked[3]));
    const [dx, dy] = DELTA[blocked[1]];
    ensure(k, from.x + dx, from.y + dy).wall = true;
    return;
  }
  const unentered = NOT_ENTERED.exec(excerpt);
  if (unentered) {
    ensure(k, Number(unentered[1]), Number(unentered[2])); // it exists and is open — it just has not been walked
    return;
  }
  const refused = NOT_A_CELL.exec(excerpt);
  if (refused) {
    const nums = /^\(?(\d+),(\d+)\)?$/.exec(refused[1].trim().replace(/[<>[\]]/g, ""));
    if (nums) ensure(k, Number(nums[1]), Number(nums[2])).wall = true;
  }
}

export interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/** The box the known cells sit in, one cell of margin so the fog has an edge. */
export function boundsOf(k: MazeKnowledge): Bounds | null {
  if (k.cells.size === 0) return null;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const c of k.cells.values()) {
    minX = Math.min(minX, c.x); maxX = Math.max(maxX, c.x);
    minY = Math.min(minY, c.y); maxY = Math.max(maxY, c.y);
  }
  return { minX: minX - 1, maxX: maxX + 1, minY: minY - 1, maxY: maxY + 1 };
}
