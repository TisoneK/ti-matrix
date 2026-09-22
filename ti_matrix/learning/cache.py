"""Not asking an unchanged world the same question twice.

A read-only probe of a world that has not moved since the last identical probe has one honest answer, and
asking again spends real time to learn nothing. That is the whole idea; the design work is in the two things
that make it safe:

  - **Only reads are cached, and only successes.** A write's whole point is to change something (and this
    engine does not perform writes anyway), and a *failure* may be transient — a lock, a timeout, a missing
    process — so caching one would turn a moment's bad luck into a permanent falsehood.
  - **"Unchanged" is the caller's word, not this wrapper's guess.** ``version`` is a callable returning a
    token that changes whenever the world does (a file's mtime, a commit hash, a counter). With no version
    the cache lives exactly as long as the object — the honest scope for one run, stated rather than assumed.

A hit is reported like any other observation, carrying its own near-zero latency, so a run's events show the
saving instead of hiding it.
"""
from __future__ import annotations

from typing import Callable, Optional

from ti_matrix.protocols import Action, ActionSpec, Observation


class CachingEnvironment:
    """Wraps an environment and answers a repeated read-only probe from the last real answer."""

    def __init__(self, inner, *, version: Optional[Callable[[], object]] = None) -> None:
        self.inner = inner
        self.name = getattr(inner, "name", "environment")
        self._version = version
        self._cache: dict[tuple[str, object], Observation] = {}
        self.hits = 0
        self.misses = 0

    def tools(self) -> dict[str, ActionSpec]:
        return self.inner.tools()

    def is_read_only(self, action: Action) -> Optional[bool]:
        return self.inner.is_read_only(action)

    def _token(self) -> object:
        if self._version is None:
            return ""  # no version given: this object's own lifetime is the scope
        try:
            return self._version()
        except Exception:  # a version probe that fails must not fail the run — it just forces a fresh read
            return object()

    async def probe(self, action: Action) -> Observation:
        if self.inner.is_read_only(action) is not True:
            return await self.inner.probe(action)  # nothing but a read is ever remembered here
        key = (action.fingerprint(), self._token())
        remembered = self._cache.get(key)
        if remembered is not None:
            self.hits += 1
            return remembered
        self.misses += 1
        obs = await self.inner.probe(action)
        if obs.ok and not obs.predicted:
            self._cache[key] = obs
        return obs

    def stats(self) -> str:
        total = self.hits + self.misses
        saved = f" ({self.hits / total:.0%} of {total})" if total else ""
        return f"read-only probes asked: {total}; served from cache: {self.hits}{saved}"


__all__ = ["CachingEnvironment"]
