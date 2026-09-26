/*
 * The vocabulary the whole renderer shares: one event log, one cursor, one artifact.
 *
 * The engine's `EngineEvent` (`ti_matrix/search.py`) is the only thing the app is told, and it is told
 * verbatim — the wire payload is `to_dict()`. So everything the window shows is derived from that log by
 * a pure function of `(events, cursor)`. That is what makes playback, scrubbing, bookmarks and compare
 * possible without any of them being special: they all just move the cursor.
 */

export interface EngineEventFrame {
  seq: number;
  t_ms: number;
  kind: string;
  [key: string]: unknown;
}

/** The fixed vocabulary a decision can be marked with. Shapes and colours both distinguish them. */
export type Flag = "confirmed" | "surprise" | "backtrack" | "guess" | "forced";

/** One proposed move and what the world did with it. */
export interface Candidate {
  fp: string;
  label: string;
  tool: string;
  why: string;
  /** Absent until the probe comes back. */
  ok?: boolean;
  excerpt?: string;
  ms?: number;
  predicted?: boolean;
  /** The evaluator's score for this outcome — the model's own belief about how good it was. */
  progress?: number;
  done?: boolean;
  reason?: string;
  /** True for the one the engine actually committed to. */
  chosen?: boolean;
}

/** How a decision ended. A search iteration always ends in exactly one of these. */
export type DecisionKind = "move" | "backtrack" | "done" | "stopped" | "needs-action";

/**
 * One turn of the search loop, folded out of the raw event stream.
 *
 * This — not the event — is the unit a person reasons about: "it had these options, the world answered
 * this, it believed that, and it did this." Every panel keys off these; the raw events stay available
 * behind the inspector for anyone who wants the machine's own view.
 */
export interface Decision {
  index: number;
  kind: DecisionKind;
  /** Search depth the decision was taken at. */
  depth: number;
  /** The first and last event index this decision covers — the cursor lands on `to`. */
  from: number;
  to: number;
  /** The move committed to, when one was. */
  move: string | null;
  /** The maze cell the move landed on, parsed from the move label — the map's end of the shared cursor. */
  cell: string | null;
  /** What the agent believed this move was worth, 0..1 — the evaluator's own score for it. */
  confidence: number;
  /** What it believed before it moved, so "did this help" is answerable. */
  priorProgress: number;
  /** Where the belief came from: the world's answer to the chosen move. */
  evidence: string;
  /** One line, plain: what this decision amounts to. */
  headline: string;
  flags: Flag[];
  options: Candidate[];
  /**
   * How many actions this decision was chosen from, when the proposer could say.
   *
   * Weighing four of thirty-five legal moves and four of four are different decisions, and without
   * this the record cannot tell them apart. Undefined where the question has no answer — a filesystem
   * admits any path — and undefined is shown as nothing rather than as a guess.
   */
  available?: number;
  /** Actions the search proposed and could not run (refused, or a tool this world does not have). */
  refused: string[];
  /** Everything the state knows after the decision — the engine's own fact text. */
  facts: string[];
  /** Model calls spent by the time this decision finished. */
  modelCalls: number;
  tMs: number;
  /** Terminal decisions only: the reason the run gave for stopping. */
  reason?: string;
  /** The settled answer, when the run reached the goal and the world confirmed it. */
  answer?: string | null;
  /**
   * A run that stopped without settling still has a last word, when a synthesizer was wired in: its own
   * best reading of the facts it actually established.
   *
   * Kept apart from `evidence` on purpose. `evidence` is always the world's own words — what the probe
   * returned, verbatim — and a synthesizer's sentence is not that: it is the run's belief about those
   * words. Two different claims, so two different fields.
   */
  partialAnswer?: string | null;
  /** What that synthesis rested on, in the engine's words — e.g. "synthesised from 3 fact(s)…". */
  answerBasis?: string | null;
  settled?: boolean;
}

/** What a run is, on disk and in the library. */
export interface RunArtifact {
  id: string;
  name: string;
  world: string;
  goal: string;
  /** The world's own fields (seed, size, root, url…) exactly as the run was given them. */
  config: Record<string, unknown>;
  model: string;
  baseUrl: string;
  /** Promoted out of config because the library sorts on it — null when the world has no seed. */
  seed: string | null;
  startedAt: string;
  endedAt: string;
  /**
   * Whether this run carried what earlier runs in the same world had established.
   *
   * Recorded because Compare exists to hold two runs against each other, and a run that started with
   * a record is not comparable to one that started cold — the benchmark has the warm pass settling the
   * same goals in half the rounds. Without this the view would show the difference and attribute it to
   * the model.
   */
  remembered?: boolean;
  events: EngineEventFrame[];
  outcome: {
    settled: boolean;
    answer: string | null;
    /** Why it stopped, when it did: `budget`, `no_moves`, `no_progress`, `needs_action`, `error: …`. */
    reason: string | null;
    summary: string | null;
    record: string | null;
  };
  /** Indices into the artifact's own decision list. */
  bookmarks: number[];
}

/** The library's row — an artifact without its event log, which is most of its weight. */
export interface ArtifactMeta {
  id: string;
  name: string;
  world: string;
  goal: string;
  model: string;
  seed: string | null;
  startedAt: string;
  endedAt: string;
  durationMs: number;
  settled: boolean;
  reason: string | null;
  decisions: number;
  backtracks: number;
  surprises: number;
  meanConfidence: number;
}

/** A pointer into a run: which decision, and which panel the pointer came from. */
export interface Cursor {
  decision: number;
  /** For the inspector strip: what the last click was about. */
  subject: { kind: "decision" | "cell" | "node"; id: string } | null;
}
