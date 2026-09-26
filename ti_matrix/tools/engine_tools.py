"""The tool the engine itself insists on, wrapped around whatever environment it is driving.

The engine's own tools are the ones whose absence makes every environment worse and whose presence no
environment should have to implement. There is exactly one, and it earns the place by being the one thing
the engine knows that an environment never will: ``recall`` — what has been established here. Which actions
have paid off, which have never once worked, and the facts real observations left behind.

It answers over **two** records, and says which is which:

  - **this run**, built here. A proposer is handed one flat ``AgentState`` and cannot select from it: no
    node id, no parent, no structure, just a tuple of strings. Showing all of it is the floor, not
    selection, and stops working the moment a world is large — fifty thousand files do not fit in a
    prompt. ``recall`` is how a model asks for the part it needs and ignores the rest, and because it is
    an action, *what it chose to look up is in the ledger* like every other move.
  - **earlier runs**, when a host supplies a ``Memory``. Optional: a caller with nothing remembered yet
    still gets the within-run half, which needs no storage and no configuration.

Nothing new was needed in the engine for the first of those, and that is the point of it living here. This
wrapper is already in the probe path, so every observation the run makes passes through it — the record
builds itself out of traffic that was going by anyway. The engine keeps no state it did not already keep,
``Environment.probe`` keeps its signature, and no world has to implement anything.

Everything else is the environment's and stays there. The set is marked ``builtin``, so a user's own tool of
the same name wins by default — unless the host prefers otherwise.
"""
from __future__ import annotations

import time
from typing import Optional, Protocol, runtime_checkable

from ti_matrix.protocols import Action, ActionSpec, Observation


@runtime_checkable
class Memory(Protocol):
    """What the engine's memory tool answers from — the accumulated record of its own previous runs.

    Declared here, next to the only thing that consumes it, rather than in the package that implements it:
    the dependency runs one way, so the engine's tool set never has to know how experience is stored.
    """

    def recall(self, text: str = "", limit: int = 8) -> str: ...


class RunMemory:
    """What *this* run has established, accumulated from the observations passing through the wrapper.

    Append-only and de-duplicated, which is what the engine already believes: a real observation from a
    probe nobody selected is still a fact (``AgentState.learn``), and a retreat keeps every fact it
    learned on the way down. So a record that only ever grows matches the search's own semantics rather
    than approximating them — and a fan is probed concurrently, so a record that could be clobbered by
    a sibling probe would come back wrong.
    """

    def __init__(self) -> None:
        self._facts: list[str] = []
        self._times: list[float] = []  # `time.monotonic()` when each fact was observed, paired by index
        self._seen: set[str] = set()

    def observe(self, observation: Observation) -> None:
        """Remember a real result. Failures and predictions are not facts and are not kept."""
        if not observation.ok or observation.predicted:
            return
        fact = observation.fact()
        if fact in self._seen:
            return
        self._seen.add(fact)
        self._facts.append(fact)
        self._times.append(time.monotonic())

    def __len__(self) -> int:
        return len(self._facts)

    def recall(self, text: str = "", limit: int = 8) -> str:
        """The facts that best match ``text``, most relevant first; the most recent when asked for nothing.

        Scoring is lexical and deliberately dumb — how many of the asked-for words a fact contains. A
        cleverer ranking would be an unverifiable belief in the one place this engine refuses to keep
        them, and the caller can see the words it asked with.

        Every line is marked with how long ago it was observed, so a forty-second-old reading is never
        handed back with the confidence of a fresh one. It needs no new probe and no new control flow:
        the model already asked to be shown its own memory.
        """
        limit = max(1, min(int(limit), 40))
        wanted = [w for w in _words(text) if w]
        if not wanted:
            idx = list(range(len(self._facts)))[-limit:]
        else:
            scored = [(sum(w in self._facts[i].lower() for w in wanted), -i, i) for i in range(len(self._facts))]
            idx = [i for score, _, i in sorted(scored, reverse=True) if score > 0][:limit]
        return _render([(self._facts[i], self._times[i]) for i in idx])


def _words(text: str) -> list[str]:
    return [w.strip(".,:;!?'\"()[]<>").lower() for w in str(text).split()]


def _render(pairs: list[tuple[str, float]]) -> str:
    now = time.monotonic()
    return "\n".join(f"- {fact} ({_age(now - t)} ago)" for fact, t in pairs)


def _age(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{seconds / 60:.1f}m"


class EngineTools:
    """Wraps an environment and adds the engine's own tools to it.

    Every other call is passed straight through, so this is safe to wrap around anything — including a
    ``CompositeEnvironment`` — and safe to leave off, which is the honest default for a caller who has
    nothing to remember yet.
    """

    builtin = True

    def __init__(self, environment, *, memory: Optional[Memory] = None, name: str = "") -> None:
        self._env = environment
        self._memory = memory
        # Built from traffic, not from configuration: every probe passes through `probe` below.
        self._run = RunMemory()
        self.name = name or f"{getattr(environment, 'name', 'environment')}+engine"

    def tools(self) -> dict[str, ActionSpec]:
        return {
            **self._env.tools(),
            "recall": ActionSpec(
                "recall",
                "Look back at what has already been established here, instead of probing for it again. "
                "Give the words you care about and it answers with the matching facts — from this run, "
                "and from earlier runs where there are any.",
                '{"text": "<what to look for>", "limit": 8}', read_only=True),
        }

    def is_read_only(self, action: Action) -> Optional[bool]:
        return True if action.tool == "recall" else self._env.is_read_only(action)

    def close(self) -> None:
        """Give back what the wrapped environment holds. A wrapper that hid this would leak a browser."""
        closer = getattr(self._env, "close", None)
        if callable(closer):
            closer()

    async def probe(self, action: Action) -> Observation:
        if action.tool != "recall":
            # Everything the run learns passes through here, so the within-run record needs no engine
            # change and no access to the state: it is built from traffic already going by.
            observation = await self._env.probe(action)
            self._run.observe(observation)
            return observation
        try:
            return Observation(action, True, self._recall(**action.args))
        except TypeError as exc:  # wrong or missing arguments — a failure the search can use
            return Observation(action, False, f"bad arguments for recall: {exc}")
        except Exception as exc:  # noqa: BLE001 — a failed probe is an observation, never a crash
            return Observation(action, False, f"{type(exc).__name__}: {exc}"[:400])

    def _recall(self, text: str = "", limit: int = 8) -> str:
        """Both records, labelled, because where a fact came from changes how much it is worth.

        This run's observations are about the world as it is right now. Earlier runs' are about how this
        world has behaved before, which is a weaker claim — a file may have moved, a page may have
        changed. Merging them silently would let the older, weaker claim pass for the newer one.
        """
        parts: list[str] = []
        here = self._run.recall(text, limit)
        if here:
            parts.append(f"this run:\n{here}")
        if self._memory is not None:
            before = self._memory.recall(text=text, limit=limit)
            if before and before.strip():
                parts.append(f"earlier runs:\n{before}")
        if not parts:
            return ("nothing established here yet" if not str(text).strip()
                    else f"nothing established here matches {str(text).strip()!r}")
        return "\n\n".join(parts)


__all__ = ["EngineTools", "Memory", "RunMemory"]
