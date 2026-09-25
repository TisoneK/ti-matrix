# Brief — the engine forgetting where it has been is mostly a prompt bug, not a design gap

**Raised by the user, 2026-09-23.** Rewritten by Mara (S004) after the user corrected the first
version, which leaned on `DESIGN.md` as though it were a specification. It is not, and the measurement
below points somewhere much cheaper than the first draft did.

## The correction that started this

The first draft opened with *"what the project already decided"* and quoted `DESIGN.md`'s three
samenesses as settled design. The user's objection: **it is not actionable, it is not tested, and the
design was written after the actions had already been implemented.** Checked, and that is exactly right:

```
2026-09-21  48d06fe  the engine ships — Action.fingerprint() already implemented
2026-09-22  a065027  the maze arrives, with a test asserting the engine CANNOT tell
2026-09-22  4faf966  "What this began as, and the three things 'the same' can mean"
```

The reasoning came **after** the implementation and after the gap was exposed. Its own commit title —
"What this began as" — says it is a look back. So "sameness of what is known is the version worth
detecting" was never a decision anybody validated; it is a post-hoc account of why action-level
fingerprints are the thing that exists. And the only test asserts the *limitation*, deliberately
("asserted rather than fixed"). Nothing measured what the limitation costs.

## What it costs, measured

Re-probing a cell whose openings the run already holds as a fact, across the saved maze runs:

| model | probes | re-learned a known place | |
|---|---|---|---|
| `deepseek-flash` | 12 | 5 | **42%** |
| `deepseek-flash` | 21 | 10 | **48%** |
| `builtin` × 8 runs | 320 | 0 | **0%** |

Nearly half of a real model's probes re-learned something it already knew — at twenty to forty-five
seconds and real money each. The rule-based reasoner did it zero times in 320 probes.

## Why the rules never do it, and what that reveals

`MazeReasoner` rebuilds what the run has seen from the run's own facts and proposes only steps into
cells it has *not* entered. It cannot re-probe a known place because it knows which places are known.

`LLMMoveProposer` calls `state.render()` — and the default is **`max_facts=8`**. At probe 30 of 40 the
model is shown the last eight facts and has no record of the first twenty-two cells it learned.

So the obvious question: is the re-probing an engine identity failure, or is the proposer simply
blindfolded? Testable without spending an API call — hold the reasoner constant and vary only how many
facts it is allowed to see:

| shown to the proposer | probes | re-learned | share |
|---|---|---|---|
| last 8 facts — *what the model gets today* | 266 | 160 | **60%** |
| last 16 | 226 | 106 | 47% |
| last 32 | 140 | 20 | 14% |
| every fact — *what the rules get* | 120 | 0 | **0%** |

Same logic throughout; only the window changed. The observed model runs at 42–48% land between the
8-fact and 16-fact rows. And the forgetting more than **doubles the total work**: 120 probes becomes 266.

**The engine's lack of state identity is not what causes the observed re-probing.** The proposer being
shown eight facts is. That is a default argument, not a protocol change.

## So what is actually actionable

1. **Raise what the proposer is shown, and measure it against a real model.** The cheap experiment
   first. Not free: facts are bounded at 320 characters, so a long files or browser run cannot simply
   pass all of them — this needs a sensible cap, or the world's own summary, not an unbounded prompt.
2. **This predicts an improvement; it does not prove one.** The rules *parse* facts; a model *reads*
   them. Showing forty facts does not guarantee a model uses them. One real run settles it, which is
   B-2026-09-23-3 (still open — no run against a large hosted model this session).
3. **Only if that fails does engine-level state identity earn its cost.** It is `search.py` and
   `state.py`, the most conservative code here, plus a new `Environment` member every world inherits.
   Nothing measured so far justifies it.

## What stays true from the first draft

Two things survive, and they are the user's own point:

- **Merging on appearance would be wrong.** Two states can hold the same facts and differ in `failed`
  and `tried` — the pruning history that makes a dead end cost one probe instead of one per turn.
- **The fact string bakes in the action that produced it.** `Observation.fact()` is
  `"{move.label()} -> ok: {text}"`, so the same cell learned by `step(...)` and by `look(...)` yields
  two different strings for one piece of knowledge. Any future attempt to hash `state.facts` for
  identity detects identical *histories*, not identical knowledge, and will appear to work while doing
  nothing.

Both are worth knowing. Neither makes state identity the next thing to build.

## Parked, with the reason

Engine-level confluence detection (`Environment.state_key`, union the pruning histories on a collision)
is **not queued as work**. It is a real idea with no evidence behind it yet, and the measurement above
moved the likely cause elsewhere. Revisit only if a real model, shown everything it has learned, still
re-probes what it knows.
