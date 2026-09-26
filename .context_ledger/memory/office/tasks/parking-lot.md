# Parking Lot (deferred knowledge — not a queue)

The backlog is a work queue you act on; this file is the knowledge base
you **don't** act on yet. Research findings, open design questions,
advisory "should we…?" items, deferred work, and someday ideas live here
so the backlog stays a queue an agent can actually work from. Nothing
here is urgent, nothing here is capped, and nothing here blocks a gate.
The record of a finding is its own row plus the commit / session entry
that produced it; git history keeps every row, so promoting or dropping
one loses nothing.

**One rule keeps the two files honest: a parking-lot row is not a task.**
If an item becomes actionable — it now has a clear next step and someone
to take it — **promote** it: cut the row here, add an actionable row to
`backlog.md` (a fresh `B-` ID, one line, pointing back at this row's `P-`
ID if the context matters), and leave it here only as a one-line
"→ promoted to B-… " stub if you want the breadcrumb. An item that turns
out to be wrong or moot is just deleted — history remembers it.

Every row gets a stable **ID** — `P-<added YYYY-MM-DD>-<n>`, n = that
date's next sequence in the file — and a **Summary** cell with enough
context that a future session can pick it up cold. Keep status
qualifiers in the text ("advisory", "needs a decision", "blocked on X",
"deferred by owner"). There is **no cap** here and **no priority** —
items are grouped by *kind*, because the whole point is that these are
not competing for the top of a queue.

This file belongs to the **current office**. When the office closes, the
parking lot is **not** re-seeded wholesale: the closing session promotes
what is now actionable into the new backlog and records the rest in the
permanent record (`history/office-<NNN>.md`, "Open threads"). A cold
idea earns its way into the next office by becoming work, not by being
copied.

Full spec: `.context_ledger/core/schemas/ledger-schema.md` →
"The parking lot".

## Findings

- **The engine hands the UI its tree.** `StateEngine.run` stamps every event: `state` carries `node` and
  `parent`, a `backtrack` names the node it returns to, everything else carries `at`. The renderer's tree
  used to derive the shape from each state's `trail` instead — a faithful guess at something the engine
  had already stated. Anything that needs parentage should read the ids first and treat trail-derivation
  as the fallback for older logs. (2026-09-23)
- **The maze's coordinates are the drawing's coordinates.** `cell 1,1` is the point (1,1) of the world's
  own textual map, walls included, so openings land directly on the points between cells and the map needs
  no rescaling. Worth knowing before anyone "normalises" the grid. (2026-09-23)
- **A world may contradict itself.** The maze adapter describes a cell's openings from the map as written,
  so a hand-written maze whose squares disagree produces observations that disagree. Knowledge needs a
  stated precedence (a refusal beats an inference; an inference never beats a corridor) rather than
  relying on the order events happen to arrive in. (2026-09-23)

- **A fact is cut to 320 characters as it enters the state.** `_FACT_CHARS` in `ti_matrix/state.py`
  truncates every observation on the way in, so a listing of a big directory enters the state as a fragment
  of itself. In the run that settled on the wrong folder, home's listing was 3,878 characters, and the name
  the run settled on survived only because a `stat_path` had echoed the resolved path back in a short
  observation of its own. A run that lists a large directory and decides several steps later is reasoning
  over its first 320 characters — and the model is never told the fact was cut, unlike the reader of an
  observation, who gets the world's own "… (truncated)" tail. (2026-09-26)
