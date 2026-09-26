/*
 * The page the browser world is really driving — and, beside it, what the run actually saw of it.
 *
 * The two layers are the whole point, and they are not the same thing. The run's model reads text
 * (`page_text`, `links`, `find`); pixels never reach it. A person looking at the screenshot sees a page
 * that may hold a cookie banner the run never read, a price rendered in an image the run never saw, a
 * chart `page_text` returns nothing for. Showing the picture alone would quietly claim the agent saw
 * what the viewer is looking at — the exact unearned trust this app exists to prevent — so the reading
 * the run actually extracted sits right beside it, and the caption says the difference in one line.
 *
 * The frame is a fold over `(events, cursor)` like every other panel: each applied move captured one
 * JPEG beside the run, the event names it by seq, and scrubbing moves the picture. The bytes never
 * enter the artifact — the renderer asks for them by run id + frame name, and main serves them only
 * after validating both against the run's own directory.
 */

import { useEffect, useState } from "react";
import { EngineEventFrame } from "../protocol";
import { Decision } from "../core/types";
import { frameOf } from "../core/worlds/browser";

export function PageSurface({ runId, events, upto, at, pageUrl, getFrame }: {
  /** The run the frames belong to — null in a plain browser tab, where nothing was ever captured. */
  runId: string | null;
  events: EngineEventFrame[];
  /** The event index the shared cursor stands at — frames past it do not exist yet. */
  upto: number;
  /** The decision at the cursor: its evidence is the "what it read" layer. */
  at: Decision | null;
  /** Where the page was, as the run's own answers named it — null before the run said. */
  pageUrl: string | null;
  /** The one file channel a panel is allowed: ask by run id + frame name, never by path. */
  getFrame: (id: string, name: string) => Promise<string | null>;
}) {
  const seq = frameOf(events, upto);
  const [data, setData] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ok" | "none">("idle");

  useEffect(() => {
    let cancelled = false;
    if (seq === null || runId === null) {
      setData(null);
      setStatus("idle");
      return;
    }
    setStatus("loading");
    getFrame(runId, `${seq}.jpg`).then((b64) => {
      if (cancelled) return;
      setData(b64);
      setStatus(b64 ? "ok" : "none");
    }).catch(() => {
      if (!cancelled) { setData(null); setStatus("none"); }
    });
    return () => { cancelled = true; };
  }, [runId, seq, getFrame]);

  const anyFrame = events.some((e) => typeof e["frame"] === "string" && e["frame"]);
  const captureFailed = seq === null && events.some((e) => typeof e["frame_error"] === "string");
  // The cursor is past a framed move but the file answered nothing: the capture failed at the time
  // (it still recorded `frame_error`) or the file was removed since. Its own sentence — "scrub
  // forward" would be a lie about where the cursor is.
  const missingFile = seq !== null && status === "none";
  const beforeFirst = seq === null && anyFrame;

  return (
    <section className="card page-surface" aria-label="the page, and what the run read of it">
      <h4>The page</h4>
      {status === "ok" && data ? (
        <img className="page-shot" src={`data:image/jpeg;base64,${data}`}
             alt={`the page as a person sees it at step ${(at?.index ?? 0) + 1}`} />
      ) : (
        <p className="dim page-shot-none">
          {status === "loading"
            ? "fetching the frame…"
            : missingFile
              ? "this step's picture is missing — the capture failed at the time, or the file was removed since"
              : beforeFirst
                ? "no picture before the first applied move — scrub forward and it appears"
                : captureFailed
                  ? "the capture failed here (the tab was probably mid-navigation) — the readings below are still what the run saw"
                  : "no picture is attached to this run — it predates page capture, or every capture failed"}
        </p>
      )}
      <p className="dim page-note">
        {pageUrl ? <span className="mono nowrap">{pageUrl}</span> : "the page, as a person sees it"}
        {" — a copy of what was on screen, kept in this run's folder on this machine, sent nowhere. "}
        <b>The run itself reads text only, never this picture.</b>
      </p>

      <h4>What it read</h4>
      {at?.evidence ? (
        <p className="mono page-read">{at.evidence}</p>
      ) : (
        <p className="dim page-read-none">nothing read yet — the page's answer to the applied move appears here</p>
      )}
    </section>
  );
}
