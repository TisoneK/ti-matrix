# Brief — "we are back where we were": the one sameness worth detecting, and the two that are not

**Raised by the user, 2026-09-23** — *"this is a matrix, endless possibilities, and what may seem they
look alike in multiple worlds or the same world could have different states."* Written by Mara (S004).

The design already agrees with that sentence, in more detail than I expected. What is missing is not
the thinking — it is that nothing in any queue points at it, so it would never have been done.

## What the project already decided

`DESIGN.md` separates three kinds of sameness and rules on each:

> *The same answer is not the same state.* Two methods reach one answer; two routes reach one
> destination; neither route is invalidated by the other. **That is not a property to collapse.**
>
> *The same knowledge is the honest form of confluence.* … Sameness of what is **known** — not of what
> was answered, not of how it was reached — is the version worth detecting, **and it is not detected
> today.** Every fingerprint in the engine belongs to an action, never to a state, so the engine knows
> "this move was already tried" and cannot know "we are back where we were."
>
> *The same action is what the search can actually act on.*

And a passing test measures the cost —
`tests/test_maze_adapter.py::test_the_engine_cannot_tell_it_has_been_somewhere_before`:

> "the engine knows an *action* was tried, never that a *place* is known … the same place was learned
> twice."

So: reasoned about in the design, asserted in the suite, **in no backlog and no ADR.** That is the state
a known limitation goes to die in.

## Both halves of the user's sentence are real, and they pull opposite ways

**Different-looking, same place.** Two routes meet at a junction. The engine pays a fresh probe to
re-learn a cell it already holds, and the tree grows two subtrees for one location. Wasted budget, and
a picture of the search that overstates how much ground was covered.

**Same-looking, different state.** Two states can hold the same facts and still differ in what they can
do next, because `AgentState` also carries `failed` and `tried` — the pruning history. Collapsing on
appearance would throw away exactly the record of what has been ruled out, which is the thing that makes
a dead end cost one probe instead of one per turn.

Which is why the rule is *sameness of what is known*, and why the merge is a **union of the pruning
histories** rather than a replacement. Two states that know the same world cannot usefully disagree
about what to do next; the only difference left unions cleanly.

## The obstacle nobody has hit yet: a fact is not just knowledge

`Observation.fact()` builds `f"{move.label()} -> {'ok'}: {text}"`. **The action that produced an
observation is baked into the fact string.** So the same cell learned by `step(cell=1,1,
direction=south)` and by `look(cell=1,2)` produces two different facts for one piece of knowledge.

A naive hash over `state.facts` therefore does **not** detect confluence — it detects identical
histories, which is nearly the thing that never happens. This is the trap waiting for whoever picks
this up, and it is why the obvious one-line implementation will appear to work and do nothing.

## The design that follows from ADR-4

The engine must not guess what "the same place" means — it is host-neutral and a place is a world's
concept, not the loop's. So the world declares it:

```python
class Environment(Protocol):
    def state_key(self, state) -> Optional[str]: ...   # optional; None means "I cannot say"
```

- The maze returns the set of cells it has entered, canonically ordered. Two routes to one junction
  collide correctly, and the fact strings never enter into it.
- Chess would return the position, side to move, castling rights and en passant — the same fields a
  transposition table hashes, and for exactly the same reason: two boards that look alike differ in
  what is legal next.
- A world that cannot answer returns `None` and simply gets today's behaviour. Nothing regresses.

On a collision the engine unions `failed`, keeps the cheaper trail, and does not re-probe. That is the
payoff and it is measurable: the maze test above becomes an assertion that the place is learned **once**.

## What this does to the picture, and why it pairs with B-2026-09-23-8

`DESIGN.md` again, and this is the line that answers "endless possibilities" most directly:

> The engine emits a tree with parent links and **never searches it** — the beam of one walks a line
> while the log describes a graph, which is why a game-tree explorer is something anyone can build on top.

Confluence detection makes the log an honest **DAG**: a node reachable two ways has two parents. The
tree panel currently draws a spine and hides the rejected siblings (B-2026-09-23-8); it would then also
need to draw a join. That is a better picture than either fix alone — the branch points show what was
weighed, and the joins show where the possibilities were never as many as they looked.

**But the merge is in the engine's bookkeeping, not on the screen.** Per `DESIGN.md`, two routes to one
destination are both real and neither invalidates the other; the run took one of them. The trail stays
a trail. Collapsing the drawing would destroy the comparison the Compare view exists for.

## Scope warning

This is `ti_matrix/search.py` and `ti_matrix/state.py` — engine core, the most conservative code in the
repo, under `test_boundary` and 236 tests. It is also the first change that would add a member to the
`Environment` protocol, which every world and every user-written world then inherits. Optional with a
`None` default is what keeps that from being a breaking change, and it should land **before**
B-2026-09-23-11 opens worlds to users, not after — adding a protocol member once people have written
against it is a different and worse job.

## Question for the user

Is the payoff you want the **saved budget** (stop re-probing what is known) or the **truer picture**
(the tree showing where possibilities converge)? Both fall out of the same detection, but they argue for
different next steps: the first is engine-only and invisible; the second needs the tree panel to learn
to draw a join, and is the one that speaks to "this is a matrix."
