"""Several environments presented as one, each action routed to the source that owns it.

The engine cannot compose this for itself: an ``Environment`` is one tool table and one ``probe``, so
presenting a filesystem, a repository's memory and an application's own actions together needs an
environment that is *made of* environments. That is all this is — it decides nothing about precedence (the
tool set does that) and performs nothing of its own except routing.
"""
from __future__ import annotations

from typing import Optional

from ti_matrix.protocols import Action, ActionSpec, Observation
from ti_matrix.tools.registry import Resolution, ToolSet, ToolSetError, ToolSource


class CompositeEnvironment:
    """Many environments, one tool table, every action routed to the environment that owns it.

    Each source environment contributes its ``name`` as its provider, and ``builtin`` (an attribute an
    environment may set) as its standing in a collision. An action resolved under a different name than its
    source gave it is translated on the way in and the answer is returned under the name the engine used, so
    a renaming never leaks into a fingerprint or a fact.
    """

    def __init__(self, *environments, prefer: str = "user", name: str = "") -> None:
        if not environments:
            raise ToolSetError("a composite environment needs at least one environment to present")
        self._envs = tuple(environments)
        self.registry = ToolSet(
            *(ToolSource(getattr(e, "name", "environment"), e.tools(), builtin=getattr(e, "builtin", False))
              for e in self._envs),
            prefer=prefer,
        )
        self.name = name or "+".join(getattr(e, "name", "environment") for e in self._envs)

    def tools(self) -> dict[str, ActionSpec]:
        return self.registry.tools()

    def resolution(self) -> Resolution:
        return self.registry.resolution()

    def is_read_only(self, action: Action) -> Optional[bool]:
        routed = self.registry.route(action)
        if routed is None:
            return None  # not an action any of these environments knows
        source, own = routed
        env = self._env_for(source.provider)
        return env.is_read_only(own) if env is not None else None

    async def probe(self, action: Action) -> Observation:
        routed = self.registry.route(action)
        if routed is None:
            return Observation(action, False, f"no environment here has an action called {action.tool!r}")
        source, own = routed
        env = self._env_for(source.provider)
        if env is None:
            return Observation(action, False, f"the source of {action.tool!r} is not attached")
        obs = await env.probe(own)
        # The answer belongs to the name the engine used, not to the name the source knows.
        return obs if own.tool == action.tool else Observation(action, obs.ok, obs.text, obs.predicted)

    def close(self) -> None:
        """Close every environment under this one that has something to close."""
        for environment in self._envs:
            closer = getattr(environment, "close", None)
            if callable(closer):
                closer()

    def _env_for(self, provider: str):
        for e in self._envs:
            if getattr(e, "name", "environment") == provider:
                return e
        return None


__all__ = ["CompositeEnvironment"]
