/*
 * The one-line narration of a run, drawn where the waiting happens.
 *
 * It renders `narrate()`'s sentence and ticks the seconds since the last event beside it — the part
 * the window never had. The pulse is ice — live — and breathes only while the current stretch is
 * inside a model call.
 *
 * Two ends of a run's life used to be silent, and both read as the app being stuck rather than as
 * what they are: before the first event arrives (the socket is up, the engine has the goal, nothing
 * has happened YET — a few seconds that felt like a dead click), and after the run ends (the line
 * vanished the instant it settled, so anyone who looked after the fact never knew it was there).
 * The line now holds from Run to clear: "starting" before the first event, the last narration
 * dimmed once the run is over.
 */

import { useEffect, useState } from "react";
import { EngineEventFrame } from "../protocol";
import { narrate } from "../core/narrate";

export function Narrator({ events, live }: { events: EngineEventFrame[]; live: boolean }) {
  // The silence counter: resets to zero the moment an event lands, ticks up once a second while the
  // run streams. A finished run needs no ticker — its silence is not "waiting on the model", it is
  // simply over.
  const [quiet, setQuiet] = useState(0);
  const tailLen = events.length;
  useEffect(() => { setQuiet(0); }, [tailLen]);
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => setQuiet((q) => q + 1), 1000);
    return () => clearInterval(t);
  }, [live]);

  const base = narrate(events, 0);
  const starting = live && tailLen === 0;
  if (!base && !starting) return null;
  const text = base ? base.text : "starting — the engine has the goal";
  const narration = { thinking: base ? base.thinking : true, text, quietFor: quiet };

  return (
    <span className={`narrator ${narration.thinking && live ? "thinking" : ""} ${live ? "" : "done"}`}
          role="status" aria-live="polite">
      <i className="pulse" aria-hidden="true" />
      <span className="narrator-text">{narration.text}</span>
      {live && narration.quietFor >= 2 ? <span className="narrator-quiet">{narration.quietFor}s</span> : null}
    </span>
  );
}
