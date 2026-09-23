"""Turning a run's `EngineEvent`s into frames — the adapter-free half of the streaming loop.

`StateEngine.run()` yields `EngineEvent`s stamped with `seq` and `t_ms` (the tree ids a UI needs live in
the data). The wire shape is `EngineEvent.to_dict()` verbatim — `ti_matrix.adapters.run_log` reads exactly
that from disk — so what the app shows live and what `run_log summarize` reads back are the same record,
and this module invents nothing.

A run's host work — the learning record, the confirmer, the ledger write-back — is all inside the
callbacks this runner takes: nothing here knows which world is being driven.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from ti_matrix.adapters.run_log import summarize
from ti_matrix.search import EngineEvent, StateEngine


def _kind(event: EngineEvent) -> str:
    return getattr(event, "kind", "")


async def stream_run(
    engine: StateEngine,
    goal: Any,
    *,
    on_event: Callable[[dict[str, Any]], Awaitable[None]],
    on_done: Callable[[Optional[str], Optional[str]], Awaitable[None]],
    stop_requested: Callable[[], bool],
) -> None:
    """Drive one run to its end, handing each event to `on_event` as it happens.

    `on_done(answer, reason)` fires once, after the last event: `answer` when the run settled,
    `reason` when it stopped (never both). `stop_requested` is polled between events — an engine that
    never yields is abandoned through the caller's own cancellation; this check is for a run that is
    merely slow. Nothing raises for a run that fails: an exception becomes `on_done(None, ...)`.
    """
    answer: Optional[str] = None
    reason: Optional[str] = None
    try:
        async for ev in engine.run(goal):
            if stop_requested():
                reason = "stopped"
                break
            await on_event(ev.to_dict())
            if _kind(ev) == "done":
                answer = str(ev.data.get("answer") or "")
            elif _kind(ev) == "stopped":
                reason = str(ev.data.get("reason") or "stopped")
    except asyncio.CancelledError:
        reason = "stopped"
        raise
    except Exception as exc:  # noqa: BLE001 — a run's failure is a frame, not a crash
        reason = f"error: {exc}"
    await on_done(answer, reason)


def events_digest(events: list[dict[str, Any]]) -> str:
    """The run_log summary of what was streamed — the same text the CLI prints after a run."""
    return summarize(events)
