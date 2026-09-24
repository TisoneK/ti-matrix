# Brief — letting the seats ask for what they need, instead of being handed everything or a window

**Raised by the user, 2026-09-23** — *"it can intuitively select nodes with the data it needs and
ignore non-relevant nodes."* Written by Mara (S004).

## What I fixed first, and why it is not this

The immediate bug was that `AgentState.render` showed the last eight facts, which cost 60% of a maze
run's probes to re-learning places it already knew (`597b12d`). That is now "show everything", and it
is the right floor — at current scale a whole run's facts are about 470 tokens.

**But "everything" is not selection, it is the absence of it**, and it stops working exactly where this
product is heading: a duplicate-file world over 50,000 files, a long browser session, chess at depth.
Recency was the wrong axis; completeness is the right one only while runs are small.

## Why the seats cannot select today

```python
async def propose(self, state: AgentState, n: int, avoid: set[str]) -> list[Action]
```

One flat state. `AgentState` carries `facts`, `failed`, `tried`, `trail`, `progress`, `depth` — and no
node id, no parent, no structure. Node ids are stamped onto **events** in `search.py:178`, after the
move is applied. `DESIGN.md` names this exactly: *"the engine emits a tree with parent links and never
searches it."*

So the tree is **output, not state**. There are no nodes a proposer could select. There is a flat tuple
of strings.

## The rules already do the thing. The model cannot.

`MazeKnowledge` reads every fact, rebuilds the corridors, computes hop distances from where the run
stands, and proposes the *nearest* unexplored opening — selecting what is relevant and ignoring the
rest, which is the user's sentence almost verbatim. `FilesReasoner` does the same: it ranks candidates
by goal words, path depth, and whether a path runs through somebody else's vendored tree.

That asymmetry is the finding. **The rule-based seats select; the model seat is handed a list.** A
model given forty facts has to re-derive on every call what `MazeKnowledge` computes once, and it has
no way to ask for anything it was not given.

## Status: the cheap half shipped (`76a0590`)

`recall` now answers from the run's own observations as well as from earlier runs, labelled by which.
It needed no protocol change: `EngineTools` already sits in the probe path, so the within-run record
builds itself from traffic going by. `memory=` became optional and the sidecar always wraps, so every
run has it with no storage and no setting.

**What that does not do**, and the reason this row stays open: it selects *facts*, lexically. It does
not let a seat select **nodes**. A proposer still receives one flat state with no structure, so a
question like "what did I learn down the branch I abandoned?" is still unanswerable. That is option A
or B below and it is a protocol change.

## Three ways to close it

**A. Pass the structure to the proposer.** Change the protocol so a proposer receives the history or
the tree. Heavy, and it drags node topology into every proposer including user-written ones — the
opposite of the host-neutral line the engine holds elsewhere.

**B. A `Retriever` port.** Optional, alongside `Simulator`, `Confirmer` and `Synthesizer`: given the
state and the goal, return the facts worth showing. Default is everything, which is today's behaviour,
so nothing regresses. A world can supply a better one, because *only the world knows what relevant
means* — the same argument that put `state_key` on the world in ADR-4. This is the pragmatic option and
it scales to the big worlds.

**C. Recall as an action.** The model proposes `recall(about="the north corridor")` and the world
answers with the matching facts. Retrieval becomes part of the search rather than plumbing underneath
it — it costs a step, it appears in the ledger, and **what the model chose to look up becomes visible
evidence about its reasoning**, which is this product's entire pitch. The most in-character option by
some distance.

Its cost is real: a recall spends a probe that could have been an action, and a model can recall
instead of exploring. That is a budget question and the budget already exists.

**B and C compose.** B is the mechanism, C is the model-facing surface of it.

## When

**Not now.** At 470 tokens per run, "show everything" is correct and selection would be machinery
without a problem. The first world that needs this is **B-2026-09-23-6**, duplicate files over a real
library — where the fact set is thousands of paths and hashes, "everything" is impossible, and
relevance is a genuine query rather than a heuristic.

So the decision to make before that world is written, not after: whether retrieval is a port (B) or an
action (C). Writing the dedupe world first and retrofitting will produce a world shaped around whatever
was convenient.

## Question for the user

Is the appeal of this **efficiency** — the model wastes less on what it already knows — or
**legibility**, the run showing what it chose to look up and what it ignored? The first argues for B,
quietly under the hood. The second argues for C, where recall is a move in the ledger like any other,
and it is the one that fits "watch it think, and check whether to believe it".
