"""Adapter #5 — a hidden maze — the first world here that makes the engine search.

The other worlds are shallow: a goal is answered in a probe or two and the run never retreats. A maze needs a
route, and the default one is built so two routes reach the same junction, which is the case the design notes
could not answer from experience — whether the engine notices it has been somewhere before. It does not, and
the last test below measures what that costs rather than asserting a fix that does not exist.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from ti_matrix import EngineBudget, Goal, LLMEvaluator, LLMMoveProposer, StateEngine
from ti_matrix.adapters.maze import MazeEnvironment
from ti_matrix.protocols import Action

# Two routes from S to E that meet again: south down the left column (5 steps) or the long way round (21),
# rejoining at 1,5. Two dead ends (4,6 and 7,6) hang off the long route, and the exit is at 1,6.
SHORT_ROUTE = [((1, 1), "south"), ((1, 2), "south"), ((1, 3), "south"), ((1, 4), "south"), ((1, 5), "south")]

# A second, smaller maze for the retreat: the left column is a dead end and the exit is a short walk east.
FORKED_MAZE = """
#####
#S..#
#.#.#
#.#E#
#####
"""


class ScriptedPort:
    """A ModelPort standing in for an endpoint: proposer JSON per round, then evaluator JSON."""

    def __init__(self, *rounds):
        self.rounds, self.i, self.prompts = list(rounds), 0, []

    async def complete(self, prompt: str, *, max_chars: int = 4000) -> str:
        self.prompts.append(prompt)
        moves, evals = self.rounds[min(self.i, len(self.rounds) - 1)]
        if '"evals"' in prompt:
            self.i += 1
            return json.dumps({"evals": evals})
        return json.dumps({"moves": moves})


def step(cell, direction):
    return {"tool": "step", "args": {"cell": f"{cell[0]},{cell[1]}", "direction": direction}, "why": "walk"}


def scored(progress, done=False, answer=""):
    return [{"i": 0, "progress": progress, "done": done, "answer": answer, "reason": ""}]


async def drive(env, goal, *rounds, calls=20):
    """Run a real StateEngine — the real proposer, evaluator and JSON parsing — over the maze."""
    port = ScriptedPort(*rounds)  # one port for both jobs: the round advances when the fan is scored
    engine = StateEngine(
        env,
        proposer=LLMMoveProposer(port, env.tools()),
        evaluator=LLMEvaluator(port),
        budget=EngineBudget(max_model_calls=calls),
    )
    return [ev async for ev in engine.run(Goal(goal))]


def probes(events):
    return [e.data for e in events if e.kind == "probe"]


@pytest.fixture()
def env():
    return MazeEnvironment()


# ─── the world ──────────────────────────────────────────────────────────────


def test_every_action_it_offers_is_read_only(env):
    assert env.tools() and all(spec.read_only for spec in env.tools().values())
    assert env.is_read_only(Action("step", {"cell": "1,1", "direction": "south"})) is True
    assert env.is_read_only(Action("teleport", {})) is None  # not an action here


@pytest.mark.asyncio
async def test_walls_and_unentered_cells_are_refused_not_raised(env):
    at_entry = await env.probe(Action("entry", {}))
    assert at_entry.ok and "1,1" in at_entry.text and "open: south, east" in at_entry.text

    grid = await env.probe(Action("grid", {}))
    assert grid.ok and "9x8" in grid.text and "27 cells" in grid.text

    # a wall is a failed observation, which is information the search can use
    into_wall = await env.probe(Action("step", {"cell": "1,1", "direction": "north"}))
    assert into_wall.ok is False and "a wall blocks north" in into_wall.text

    # and a cell has to be walked into before it can be read or walked out of
    unentered = await env.probe(Action("look", {"cell": "7,5"}))
    assert unentered.ok is False and "has not been entered" in unentered.text
    assert (await env.probe(Action("step", {"cell": "7,5", "direction": "west"}))).ok is False

    assert (await env.probe(Action("look", {"cell": "nope"}))).ok is False
    assert (await env.probe(Action("step", {"cell": "1,1", "direction": "up"}))).ok is False
    assert (await env.probe(Action("grid", {"wrong": 1}))).ok is False


@pytest.mark.asyncio
async def test_a_cell_is_read_the_way_the_action_specs_write_it(env):
    """The specs hand the model `<x,y>`; the bare `x,y` is what every caller here writes. Both land."""
    assert (await env.probe(Action("entry", {}))).ok
    for written in ("1,1", "<1,1>", " 1 , 1 ", "(1,1)"):
        looked = await env.probe(Action("look", {"cell": written}))
        assert looked.ok, f"{written!r} was refused"
    stepped = await env.probe(Action("step", {"cell": "<1,1>", "direction": "south"}))
    assert stepped.ok and "cell 1,2" in stepped.text


@pytest.mark.asyncio
async def test_a_step_hands_back_the_far_side_and_the_exit_announces_itself(env):
    walked = await env.probe(Action("step", {"cell": "1,1", "direction": "south"}))
    assert walked.ok and "from 1,1 south" in walked.text and "cell 1,2" in walked.text
    assert "EXIT" not in walked.text

    # stepping is idempotent and safe to repeat: the world records what was entered, not where a walker is
    again = await env.probe(Action("step", {"cell": "1,1", "direction": "south"}))
    assert again.ok and again.text == walked.text

    for cell, direction in SHORT_ROUTE:
        reached = await env.probe(Action("step", {"cell": f"{cell[0]},{cell[1]}", "direction": direction}))
        assert reached.ok
    assert "THIS IS THE EXIT" in reached.text and "cell 1,6" in reached.text


@pytest.mark.asyncio
async def test_a_fan_of_steps_is_safe_because_the_world_only_ever_grows():
    """A fan is probed all at once, so anything a probe could clobber would come back wrong."""
    env = MazeEnvironment()
    await env.probe(Action("step", {"cell": "1,1", "direction": "south"}))  # 1,2 known
    east, south = await asyncio.gather(
        env.probe(Action("step", {"cell": "1,1", "direction": "south"})),
        env.probe(Action("step", {"cell": "1,2", "direction": "south"})),
    )
    assert east.ok and south.ok and "cell 1,3" in south.text
    assert (await env.probe(Action("look", {"cell": "1,3"}))).ok  # both siblings landed


# ─── the engine, searching ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_run_walks_the_maze_and_settles_on_the_exit(env):
    rounds = []
    for i, (cell, direction) in enumerate(SHORT_ROUTE):
        last = i == len(SHORT_ROUTE) - 1
        rounds.append(([step(cell, direction)],
                       scored(1.0, True, "the exit is at 1,6") if last else scored(0.2 * (i + 1))))
    events = await drive(env, "reach the exit of the maze from its entry", *rounds)

    assert events[-1].kind == "done"
    assert events[-1].data["answer"] == "the exit is at 1,6"
    assert [p["ok"] for p in probes(events)] == [True] * 5
    # the last step led into the exit, and the far side said so
    assert "direction=south" in events[-1].data["trail"][-1]
    assert "THIS IS THE EXIT" in probes(events)[-1]["excerpt"]


@pytest.mark.asyncio
async def test_a_dead_end_makes_the_engine_retreat_and_prune_the_move():
    """The point of the maze: a world where nothing beats where the state stands, so the search backs out."""
    env = MazeEnvironment(FORKED_MAZE)
    events = await drive(
        env, "reach the exit of the maze from its entry",
        ([step((1, 1), "south")], scored(0.5)),          # into the dead-end column
        ([step((1, 2), "south")], scored(0.0)),          # 1,3 — sealed, nothing learned, nothing scored
        ([step((1, 1), "east")], scored(0.6)),           # back out and east instead
        ([step((2, 1), "east")], scored(0.8)),
        ([step((3, 1), "south")], scored(0.9)),
        ([step((3, 2), "south")], scored(1.0, True, "the exit is at 3,3")),
    )

    kinds = [e.kind for e in events]
    assert kinds[-1] == "done" and "backtrack" in kinds, "nothing made the engine retreat"
    assert events[-1].data["answer"] == "the exit is at 3,3"

    # and the move that led into the dead end is remembered, so it is not proposed again
    dead_end = Action("step", {"cell": "1,2", "direction": "south"}).fingerprint()
    failed = {fp for e in events if e.kind == "state" for fp in e.data["failed_fps"]}
    assert dead_end in failed, "the move that led into the dead end was not pruned"


@pytest.mark.asyncio
async def test_the_engine_cannot_tell_it_has_been_somewhere_before(env):
    """The measurement the design notes wanted, asserted rather than fixed.

    The default maze's two routes meet at 1,5. A run that has walked the short route down to 1,5 and then steps
    east to 2,5, and then west again, pays a probe to re-learn a cell it already holds as a fact: the engine
    knows an *action* was tried, never that a *place* is known. Detecting that is the "same knowledge" case in
    DESIGN.md, and it is not detected today.
    """
    rounds = []
    for i, (cell, direction) in enumerate(SHORT_ROUTE):          # 1,1 -> 1,5, all known
        rounds.append(([step(cell, direction)], scored(0.2 * (i + 1))))
    rounds.append(([step((1, 5), "east")], scored(0.9)))          # 1,5 -> 2,5
    rounds.append(([step((2, 5), "west")], scored(0.9)))          # back into 1,5, which it already knows
    events = await drive(env, "reach the exit of the maze from its entry", *rounds)

    relit = probes(events)[-1]
    assert relit["ok"] is True and "cell 1,5" in relit["excerpt"], "the re-walk did not happen"

    # ... and nothing in the record says so: the engine's own vocabulary has no word for a place it knows
    told = {"state", "thinking", "candidates", "probe", "evaluation", "selected", "backtrack",
            "needs_confirmation", "done", "stopped"}
    assert {e.kind for e in events} <= told
    facts = [f for e in events if e.kind == "state" for f in e.data["fact_list"]]
    assert sum(1 for f in facts if "cell 1,5" in f) >= 2, "the same place was learned twice"
