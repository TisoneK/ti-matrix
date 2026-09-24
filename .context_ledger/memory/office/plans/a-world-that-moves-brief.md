# Brief — a world that moves underneath the run

**Raised by the user, 2026-09-24**, from a live trading page: *"this challenge is hard because the
market changes in seconds and by the time our agent learns to make a decision it's too late — but what
if the agent learns and notices the challenge and adapts to reality."* The contract is **ADR-5**; this
is how to build it and the one choice still open.

## The gap, located exactly

The engine already measures time and throws it away.

| | today |
|---|---|
| `EngineEvent.t_ms` | stamped on every event |
| probe duration | recorded per probe (`"ms": ms`) |
| `AgentState.facts` | `tuple[str, ...]` — **bare strings, no time** |
| `RunMemory` (`76a0590`) | append-only, **nothing ever ages** |

So the state knows *what* it learned and never *when*, and the memory built this session will return a
forty-second-old reading with the confidence of a fresh one. In the maze that is correct. On a page
that reprices every second it is the engine asserting something it has no evidence for.

## Why this is a pillar and not a market feature

Every shipped world holds still. The maze does not move, a filesystem does not change mid-run, chess
waits its turn — so the loop's central assumption, **observe → the state is true → decide → act**, has
never actually been tested. It is broken by a market, and also by a file written while a directory is
being read, a page that reloads, a ledger another agent is editing, a CI run whose status changes
between two checks. **The still worlds are the unusual ones**, and the engine has only ever been shown
those.

## Shape: additive, not a rewrite of `facts`

`AgentState.facts` is read by `render`, `to_dict`, `MazeKnowledge`, `FilesReasoner`, `BrowserReasoner`,
`ChessReasoner._here` and `RunMemory` — and shortly by worlds people write themselves (B-2026-09-23-11).
Changing its element type breaks all of them and every user-written proposer at once.

Prefer a parallel sequence of observation times, or an accessor that pairs them. Slightly less elegant
than a tuple of records, and it lets the feature land without a breaking change. This is the same
reasoning that made `Counting` an optional duck-typed protocol rather than a change to `Proposer`:
**an optional capability that nothing has to know about beats a correct shape nobody can adopt.**

## The open choice: declared or measured

**Declared** — a world states its own shelf life. One line per world (`stable_for_ms`, or per
`ActionSpec` since a price moves and a page title does not). Free at runtime. But it is the developer's
guess about their own world, and this engine's whole posture is that a claim is worth less than a
measurement.

**Measured** — the run re-probes a fact and sees whether it changed. Checkable, world-agnostic, needs
no cooperation from the world. Costs probes, and probes are the budget.

**Recommendation: measured, with the world allowed to declare a hint.** Consistent with how everything
else here earns its claims — the branch counts, the perft numbers, the 60% re-probing measurement that
overturned my own brief — and the hint keeps the first probe from being wasted.

## Build order, cheapest first

1. **Report staleness. Nothing else.** Every decision already knows when the fact it rests on was
   observed and when it acted. Surface the gap: in the ledger row, and as an ending
   (`stopped: information was 3.2s old`). **This is the whole feature for a first pass** — it costs no
   probes, it cannot make a run worse, and it is the purest form of the product's own claim. A run that
   reports its information was stale is "check whether to believe it" with no interpretation required.
2. **Re-check before committing.** Probe the one fact the decision rests on, at the moment of acting.
   This is what a real execution system does, and it is the first thing that costs budget.
3. **Narrow the fan.** If five candidates take two seconds to probe and the world turns over in one,
   probe one. `max_branches` becomes adaptive rather than fixed. Most invasive; do last, if at all.

## What success looks like, and it includes failing

**It cannot beat the physics.** Four hundred milliseconds of round-trip against a one-second tick is
workable; against a hundred-millisecond tick nothing helps, and the correct output is *"I cannot act on
this world."* Per ADR-5 that is an honest ending alongside `budget` and `no_progress`.

**A version of this that always finds a way to act is a bug.** The test that matters is a world
deliberately faster than the loop, and the assertion is that the run stops and says so.

## The demo this came from

A live trading page is the right test world and the wrong test *goal*. Reading state — "what are the
last ten digits, and which is most frequent?" — exercises everything here with a checkable answer and
no money. Trading does not: real funds, and the page is stale before a multi-step search finishes,
which is the very thing being measured. See also B-2026-09-23-7, where the same page is the best
argument for showing what the run actually saw — the digits are text and the chart is a drawing the
agent cannot read at all.

## Questions for the user

1. **Declared, measured, or both?** The recommendation above is both, measured-led. It is the only
   choice that changes the shape of the code.
2. **Does step 1 ship alone?** Reporting staleness without adapting is small, safe, and useful on its
   own. Steps 2 and 3 spend budget and change how runs behave.
3. **Is there a world to test against that is fast but free?** A market needs an account and moves on
   its own schedule. A local world that changes on a timer would make the "too fast to act" case
   reproducible in the suite, which the real one never will be.
