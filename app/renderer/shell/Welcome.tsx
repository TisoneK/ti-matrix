/*
 * The welcome: the window's first answer to "what is this, and what do I do now?"
 *
 * A run inspector arrives empty — no map, no tree, no ledger — and an empty instrument reads as a broken
 * one. This overlay stands in the stage until the first run exists, and then never comes back.
 *
 * It used to be a wall of prose over three identical numbered boxes: a screen whose whole claim is
 * "watch it think" making that claim in words, with no evidence of what it looks like, in the same
 * equal-weight card grid the run view was criticised for. Three boxes of the same size say the three
 * things matter equally, and they do not — two are form-filling and the third is the payoff.
 *
 * So the right half is a frozen, muted, non-interactive picture of the actual run view: the map with a
 * route walked and a branch abandoned, the search tree with the retreat in it, three ledger rows
 * carrying the real flag glyphs. It is drawn with the same vocabulary the live panels use — the glyph
 * paths are imported from `core/flags`, not redrawn, so this cannot drift from what a run actually
 * shows — and in the same colours, so the palette a run speaks in (green held, red refused, violet
 * retreated, amber a hunch) is legible before the first run rather than after it.
 *
 * The preview is `aria-hidden` and untabbable on purpose: it is an illustration of the product, not a
 * control, and a screen reader reading out a fake ledger would be a lie.
 */

import { Button } from "../ui/controls";
import { Wordmark } from "../ui/atoms";
import { FLAGS } from "../core/flags";

/* ── the frozen run, as a picture ───────────────────────────────────────── */

// The same string format `MazeEnvironment` parses, so the picture is of a maze that could exist.
const GHOST_MAZE = [
  "#########",
  "#S..#...#",
  "#.#.#.#.#",
  "#.#...#.#",
  "#.#####.#",
  "#E......#",
  "#########",
];

const CELL = 12;

/** Cells the run has entered — the map is drawn from what it saw, never from the maze. */
const WALKED: [number, number][] = [[1, 1], [2, 1], [3, 1], [3, 2], [3, 3], [4, 3], [5, 3],
                                    [1, 2], [1, 3], [1, 4], [1, 5]];
/** The route it kept: down the left column to the exit. */
const KEPT = [[1, 1], [1, 2], [1, 3], [1, 4], [1, 5]];
/** The branch it gave up on — drawn the way a retreat is drawn everywhere else. */
const ABANDONED = [[1, 1], [2, 1], [3, 1], [3, 2], [3, 3], [4, 3], [5, 3]];

const mid = (p: number[] | [number, number]): string => `${p[0] * CELL + CELL / 2},${p[1] * CELL + CELL / 2}`;

function GhostMap() {
  const walked = new Set(WALKED.map(([x, y]) => `${x},${y}`));
  const cells = [];
  for (let y = 0; y < GHOST_MAZE.length; y++) {
    for (let x = 0; x < GHOST_MAZE[y].length; x++) {
      const ch = GHOST_MAZE[y][x];
      const seen = walked.has(`${x},${y}`);
      // Three weights, and they have to stay distinguishable at this size or the picture is a black
      // rectangle with a line through it: a wall is the darkest thing on screen, floor the run has not
      // reached is barely there (it has not been seen — that is the map panel's whole idea), and a cell
      // it walked into is lit. The hairline is what makes the maze read as a maze rather than a blur.
      const fill = ch === "#" ? "var(--void)" : seen ? "rgba(88,182,255,0.16)" : "rgba(255,255,255,0.035)";
      cells.push(<rect key={`${x},${y}`} x={x * CELL + 0.5} y={y * CELL + 0.5} width={CELL - 1} height={CELL - 1}
                       rx="1.5" fill={fill}
                       stroke={ch === "#" ? "rgba(255,255,255,0.045)" : "none"} strokeWidth="0.5" />);
    }
  }
  return (
    <svg viewBox={`-2 -2 ${9 * CELL + 4} ${7 * CELL + 4}`} className="ghost-map">
      {cells}
      <polyline points={ABANDONED.map(mid).join(" ")} fill="none" stroke="var(--violet)"
                strokeWidth="1.4" strokeDasharray="2 2" opacity="0.75" strokeLinejoin="round" />
      <polyline points={KEPT.map(mid).join(" ")} fill="none" stroke="var(--ice)"
                strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <rect x={1 * CELL} y={5 * CELL} width={CELL - 1} height={CELL - 1} rx="1.5" fill="var(--green)" opacity="0.9" />
      <circle cx={1 * CELL + CELL / 2} cy={1 * CELL + CELL / 2} r="2.4" fill="var(--ice)" />
    </svg>
  );
}

