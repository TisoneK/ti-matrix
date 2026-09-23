/*
 * The rail: who is running, what state the window is in, and the way to the secondary surfaces.
 *
 * Run / Library / Compare are tabs rather than pages, because they are three views of the same thing — a
 * run — and switching between them must not feel like leaving. The config drawer is the fourth control
 * and deliberately the quietest: the endpoint, the model and the key are real, but they are the ship's
 * instruments, not the ship.
 */

import { ReactNode } from "react";
import { Status } from "../protocol";
import { Readouts, StatusLamp } from "../ui/atoms";
import { Tab } from "../ui/controls";

export type View = "run" | "library" | "compare";

export function TopRail({ view, onView, status, running, readouts, libraryCount, configOpen, onConfig, children }: {
  view: View;
  onView: (view: View) => void;
  status: Status;
  running: boolean;
  readouts: { label: string; value: ReactNode; tone?: "pos" | "neg" }[];
  libraryCount: number;
  configOpen: boolean;
  onConfig: () => void;
  children?: ReactNode;
}) {
  return (
    <header className="rail">
      <div className="brand">
        <h1>Ti Matrix</h1>
        <span className="ver">TM1</span>
      </div>

      <StatusLamp status={status} detail={running ? "running" : undefined} />

      <Readouts items={readouts} />

      <div className="rail-group">
        {children}
        <nav className="tabs" role="tablist" aria-label="what to look at">
          <Tab label="Run" selected={view === "run"} onClick={() => onView("run")} />
          <Tab label="Library" selected={view === "library"} onClick={() => onView("library")} count={libraryCount} />
          <Tab label="Compare" selected={view === "compare"} onClick={() => onView("compare")} />
        </nav>
        <button type="button" className="tab" aria-expanded={configOpen} onClick={onConfig}
                title="the world, the model and the key">
          config {configOpen ? "▴" : "▾"}
        </button>
      </div>
    </header>
  );
}
