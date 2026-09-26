"""Spending the engine's accumulated experience on the fan — the one place a proposal is chosen from.

The engine's scarce resource is its model budget: one call to propose a fan, one to score it. When a model
offers more candidates than the fan has room for, its own ordering decides what gets probed — and the model's
ordering is uninformed, because it does not know which tools work in *this* world. The engine's own runs do
know.

Three changes, each of which a caller can turn off:

  - **It asks for a few more candidates than the fan needs** (``extra``). This is the one that makes the rest
    matter: a proposer cuts its own list to the fan size before anyone sees it, so by the time the experience
    could reorder the candidates, the useful ones may already be gone. Asking for two more costs output
    tokens inside the same model call, not another call.
  - **Hopeless tools are dropped.** A tool really tried at least ``min_tries`` times here, never chosen and
    never once a real success does not deserve a slot that a plausible action could use — and neither does one
    that keeps being proposed and only ever *predicted*, since this engine cannot perform it at all and every
    proposal costs a model call.
  - **The rest is ordered by prior** — how often the tool has been chosen, and how much progress it produced,
    with an untried tool sitting neutrally in the middle rather than last, because exploring is not a mistake.

One floor, because the alternative is worse than either: if filtering would leave the fan empty, the best
candidate the model offered is kept. A learner that answers "nothing is worth trying" to a goal the model had
a plausible idea for has made the engine worse, not smarter.
"""
from __future__ import annotations

from typing import Any, Optional

from ti_matrix.learning.statistics import HOPELESS_TRIES, Statistics
from ti_matrix.protocols import Action, Proposer

EXTRA_CANDIDATES = 2  # how much wider than the fan to ask, so experience has something to choose between


class LearningProposer:
    """A proposer that proposes like the model, ordered by what this environment has actually rewarded."""

    def __init__(
        self,
        inner: Proposer,
        statistics: Statistics,
        *,
        drop_hopeless: bool = True,
        min_tries: int = HOPELESS_TRIES,
        extra: int = EXTRA_CANDIDATES,
    ) -> None:
        self.inner = inner
        self.statistics = statistics
        self.drop_hopeless = drop_hopeless
        self.min_tries = min_tries
        self.extra = max(0, extra)

    async def propose(self, state: Any, n: int, avoid: set[str]) -> list[Action]:
        moves = list(await self.inner.propose(state, n + self.extra, avoid))
        if not moves:
            return []
        stats = self.statistics
        dead = stats.hopeless_tools(self.min_tries) if self.drop_hopeless else set()
        kept = [m for m in moves if m.tool not in dead]
        if not kept:  # never propose nothing when the model proposed something
            kept = [max(moves, key=lambda m: stats.prior(m.tool))]
        # sorted() is stable, so candidates the experience cannot separate stay in the model's own order.
        return sorted(kept, key=lambda m: stats.prior(m.tool), reverse=True)[:n]

    def considered(self, state: Any) -> Optional[int]:
        """Pass through how many actions the inner proposer was choosing from.

        A wrapper that swallowed this would quietly cost the record a number nobody could recover: the
        engine asks the proposer it holds, and the proposer it holds is this. The symptom was exactly
        that — chess reported "4 of 35" with learning off and nothing at all with it on, because the
        app turns learning on by default. An optional capability has to survive being wrapped, or it is
        only optional in the sense that it usually disappears.
        """
        inner = getattr(self.inner, "considered", None)
        if not callable(inner):
            return None
        try:
            return inner(state)
        except Exception:  # noqa: BLE001 — bookkeeping must never end a run
            return None

    def __repr__(self) -> str:
        return (f"LearningProposer(inner={type(self.inner).__name__}, "
                f"tools={len(self.statistics.by_tool)}, extra={self.extra})")


__all__ = ["EXTRA_CANDIDATES", "LearningProposer"]
