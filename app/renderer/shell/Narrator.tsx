/*
 * The one-line narration of a live run, drawn where the waiting happens.
 *
 * It renders `narrate()`'s sentence and ticks the seconds since the last event beside it — the part
 * the window never had. The pulse dot says "inside a model call" without a single word, and stops
 * the moment data is flowing again.
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
  if (!base) return null;
  const narration = { ...base, quietFor: quiet };

  return (
    <span className={`narrator ${narration.thinking ? "thinking" : ""}`} role="status" aria-live="polite">
      <i className="pulse" aria-hidden="true" />
      <span className="narrator-text">{narration.text}</span>
      {narration.quietFor >= 2 ? <span className="narrator-quiet">{narration.quietFor}s</span> : null}
    </span>
  );
}
