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
    BrowserReasoner,
    FilesReasoner,
    MazeKnowledge,
    MazeReasoner,
    SurveyReasoner,
    goal_words,
    is_builtin,
    is_noise,
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


@pytest.mark.parametrize("world,expected", [("maze", MazeReasoner), ("files", FilesReasoner),
                                            ("browser", BrowserReasoner), ("", SurveyReasoner)])
def test_each_world_gets_the_seats_that_suit_it(world, expected):
    assert isinstance(reasoner_for(world), expected)


@pytest.mark.parametrize("name,expected", [("builtin", True), ("BUILTIN", True), (" Builtin ", True),
                                           ("qwen2.5:7b", False), ("", False)])
def test_the_builtin_name_is_recognised_however_it_is_typed(name, expected):
    assert is_builtin(name) is expected
    assert BUILTIN == "builtin"


# ── the filesystem's seats ──────────────────────────────────────────────────
#
# These exist because `builtin` is the app's default and it was functional for exactly one of the four
# shipped worlds. `SurveyReasoner` proposed every action with no arguments; every files action needs a
# `path`; so every probe came back "bad arguments for list_dir", and the run stopped on `no_progress`
# at its second event while the window offered all four worlds as equals.


class _Rooted:
    """Stands in for `RootedFiles` — the reasoner only ever reads `.root` off the environment."""

    def __init__(self, root: str) -> None:
        self.root = root


def test_a_files_run_starts_somewhere_instead_of_proposing_bare_actions():
    moves = asyncio.run(FilesReasoner({}, _Rooted("/w")).propose(
        AgentState(GoalType("find the README")), 3, set()))
    assert moves, "the reasoner proposed nothing at all"
    # The failure this replaces: every action proposed with empty args.
    assert all(m.args for m in moves), [m.label() for m in moves]
    assert any(m.tool == "list_dir" and m.args.get("path") == "/w" for m in moves), [m.label() for m in moves]


def test_with_no_root_it_proposes_nothing_rather_than_guessing_at_slash():
    moves = asyncio.run(FilesReasoner({}, None).propose(AgentState(GoalType("find x")), 3, set()))
    assert moves == []


def test_the_goal_decides_what_is_searched_for():
    assert "README" in goal_words("find the README and say what this project is")
    # Stopwords would otherwise dominate; a search for "the" is a search for everything.
    assert not {"the", "and", "what", "is"} & set(goal_words("find the README and what is"))


@pytest.mark.parametrize("path,noisy", [
    ("/w/app/node_modules/x/Project.xml", True),
    ("/w/.venv/lib/python3.10/site-packages/a.py", True),
    ("/w/ti_matrix.egg-info/PKG-INFO", True),
    ("/w/app/renderer/core/project.ts", False),
    ("/w/README.md", False),
])
def test_somebody_elses_code_is_not_this_project_s_answer(path, noisy):
    assert is_noise(path) is noisy


def test_a_vendored_match_never_beats_a_real_one():
    """The first rule-based files run settled on a file inside node_modules. It was a correct match."""
    state = AgentState(GoalType("what is this project"), facts=(
        "list_dir(path=/w) -> ok: Contents of /w — 2 entries: 📁 app · 📄 README.md (10 B)",
        "find_files(path=/w, contains=project) -> ok: 2 file(s) under /w with 'project' in the name: "
        "/w/app/node_modules/iconv/.idea/Project_Default.xml · /w/app/renderer/core/project.ts",
    ))
    moves = asyncio.run(FilesReasoner({}, _Rooted("/w")).propose(state, 3, set()))
    reads = [m.args.get("path") for m in moves if m.tool == "read_file"]
    assert reads, [m.label() for m in moves]
    assert not any("node_modules" in str(p) for p in reads), reads