- **`find_files` cannot match a directory.** `_find_files` filters its walk to `p.is_file()`, so a name
  search can never return a folder: a goal naming a directory ("locate the X repo", "where is the config
  folder") cannot be satisfied by search at all, only by opening directories one at a time and reading their
  listings. Verified by running it — `find_files(path=<fixture>, contains='acme')` over a tree holding
  `Dev/acme/.git` answers "no file under … has 'acme' in its name (3 paths searched)". Whether the honest
  repair is a directory-inclusive search or a separate action is an open design question. The walk it filters
  was bounded on 2026-09-26 (20,000 entries, six levels, and a line that says when it stopped early), so a
  search over a home directory now finishes and says so; the directory blindness is untouched by that and
  still stands. (2026-09-26)
- **`stat_path` reports a directory as `0 bytes`.** An artefact of the platform — `stat().st_size` for a
  directory is not a content size — but the observation is read by a model, and "dir, 0 bytes" reads as
  "empty". It is the line the real run used as its confirmation of the wrong answer. (2026-09-26)
- **Every other world's probe runs on the host's event loop too.** `FilesEnvironment.probe` was the one found
  blocking, and the way it surfaced is worth keeping: a `find_files` over a real home directory wedged the
  sidecar, so the window showed a run that looked alive — the elapsed clock kept ticking — and that could not
  be stopped, because the stop path is served by the same loop. Fixed there (probes on a worker thread,
  `82796d0`), but the other adapters were not audited and the same shape is available in each: the browser
  world shells out to `agent-browser` and speaks CDP, the ledger world reads a vault, and any call that hangs
  takes the loop — and the stop button — with it for as long as it hangs. Worth auditing before another
  long-running world ships. (2026-09-26)

- **A real model costs ~35 seconds per decision.** Two runs against `deepseek-flash` took 3m29s/6
  decisions and 6m37s/10 decisions — roughly 35s per step, because each step is a proposer call plus an
  evaluator call and both are slow. Any UI decision about "live" runs has to assume a viewer waits minutes
  between changes, not seconds: an idle-looking window during a real run is normal. The engine's default
  budget (depth 6, 16 calls) is sized for a stub, not for this. (2026-09-23)
- **The app's confidence numbers are the model's own, not a probability.** "mean belief 45%" is the mean of
  the evaluator's `progress` scores for the moves a run committed to. It reads like a probability and is
  not one; it is only ever comparable within a model, which is what makes the run-vs-run column in Compare
  the honest place for it. (2026-09-23)

## Open questions

What we learned that isn't work yet — observations, measurements, root
causes, "the current design does X because Y".

| ID | Summary |
|----|---------|

- **A real model costs ~35 seconds per decision.** Two runs against `deepseek-flash` took 3m29s/6
  decisions and 6m37s/10 decisions — roughly 35s per step, because each step is a proposer call plus an
  evaluator call and both are slow. Any UI decision about "live" runs has to assume a viewer waits minutes
  between changes, not seconds: an idle-looking window during a real run is normal. The engine's default
  budget (depth 6, 16 calls) is sized for a stub, not for this. (2026-09-23)
- **The app's confidence numbers are the model's own, not a probability.** "mean belief 45%" is the mean of
  the evaluator's `progress` scores for the moves a run committed to. It reads like a probability and is
  not one; it is only ever comparable within a model, which is what makes the run-vs-run column in Compare
  the honest place for it. (2026-09-23)

## Open questions

Advisory questions, decisions still up for grabs, "should we…?" — a
question is not a task until it has an owner and a next step (then it
becomes a backlog row or an ADR in `plans/decisions.md`).

| ID | Summary |
|----|---------|
| P-2026-09-25-1 | **Should we build a "civilization" world (Civ-style: cities, tech trees, diplomacy, long time horizons)?** Raised by the user, discussed with Marlowe (S005). Lean: not yet as a fifth first-party shipped world (`worlds.py`) — it's a different order of scope than maze/chess/files/browser (long-horizon, heavily stateful, arguably multi-agent) and would stress every open architecture question at once (the moving-world staleness contract in `plans/a-world-that-moves-brief.md` / ADR-5, the state-identity gap, structural recall in `plans/recall-what-is-relevant-brief.md`) rather than let any one of them get settled first. It's a strong fit as the flagship example world for **bring-your-own-world** (B-2026-09-23-11, `plans/worlds-users-can-bring-brief.md`) once that plugin loader ships — exactly the kind of world a third party would want to plug in rather than have hardcoded. No owner, no next step yet; promote to backlog once bring-your-own-world lands and someone wants to build the example. |

## Deferred work

Real tasks, consciously parked — not now, but keepable. This is where a
backlog row goes when the cap forces a prune and the item still matters:
out of the queue, not into the void.

| ID | Summary |
|----|---------|
| P-2026-09-26-2 | **Give the three worst small-viewport overflows a breakpoint.** Raised as "the UI looked like a mess" and correctly diagnosed by the supervisor as a small window, not a design fault — the layout already breaks at 1180/820/720/700px. Three gaps remain below roughly 700px, all read out of `app/renderer/styles.css`: `.rail` is a single non-wrapping flex row carrying six metrics, the run controls and the window buttons, so it overflows rather than wrapping; the inspector row's three columns (`.inspector`, ~line 574) have minimums summing to about 640px with no breakpoint of their own; and the stage's pane minimums (`420px + 360px`, `.stage`) only collapse at 1180px. Advisory, no owner: it is a layout change and needs its own render at 360/768/1280 to verify, which the session that found it did not run — an unverified CSS change is exactly what this repo's verification rule forbids. |

## Someday

Loose ideas with no owner and no hook yet. The lowest-pressure shelf.

| ID | Summary |
|----|---------|

<!-- TEMPLATE — add one row to the matching section:
| P-<YYYY-MM-DD>-<n> | <enough context that a future session can pick
      this up cold — status qualifiers in the text; promote to the
      backlog when it becomes actionable> |
-->
