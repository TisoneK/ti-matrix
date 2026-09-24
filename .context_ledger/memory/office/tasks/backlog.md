# Backlog (work queue — actionable items only)

The queue of work a session can pick up and **do**. One row per item, in
its priority table. It is a queue, not a knowledge base: the test for a
row is "can an agent start on this and finish it?" If the answer is no —
it's a finding, an open question, an advisory "should we…?", a deferred
"someday" idea — it belongs in [`parking-lot.md`](parking-lot.md), not
here. Writing discoveries into the backlog is how a queue turns into a
57-row document nobody can work from.

**Done = delete the row. Stale = delete the row.** The backlog holds
open, actionable work only. When an item is finished, delete its row —
the completion record is the finishing session's `agents/sessions.md`
entry and the commit, never a tombstone here. When an item stops
mattering, delete it too; if it still carries information worth keeping,
move it to the parking lot first. Git history keeps every removed row,
so deleting loses nothing. (The one thing you must not do is delete a row
whose work is genuinely still open and recorded nowhere else — a row
vanishing from the diff with no session entry or promotion behind it is a
dropped handoff, not cleanup. Legacy checkbox-format backlogs:
`ledger-mem closeout` sweeps checked-off `- [x]` tombstones a session
left behind — dry run by default; `--confirm` deletes.)

**The queue is capped at ~20 rows** (`backlog_cap` in
`workflows/history.conf`; `ledger-mem check` warns past it). Twenty is a
working set, not a limit to fill. When you'd add a 21st actionable item,
prune one first: the lowest-value open row goes to the parking lot
(deferred, still valuable) or is deleted (no longer relevant) — never a
row you can't justify dropping. A queue you can hold in your head beats
a comprehensive one you can't.

**Only actionable work, and context lives where the work is.** Every row
gets a stable **ID** — `B-<added YYYY-MM-DD>-<n>`, n = that date's next
sequence in the file — and a **Summary** cell that says what to *do*, not
everything known about it. A fresh agent should be able to start from the
one line; the deep context belongs in the linked issue, PR, ADR, or
parking-lot finding the row points at, not packed into the cell. Keep
status qualifiers short ("partial", "blocked on X"). Don't append
research narrative to a row to "preserve" it — that's the parking lot's
job.

**Priority is the table an item sits in (High / Medium / Low), and it is
dynamic.** Only the top of the queue really matters — when you start a
session, the handful of High rows (roughly the top 3–5) are the work; the
rest is context, and a row that has sat in Low for many sessions is a
candidate for the parking lot, not a permanent resident. When unsure
between two tables, pick the lower one; promoting a row later is cheap,
and a backlog where everything is High says nothing.

This backlog belongs to the **current office**. When the office closes,
open items do not carry over implicitly — the closing session re-seeds
into the new office's backlog **only items with an active owner or a
clear next step**; everything else is recorded in the permanent record
(`history/office-<NNN>.md`, "Open threads") or parked. A re-seeded row
describes the work in plain words and never cites the old office's
session numbers or codenames.

Full spec: `.context_ledger/core/schemas/ledger-schema.md` →
"The backlog: a capped work queue" and "The parking lot".

## Open Items

### High Priority

| ID | Summary |
|----|---------|
| B-2026-09-23-6 | **Duplicate files of any kind, judged by content not filename — the next session's focus, raised by the user.** A registry of file families, each climbing the same cheap→expensive ladder: identify, describe, hash the *payload* (not the file, so retagging does not hide a duplicate), and only where that cannot settle it, the expensive perceptual probe. Songs are the motivating case, not the scope. The brief carries the boundary-test constraint, a per-family feasibility table, the verified stdlib tier, the decision about where a package this size may live, and four questions to put to the user first: `.context_ledger/memory/office/plans/duplicate-files-brief.md` (working spike beside it). |
| B-2026-09-23-7 | **Show the page the browser world is driving, and what the run actually saw of it.** The engine already has `cdp.screenshot()`, `BrowserEnvironment(screenshot_dir=...)` and a `screenshot` action; the CLI uses them via `--shots`. The gap is one call site — `worlds.py::_browser_world` never passes `screenshot_dir` — plus a panel, a frame-per-decision written beside the run (not inside the artifact), and a `window.tm` channel to read one. **The agent reads text, never pixels**, so the panel must show the page *and* what the run extracted from it, distinguishably; a bare screenshot would imply the agent saw what the viewer sees. Sharpens B-2026-09-23-2 for the browser. Brief: `.context_ledger/memory/office/plans/browser-what-it-sees-brief.md`. |
| B-2026-09-23-11 | **Let people bring their own world.** The `Environment` protocol is four members and the README promises a new world is one row — true inside this repo, false outside it: `worlds.py` is a hardcoded dict and there is no discovery mechanism at all. Add a loader over `ti_matrix.worlds` entry points plus a `~/.ti-matrix/worlds/` directory, a template world that is correct by construction, and an order-dependence check at registration — because ADR-4 rule 1 is the rule nobody guesses and the one whose failure looks like model hallucination. Options, costs and three questions for the user: `.context_ledger/memory/office/plans/worlds-users-can-bring-brief.md`. |
| B-2026-09-23-12 | **Selection over the state space — the within-run half is done; the structural half is not.** `76a0590` gave every run a `recall` action answering from its own observations, built inside `EngineTools` from probes already passing through it, so `Environment.probe` kept its signature and no world implements anything. What is still true: a proposer is handed one flat `AgentState` with no node id, no parent and no structure, and the tree is stamped onto *events*, so a seat still cannot select **nodes** — only facts, and only lexically. If the search's shape is ever wanted at proposal time ("what did I learn down the branch I abandoned?"), that needs the history passed to the proposer or a `Retriever` port, and it is a protocol change that should land before B-2026-09-23-11 opens worlds to users. Brief: `.context_ledger/memory/office/plans/recall-what-is-relevant-brief.md`. |

### Medium Priority

| ID | Summary |
|----|---------|
| B-2026-09-23-5 | The endpoint-backed path is weak on small models, independently of the sidecar. Measured this session against a real local `phi4-mini:latest`: one proposer call took 48s and returned two moves naming cell `0,0` (a wall — it is not in the maze), the evaluator then scored a successful, informative `entry()` probe at 0.0, and `NothingImproves` stopped the run at 9 events with `no_progress`. So a viewer who configures a small model correctly still gets a near-empty window. Two separable fixes: the proposer prompt never shows the model which cells it has actually entered (the maze states them in every fact, `LLMMoveProposer` just renders the state), and a run whose very first probe succeeds should not be able to stop on `no_progress` at depth 0. `ti_matrix/model.py`, `ti_matrix/search.py`. |
| B-2026-09-23-2 | Rebuild the prose worlds' panels (files/ledger/browser) as rich surfaces — the parsers are intact and tested in `app/renderer/core/worlds/`, but `panels/WorldSurface.tsx` shows less than the views the old renderer had (directory tree, vault report, page view). See `.context_ledger/memory/office/reviews/2026-09-23-review-2.md`. |

### Low Priority

| ID | Summary |
|----|---------|

<!-- TEMPLATE — add one ACTIONABLE row to the matching priority table
     (a finding, question, or someday idea goes in parking-lot.md instead):
| B-<YYYY-MM-DD>-<n> | <what to DO, one line, pointing at the issue/PR/
      parking-lot finding for detail — not the full context> |
-->
