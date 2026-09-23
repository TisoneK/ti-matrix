/*
 * The transport: the bar that turns a run into an artifact you can drive.
 *
 * A run used to be something you watched and then lost. This bar is the whole difference: a cursor over
 * the run's decisions, with play, step, speed and bookmarks — so the thing you missed at minute three is
 * still there at minute thirty, and so a run you finished last week can be walked through again.
 *
 * The marks on the scrubber are the run's own flags. That is not decoration: the places worth stopping are
 * exactly the places the run was surprised or corrected itself, and putting them on the timeline means you
 * can find them without reading forty rows.
 */

import { KeyboardEvent as ReactKeyboardEvent } from "react";
import { Decision } from "../core/types";
import { Playback, SPEEDS, Speed } from "../hooks/usePlayback";
import { IconButton } from "../ui/controls";

export function Transport({ playback, decisions, durationMs, label, live }: {
  playback: Playback;
  decisions: Decision[];
  durationMs: number;
  label: string;
  /** True while the sidecar is still streaming this run. */
  live: boolean;
}) {
  const count = decisions.length;
  const at = decisions[playback.cursor];
  const followingLive = playback.pin === null;
  const marks = decisions.filter((d) => d.index !== playback.cursor && d.flags.some((f) => f !== "confirmed"));

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
    switch (e.key) {
      case " ": e.preventDefault(); playback.toggle(); break;
      case "ArrowLeft": e.preventDefault(); playback.step(-1); break;
      case "ArrowRight": e.preventDefault(); playback.step(1); break;
      case "Home": e.preventDefault(); playback.toStart(); break;
      case "End": e.preventDefault(); playback.toEnd(); break;
      case "b": case "B": playback.toggleBookmark(); break;
      case "[": playback.seekBookmark(-1); break;
      case "]": playback.seekBookmark(1); break;
      default: break;
    }
  };

  return (
    <div className="transport" onKeyDown={onKeyDown} role="group" aria-label="playback">
      <div className="transport-controls">
        <IconButton label="first step" onClick={playback.toStart} disabled={count === 0}>⏮</IconButton>
        <IconButton label="previous step" onClick={() => playback.step(-1)} disabled={count === 0}>◀</IconButton>
        <IconButton label={playback.playing ? "pause" : "play through the run"} onClick={playback.toggle} disabled={count === 0}>
          {playback.playing ? "❙❙" : "▶"}
        </IconButton>
        <IconButton label="next step" onClick={() => playback.step(1)} disabled={count === 0}>▶▶</IconButton>
        <IconButton label="last step" onClick={playback.toEnd} disabled={count === 0}>⏭</IconButton>
        <IconButton label={playback.bookmarks.includes(playback.cursor) ? "remove bookmark" : "bookmark this step"}
                    onClick={() => playback.toggleBookmark()} disabled={count === 0}>☆</IconButton>

        <label className="sr" htmlFor="speed">speed</label>
        <select id="speed" className="pick" value={playback.speed}
                onChange={(e) => playback.setSpeed(Number(e.target.value) as Speed)}
                title="how fast the play button walks the run">
          {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
        </select>
      </div>

      <div className={`scrubwrap ${followingLive ? "" : "scrubbed"}`}>
        <input
          className="scrub"
          type="range"
          min={0}
          max={Math.max(0, count - 1)}
          step={1}
          value={playback.cursor}
          disabled={count === 0}
          aria-label="scrub through the run's decisions"
          aria-valuetext={count === 0 ? "no decisions yet" : `step ${playback.cursor + 1} of ${count}`}
          onChange={(e) => playback.at(Number(e.target.value))}
        />
        <div className="scrub-marks" aria-hidden="true">
          {count > 1 ? marks.map((d) => (
            <button
              key={d.index}
              type="button"
              className={`scrub-mark ${d.flags[0]}`}
              style={{ left: `${(d.index / (count - 1)) * 100}%` }}
              title={`step ${d.index + 1}: ${d.headline}`}
              tabIndex={-1}
              onClick={() => playback.at(d.index)}
            />
          )) : null}
          {count > 1 ? playback.bookmarks.map((i) => (
            <button
              key={`bm-${i}`}
              type="button"
              className="scrub-mark bookmark"
              style={{ left: `${(i / (count - 1)) * 100}%` }}
              title={`bookmark: step ${i + 1}`}
              tabIndex={-1}
              onClick={() => playback.at(i)}
            />
          )) : null}
        </div>
      </div>

      <div className="transport-time">
        {!followingLive ? (
          <button type="button" className="pick" onClick={playback.follow}
                  title={live ? "stop scrubbing and follow the run again" : "back to the end of the run"}>
            {live ? "jump to live" : "jump to end"}
          </button>
        ) : null}
        <span className={followingLive && live ? "live-tag" : "live-tag"}>
          {followingLive ? (live ? "following the run" : "at the end") : `rewound to ${playback.cursor + 1}`}
        </span>
        <span className="nowrap" title={label}>{label}</span>
        <span>step {count === 0 ? 0 : playback.cursor + 1}/{count}</span>
        <span>{formatDuration(durationMs, at?.tMs)}</span>
      </div>
    </div>
  );
}

const formatDuration = (totalMs: number, atMs?: number): string => {
  const ms = atMs ?? totalMs;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
};
