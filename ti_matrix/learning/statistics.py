"""The record of what the engine's own runs have established about one environment.

Two keys, because they answer different questions:

  - **by tool** — "what is this world like?" A tool's rate of success, selection and progress is a prior for
    what to propose, and it generalises across arguments in a way a fingerprint cannot. The engine could not
    previously learn that a *tool* is hopeless here; it knew only that one exact call had failed.
  - **by fingerprint** — "have we made this exact call, with these exact arguments, before?" That is a cache
    key and a cross-run avoid list, and it is precise on purpose.

Facts come along for free: the one-line records real observations already leave in ``state.to_dict()`` and in
a stopped run's payload. They are what ``EngineTools``' ``recall`` hands back to a model that asks.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable

# Evidence thresholds. Each is a judgement call, so each says what it is for: a tool is called hopeless only
# once it has been tried enough times to mean something. Deleting a candidate the model would have tried is a
# real cost, so the bar is deliberately more than one early failure.
HOPELESS_TRIES = 3
_NEUTRAL_PRIOR = 0.5  # an action nobody has tried yet sits in the middle: worth exploring, not preferred
_SELECT_WEIGHT = 0.6  # how much of a tool's prior comes from being chosen vs. from the progress it made
_RECALL_CHARS = 2400  # what a memory answer may cost the model that asked (its evaluator view is 2800)
_FACT_LIMIT = 200  # how many observed facts this keeps, newest last
_FORMAT = 1  # the on-disk shape; a record from another version is refused rather than half-read


def _rate(part: float, whole: float) -> float:
    return part / whole if whole else 0.0


def _add(record: "ActionRecord", changes: dict[str, float]) -> "ActionRecord":
    return replace(record, **{k: getattr(record, k) + v for k, v in changes.items()})


@dataclass(frozen=True)
class ActionRecord:
    """What one tool — or one exact action — has actually done here, across every run that was recorded."""

    tool: str
    probes: int = 0
    failures: int = 0
    selections: int = 0
    progress: float = 0.0  # summed over probes that were scored
    scored: int = 0
    ms: int = 0
    chars: int = 0
    predicted: int = 0

    @property
    def ok_rate(self) -> float:
        return _rate(self.probes - self.failures, self.probes)

    @property
    def select_rate(self) -> float:
        return _rate(self.selections, self.probes)

    @property
    def mean_progress(self) -> float:
        return self.progress / self.scored if self.scored else 0.0

    @property
    def mean_ms(self) -> int:
        return int(_rate(self.ms, self.probes))

    def prior(self) -> float:
        """How promising this tool looks here: 0 (never useful) to 1 (the one that does the work).

        An untried tool sits at ``_NEUTRAL_PRIOR`` — the search should still explore — while a tool tried
        repeatedly and never chosen sorts *below* it, which is how a hopeless action stops crowding out a good
        one when the model offers more candidates than the fan has room for.
        """
        if not self.probes:
            return _NEUTRAL_PRIOR
        return _SELECT_WEIGHT * self.select_rate + (1 - _SELECT_WEIGHT) * self.mean_progress

    def hopeless(self, min_tries: int = HOPELESS_TRIES) -> bool:
        """Tried enough times to know: never chosen, and never once a real success."""
        return self.probes >= min_tries and self.selections == 0 and self.ok_rate == 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"tool": self.tool, "probes": self.probes, "failures": self.failures,
                "selections": self.selections, "progress": round(self.progress, 4),
                "scored": self.scored, "ms": self.ms, "chars": self.chars, "predicted": self.predicted}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ActionRecord":
        def num(key: str) -> float:
            value = raw.get(key, 0)
            return value if isinstance(value, (int, float)) else 0
        return cls(str(raw.get("tool", "")), int(num("probes")), int(num("failures")),
                   int(num("selections")), float(num("progress")), int(num("scored")),
                   int(num("ms")), int(num("chars")), int(num("predicted")))

    def to_text(self) -> str:
        if not self.probes:
            return f"{self.tool}: never tried here"
        return (f"{self.tool}: {self.probes} probe(s), {self.failures} failed, chosen {self.selections}×, "
                f"mean progress {self.mean_progress:.2f}, mean {self.mean_ms} ms")


@dataclass
class Statistics:
    """The engine's accumulated experience with one environment. Plain counters, safe to write to disk."""

    by_tool: dict[str, ActionRecord] = field(default_factory=dict)
    by_fingerprint: dict[str, ActionRecord] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    _tools: dict[str, str] = field(default_factory=dict)  # fingerprint -> tool, to attribute later events
    _predicted: set[str] = field(default_factory=set)  # fingerprints only ever predicted, never tried

    # ── learning from what a run emits ──

    def observe(self, event: Any) -> None:
        """Take one ``EngineEvent`` (anything with ``.kind`` and ``.data``)."""
        kind, data = getattr(event, "kind", ""), getattr(event, "data", None) or {}
        if kind == "candidates":
            for move in data.get("moves", []) if isinstance(data.get("moves"), list) else []:
                fp, tool = move.get("fp"), move.get("tool")
                if isinstance(fp, str) and isinstance(tool, str):
                    self._tools[fp] = tool  # how a later probe or evaluation finds the tool it belongs to
        elif kind == "probe":
            self._observe_probe(data)
        elif kind == "evaluation":
            self._observe_evaluation(data)
        elif kind == "selected":
            self._bump(data, selections=1)
        elif kind == "state":
            self.add_facts(data.get("fact_list"))
        elif kind == "stopped":
            self.add_facts(data.get("facts"))

    def observe_all(self, events: Iterable[Any]) -> "Statistics":
        for event in events:
            self.observe(event)
        return self

    def _observe_probe(self, data: dict[str, Any]) -> None:
        fp = data.get("fp")
        if not isinstance(fp, str) or fp not in self._tools:
            return  # a probe of something no candidate listed: nothing to attribute it to
        if data.get("predicted"):
            # The engine predicted this action instead of performing it. Remember that it was predicted, and
            # nothing else: a prediction is not a probe, and its text says nothing about the world.
            self._predicted.add(fp)
            self._bump(data, to_tool=False, predicted=1)
            return
        changes: dict[str, float] = {"probes": 1, "chars": float(data.get("chars") or 0),
                                     "ms": float(data.get("ms") or 0)}
        if not data.get("ok"):
            changes["failures"] = 1
        self._bump(data, **changes)

    def _observe_evaluation(self, data: dict[str, Any]) -> None:
        fp = data.get("fp")
        if not isinstance(fp, str) or fp in self._predicted:
            return  # a score for something that never happened is a hypothesis, not a measurement
        try:
            progress = float(data.get("progress", 0.0))
        except (TypeError, ValueError):
            return
        self._bump(data, progress=progress, scored=1)

    def _bump(self, data: dict[str, Any], *, to_tool: bool = True, **changes: float) -> None:
        """Add one observation to both keys — the tool, and the exact action.

        ``to_tool=False`` records it against the exact action only, which is what a predicted outcome gets: the
        engine remembers having predicted that action, but nothing passes into what the tool's record claims
        about this environment. So ``probes`` counts real probes everywhere, which is what makes ``avoids()`` a
        statement about reality.
        """
        fp = data.get("fp")
        if not isinstance(fp, str) or fp not in self._tools:
            return  # nothing can be attributed to a candidate the engine never listed
        tool = self._tools.get(fp, "")
        if to_tool and tool:
            self.by_tool[tool] = _add(self.by_tool.get(tool) or ActionRecord(tool), changes)
        current = self.by_fingerprint.get(fp) or ActionRecord(tool or fp)
        self.by_fingerprint[fp] = _add(replace(current, tool=tool or fp), changes)

    def add_facts(self, facts: Any, *, limit: int = _FACT_LIMIT) -> None:
        """Keep the one-line records real observations left behind, newest last, without duplicates."""
        if not isinstance(facts, list):
            return
        for fact in facts:
            text = " ".join(str(fact).split())
            if text and text not in self.facts:
                self.facts.append(text)
        del self.facts[: max(0, len(self.facts) - limit)]

    # ── what the wrappers and the memory tool ask ──

    def record(self, tool: str) -> ActionRecord:
        return self.by_tool.get(tool, ActionRecord(tool))

    def prior(self, tool: str) -> float:
        return self.record(tool).prior()

    def hopeless_tools(self, min_tries: int = HOPELESS_TRIES) -> set[str]:
        return {t for t, r in self.by_tool.items() if r.hopeless(min_tries)}

    def avoids(self, *, min_tries: int = 2) -> set[str]:
        """Fingerprints that have failed every time they were really tried — the cross-run avoid list."""
        return {fp for fp, r in self.by_fingerprint.items()
                if r.probes >= min_tries and r.failures == r.probes}

    def recall(self, text: str = "", limit: int = 8) -> str:
        """The engine's answer to "what do we already know here?" — facts first, then the action record.

        Bounded on purpose: a model reads this inside a fan, so it costs the same budget as any other probe.
        """
        wanted = str(text or "").strip().lower()
        hits = [f for f in self.facts if wanted and wanted in f.lower()] if wanted else []
        shown = hits[-limit:] if hits else (self.facts[-limit:] if not wanted else [])
        lines: list[str] = []
        if shown:
            head = f"matching {text!r} in earlier runs:" if wanted else "what earlier runs established:"
            lines += [head] + [f"- {f}" for f in shown]
        elif wanted:
            lines.append(f"nothing in earlier runs matches {text!r}")
        tried = sorted(self.by_tool.values(), key=lambda r: r.prior(), reverse=True)
        useful = [r for r in tried if r.selections][:4]
        dead = [r for r in tried if r.hopeless()][:4]
        if useful:
            lines.append("actions that have paid off here: "
                         + "; ".join(f"{r.tool} (chosen {r.selections}×, progress {r.mean_progress:.2f})"
                                     for r in useful))
        if dead:
            lines.append("actions that have never worked here: " + ", ".join(r.tool for r in dead))
        return ("\n".join(lines) or "nothing learned about this environment yet")[:_RECALL_CHARS]

    # ── persistence (pure: the file itself belongs to an adapter) ──

    def to_dict(self) -> dict[str, Any]:
        return {"version": _FORMAT,
                "tools": {t: r.to_dict() for t, r in sorted(self.by_tool.items())},
                "fingerprints": {fp: r.to_dict() for fp, r in sorted(self.by_fingerprint.items())},
                "facts": list(self.facts)}

    @classmethod
    def from_dict(cls, raw: Any) -> "Statistics":
        """Read what ``to_dict`` wrote. A shape from another format version is refused, not half-read."""
        stats = cls()
        if not isinstance(raw, dict) or int(raw.get("version", 0) or 0) != _FORMAT:
            return stats
        for tool, rec in (raw.get("tools") or {}).items():
            if isinstance(rec, dict):
                stats.by_tool[str(tool)] = ActionRecord.from_dict({**rec, "tool": str(tool)})
        for fp, rec in (raw.get("fingerprints") or {}).items():
            if isinstance(rec, dict):
                stats.by_fingerprint[str(fp)] = ActionRecord.from_dict(rec)
        stats.add_facts(raw.get("facts"))
        return stats

    def to_text(self) -> str:
        """The whole picture, widest evidence first — what a person reads to see what the engine learned."""
        if not self.by_tool:
            return "no experience recorded yet"
        rows = sorted(self.by_tool.values(), key=lambda r: (r.probes, r.selections), reverse=True)
        lines = [f"{len(self.facts)} fact(s), {len(self.by_tool)} tool(s), "
                 f"{len(self.by_fingerprint)} action(s) tried"]
        lines += [f"- {r.to_text()}" for r in rows]
        return "\n".join(lines)


__all__ = ["ActionRecord", "HOPELESS_TRIES", "Statistics"]
