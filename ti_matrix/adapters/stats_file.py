"""Where the engine's statistics live between runs — a JSON file, written by the host, never by the engine.

The core's boundary rule (``tests/test_boundary.py``) is that the engine reads no ambient configuration and
touches no files of its own, so persistence cannot live in ``ti_matrix.learning``. It lives here, where every
other kind of I/O in this project lives, and a host decides the path — or decides not to persist at all.

Reading is lenient by default and that is deliberate: a run must never fail because a statistics file is
missing, truncated or from a format this version does not know. The engine's own honest-stop rule is about
what it can establish, not about bookkeeping; losing experience degrades the next run to a cold start, which
is exactly where it would have been anyway. ``strict=True`` is there for the caller who wants to know.
"""
from __future__ import annotations

import json
from pathlib import Path

from ti_matrix.learning.statistics import Statistics


def load(path: str | Path, *, strict: bool = False) -> Statistics:
    """The statistics at ``path``, or an empty record when there are none to read."""
    p = Path(path).expanduser()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Statistics()
    except (OSError, ValueError):
        if strict:
            raise
        return Statistics()
    stats = Statistics.from_dict(raw)
    if strict and not stats.by_tool and raw:
        raise ValueError(f"{p} holds no experience this version can read (shape of another format?)")
    return stats


def save(path: str | Path, statistics: Statistics) -> None:
    """Write the record, replacing what was there. Counters only — never anything a model wrote."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(statistics.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["load", "save"]
