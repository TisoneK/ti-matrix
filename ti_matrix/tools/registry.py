"""Who wins when two sources of actions offer the same tool.

Pure resolution: this module decides names and routes them to the source that owns them. It performs
nothing, imports nothing outside the engine, and holds no state a run can change — so the precedence rules
can be tested on their own, which is the only way they stay trustworthy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ti_matrix.protocols import Action, ActionSpec


class ToolSetError(ValueError):
    """A tool set that cannot mean anything — an unknown preference, a tool that is not there."""


@dataclass(frozen=True)
class ToolSource:
    """One source of actions. ``builtin`` marks the ones a user's own tools are preferred over."""

    provider: str
    tools: dict[str, ActionSpec]
    builtin: bool = False


@dataclass(frozen=True)
class Resolution:
    """What a tool set decided: the names the model will see, and what became of the rest."""

    kept: tuple[str, ...] = ()
    dropped: tuple[tuple[str, str], ...] = ()  # (provider:name, why)
    renamed: tuple[tuple[str, str], ...] = ()  # (resolved name, the name its source gave it)

    def to_text(self) -> str:
        lines = [f"{len(self.kept)} tool(s) the model will see: {', '.join(self.kept) or 'none'}"]
        lines += [f"  dropped {name} — {why}" for name, why in self.dropped]
        lines += [f"  renamed {resolved} (its source knows it as {was})" for resolved, was in self.renamed]
        return "\n".join(lines)


class ToolSet:
    """Several sources of actions, resolved to the one set the model is shown.

    ``prefer`` is the collision direction: ``"user"`` (the default) keeps a non-builtin tool over a builtin
    one — a user's tool replaces ours — and ``"builtin"`` keeps ours. Sources of equal standing are decided
    by the order they were passed: the earlier source wins, so a caller controls it by ordering.
    """

    def __init__(self, *sources: ToolSource, prefer: str = "user") -> None:
        if prefer not in ("user", "builtin"):
            raise ToolSetError(f"prefer must be 'user' or 'builtin', not {prefer!r}")
        self.prefer = prefer
        self.sources = tuple(sources)
        self._tools: dict[str, ActionSpec] = {}
        self._route: dict[str, tuple[ToolSource, str]] = {}  # resolved name -> (source, its own name)
        self._resolution = Resolution()
        self._resolve()

    # ── the resolution ──

    def _claims(self) -> dict[str, list[tuple[int, ToolSource, str, ActionSpec]]]:
        """The name each tool contests, and who is contesting it.

        A tool contests exactly one name — the one it supersedes if it supersedes anything, otherwise its
        own. One name means one identity: a tool cannot occupy two slots, and the fingerprint every later
        record is keyed by is never ambiguous.
        """
        wants: dict[str, list[tuple[int, ToolSource, str, ActionSpec]]] = {}
        for i, source in enumerate(self.sources):
            for name, spec in source.tools.items():
                wants.setdefault(spec.supersedes or name, []).append((i, source, name, spec))
        return wants

    @staticmethod
    def _rank(entry: tuple[int, ToolSource, str, ActionSpec], prefer: str) -> tuple[int, int]:
        """Sort key: the preferred standing first, then the earlier source."""
        i, source, _name, _spec = entry
        standing = 0 if (source.builtin == (prefer == "builtin")) else 1
        return (standing, i)

    def _resolve(self) -> None:
        """Each tool contests one name and either takes it or is out entirely — a tool declared to replace
        another was not meant to sit beside it under a second name. Names are settled in alphabetical order,
        so the outcome never depends on dictionary ordering."""
        dropped: list[tuple[str, str]] = []
        renamed: list[tuple[str, str]] = []
        claims = self._claims()
        for name in sorted(claims):
            entries = claims[name]
            winner = min(entries, key=lambda e: self._rank(e, self.prefer))
            _i, source, own_name, spec = winner
            self._tools[name] = spec
            self._route[name] = (source, own_name)
            if own_name != name:
                renamed.append((name, own_name))
            for other in entries:
                if other is winner:
                    continue
                _oi, other_source, other_name, _ospec = other
                dropped.append((f"{other_source.provider}:{other_name}",
                                f"shadowed by {source.provider}:{own_name}"))
        self._resolution = Resolution(tuple(sorted(self._tools)), tuple(dropped), tuple(renamed))

    # ── what a caller uses ──

    def tools(self) -> dict[str, ActionSpec]:
        """The set the model is shown, under the names it will use."""
        return dict(self._tools)

    def resolution(self) -> Resolution:
        return self._resolution

    def provider_of(self, tool: str) -> Optional[str]:
        """Which source answers for a resolved tool name."""
        route = self._route.get(tool)
        return route[0].provider if route else None

    def source_name(self, tool: str) -> Optional[str]:
        """The name the owning source knows this tool by (differs from ``tool`` after a rename)."""
        route = self._route.get(tool)
        return route[1] if route else None

    def route(self, action: Action) -> Optional[tuple[ToolSource, Action]]:
        """The source that owns an action, and the action under the name that source gave it."""
        route = self._route.get(action.tool)
        if route is None:
            return None
        source, own_name = route
        if own_name == action.tool:
            return source, action
        return source, Action(own_name, action.args, action.why)

    def require(self, *names: str) -> None:
        """Fail loudly when a whole run depends on tools this set does not carry — the one check that turns a
        silently degraded run into a misconfiguration anyone can read."""
        missing = [n for n in names if n not in self._tools]
        if missing:
            raise ToolSetError(f"required tool(s) missing from this set: {', '.join(missing)} "
                               f"(it has: {', '.join(sorted(self._tools)) or 'none'})")


__all__ = ["Resolution", "ToolSet", "ToolSetError", "ToolSource"]
