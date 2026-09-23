/*
 * The renderer's session with the sidecar: connect once, and let frames become a run.
 *
 * The URL arrives from the main process (the token never crosses into the renderer), and every frame is
 * one of five shapes — worlds, event, confirm-request, settled, error. This hook is the only place that
 * knows them. Panels are handed events and a cursor; they never see a socket.
 *
 * The one thing this hook does beyond relaying frames is hand the run to the library: it asks the main
 * process for a run directory before the goal goes out (so the engine's own run log is written beside the
 * artifact the window will save), and saves the artifact the moment the run settles. A run that is never
 * saved is a run nobody can compare against anything.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Frame, Sidecar, Status, TmApi, WorldInfo } from "../protocol";
import { EngineEventFrame, RunArtifact } from "../core/types";
import { createLibrary, LibraryBackend, newRunId, summarise } from "../core/library";

export interface ConfirmRequest {
  id: string;
  action: { tool: string; args: Record<string, unknown>; label: string };
  reason: string;
}

export interface Settled {
  answer: string | null;
  reason: string | null;
  events: number;
  summary: string | null;
  record: string | null;
  learned: string | null;
  error?: string;
}

export interface Session {
  status: Status;
  worlds: WorldInfo[];
  events: EngineEventFrame[];
  settled: Settled | null;
  confirm: ConfirmRequest | null;
  /** The artifact of the run that just finished, once the library has it. */
  saved: RunArtifact | null;
  /** True when there is no preload — a browser tab, where nothing can be saved to disk. */
  headless: boolean;
  library: LibraryBackend;
  run: (goal: string, world: string, config: Record<string, unknown>) => Promise<void>;
  stop: () => void;
  answer: (granted: boolean) => void;
  pickDirectory: () => Promise<string | null>;
  /** Reopen a stored run: its events become the current run, with no socket involved. */
  open: (artifact: RunArtifact) => void;
  clear: () => void;
}

