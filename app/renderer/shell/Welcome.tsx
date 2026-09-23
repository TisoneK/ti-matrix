/*
 * The welcome: the window's first answer to "what is this, and what do I do now?"
 *
 * A run inspector arrives empty — no map, no tree, no ledger — and an empty instrument reads as a broken
 * one. This overlay stands in the stage until the first run exists, saying plainly what the tool is for
 * and putting the three moves that matter (say what to do, point it at a model, run) in one place. It
 * disappears the moment there is something to look at, and never comes back for that run.
 *
 * The button that opens config is the same toggle the rail carries — it only looks like a next step,
 * because on a first run it is.
 */

import { Button } from "../ui/controls";

export function Welcome({ onConfigure, blocked, hint }: { onConfigure: () => void; blocked: string; hint: string }) {
  return (
    <div className="welcome">
      <div className="welcome-card">
        <div className="mark"><i>Ti</i><span>Ti Matrix</span></div>
        <h2>Watch an AI agent think — and check whether to believe it.</h2>
        <p className="lede">
          You give a small language model a goal in a world it can probe — a maze, a codebase, a vault.
          It proposes moves, the world answers, and this window draws the whole exchange: the map as the
          agent actually learned it, every branch of its search, and the belief behind each decision.
          Nothing here is taken on faith — every claim a panel makes is backed by the world's own words.
        </p>
        <ol className="welcome-steps">
          <li><span><b>Say what the agent should do.</b> One sentence — “find the exit”, “find the leaked key”. That is the goal.</span></li>
          <li><span><b>Point it at a model.</b> Any OpenAI-compatible endpoint — local Ollama, DeepSeek, OpenAI. Your key stays in this window's memory, never on disk.</span></li>
          <li><span><b>Run it.</b> The map, tree and ledger fill in live. Scrub back through the run, mark the moments it was wrong, compare two runs of the same seed.</span></li>
        </ol>
        <div className="welcome-go">
          <Button variant="primary" onClick={onConfigure} disabled={Boolean(blocked) && !hint}>
            {blocked && hint ? blocked : "Open setup — model, key, goal"}
          </Button>
          <span className="dim" style={{ fontSize: 11.5 }}>
            or press Ctrl+Enter once it is set · saved runs live in the Library
          </span>
        </div>
      </div>
    </div>
  );
}
