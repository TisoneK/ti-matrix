/*
 * The transport: a cursor into a run, and the controls that move it.
 *
 * The run is not a thing you watch and then lose — it is an artifact with a timeline. This hook owns the
 * one number that means "where in that timeline we are", plus whether we are following the live edge,
 * whether it is playing, and which decisions were marked.
 *
 * Everything else in the window derives from that number, which is why stepping, scrubbing, bookmarking
 * and comparing are all the same operation in different clothes.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export const SPEEDS = [0.5, 1, 2, 4] as const;
export type Speed = typeof SPEEDS[number];

/** Milliseconds a decision stays on screen at 1×. Fast enough to watch, slow enough to read. */
const BASE_MS = 900;

export interface Playback {
  /** The decision being shown. In live mode this is the newest one. */
  cursor: number;
  /** Null while following the live edge; a number once the viewer has taken the wheel. */
  pin: number | null;
  playing: boolean;
  speed: Speed;
  bookmarks: number[];
  at: (index: number) => void;
  step: (delta: number) => void;
  toStart: () => void;
  toEnd: () => void;
  toggle: () => void;
  setSpeed: (speed: Speed) => void;
  toggleBookmark: (index?: number) => void;
  seekBookmark: (direction: 1 | -1) => void;
  follow: () => void;
  /** Set when a different run becomes current, so bookmarks do not leak between runs. */
  reset: (bookmarks?: number[]) => void;
}

export function usePlayback(count: number): Playback {
  const [pin, setPin] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
  const [bookmarks, setBookmarks] = useState<number[]>([]);
  const last = Math.max(0, count - 1);
  const cursor = pin === null ? last : Math.max(0, Math.min(pin, last));

  // Playing walks the cursor one decision at a time. At the end it stops rather than looping: a replay
  // that loops forever is a screensaver, and this is a debugger.
  const cursorRef = useRef(cursor);
  cursorRef.current = cursor;
  useEffect(() => {
    if (!playing) return;
    if (count === 0) { setPlaying(false); return; }
    const timer = window.setTimeout(() => {
      const next = cursorRef.current + 1;
      if (next > last) { setPlaying(false); setPin(last); return; }
      setPin(next);
    }, BASE_MS / speed);
    return () => window.clearTimeout(timer);
  }, [playing, cursor, speed, last, count]);

  const at = useCallback((index: number) => {
    setPlaying(false);
    setPin(Math.max(0, Math.min(index, Math.max(0, count - 1))));
  }, [count]);

  const step = useCallback((delta: number) => {
    setPlaying(false);
    setPin(Math.max(0, Math.min(cursorRef.current + delta, Math.max(0, count - 1))));
  }, [count]);

  const toStart = useCallback(() => { setPlaying(false); setPin(0); }, []);
  const toEnd = useCallback(() => { setPlaying(false); setPin(null); }, []);
  const follow = useCallback(() => { setPlaying(false); setPin(null); }, []);

  const toggle = useCallback(() => {
    setPlaying((p) => {
      if (p) return false;
      // Pressing play at the end replays from the beginning — the whole point of keeping the run around.
      if (cursorRef.current >= Math.max(0, count - 1)) setPin(0);
      return true;
    });
  }, [count]);

  const toggleBookmark = useCallback((index?: number) => {
    const target = index ?? cursorRef.current;
    setBookmarks((marks) => (marks.includes(target) ? marks.filter((m) => m !== target) : [...marks, target].sort((a, b) => a - b)));
  }, []);

  const seekBookmark = useCallback((direction: 1 | -1) => {
    setPlaying(false);
    const here = cursorRef.current;
    const marks = direction === 1
      ? bookmarks.filter((m) => m > here)
      : bookmarks.filter((m) => m < here).reverse();
    if (marks.length === 0) return;
    setPin(marks[0]);
  }, [bookmarks]);

  const reset = useCallback((marks: number[] = []) => {
    setPin(null);
    setPlaying(false);
    setBookmarks(marks);
  }, []);

  return {
    cursor, pin, playing, speed, bookmarks,
    at, step, toStart, toEnd, toggle, setSpeed, toggleBookmark, seekBookmark, follow, reset,
  };
}
