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

export function CommandBar({ worlds, world, onWorld, goal, onGoal, onRun, onStop, running, blocked, hint, configOpen, onRetry, retryable }: {
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
  /** Offered instead of Run when the socket is the thing that is wrong — see `retryable`. */
  onRetry: () => void;
  /** True when the engine is unreachable and trying again is the move that could fix it. */
  retryable: boolean;
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
        {/* One slot, two jobs, and only one of them is ever urgent.
            When the button cannot be pressed, this is the sentence that says why — and it is a sentence,
            in amber, at reading size, because the old home for it was a `title` attribute and Chromium
            does not fire hover on a disabled control: the reason was on screen nowhere. When there is
            nothing to warn about, the slot carries the world's own note; it is no longer clipped to a
            fragment mid-word, because the world picker and the setup sheet both say it in full and a
            truncated half-sentence parked next to Run reads as a rendering fault. */}
        {blocked ? (
          <span className="goal-blocked" role="status">{blocked}</span>
        ) : hint ? (
          <span className="goal-note nowrap" title={hint}>{hint}</span>
        ) : null}
        {running
          ? <Button variant="danger" onClick={onStop}>Stop</Button>
          : retryable
            // A disabled Run button next to "the engine is not running" is a dead end: the one thing
            // that could fix it is not on screen. When the engine is what is wrong, the button becomes
            // the fix rather than staying a greyed-out reminder of it.
            ? <Button variant="primary" onClick={onRetry} title="start the engine again and reconnect">Reconnect</Button>
            : <Button variant="primary" onClick={onRun} disabled={Boolean(blocked)} title={blocked || "start the run"}>Run</Button>}
        <span className="kbd">⌘↵</span>
      </div>
    </div>
  );
}
