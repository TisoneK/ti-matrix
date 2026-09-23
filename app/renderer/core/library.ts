/*
 * The session library: every run, kept as an artifact.
 *
 * A run used to be a thing you watched and lost. Here a run is a file: the events verbatim, the world it
 * was driven against, the model that proposed for it, and how it ended — so it can be reopened, compared,
 * and audited later. The renderer has no filesystem (context isolation, no node integration), so the
 * reading and writing happen in the main process behind the `tm.runs*` channels; this module is the typed
 * face of that, plus the derived summary the library table sorts on.
 *
 * A browser tab is not the app and has no preload, so the whole store falls back to memory: the UI stays
 * usable when the renderer is opened on its own, and nothing pretends a run was saved.
 */

import { ArtifactMeta, Decision, EngineEventFrame, RunArtifact } from "./types";
import { foldDecisions } from "./decisions";
import { readTrust } from "./trust";

export interface RunStart {
  id: string;
  /** Where the run's own directory is, for the "reveal in folder" affordance and the CLI's run log. */
  recordPath: string | null;
}

export interface LibraryBackend {
  /** Ask for a run directory before the goal goes out. The id is minted by the caller, so it can be reused. */
  begin(id: string, world: string, goal: string, config: Record<string, unknown>): Promise<RunStart | null>;
  /** The artifact and its summary are written together, once, when the run settles. */
  save(artifact: RunArtifact, meta: ArtifactMeta): Promise<boolean>;
  list(): Promise<ArtifactMeta[]>;
  load(id: string): Promise<RunArtifact | null>;
  remove(id: string): Promise<boolean>;
}

/** A run id that sorts by time and cannot be mistaken for another: `20260923-181500-4f2a`. */
export function newRunId(now = new Date()): string {
  const pad = (n: number, w = 2): string => String(n).padStart(w, "0");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}`
    + `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  const salt = Math.floor(Math.random() * 0xffff).toString(16).padStart(4, "0");
  return `${stamp}-${salt}`;
}

/**
 * The library row: everything the table shows, derived from the artifact rather than stored beside it, so
 * a summary can never drift from the events it describes.
 */
export function summarise(artifact: RunArtifact, decisions?: Decision[]): ArtifactMeta {
  const run = decisions ?? foldDecisions(artifact.events);
  const trust = readTrust(run);
  const started = Date.parse(artifact.startedAt);
  const ended = Date.parse(artifact.endedAt);
  const lastEvent = artifact.events.length > 0 ? artifact.events[artifact.events.length - 1].t_ms : 0;
  return {
    id: artifact.id,
    name: artifact.name,
    world: artifact.world,
    goal: artifact.goal,
    model: artifact.model,
    seed: artifact.seed,
    startedAt: artifact.startedAt,
    endedAt: artifact.endedAt,
    durationMs: Number.isFinite(started) && Number.isFinite(ended) ? Math.max(0, ended - started) : lastEvent,
    settled: artifact.outcome.settled,
    reason: artifact.outcome.reason,
    decisions: run.length,
    backtracks: run.filter((d) => d.kind === "backtrack").length,
    surprises: run.filter((d) => d.flags.includes("surprise")).length,
    meanConfidence: trust.mean,
  };
}

/** The artifact for a run that has just ended. The name is derived, not asked for: naming is optional. */
export function artifactOf(input: {
  id: string;
  world: string;
  goal: string;
  config: Record<string, unknown>;
  events: EngineEventFrame[];
  outcome: RunArtifact["outcome"];
  startedAt: string;
  endedAt: string;
  bookmarks: number[];
}): RunArtifact {
  const model = String(input.config["model"] ?? "");
  const baseUrl = String(input.config["base_url"] ?? "");
  const seed = input.config["seed"] === undefined || String(input.config["seed"]).trim() === ""
    ? null
    : String(input.config["seed"]);
  const seedPart = seed === null ? "" : ` · seed ${seed}`;
  return {
    id: input.id,
    name: `${input.world}${seedPart} · ${model || "no model"}`,
    world: input.world,
    goal: input.goal,
    config: input.config,
    model,
    baseUrl,
    seed,
    startedAt: input.startedAt,
    endedAt: input.endedAt,
    events: input.events,
    outcome: input.outcome,
    bookmarks: [...input.bookmarks],
  };
}

/** The library as the renderer sees it: the preload's channels when there is a shell, memory otherwise. */
export function createLibrary(api: Partial<LibraryBackend> | undefined): LibraryBackend {
  const memory = new Map<string, RunArtifact>();
  if (!api || typeof api.list !== "function" || typeof api.save !== "function") {
    return {
      begin: async () => null,
      save: async (artifact) => { memory.set(artifact.id, artifact); return true; },
      list: async () => [...memory.values()].map((a) => summarise(a)),
      load: async (id) => memory.get(id) ?? null,
      remove: async (id) => memory.delete(id),
    };
  }
  return {
    begin: (id, world, goal, config) => api.begin!(id, world, goal, config),
    save: (artifact, meta) => api.save!(artifact, meta),
    list: () => api.list!(),
    load: (id) => api.load!(id),
    remove: (id) => api.remove!(id),
  };
}
