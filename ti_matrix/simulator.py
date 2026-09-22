"""Predicting what an action would do, without doing it.

An engine that can only act cannot reason about acting: a goal that needs a file written, a command run or
a message sent would leave the search blind at exactly the point where the plan gets interesting. A
Simulator closes that gap — it answers "if this were performed, what would it produce?" so the outcome can
be scored and chosen between, while the action itself is never performed.

What a prediction is NOT, and the engine enforces all three: a prediction is labelled ``predicted`` (a UI
can show it as such), it is never learned as a fact (``AgentState.learn/apply`` ignore it), and it can
never settle a goal (``LLMEvaluator`` refuses a ``done`` built on a predicted outcome). A prediction is a
hypothesis the search may use; only a real probe becomes knowledge.
"""
from __future__ import annotations

from ti_matrix.model import ModelPort, parse_json
from ti_matrix.protocols import Action, Observation
from ti_matrix.state import AgentState

_SIM_VIEW_CHARS = 1200  # how much of the action's arguments a prediction is based on


class LLMSimulator:
    """Asks the model what an action would produce, given what the state already knows."""

    def __init__(self, model: ModelPort) -> None:
        self._model = model

    async def predict(self, state: AgentState, action: Action) -> Observation:
        prompt = (
            f"{state.render()}\n\n"
            f"An action is about to be taken but must NOT be performed yet:\n"
            f"  {action.label()}\n"
            f"  arguments: {str(action.args)[:_SIM_VIEW_CHARS]}\n\n"
            "Predict what performing it WOULD produce, using only what is already known above. Be concrete and "
            "honest: if the arguments are missing, wrong or would be refused, say that and mark it as failing. "
            "Do not claim the action happened.\n"
            'Reply with JSON only: {"ok": true, "result": "<what it would produce, briefly>", "why": "<one line>"}'
        )
        obj = parse_json(await self._model.complete(prompt)) or {}
        text = " ".join(str(obj.get("result") or obj.get("why") or "").split())
        if not text:
            # An unusable prediction is reported as a failure rather than guessed at: the search then treats
            # this action as uninformative, which is the truth.
            return Observation(action, False, "could not predict this action", predicted=True)
        return Observation(action, bool(obj.get("ok", False)), text[:900], predicted=True)
