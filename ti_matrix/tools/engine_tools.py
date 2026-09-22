"""The tool the engine itself insists on, wrapped around whatever environment it is driving.

The engine's own tools are the ones whose absence makes every environment worse and whose presence no
environment should have to implement. There is exactly one, and it earns the place by being the one thing
the engine knows that an environment never will: ``recall`` — what *previous runs* established here. Which
actions have paid off, which have never once worked, and the facts real observations left behind. A model
given it stops re-deriving the world's affordances from scratch on every run.

Everything else is the environment's and stays there. The set is marked ``builtin``, so a user's own tool of
the same name wins by default — unless the host prefers otherwise.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ti_matrix.protocols import Action, ActionSpec, Observation


@runtime_checkable
class Memory(Protocol):
    """What the engine's memory tool answers from — the accumulated record of its own previous runs.

    Declared here, next to the only thing that consumes it, rather than in the package that implements it:
    the dependency runs one way, so the engine's tool set never has to know how experience is stored.
    """

    def recall(self, text: str = "", limit: int = 8) -> str: ...


class EngineTools:
    """Wraps an environment and adds the engine's own tools to it.

    Every other call is passed straight through, so this is safe to wrap around anything — including a
    ``CompositeEnvironment`` — and safe to leave off, which is the honest default for a caller who has
    nothing to remember yet.
    """

    builtin = True

    def __init__(self, environment, *, memory: Memory, name: str = "") -> None:
        self._env = environment
        self._memory = memory
        self.name = name or f"{getattr(environment, 'name', 'environment')}+engine"

    def tools(self) -> dict[str, ActionSpec]:
        return {
            **self._env.tools(),
            "recall": ActionSpec(
                "recall",
                "What previous runs of this engine established here: which actions have paid off, which "
                "have never worked, and the facts real observations left behind.",
                '{"text": "<what to look for>", "limit": 8}', read_only=True),
        }

    def is_read_only(self, action: Action) -> Optional[bool]:
        return True if action.tool == "recall" else self._env.is_read_only(action)

    async def probe(self, action: Action) -> Observation:
        if action.tool != "recall":
            return await self._env.probe(action)
        try:
            return Observation(action, True, self._memory.recall(**action.args))
        except TypeError as exc:  # wrong or missing arguments — a failure the search can use
            return Observation(action, False, f"bad arguments for recall: {exc}")
        except Exception as exc:  # noqa: BLE001 — a failed probe is an observation, never a crash
            return Observation(action, False, f"{type(exc).__name__}: {exc}"[:400])


__all__ = ["EngineTools", "Memory"]
