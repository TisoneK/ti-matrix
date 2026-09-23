/*
 * The maze world: the map as far as the run has walked it. No answer key — the fog clears at the speed of
 * the search, and every tile here is something a probe actually reported.
 */

import { useMemo } from "react";
import { EngineEventFrame } from "../protocol";
import { applyProbe, emptyKnowledge, MazeKnowledge } from "../lib/maze";
import { Panel } from "../ui/Panel";
import { MazeMap } from "./MazeMap";

export function readMaze(events: EngineEventFrame[]): MazeKnowledge {
  const k = emptyKnowledge();
  for (const e of events) {
    if (e.kind !== "probe") continue;
    applyProbe(k, String(e["move"] ?? ""), Boolean(e["ok"]), String(e["excerpt"] ?? ""));
  }
  return k;
}

export function MazeView({ events }: { events: EngineEventFrame[] }) {
  const knowledge = useMemo(() => readMaze(events), [events]);
  const walked = [...knowledge.cells.values()].filter((c) => !c.wall).length;

  return (
    <Panel
      title="the maze, as far as the run has walked"
      meta={knowledge.grid
        ? `${knowledge.grid.width}×${knowledge.grid.height} · ${knowledge.grid.floors} cells in the maze`
        : walked > 0 ? `${walked} cells walked` : undefined}
    >
      <MazeMap knowledge={knowledge} />
    </Panel>
  );
}
