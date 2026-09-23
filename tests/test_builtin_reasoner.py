"""The two seats, filled by rules — a run with no model in it at all.

Why this matters enough to test. Every shipped run needed an OpenAI-compatible endpoint, a model name
that resolved there, and twenty-odd seconds per decision. A machine without all three produced a run
two events long — one `state`, one `stopped: proposer_error` — which is a window with nothing in it,
not a search that failed. `ti_matrix.adapters.builtin` fills the seats with rules so a first run is
always possible, and these tests hold it to the same bar a model is held to: it must search a maze it
cannot see, it must ground its answer in a real observation, and its progress must actually rise —
because the engine retreats from a step that does not beat where it stands, and a rule that returns a
flat score would stall the run on its second move while looking like it was working.
"""
from __future__ import annotations

import asyncio

import pytest

from ti_matrix import EngineBudget, Goal, StateEngine
from ti_matrix.adapters.builtin import (
    BUILTIN,
    MazeKnowledge,
    MazeReasoner,
    SurveyReasoner,
    is_builtin,
    reasoner_for,
)
from ti_matrix.adapters.maze import MazeEnvironment
from ti_matrix.protocols import Action, Goal as GoalType, Observation
from ti_matrix.state import AgentState

# A maze with a fork: the left column runs down to a dead end, the exit sits east behind a corner. Small
# enough to solve in a handful of steps, shaped so a wrong first guess has to be abandoned.
FORKED = """
#####
#S..#
#.#.#
#.#E#
#####
"""


def drive(env, budget: EngineBudget) -> list:
    """Run the rules against a world and collect every event, the way the sidecar streams them."""
    reasoner = MazeReasoner(env.tools())
    engine = StateEngine(env, proposer=reasoner, evaluator=reasoner, budget=budget)

    async def go() -> list:
        return [ev async for ev in engine.run(Goal("find the exit"))]

    return asyncio.run(go())


def test_a_maze_run_needs_no_model_and_reaches_the_exit():
    events = drive(MazeEnvironment(FORKED), EngineBudget(max_depth=40, max_model_calls=300,
                                                         max_backtracks=20))
    kinds = [e.kind for e in events]
    assert "done" in kinds, f"the rules never settled the maze: {kinds[-4:]}"
    answer = next(e for e in events if e.kind == "done").data["answer"]
    # The exit of FORKED is the 'E' at 3,3 — and the answer must name it, not merely claim success.
    assert "3,3" in answer, answer
    # A real search, not a lucky first guess: the run probed the world repeatedly.
    assert kinds.count("probe") >= 4, kinds


def test_progress_rises_so_the_engine_does_not_stall():
    """The engine backtracks when nothing beats where it stands. A flat score would stop the run dead."""
    events = drive(MazeEnvironment(FORKED), EngineBudget(max_depth=40, max_model_calls=300,
                                                         max_backtracks=20))
    seen = [e.data["progress"] for e in events if e.kind == "selected"]
    assert len(seen) >= 3, seen
    assert seen == sorted(seen), f"progress went backwards: {seen}"
    assert seen[-1] > seen[0], seen


def test_the_reasoner_reads_only_what_the_run_itself_observed():
    """It must not be able to see the maze — only the facts the run collected, as a model would."""
    state = AgentState(GoalType("find the exit"), facts=(
        "grid() -> ok: a 5x5 grid holding 8 cells; a run enters at 1,1 and looks for the exit",
        "entry() -> ok: cell 1,1 — open: south, east",
    ))
    known = MazeKnowledge(state)
    assert known.total == 8
    assert known.open == {(1, 1): {"south", "east"}}
    # Two openings from a cell nobody has stepped through yet: both are frontier.
    assert sorted(known.frontier()) == [((1, 1), "east"), ((1, 1), "south")]
    assert known.exit is None


def test_the_exit_is_recognised_and_answered_from_the_observation():
    state = AgentState(GoalType("find the exit"))
    reasoner = MazeReasoner()
    move = Action("step", {"cell": "2,3", "direction": "east"}, "")
    obs = Observation(move, True, "from 2,3 east: cell 3,3 — open: west · THIS IS THE EXIT")
    [verdict] = asyncio.run(reasoner.evaluate(state, [obs]))
    assert verdict.done is True
    assert "3,3" in verdict.answer
    assert verdict.progress == 1.0


def test_a_predicted_exit_never_settles_the_goal():
    """`done` on a simulated outcome would be a claim about a place the run has not actually been."""
    reasoner = MazeReasoner()
    move = Action("step", {"cell": "2,3", "direction": "east"}, "")
    guess = Observation(move, True, "from 2,3 east: cell 3,3 — open: west · THIS IS THE EXIT",
                        predicted=True)
    [verdict] = asyncio.run(reasoner.evaluate(AgentState(GoalType("find the exit")), [guess]))
    assert verdict.done is False


def test_a_failed_probe_scores_nothing():
    reasoner = MazeReasoner()
    move = Action("look", {"cell": "0,0"}, "")
    obs = Observation(move, False, "not a cell of this maze: '0,0'")
    [verdict] = asyncio.run(reasoner.evaluate(AgentState(GoalType("x")), [obs]))
    assert verdict.progress == 0.0 and verdict.done is False


def test_an_action_already_ruled_out_is_never_proposed_again():
    ruled_out = Action("step", {"cell": "1,1", "direction": "south"}, "")
    state = AgentState(GoalType("find the exit"), facts=(
        "entry() -> ok: cell 1,1 — open: south, east",
    ), failed=(ruled_out.fingerprint(),))
    moves = asyncio.run(MazeReasoner().propose(state, 3, set()))
    assert all(m.fingerprint() != ruled_out.fingerprint() for m in moves), [m.label() for m in moves]


def test_the_survey_reasoner_only_ever_proposes_read_only_actions():
    """The fallback seats must never propose something that would change a world."""
    from ti_matrix.protocols import ActionSpec

    specs = {
        "read": ActionSpec("read", "reads", "{}", read_only=True),
        "write": ActionSpec("write", "writes", "{}", read_only=False),
    }
    moves = asyncio.run(SurveyReasoner(specs).propose(AgentState(GoalType("x")), 5, set()))
    assert [m.tool for m in moves] == ["read"]


def test_the_survey_never_claims_to_have_settled_anything():
    obs = Observation(Action("read", {}, ""), True, "some real content")
    [verdict] = asyncio.run(SurveyReasoner().evaluate(AgentState(GoalType("x")), [obs]))
    assert verdict.done is False and verdict.progress > 0


@pytest.mark.parametrize("world,expected", [("maze", MazeReasoner), ("files", SurveyReasoner),
                                            ("ledger", SurveyReasoner), ("", SurveyReasoner)])
def test_each_world_gets_the_seats_that_suit_it(world, expected):
    assert isinstance(reasoner_for(world), expected)


@pytest.mark.parametrize("name,expected", [("builtin", True), ("BUILTIN", True), (" Builtin ", True),
                                           ("qwen2.5:7b", False), ("", False)])
def test_the_builtin_name_is_recognised_however_it_is_typed(name, expected):
    assert is_builtin(name) is expected
    assert BUILTIN == "builtin"
