/*
 * The command bar: the world, the goal, and the button.
 *
 * This is the only part of the window that is always in the same place, and it stays small on purpose. Its
 * second line is not decoration — it is the one place that says *why* the button is unavailable, because a
 * disabled button with no reason is the most common way a person loses five minutes.
 */

import { useEffect, useRef } from "react";
import { WorldInfo } from "../protocol";
import { Button } from "../ui/controls";

export function CommandBar({ worlds, world, onWorld, goal, onGoal, onRun, onStop, running, blocked, hint, configOpen }: {
  worlds: WorldInfo[];
  world: string;
  onWorld: (name: string) => void;
  goal: string;
  onGoal: (text: string) => void;
  onRun: () => void;
  onStop: () => void;
  running: boolean;
  blocked: string;
  hint: string;
  configOpen: boolean;
}) {
  const field = useRef<HTMLTextAreaElement>(null);
  const current = worlds.find((w) => w.name === world);

  // The goal is one line until it needs to be two: growing the box costs nothing and a clipped goal is a
  // goal you cannot check before committing to it.
  useEffect(() => {
    const el = field.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(96, el.scrollHeight)}px`;
  }, [goal]);

  return (
    <div className={`command ${configOpen ? "narrow" : ""}`}>
      {!configOpen ? (
        <div className="worldpick" role="group" aria-label="world to drive">
          {worlds.map((w) => (
            <button key={w.name} type="button" aria-pressed={w.name === world} onClick={() => onWorld(w.name)}
                    title={w.note}>
              {w.title}
            </button>
          ))}
        </div>
      ) : null}

      <label className="goalwrap">
        <span className="sr">Goal</span>
        <textarea
          ref={field}
          rows={1}
          value={goal}
          spellCheck={false}
          disabled={running}
          placeholder={current ? `what should the ${current.name} world find out or reach?` : "what should it find out?"}
          onChange={(e) => onGoal(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); onRun(); }
          }}
        />
      </label>

      <div className="goalmeta">
        <span className="pane-sub nowrap hintline" title={hint}>{hint}</span>
        {running
          ? <Button variant="danger" onClick={onStop}>Stop</Button>
          : <Button variant="primary" onClick={onRun} disabled={Boolean(blocked)} title={blocked || "start the run"}>Run</Button>}
        <span className="kbd">⌘↵</span>
      </div>
    </div>
  );
}
