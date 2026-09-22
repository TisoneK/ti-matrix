"""The canonical state. Immutable: a transition returns a NEW state.

The model never owns this — it is rebuilt from observations, rendered compactly
for the model, and fingerprinted so an action that failed is never proposed twice.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ti_matrix.protocols import Action, Evaluation, Goal, Observation

_FACT_CHARS = 320
_UI_FACTS = 12  # how many facts a state carries to the UI (the model sees the last 8)


@dataclass(frozen=True)
class AgentState:
    goal: Goal
    facts: tuple[str, ...] = ()  # what real observations established
    failed: tuple[str, ...] = ()  # action fingerprints that failed or led nowhere
    tried: tuple[str, ...] = ()  # every action fingerprint applied on this path
    progress: float = 0.0
    depth: int = 0
    trail: tuple[str, ...] = ()  # human-readable path of applied actions

    def apply(self, obs: Observation, evaluation: Evaluation) -> "AgentState":
        """State[n] + Action + Outcome -> State[n+1] (a predicted outcome is never applied as fact)."""
        fp = obs.move.fingerprint()
        return replace(
            self,
            facts=self.facts + ((obs.fact(),) if obs.ok and not obs.predicted else ()),
            failed=self.failed + ((fp,) if not obs.ok else ()),
            tried=self.tried + (fp,),
            progress=max(self.progress, evaluation.progress) if obs.ok else self.progress,
            depth=self.depth + 1,
            trail=self.trail + (obs.move.label(),),
        )

    def learn(self, obs: Observation) -> "AgentState":
        """A real observation from a probe that was NOT selected is still a fact."""
        if not obs.ok or obs.predicted:
            return self
        return replace(self, facts=self.facts + (obs.fact(),))

    def retreat_to(self, parent: "AgentState") -> "AgentState":
        """Back up to ``parent`` from a dead end: keep every real fact learned, remember every failed
        action, and prune the action that led INTO this dead end so the branch is not re-taken."""
        restored = replace(parent, facts=self.facts, failed=tuple(dict.fromkeys(parent.failed + self.failed)))
        return restored.with_failed(self.tried[-1]) if self.tried else restored

    def with_failed(self, fingerprint: str) -> "AgentState":
        """An action that led nowhere is remembered so it is not proposed again."""
        return self if fingerprint in self.failed else replace(self, failed=self.failed + (fingerprint,))

    def render(self, max_facts: int = 8) -> str:
        """Compact canonical view for the model (bounded, no chat history)."""
        lines = [f"GOAL: {self.goal.text}"]
        if self.goal.constraints:
            lines.append("CONSTRAINTS: " + "; ".join(self.goal.constraints))
        lines.append(f"PROGRESS: {self.progress:.2f}   DEPTH: {self.depth}")
        lines.append("KNOWN FACTS:" + ("" if self.facts else " (none yet)"))
        lines += [f"  - {f}" for f in self.facts[-max_facts:]]
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
            "failed_fps": list(self.failed),
            "trail": list(self.trail),
        }


__all__ = ["AgentState", "Action", "Goal"]