export function useSidecar(bookmarks: number[]): Session {
  const tm = (window as unknown as { tm?: TmApi }).tm;
  // The preload's channel names are the boundary's business; the library's vocabulary is the app's. This
  // is the one place they are translated, and a tab with no preload simply gets no backend at all.
  const backend = useMemo<Partial<LibraryBackend> | undefined>(() => (tm ? {
    begin: async (id, world, goal, config) => (tm.runsBegin ? tm.runsBegin(id, world, goal, config) : null),
    save: async (artifact, meta) => (tm.runsSave ? tm.runsSave(artifact, meta) : false),
    list: async () => (tm.runsList ? tm.runsList() : []),
    load: async (id) => (tm.runsLoad ? tm.runsLoad(id) : null),
    remove: async (id) => (tm.runsDelete ? tm.runsDelete(id) : false),
  } : undefined), [tm]);
  const library = useMemo(() => createLibrary(backend), [backend]);

  const [status, setStatus] = useState<Status>("connecting");
  const [worlds, setWorlds] = useState<WorldInfo[]>([]);
  const [events, setEvents] = useState<EngineEventFrame[]>([]);
  const [settled, setSettled] = useState<Settled | null>(null);
  const [confirm, setConfirm] = useState<ConfirmRequest | null>(null);
  const [saved, setSaved] = useState<RunArtifact | null>(null);

  const sidecar = useRef<Sidecar | null>(null);
  // The frames as they arrive, kept outside React state: the artifact is assembled in the frame handler,
  // where the state array would still be a render behind.
  const collected = useRef<EngineEventFrame[]>([]);
  const bookmarksRef = useRef<number[]>(bookmarks);
  bookmarksRef.current = bookmarks;
  const pending = useRef<{ id: string; goal: string; world: string; config: Record<string, unknown>; startedAt: string } | null>(null);

  useEffect(() => {
    if (!tm) {
      setStatus("crashed");
      return;
    }
    let cancelled = false;
    tm.connection().then(({ url }) => {
      if (cancelled) return;
      const s = new Sidecar(url);
      sidecar.current = s;
      s.onStatus((next) => setStatus((prev) => (prev === "running" && next === "ready" ? prev : next)));
      s.onFrame((frame: Frame) => {
        if (frame.type === "worlds") {
          setWorlds(frame.worlds);
          setStatus((current) => (current === "running" ? current : "ready"));
          return;
        }
        if (frame.type === "event") {
          const e = frame as unknown as EngineEventFrame;
          collected.current = [...collected.current, e];
          setEvents(collected.current);
          return;
        }
        if (frame.type === "confirm-request") {
          setConfirm(frame as unknown as ConfirmRequest);
          return;
        }
        if (frame.type === "settled" || frame.type === "error") {
          const info: Settled = frame.type === "settled"
            ? (frame as unknown as Settled)
            : { answer: null, reason: null, events: collected.current.length, summary: null, record: null, learned: null, error: frame.message };
          setSettled(info);
          setStatus("ready");
          const run = pending.current;
          if (run) {
            const artifact = buildArtifact(run, collected.current, info, bookmarksRef.current);
            void library.save(artifact, summarise(artifact)).then((ok) => { if (ok) setSaved(artifact); });
            pending.current = null;
          }
        }
      });
      s.connect();
    }).catch(() => { if (!cancelled) setStatus("crashed"); });
    tm.onSidecarExit(() => setStatus("crashed"));
    return () => { cancelled = true; };
  }, [tm, library]);

  const run = useCallback(async (goal: string, world: string, config: Record<string, unknown>) => {
    collected.current = [];
    setEvents([]);
    setSettled(null);
    setSaved(null);
    setConfirm(null);
    setStatus("running");
    // A run directory first, so the engine's own JSON-lines log lands next to the artifact. If there is no
    // preload the run still happens — it simply will not outlive the window.
    const id = newRunId();
    const started = await library.begin(id, world, goal, config).catch(() => null);
    pending.current = { id, goal, world, config, startedAt: new Date().toISOString() };
    sidecar.current?.goal(goal, world, config, { record: started?.recordPath ?? null });
  }, [library]);

  const stop = useCallback(() => sidecar.current?.stop(), []);

  const answer = useCallback((granted: boolean) => {
    setConfirm((request) => {
      if (request) sidecar.current?.confirm(request.id, granted);
      return null;
    });
  }, []);

  const pickDirectory = useCallback(async (): Promise<string | null> => (tm?.pickDirectory ? tm.pickDirectory() : null), [tm]);

  /** Open a stored run into the same surface a live one uses: same events, same folds, no socket. */
  const open = useCallback((artifact: RunArtifact) => {
    collected.current = [...artifact.events];
    setEvents(collected.current);
    setSettled({
      answer: artifact.outcome.answer, reason: artifact.outcome.reason,
      events: artifact.events.length, summary: artifact.outcome.summary,
      record: artifact.outcome.record, learned: null,
    });
    setSaved(artifact);
    setStatus("ready");
  }, []);

  const clear = useCallback(() => {
    collected.current = [];
    setEvents([]);
    setSettled(null);
    setSaved(null);
  }, []);

  const headless = !tm?.runsSave;

  return { status, worlds, events, settled, confirm, saved, headless, library, run, stop, answer, pickDirectory, open, clear };
}

/** The run as an artifact: the events verbatim, the world, the model, and how it ended. */
function buildArtifact(
  run: { id: string; goal: string; world: string; config: Record<string, unknown>; startedAt: string },
  events: EngineEventFrame[],
  info: Settled,
  bookmarks: number[],
): RunArtifact {
  const seedPart = String(run.config["seed"] ?? "").trim();
  return {
    ...run,
    name: `${run.world}${seedPart ? ` · seed ${seedPart}` : ""} · ${String(run.config["model"] ?? "no model")}`,
    model: String(run.config["model"] ?? ""),
    baseUrl: String(run.config["base_url"] ?? ""),
    seed: seedPart || null,
    endedAt: new Date().toISOString(),
    events,
    outcome: {
      settled: info.error === undefined && info.reason === null && info.answer !== null,
      answer: info.answer,
      reason: info.error ?? info.reason,
      summary: info.summary,
      record: info.record,
    },
    bookmarks: [...bookmarks],
  };
}
