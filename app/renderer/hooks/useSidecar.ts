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
  run: (goal: string, world: string, config: Record<string, unknown>, budget?: Record<string, number>,
        remember?: boolean) => Promise<void>;
  stop: () => void;
  answer: (granted: boolean) => void;
  pickDirectory: () => Promise<string | null>;
  /** Reopen a stored run: its events become the current run, with no socket involved. */
  open: (artifact: RunArtifact) => void;
  clear: () => void;
  /** Try the socket again now, from a button. Also respawns the sidecar when it is the thing that died. */
  retry: () => void;
  /** Why the socket is not usable, when it is not — the sentence the UI shows instead of guessing. */
  trouble: string | null;
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
  const [trouble, setTrouble] = useState<string | null>(null);
  // Bumped by `retry` to re-run the connect effect from the top.
  const [attempt, setAttempt] = useState(0);

  const sidecar = useRef<Sidecar | null>(null);
  // The frames as they arrive, kept outside React state: the artifact is assembled in the frame handler,
  // where the state array would still be a render behind.
  const collected = useRef<EngineEventFrame[]>([]);
  const bookmarksRef = useRef<number[]>(bookmarks);
  bookmarksRef.current = bookmarks;
  const pending = useRef<{ id: string; goal: string; world: string; config: Record<string, unknown>;
                          startedAt: string; remembered: boolean } | null>(null);

  useEffect(() => {
    if (!tm) {
      // A plain browser tab, not a broken app: there is no preload here, so there is no sidecar to
      // reach and no app to restart. Saying "restart the app" to someone looking at :5173 sends them
      // to fix a thing that is not wrong.
      setStatus("crashed");
      setTrouble("this page is not running inside the desktop app, so there is no engine to talk to — "
        + "start it with `npm run dev` and use the window it opens");
      return;
    }
    let cancelled = false;
    setTrouble(null);
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
    }).catch((err: unknown) => {
      if (cancelled) return;
      setStatus("crashed");
      // main rejects this when the boot failed, and the reason it gives is the only thing that
      // explains an app that came up with nothing behind it.
      setTrouble(err instanceof Error && err.message ? err.message : "the engine never started");
    });
    return () => {
      cancelled = true;
      sidecar.current?.close();
      sidecar.current = null;
    };
  }, [tm, library, attempt]);

  // The sidecar's own death, heard once. This used to be registered inside the connect effect, where
  // every re-run stacked another listener on the same channel that nothing ever removed.
  useEffect(() => {
    if (!tm) return;
    tm.onSidecarExit(({ code }) => {
      setStatus("crashed");
      setTrouble(`the engine exited (code ${code ?? "signal"}) — restart it to run again`);
    });
  }, [tm]);

  const run = useCallback(async (goal: string, world: string, config: Record<string, unknown>,
                                 budget?: Record<string, number>, remember = true) => {
    collected.current = [];
    setEvents([]);
    setSettled(null);
    setSaved(null);
    setConfirm(null);
    setStatus("running");
    // A pasted key rides to the sidecar and nowhere else: the run directory and the artifact are
    // written to disk, and a secret has no business in either.
    const { api_key, ...kept } = config as Record<string, unknown>;
    // A run directory first, so the engine's own JSON-lines log lands next to the artifact. If there is no
    // preload the run still happens — it simply will not outlive the window.
    const id = newRunId();
    const started = await library.begin(id, world, goal, kept).catch(() => null);
    // What earlier runs in this world established. The sidecar loads it before the run and saves it
    // after, which is what puts `recall` in the model's tools and wraps the proposer in the learning
    // layer. A browser tab has no filesystem, so it simply runs without a memory.
    const memory = remember && tm?.memoryPath ? await tm.memoryPath(world).catch(() => null) : null;
    pending.current = { id, goal, world, config: kept, startedAt: new Date().toISOString(),
                        remembered: memory !== null };
    sidecar.current?.goal(goal, world, api_key === undefined ? config : { ...kept, api_key },
                          { record: started?.recordPath ?? null, remember: memory, budget });
  }, [library, tm]);

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

  /**
   * The way back from a dead socket, without reloading the window.
   *
   * Two different things can be wrong, so this tries both in order: if the sidecar process itself is
   * gone, ask main to spawn a fresh one (it re-announces a new URL when it is healthy); otherwise the
   * process is fine and only the socket dropped, which `Sidecar.reconnect` handles on its own. Bumping
   * `attempt` re-runs the connect effect against whatever URL main now reports.
   */
  const retry = useCallback(() => {
    setTrouble(null);
    setStatus("connecting");
    const restart = (tm as (TmApi & { sidecarRestart?: () => Promise<{ ok: boolean; error?: string }> }) | undefined)?.sidecarRestart;
    if (restart) {
      void restart().then((res) => {
        if (res && res.ok === false && res.error) setTrouble(res.error);
        setAttempt((n) => n + 1);
      }).catch(() => setAttempt((n) => n + 1));
      return;
    }
    if (sidecar.current) { sidecar.current.reconnect(); return; }
    setAttempt((n) => n + 1);
  }, [tm]);

  const headless = !tm?.runsSave;

  return { status, worlds, events, settled, confirm, saved, headless, library, run, stop, answer, pickDirectory, open, clear, retry, trouble };
}

/** The run as an artifact: the events verbatim, the world, the model, and how it ended. */
function buildArtifact(
  run: { id: string; goal: string; world: string; config: Record<string, unknown>; startedAt: string;
         remembered: boolean },
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
    remembered: run.remembered,
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
