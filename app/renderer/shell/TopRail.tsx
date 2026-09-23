/*
 * The rail, which is also the window's title bar.
 *
 * Everything a title bar carries is already here — the name, the state of the thing, the way to the other
 * surfaces — so the window owns no chrome above this strip: it *is* the chrome. That is why the rail
 * takes the drag region, why a double-click on its empty space maximizes the window the way every other
 * title bar does, and why the window buttons live at its right edge everywhere except macOS, where the OS
 * keeps its traffic lights and the rail only leaves room for them.
 *
 * Two rules make the drag region work, and both are easy to get wrong: the region must not swallow the
 * controls inside it (anything clickable is marked `no-drag` in the stylesheet), and the double-click
 * handler must ignore events that came from those controls.
 */

import { MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { Status } from "../protocol";
import { WindowChrome, WindowGlyph } from "../hooks/useWindowChrome";
import { Readouts, StatusLamp, Wordmark } from "../ui/atoms";
import { Tab } from "../ui/controls";
import { View } from "../core/nav";

export function TopRail({ view, onView, status, running, readouts, libraryCount, configOpen, onConfig, chrome, children }: {
  view: View;
  onView: (view: View) => void;
  status: Status;
  running: boolean;
  readouts: { label: string; value: ReactNode; tone?: "pos" | "neg" }[];
  libraryCount: number;
  configOpen: boolean;
  onConfig: () => void;
  chrome: WindowChrome;
  children?: ReactNode;
}) {
  // A double-click on the bar maximizes — but only on the bar, not on anything sitting in it.
  const onDoubleClick = (e: ReactMouseEvent<HTMLElement>): void => {
    if ((e.target as HTMLElement).closest("button, select, input, a, [role='tab']")) return;
    if (!chrome.nativeControls) chrome.toggleMaximize();
  };

  return (
    <header
      className={`rail ${chrome.nativeControls ? "mac" : ""} ${chrome.maximized ? "maximized" : ""}`}
      onDoubleClick={onDoubleClick}
    >
      <div className="brand">
        <h1><Wordmark /></h1>
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

        {/* macOS draws its own; everywhere else these are the only way to close the window. */}
        {chrome.available && !chrome.nativeControls ? (
          <div className="wincontrols">
            <button type="button" className="winbtn" onClick={chrome.minimize} aria-label="minimize the window" title="minimize">
              <WindowGlyph kind="minimize" />
            </button>
            <button type="button" className="winbtn" onClick={chrome.toggleMaximize}
                    aria-label={chrome.maximized ? "restore the window" : "maximize the window"}
                    title={chrome.maximized ? "restore" : "maximize"}>
              <WindowGlyph kind={chrome.maximized ? "restore" : "maximize"} />
            </button>
            <button type="button" className="winbtn danger" onClick={chrome.close} aria-label="close the window" title="close">
              <WindowGlyph kind="close" />
            </button>
          </div>
        ) : null}
      </div>
    </header>
  );
}
