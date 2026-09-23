/*
 * The maze, drawn: the walls the run has learned, the path it actually walked, and the exit when it finds it.
 *
 * A tile grid says "here are some cells". A maze drawing says what happened: you can see the corridor the
 * run came down, the dead end it backed out of (the walk visits a cell twice), and the moment the exit
 * lights up. Nothing is drawn that a probe did not report — a side is a wall only when the world listed
 * that cell's openings — and everything else stays fog.
 */

import { ReactNode } from "react";
import { Dir, MazeKnowledge, boundsOf, cellKey } from "../lib/maze";

const S = 34; // cell size in px

const SIDES: [Dir, [number, number], [number, number]][] = [
  // direction, start point (in cell-relative units), end point — the four sides of a cell
  ["north", [0, 0], [1, 0]],
  ["south", [0, 1], [1, 1]],
  ["west", [0, 0], [0, 1]],
  ["east", [1, 0], [1, 1]],
];

export function MazeMap({ knowledge }: { knowledge: MazeKnowledge }) {
  const bounds = boundsOf(knowledge);

  if (!bounds) {
    return (
      <p className="hint">
        Nothing seen yet — the map draws itself as probes walk the maze. A run is never shown the map; every
        wall here is one it walked into.
      </p>
    );
  }

  const cols = bounds.maxX - bounds.minX + 1;
  const rows = bounds.maxY - bounds.minY + 1;
  const px = (x: number) => (x - bounds.minX) * S;
  const py = (y: number) => (y - bounds.minY) * S;
  const centre = (key: string): [number, number] => {
    const [x, y] = key.split(",").map(Number);
    return [px(x) + S / 2, py(y) + S / 2];
  };

  const fog: ReactNode[] = [];
  const floors: ReactNode[] = [];
  const walls: ReactNode[] = [];

  for (let y = bounds.minY; y <= bounds.maxY; y++) {
    for (let x = bounds.minX; x <= bounds.maxX; x++) {
      const cell = knowledge.cells.get(cellKey(x, y));
      if (!cell) {
        fog.push(<rect key={`f${x},${y}`} className="fog" x={px(x) + 1} y={py(y) + 1}
                       width={S - 2} height={S - 2} rx={3} />);
        continue;
      }
      if (cell.wall) {
        walls.push(<rect key={`w${x},${y}`} className="wall" x={px(x) + 3} y={py(y) + 3}
                         width={S - 6} height={S - 6} rx={3} />);
        continue;
      }
      floors.push(<rect key={`c${x},${y}`} className="floor" x={px(x) + 2} y={py(y) + 2}
                        width={S - 4} height={S - 4} rx={4} />);
      if (cell.described) {
        for (const [dir, [ax, ay], [bx, by]] of SIDES) {
          if (cell.open.has(dir)) continue;
          walls.push(
            <line key={`${x},${y}-${dir}`} className="edge"
                  x1={px(x) + ax * S} y1={py(y) + ay * S} x2={px(x) + bx * S} y2={py(y) + by * S} />,
          );
        }
      }
    }
  }

  const walked = knowledge.steps;
  const start = knowledge.start ? centre(knowledge.start) : null;
  const exit = knowledge.exit ? centre(knowledge.exit) : null;
  const here = knowledge.current ? centre(knowledge.current) : null;
  const segment = ([a, b]: [string, string]) => {
    const [x1, y1] = centre(a);
    const [x2, y2] = centre(b);
    return { x1, y1, x2, y2 };
  };

  return (
    <div className="maze-wrap">
      <svg className="maze" width={cols * S} height={rows * S} role="img"
           aria-label={`the maze walked so far: ${knowledge.entered.length} cells entered, `
             + `${walked.length} corridors walked`
             + (knowledge.exit ? ", the exit has been found" : "")}>
        <g>{fog}</g>
        <g>{floors}</g>
        <g>{walls}</g>
        {/* the wide soft stroke sits under the bright one: a glow without a filter */}
        <g className="walk-glow">
          {walked.map((s, i) => <line key={i} {...segment(s)} />)}
        </g>
        <g className="walk">
          {walked.map((s, i) => <line key={i} {...segment(s)} />)}
        </g>
        {start ? <circle className="start" cx={start[0]} cy={start[1]} r={5} /> : null}
        {exit ? (
          <g className="exit-mark">
            <circle cx={exit[0]} cy={exit[1]} r={11} />
            <text x={exit[0]} y={exit[1] + 4} textAnchor="middle">E</text>
          </g>
        ) : null}
        {here ? <circle className="here" cx={here[0]} cy={here[1]} r={7} /> : null}
      </svg>

      <p className="legend">
        <span><i className="sw-walk" />a corridor it walked</span>
        <span><i className="sw-here" />where the run stands</span>
        <span><i className="sw-exit" />exit</span>
        <span><i className="sw-wall" />a wall it found</span>
        <span><i className="sw-fog" />unseen</span>
      </p>
    </div>
  );
}