function GhostTree() {
  // The spine it kept, and the limb it retreated out of — the same story the map above tells.
  return (
    <svg viewBox="0 0 74 54" className="ghost-tree">
      <path d="M12 8 L12 46" stroke="var(--line-2)" strokeWidth="1.2" fill="none" />
      <path d="M12 18 C 12 24, 26 24, 32 31" stroke="var(--violet)" strokeWidth="1.2" fill="none"
            strokeDasharray="2 2" opacity="0.8" />
      <path d="M32 31 L 44 38" stroke="var(--violet)" strokeWidth="1.2" fill="none"
            strokeDasharray="2 2" opacity="0.5" />
      {[8, 18, 28, 38, 46].map((y) => (
        <circle key={y} cx="12" cy={y} r="3" fill="var(--bg)" stroke="var(--ice)" strokeWidth="1.3" />
      ))}
      <circle cx="32" cy="31" r="2.6" fill="var(--bg)" stroke="var(--violet)" strokeWidth="1.2" />
      {/* the dead end it retreated out of */}
      <circle cx="44" cy="38" r="2.2" fill="var(--bg)" stroke="var(--violet)" strokeWidth="1" opacity="0.6" />
      <circle cx="12" cy="46" r="3" fill="var(--green)" />
    </svg>
  );
}

/** One ledger row, using the ledger's own glyph for the flag rather than a lookalike. */
function GhostRow({ flag, text, score }: { flag: keyof typeof FLAGS; text: string; score: string }) {
  const spec = FLAGS[flag];
  return (
    <div className={`ghost-row tone-${flag}`}>
      <svg viewBox="0 0 10 10" className="ghost-flag" data-flag={flag}>
        <path d={spec.path} fill={spec.filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.2" />
      </svg>
      <span className="ghost-move">{text}</span>
      <span className="ghost-score">{score}</span>
    </div>
  );
}

function GhostRun() {
  return (
    <div className="ghost-run" aria-hidden="true">
      <div className="ghost-bar">
        <span className="ghost-run-dot" /> a run, already finished
      </div>
      <div className="ghost-body">
        <div className="ghost-pane">
          <span className="ghost-title">§ Map</span>
          <GhostMap />
        </div>
        <div className="ghost-pane">
          <span className="ghost-title">§ Search tree</span>
          <GhostTree />
        </div>
      </div>
      <div className="ghost-pane ghost-ledger">
        <span className="ghost-title">§ Ledger</span>
        <GhostRow flag="confirmed" text="step(1,4 → south)" score="100%" />
        <GhostRow flag="backtrack" text="retreat to 1,1" score="41%" />
        <GhostRow flag="surprise" text="step(5,3 → east)" score="0%" />
      </div>
      <div className="ghost-legend">
        {(["confirmed", "surprise", "guess", "backtrack"] as const).map((f) => (
          <span key={f} className="ghost-key" data-flag={f}>
            <svg viewBox="0 0 10 10"><path d={FLAGS[f].path} fill={FLAGS[f].filled ? "currentColor" : "none"}
                                           stroke="currentColor" strokeWidth="1.2" /></svg>
            {FLAGS[f].label}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ── the screen ─────────────────────────────────────────────────────────── */

export function Welcome({ onConfigure, onDismiss }: { onConfigure: () => void; onDismiss: () => void }) {
  return (
    <div className="welcome">
      <div className="welcome-card">
        <div className="welcome-say">
          <div className="mark"><Wordmark className="big" /></div>
          <h2>Watch an AI agent think — and check whether to believe it.</h2>
          <p className="lede">
            Give it a goal in a world it can probe — a maze, a codebase, a vault. It proposes moves, the
            world answers, and this window draws the exchange: the map as the agent actually learned it,
            every branch of its search, and the belief behind each decision. Nothing is taken on faith —
            every claim a panel makes is backed by the world's own words.
          </p>

          <ol className="welcome-steps">
            <li>
              <b>Say what it should do.</b>
              <span>One sentence — “find the exit”, “find the leaked key”.</span>
            </li>
            <li>
              <b>Choose what decides.</b>
              <span>Built-in rules need nothing at all; a language model needs an endpoint.</span>
            </li>
            <li className="payoff">
              <b>Run it.</b>
              <span>The map, tree and ledger fill in live. Scrub back, mark where it went wrong,
                compare two runs of the same seed.</span>
            </li>
          </ol>

          <div className="welcome-go">
            {/* Never disabled: setup is the way *out* of not being set up yet — a button that refuses to
                open the settings you came here to change is a dead end, and this screen is the first one. */}
            <Button variant="primary" onClick={onConfigure}>Open setup</Button>
            <button type="button" className="btn ghost-btn" onClick={onDismiss}
                    title="dismiss this; it will not come back">
              skip — it runs out of the box →
            </button>
          </div>
          <p className="welcome-foot">
            ⌘↵ runs · saved runs live in the Library · a pasted key stays in this window, never on disk
          </p>
        </div>

        <div className="welcome-show">
          <GhostRun />
          <span className="welcome-caption">what a finished run looks like</span>
        </div>
      </div>
    </div>
  );
}
