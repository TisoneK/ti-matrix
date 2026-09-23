/*
 * The renderer's session with the sidecar: connect once, then let frames become state.
 *
 * The URL arrives from the main process (the token never crosses into the renderer), and every frame the
 * engine sends is one of five shapes — worlds, event, confirm-request, settled, error. This hook is the
 * only place that knows them; the components below are handed state and never a socket.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { EngineEventFrame, Sidecar, Status, TmApi, WorldInfo } from "../protocol";
import { ConfirmRequest } from "../components/ConfirmDialog";
import { Settled } from "../components/Outcome";

export interface Session {
  status: Status;
  worlds: WorldInfo[];
  events: EngineEventFrame[];
  settled: Settled | null;
  confirm: ConfirmRequest | null;
  run: (goal: string, world: string, config: Record<string, unknown>) => void;
  stop: () => void;
  answer: (granted: boolean) => void;
  pickDirectory: () => Promise<string | null>;
}

export function useSidecar(): Session {
  const [status, setStatus] = useState<Status>("connecting");
  const [worlds, setWorlds] = useState<WorldInfo[]>([]);
  const [events, setEvents] = useState<EngineEventFrame[]>([]);
  const [settled, setSettled] = useState<Settled | null>(null);
  const [confirm, setConfirm] = useState<ConfirmRequest | null>(null);
  const sidecar = useRef<Sidecar | null>(null);
  const tm = (window as unknown as { tm?: TmApi }).tm;

  useEffect(() => {
    if (!tm) {
      // Opened outside the shell — a browser tab has no preload, so there is nothing to talk through.
      setStatus("crashed");
      return;
    }
    let cancelled = false;
    // Ask rather than wait to be told: the window may load before the sidecar is up, or long after.
    tm.connection().then(({ url }) => {
      if (cancelled) return;
      const s = new Sidecar(url);
      sidecar.current = s;
      s.onStatus((next) => setStatus((prev) => (prev === "running" && next === "ready" ? prev : next)));
      s.onFrame((frame) => {
        if (frame.type === "worlds") {
          setWorlds(frame.worlds);
          setStatus((s) => (s === "running" ? s : "ready"));
        } else if (frame.type === "event") {
          setEvents((prev) => [...prev, frame as unknown as EngineEventFrame]);
        } else if (frame.type === "confirm-request") {
          setConfirm(frame as unknown as ConfirmRequest);
        } else if (frame.type === "settled") {
          setSettled(frame as unknown as Settled);
          setStatus("ready");
        } else if (frame.type === "error") {
          setSettled({ error: frame.message });
          setStatus("ready");
        }
      });
      s.connect();
    }).catch(() => { if (!cancelled) setStatus("crashed"); });
    tm.onSidecarExit(() => setStatus("crashed"));
    return () => { cancelled = true; };
  }, [tm]);

  const run = useCallback((goal: string, world: string, config: Record<string, unknown>) => {
    setEvents([]);
    setSettled(null);
    setConfirm(null);
    setStatus("running");
    sidecar.current?.goal(goal, world, config);
  }, []);

  const stop = useCallback(() => sidecar.current?.stop(), []);

  const answer = useCallback((granted: boolean) => {
    setConfirm((request) => {
      if (request) sidecar.current?.confirm(request.id, granted);
      return null;
    });
  }, []);

  const pickDirectory = useCallback(async (): Promise<string | null> => (tm ? tm.pickDirectory() : null), [tm]);

  return { status, worlds, events, settled, confirm, run, stop, answer, pickDirectory };
}
