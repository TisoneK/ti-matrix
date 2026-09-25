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

## Deferred work

Real tasks, consciously parked — not now, but keepable. This is where a
backlog row goes when the cap forces a prune and the item still matters:
out of the queue, not into the void.

| ID | Summary |
|----|---------|

## Someday

Loose ideas with no owner and no hook yet. The lowest-pressure shelf.

| ID | Summary |
|----|---------|

<!-- TEMPLATE — add one row to the matching section:
| P-<YYYY-MM-DD>-<n> | <enough context that a future session can pick
      this up cold — status qualifiers in the text; promote to the
      backlog when it becomes actionable> |
-->
