"""The canonical state. Immutable: a transition returns a NEW state.

The model never owns this — it is rebuilt from observations, rendered compactly
for the model, and fingerprinted so an action that failed is never proposed twice.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Optional

from ti_matrix.protocols import Action, Evaluation, Goal, Observation

_FACT_CHARS = 320
_UI_FACTS = 12  # how many facts a state carries to the UI (the model sees the last 8)


@dataclass(frozen=True)
class AgentState:
    goal: Goal
    facts: tuple[str, ...] = ()  # what real observations established
    fact_times: tuple[float, ...] = ()  # when each fact was observed — `time.monotonic()`, paired
    # index-for-index with `facts` rather than folded into it, so every existing reader of `facts` (render,
    # to_dict, the reasoners, RunMemory) keeps working unchanged. A fact and its time are always appended
    # together — the two tuples are always the same length.
    failed: tuple[str, ...] = ()  # action fingerprints that failed or led nowhere
    tried: tuple[str, ...] = ()  # every action fingerprint applied on this path
    progress: float = 0.0
    depth: int = 0
    trail: tuple[str, ...] = ()  # human-readable path of applied actions

    def apply(self, obs: Observation, evaluation: Evaluation, observed_at: Optional[float] = None) -> "AgentState":
        """State[n] + Action + Outcome -> State[n+1] (a predicted outcome is never applied as fact).

        ``observed_at`` is the moment (``time.monotonic()``) the underlying probe actually returned — the
        caller knows this more precisely than "now" (an evaluator call may sit between the two). Defaults
        to "now" for callers that do not track it.
        """
        fp = obs.move.fingerprint()
        learns = obs.ok and not obs.predicted
        return replace(
            self,
            facts=self.facts + ((obs.fact(),) if learns else ()),
            fact_times=self.fact_times + ((observed_at if observed_at is not None else time.monotonic(),) if learns else ()),
            failed=self.failed + ((fp,) if not obs.ok else ()),
            tried=self.tried + (fp,),
            progress=max(self.progress, evaluation.progress) if obs.ok else self.progress,
            depth=self.depth + 1,
            trail=self.trail + (obs.move.label(),),
        )

    def learn(self, obs: Observation, observed_at: Optional[float] = None) -> "AgentState":
        """A real observation from a probe that was NOT selected is still a fact."""
        if not obs.ok or obs.predicted:
            return self
        return replace(
            self,
            facts=self.facts + (obs.fact(),),
            fact_times=self.fact_times + (observed_at if observed_at is not None else time.monotonic(),),
        )

    def retreat_to(self, parent: "AgentState") -> "AgentState":
        """Back up to ``parent`` from a dead end: keep every real fact learned, remember every failed
        action, and prune the action that led INTO this dead end so the branch is not re-taken."""
        restored = replace(
            parent, facts=self.facts, fact_times=self.fact_times,
            failed=tuple(dict.fromkeys(parent.failed + self.failed)),
        )
        return restored.with_failed(self.tried[-1]) if self.tried else restored

    def with_failed(self, fingerprint: str) -> "AgentState":
        """An action that led nowhere is remembered so it is not proposed again."""
        return self if fingerprint in self.failed else replace(self, failed=self.failed + (fingerprint,))

    def render(self, max_facts: Optional[int] = None) -> str:
        """Canonical view for the model: everything known, bounded per fact rather than by count.

        This used to show the last eight facts. Measured, that was the most expensive line in the
        engine. Holding one reasoner constant and varying only this window against the maze:

            last 8 facts   266 probes, 160 re-learned a known place  (60%)
            last 16        226 probes, 106                           (47%)
            last 32        140 probes,  20                           (14%)
            every fact     120 probes,   0                           ( 0%)

        Forgetting more than doubled the work. Real runs agreed: `deepseek-flash` re-probed places it
        already knew on 42% and 48% of its successful probes, while the rule-based seats — which read
        every fact — did it zero times in 320. At probe thirty of forty the model was being shown the
        last eight places it had been and had no record of the first twenty-two.

        Nothing was bought with that. A complete forty-probe run's entire fact set is 1,888 characters,
        about 470 tokens; eight facts is about 98. The bound that matters is already in place and is a
        real one — `_FACT_CHARS` truncates each observation as it becomes a fact, so a 5,000-character
        page read enters the state at 320 — and the run's own budget caps how many there can be. A
        hundred-probe run at the per-fact ceiling is roughly 8,000 tokens, which is the worst case, not
        the typical one. A second bound on top of those cost more than half the probes in the run.

        `max_facts` stays for a caller that wants a smaller view on purpose.
        """
        lines = [f"GOAL: {self.goal.text}"]
        if self.goal.constraints:
            lines.append("CONSTRAINTS: " + "; ".join(self.goal.constraints))
        lines.append(f"PROGRESS: {self.progress:.2f}   DEPTH: {self.depth}")
        lines.append("KNOWN FACTS:" + ("" if self.facts else " (none yet)"))
        shown = self.facts if max_facts is None else self.facts[-max_facts:]
        lines += [f"  - {f}" for f in shown]
        if self.trail:
            lines.append("MOVES SO FAR: " + " | ".join(self.trail[-6:]))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": len(self.facts),
            "failed": len(self.failed),
            "progress": self.progress,
            "depth": self.depth,
            # What the state actually holds, for the UI: the real observations (the same bounded text the
            # model is shown — never reasoning), the fingerprints of the actions this state has ruled out,
            # and the path of applied actions that reached it. All bounded; a UI can read the search.
            "fact_list": [f[:_FACT_CHARS] for f in self.facts[-_UI_FACTS:]],
            # Paired index-for-index with `fact_list` — how old each shown fact is, as of right now. A
            # reader zips the two rather than the engine folding age into the text itself.
            "fact_ages_ms": [int((time.monotonic() - t) * 1000) for t in self.fact_times[-_UI_FACTS:]],
            "failed_fps": list(self.failed),
            "trail": list(self.trail),
        }


__all__ = ["AgentState", "Action", "Goal"]
