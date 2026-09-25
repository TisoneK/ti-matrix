# Brief — chess, or: the tree is a line because the world is a line

**Raised by the user, 2026-09-23** ("what about chess scenarios or real matrix or multi
universe"). Written by Mara (S004) after measuring the maze's branching factor.

## The measurement that reframes B-2026-09-23-8

```
maze:  1.35 candidates per decision, across 202 decisions
chess: ~35 legal moves per position
```

B-2026-09-23-8 says the tree draws only the path taken and hides the rejected siblings,
which is true and worth fixing. But it is **not sufficient on its own**, and this number
is why: at 1.35 candidates per decision there are 0.35 siblings per node to draw. Drawing
them turns a line into a line with occasional whiskers. The product is named for a matrix
of possibilities and the shipped world does not have one.

So the two items are complementary and neither works alone:

- **B-8 without a branching world** → still a line, now with stubs.
- **A branching world without B-8** → a line with 34 invisible siblings per node, which is
  worse, because the search really did weigh them.

## Why chess is the right world, specifically for this product

It is not "a fun demo." It is the domain this engine's whole vocabulary already comes from.

- **~35 legal moves per position** — a real fan, at every single node. The tree branches
  because the world branches.
- **Everyone already has the intuition.** Nobody needs the concept of a search tree
  explained in chess; the panel stops being an abstraction.
- **Belief is checkable against ground truth.** This is the one that matters. The app's
  pitch is "watch it think — and check whether to believe it." In the maze, "was it right?"
  is only answerable at the end. In chess, every single evaluation is checkable: the ledger
  says it believed this move was worth 0.7, and it hangs a queen. **That is the product's
  claim made concrete and falsifiable**, and no other shipped world offers it.
- **Blunders are legible.** A retreat in the maze is a corridor that dead-ended. A retreat
  in chess is "it saw the refutation one move later", which reads as reasoning.

## Feasibility under the standard-library rule

`python-chess` is third-party and therefore forbidden inside `ti_matrix/` — same constraint
as ADR-2. That is fine; this is a well-trodden ~400 lines:

- Board as a 64-square array, legal move generation with the awkward bits (castling rights,
  en passant, promotion, pinned pieces, check evasion) — tedious, not hard, and every edge
  case is testable against known positions.
- **Perft is the test.** Move-generation correctness has published node counts for known
  positions at each depth; a handful of `perft` assertions proves the generator or fails it
  loudly. Do not hand-roll test expectations — use the published numbers.
- Evaluation for the built-in seats: material plus a simple piece-square table. Deterministic,
  instant, no model, and good enough to make sensible-looking moves.

## The design constraint the maze already solved

The engine probes a **fan** of candidates from one state before applying any of them. So a
chess action must not mutate a shared board — probing `e4` and then `d4` from the same
position has to leave the position alone.

The maze solved this by making the action carry its own origin (`step(cell, direction)`),
with the environment keeping only a monotonic set of what has been seen. Do the same here:
**the action carries the position** (`move(fen, "e2e4")`), and the observation returns the
resulting position plus the opponent's reply. Stateless per probe, so a fan is safe.

The opponent's reply belongs to the world, not the agent — a fixed weak engine, or random
legal, seeded so a run is reproducible the way a seeded maze is.

## Set expectations honestly, in the brief and in the UI

The engine is **a beam of one with backtracking, not minimax**. It commits to a move,
explores forward, and retreats when nothing improves. It will not play strong chess, and
nobody should try to make it. This world exists to make the *search legible*, not to win
games. If a future session starts adding alpha-beta to the engine core to make it play
better, it has misread what the world is for — the engine is host-neutral and stays that way.

Also: with `max_branches: 3`, a chess run weighs 3 of ~35 legal moves. **Report both
numbers.** "3 of 35 considered" is a more honest and more interesting thing for the tree
header to say than a raw node count, and it is the kind of admission the whole app is built
around. It may be worth more than drawing all 35 arms.

## On "real matrix / multi universe"

Taking that as the instinct behind the question rather than a separate feature: the matrix
*is* the fan of legal moves at each node, and the universes *are* the branches the search
weighed and abandoned. The product already computes both and throws both away. Chess makes
them big enough to see; B-8 draws them. There is no third thing to build.

## Order

1. **B-8 first** if only one gets done — it is small, the fold already exists, and it
   improves every world including this one.
2. **Chess after**, because it is what makes B-8 worth looking at.

Both are smaller than B-2026-09-23-6 (duplicate files), and unlike it, both go directly at
the thing the user keeps pointing out.
