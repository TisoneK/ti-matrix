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

## A world has several clocks, not one

**Corrected after the user's note that the world rotates *and* revolves.** The first draft of this
brief asked whether a *world* declares or measures its shelf life, and put the real point in a
parenthesis. The real point is that the question has no world-level answer.

Every one of these is a fact about the same page:

| fact | good for |
|---|---|
| the last digit | about a second |
| the digit frequencies | tens of seconds |
| the account balance | until a trade settles |
| which symbols exist | hours |

A single shelf life is wrong in **both** directions simultaneously: re-probe everything at the fastest
rate and the budget goes on facts that never move; trust everything at the slowest and act on a price
from a minute ago. So the unit is the observation, not the environment.

That also makes it measurable, which the world-level version never was. *"Did this action's answer
change between two probes"* is a real question with a cheap answer. *"How volatile is this world"* is
not a question at all.

## The open choice, restated: declared or measured — **per action**

**Declared** — an `ActionSpec` says how long its answer holds. That is where it belongs: `look` on a
chess position is good until someone moves, `page_text` on a price is good for a tick, `grid()` on a
maze is good forever. One field, and worlds already declare `read_only` in the same place, so the
precedent and the shape both exist.

**Measured** — probe the same action twice and compare. Targeted and cheap, because it is one action
rather than a survey of the world, and it needs no cooperation from a world someone else wrote.

**Recommendation unchanged in spirit, sharper in form: both, per action, measurement winning.** The
spec's number is a hint that saves the first probe; what the run actually observes overrides it. This
is how everything else here earns its claims, and a declaration that turns out to be wrong is exactly
the failure the engine should catch rather than inherit.

## A third way to adapt, which the metaphor surfaced

ADR-5 names three: re-check, narrow the fan, stop. Per-fact rates add a fourth and it may be the best
of them:

**Prefer the slow facts.** If a goal can be answered from things that are not moving, answer it from
those. "Which digit came up most often in the last hundred ticks" is nearly as stale-proof as the
symbol list; "what is the last digit right now" cannot be made safe at all. A run that notices it is
being beaten by the clock and *reframes onto slower evidence* is adapting in the way the user
described, and unlike narrowing the fan it costs nothing and makes the answer better rather than just
faster.

It also changes what re-checking costs. Re-probing "the one fact the decision rests on" is cheap when
you know which fact that is and that it is the fast one — the first draft implied re-probing broadly.

## Periodic, not just drifting

Rotation and revolution are cycles, not random walk. Some world change is predictable: a page that
polls on a timer, a market session, a job on a schedule. A run that measured a *period* could time
itself against it rather than race it.

Out of scope for a first pass and recorded so nobody designs it out — the shape above (a rate per
action, measured) extends to a period per action without being rebuilt, and a design that assumed one
global drift rate would not.

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

1. **Declared, measured, or both — per action?** The recommendation is both, measured-led, with the
   `ActionSpec` carrying a hint. It is the only choice that changes the shape of the code, and the
   per-action part is not optional: a world-level rate is wrong in both directions at once.
2. **Does step 1 ship alone?** Reporting staleness without adapting is small, safe, and useful on its
   own. Steps 2 and 3 spend budget and change how runs behave.
3. **Is "prefer the slow facts" worth building, or just worth knowing?** It is the most interesting of
   the four adaptations and the least like the others — it changes which question gets answered rather
   than how fast. It may belong to the seats (a reasoner's judgement) rather than to the engine.
4. **Is there a world to test against that is fast but free?** A market needs an account and moves on
   its own schedule. A local world that changes on a timer would make the "too fast to act" case
   reproducible in the suite, which the real one never will be.
