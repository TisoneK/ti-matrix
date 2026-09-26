"""The run loop's half of the sidecar: what the app sees while a run streams, and how it ends.

`stream_run` is the sidecar's heart — a real `StateEngine` driven to its end with the wire frames of
`run_log`. One fake model port (the maze tests' pattern) is enough: the point is what the *runner*
does — every event lands in order with engine stamps, a done fires exactly one settled answer, a
failed model becomes a failed run rather than a raised exception, and a stop is polled between events.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from appserver.events import events_digest, stream_run
from ti_matrix.adapters.maze import MazeEnvironment
from ti_matrix.model import LLMEvaluator, LLMMoveProposer
from ti_matrix.search import EngineBudget, EngineEvent, StateEngine
from ti_matrix.protocols import Goal


class ScriptedPort:
    """A ModelPort standing in for an endpoint: proposer JSON per round, then evaluator JSON."""

    def __init__(self, *rounds) -> None:
        self.rounds, self.i = list(rounds), 0

    async def complete(self, prompt: str, *, max_chars: int = 4000) -> str:
        moves, evals = self.rounds[min(self.i, len(self.rounds) - 1)]
        if '"evals"' in prompt:
            self.i += 1
            return json.dumps({"evals": evals})
        return json.dumps({"moves": moves})


class Boom:
    """A model port that always fails — the model endpoint died mid-run."""

    async def complete(self, prompt: str, *, max_chars: int = 4000) -> str:
        raise RuntimeError("the endpoint is down")


def step(cell, direction):
    return {"tool": "step", "args": {"cell": cell, "direction": direction}, "why": "walk"}


def scored(progress, done=False, answer=""):
    return [{"i": 0, "progress": progress, "done": done, "answer": answer, "reason": ""}]


def route_rounds():
    route = [("1,1", "south"), ("1,2", "south"), ("1,3", "south"), ("1,4", "south"), ("1,5", "south")]
    rounds = []
    for i, (cell, direction) in enumerate(route):
        last = i == len(route) - 1
        rounds.append(([step(cell, direction)],
                       scored(1.0, True, "the exit is at 1,6") if last else scored(0.2 * (i + 1))))
    return rounds


class Recording:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.done: tuple | None = None

    async def on_event(self, frame: dict) -> None:
        self.events.append(dict(frame))

    async def on_done(self, answer, reason, verified, basis) -> None:
        self.done = (answer, reason, verified, basis)


class FakeStoppedEngine:
    """A stand-in for StateEngine: yields exactly the events a real stopped-with-synthesis run
    would produce, without needing a real synthesizer or model behind it."""

    def __init__(self, events: list[EngineEvent]) -> None:
        self._events = events

    async def run(self, goal):
        for ev in self._events:
            yield ev


def maze_engine(*rounds):
    """The real engine over the real maze, with the scripted port where the endpoint would be —
    the same wiring tests/test_maze_adapter.py's drive() uses."""
    port = ScriptedPort(*rounds)
    return StateEngine(MazeEnvironment(), proposer=LLMMoveProposer(port, MazeEnvironment().tools()),
                       evaluator=LLMEvaluator(port))


@pytest.mark.asyncio
async def test_a_run_streams_every_event_in_order_and_settles_once():
    engine = maze_engine(*route_rounds())
    rec = Recording()
    await stream_run(engine, Goal("reach the exit"), on_event=rec.on_event,
                     on_done=rec.on_done, stop_requested=lambda: False)

    kinds = [e["kind"] for e in rec.events]
    assert kinds[0] == "state" and "done" in kinds
    assert rec.done == ("the exit is at 1,6", None, True, None)
    # engine stamps, on every frame, in the same shapes run_log writes to disk
    assert [e["seq"] for e in rec.events] == list(range(1, len(rec.events) + 1))
    assert all("t_ms" in e for e in rec.events)
    assert any(e["kind"] == "probe" and e["ok"] for e in rec.events)


@pytest.mark.asyncio
async def test_a_failed_model_becomes_a_failed_run_not_a_raised_exception():
    env = MazeEnvironment()
    engine = StateEngine(env, proposer=LLMMoveProposer(Boom(), env.tools()),
                         evaluator=LLMEvaluator(Boom()))
    rec = Recording()
    await stream_run(engine, Goal("reach the exit"), on_event=rec.on_event,
                     on_done=rec.on_done, stop_requested=lambda: False)

    # the engine catches a proposer's exception itself and stops with its own reason string —
    # which stream_run hands to on_done untouched: a failed run is a recorded stop, not a crash
    answer, reason, verified, basis = rec.done
    assert answer is None and "the endpoint is down" in reason
    assert verified is False and basis is None
    assert rec.events and rec.events[-1]["kind"] == "stopped"


@pytest.mark.asyncio
async def test_a_stop_between_events_ends_the_run_without_a_settled_answer():
    engine = maze_engine(*route_rounds())
    rec = Recording()
    stop_after = {"n": 3}

    def stop_requested() -> bool:
        stop_after["n"] -= 1
        return stop_after["n"] <= 0

    await stream_run(engine, Goal("reach the exit"), on_event=rec.on_event,
                     on_done=rec.on_done, stop_requested=stop_requested)

    # the stop is polled before each delivery: three noes and the third frame is never sent
    assert len(rec.events) == 2
    assert rec.done == (None, "stopped", False, None)


@pytest.mark.asyncio
async def test_a_stopped_runs_synthesized_answer_reaches_on_done_marked_unverified():
    """B-2026-09-26-4: a run that stops without settling still has something to say, when a
    synthesizer said it — on_done must carry that answer, not silently prefer nothing because
    the run never hit `done`."""
    events = [
        EngineEvent(kind="state", data={"depth": 0, "goal": "what does openai_compat.py do?"}),
        EngineEvent(kind="stopped", data={
            "reason": "no_progress",
            "partial_answer": "openai_compat.py is a model port over any OpenAI-compatible endpoint.",
            "answer_basis": "synthesised from 1 fact(s) established by real readings; NOT verified against the world",
        }),
    ]
    engine = FakeStoppedEngine(events)
    rec = Recording()
    await stream_run(engine, Goal("what does openai_compat.py do?"), on_event=rec.on_event,
                     on_done=rec.on_done, stop_requested=lambda: False)

    answer, reason, verified, basis = rec.done
    assert answer == "openai_compat.py is a model port over any OpenAI-compatible endpoint."
    assert reason == "no_progress"
    assert verified is False
    assert basis is not None and "NOT verified against the world" in basis


@pytest.mark.asyncio
async def test_the_digest_is_the_run_log_summary_of_the_same_frames():
    engine = maze_engine(*route_rounds())
    rec = Recording()
    await stream_run(engine, Goal("reach the exit"), on_event=rec.on_event,
                     on_done=rec.on_done, stop_requested=lambda: False)

    text = events_digest(rec.events)
    assert "settled: the exit is at 1,6" in text
    assert "probes, in order:" in text
