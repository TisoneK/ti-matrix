# Brief — draw the branches, not just the path: the alternatives are folded and nobody renders them

**Raised by the user, 2026-09-23.** Written by Mara (S004) after measuring it.

> we saw matrix but not multi universe and nodes

The user is right, and the gap is narrower and more fixable than it looks: **the data is
already there, already folded, and nothing consumes it.**

## What is true, measured

At every step the engine proposes up to `max_branches` actions, **probes every one of
them against the real world**, and **scores every one of them**. Only one is applied.
The rest are real observations with real evaluator scores attached — and they vanish.

Across the saved `builtin` runs in the library right now:

```
186 decision points
 54 alternatives probed, scored, and discarded   (29% as many again)
```

The tree draws 186 nodes in a line. The 54 roads not taken are invisible.

**A correction to my own first read of this.** I first sampled one run and found 38 of 39
steps offering a single option, and said the search was not branching at all. That run was
an outlier. Measured across runs, branching happens on roughly 30–45% of steps and varies
with the maze — a corridor offers one way on, a junction offers three. The search *is*
branching. The problem is purely that the branching is not drawn.

## Where it already exists

- `ti_matrix/search.py` emits a `candidates` event carrying **every** proposed move
  (`fp`, `label`, `tool`, `why`), then a `probe` and an `evaluation` per candidate, each
  stamped with `at: <node>` — the node the run was standing on.
- `app/renderer/core/decisions.ts` already folds all of that into
  **`Decision.options: Candidate[]`**, and `Candidate` already carries everything needed:
  `label`, `why`, `ok`, `excerpt` (what the world actually answered), `ms`, `predicted`,
  **`progress`** (the evaluator's own score for that outcome), `reason`, and a flag for
  the one that was chosen.
- `core/tree.ts` even exports `siblingContext(tree, decisions, nodeId)`.

And then:

```
$ grep -rn "\.options" app/renderer/panels/*.tsx app/renderer/shell/*.tsx
(no matches)
```

**Nothing in the app renders `options`.** Not the ledger, not the tree. `siblingContext`
is called in exactly one place — the `<title>` of a tree node, i.e. an OS tooltip on
hover. The fold was written and never wired to a surface.

## Why the tree is a spine, and why that part is correct

`readTree` builds a `TreeNode` only from a `state` event, and the engine emits `state`
only for a move it **applied**. That is right and should not change: a node means "the run
actually stood here". The engine is a beam of one with backtracking — it commits to one
move per step — so the trunk is genuinely a line, and dead ancestors after a retreat are
genuinely the only other real nodes.

The alternatives are not unexplored subtrees and must not be drawn as though they were.
They are **leaves that were looked at once and rejected** — each with one real observation
and one score. Drawing them as speculative branches would invent a search that never
happened; drawing them as stubs off the node they were considered at is exactly true.

## What to build

**1. Sibling stubs in the tree.** At each node, a short spur per rejected candidate,
ending in a small open marker — visibly different from a node the run entered. Colour by
outcome using the palette already in `core/flags.ts`: refused by the world is the red the
ledger already uses for a surprise, scored-but-not-chosen is the amber of a low-confidence
move. Hovering a stub gives its score and the world's own answer; the chosen edge stays
the solid one. The branch points then become visible as branch points, which is the whole
of the user's complaint.

**2. The alternatives in the ledger row.** A decision currently says what was taken and
what it was worth. It should be able to say *what else was on the table and what those
scored* — that is the difference between "it went east" and "it went east at 0.41 over
north at 0.38, and the world refused west". `options` already holds it; this is a
rendering job, not a fold.

**3. Say it in the header.** "39 states · 1 retreat" should also carry the alternatives
considered, because a search that weighed 54 options and a walk that weighed none look
identical today.

## Why this matters more than it sounds

This is the product's actual pitch. "Watch an AI agent think — and check whether to
believe it" is not answerable from the path alone: a path shows what it did, and
believing it requires seeing **what it passed up and why**. A single line of nodes is a
record of a decision already made. The branch points, with scores on every arm, are the
decision itself.

It is also the honest answer to the name. The maze map shows the fog; the ledger shows
the belief; the tree is the only panel that could show the *shape of the search*, and
right now it shows a list.

## Watch out for

- **Do not invent depth.** A rejected candidate was probed once. It has no subtree and no
  descendants; if the layout makes it look explorable, the picture lies.
- **Folding already exists** (`view.folds`, cold-branch collapse) and stubs multiply the
  node count by ~1.3. Fold stubs with the branch they hang off, not separately.
- **A predicted outcome is not a fact.** `Candidate.predicted` marks a simulated result;
  the engine already refuses to settle on one, and the stub should mark it too rather than
  drawing it like a real probe.
- `siblingContext` exists but was written for a tooltip. Check whether it gives what the
  stubs need before extending it, and if it does not, the fold in `decisions.ts` is the
  place to change — not the panel.