def test_reading_the_file_the_goal_named_settles_it_with_the_file_s_own_words():
    r = FilesReasoner({}, _Rooted("/w"))
    move = Action("read_file", {"path": "/w/README.md"}, "")
    obs = Observation(move, True, "Ti Matrix is an engine for state-driven search.")
    [verdict] = asyncio.run(r.evaluate(AgentState(GoalType("find the README")), [obs]))
    assert verdict.done is True
    assert "README.md" in verdict.answer and "state-driven" in verdict.answer


def test_a_files_probe_that_failed_still_scores_nothing():
    r = FilesReasoner({}, _Rooted("/w"))
    obs = Observation(Action("list_dir", {"path": "/nope"}, ""), False, "no such directory")
    [verdict] = asyncio.run(r.evaluate(AgentState(GoalType("find x")), [obs]))
    assert verdict.progress == 0.0 and verdict.done is False


# ── the browser's seats ─────────────────────────────────────────────────────
#
# Same defect the filesystem had: `SurveyReasoner` proposed `goto()`, `page_text()`, `html()` with no
# arguments, and `goto` with no URL cannot do anything. Verified against real headless Chrome after the
# fix: 16 events, page loaded, text read, settled on the page's own words.


class _Started:
    """Stands in for `BrowserEnvironment` — the reasoner only reads `.start_url` off it."""

    def __init__(self, url: str | None) -> None:
        self.start_url = url


def test_the_first_move_is_the_page_the_run_was_pointed_at():
    moves = asyncio.run(BrowserReasoner({}, _Started("https://example.com")).propose(
        AgentState(GoalType("find the price")), 3, set()))
    assert [m.label() for m in moves] == ["goto(url=https://example.com)"]


def test_with_no_start_url_it_proposes_nothing_rather_than_inventing_one():
    moves = asyncio.run(BrowserReasoner({}, _Started(None)).propose(
        AgentState(GoalType("find the price")), 3, set()))
    assert moves == []


def test_once_a_page_is_open_it_reads_before_it_navigates():
    state = AgentState(GoalType("find the price"), facts=(
        "goto(url=https://shop.test) -> ok: loaded https://shop.test/ — Shop",))
    moves = asyncio.run(BrowserReasoner({}, _Started("https://shop.test")).propose(state, 3, set()))
    assert {m.tool for m in moves} <= {"title_and_url", "page_text", "links"}, [m.label() for m in moves]


def test_it_follows_a_link_the_goal_names_and_ignores_the_rest():
    state = AgentState(GoalType("find the pricing page"), facts=(
        "goto(url=https://shop.test) -> ok: loaded https://shop.test/ — Shop",
        "links() -> ok: - About us — https://shop.test/about\n- Pricing — https://shop.test/pricing",
    ))
    moves = asyncio.run(BrowserReasoner({}, _Started("https://shop.test")).propose(state, 6, set()))
    gotos = [m.args.get("url") for m in moves if m.tool == "goto"]
    assert "https://shop.test/pricing" in gotos, [m.label() for m in moves]
    assert "https://shop.test/about" not in gotos, [m.label() for m in moves]


def test_a_rule_never_proposes_something_that_changes_the_page():
    """click, type, press and evaluate exist. Deciding to press a button is a judgement, not a rule."""
    state = AgentState(GoalType("buy the thing"), facts=(
        "goto(url=https://shop.test) -> ok: loaded https://shop.test/ — Shop",))
    moves = asyncio.run(BrowserReasoner({}, _Started("https://shop.test")).propose(state, 9, set()))
    assert not ({m.tool for m in moves} & {"click", "type", "press", "evaluate", "new_tab", "close_tab"})


def test_the_page_s_own_words_are_the_answer_when_they_carry_the_goal():
    r = BrowserReasoner({}, _Started("https://shop.test"))
    move = Action("page_text", {}, "")
    obs = Observation(move, True, "Our pricing starts at 9 dollars per month.")
    [verdict] = asyncio.run(r.evaluate(AgentState(GoalType("find the pricing")), [obs]))
    assert verdict.done is True and "pricing" in verdict.answer.lower()
