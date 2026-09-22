"""The engine's search behavior, with scripted stubs — no environment, no host, no model."""
from __future__ import annotations

import pytest

from ti_matrix import ActionSpec, AgentState, EngineBudget, Evaluation, Goal, Move, Observation, StateEngine
from ti_matrix.model import LLMEvaluator, LLMMoveProposer, parse_json

GOAL = Goal("find the project name")


def mv(tool="dir_explorer", **args):
    return Move(tool, args or {"path": "/x"}, "why")


class ScriptedProposer:
    """Returns the next scripted list of moves, minus anything in `avoid` (as the real one does)."""

    def __init__(self, *rounds):
        self.rounds, self.seen_avoid = list(rounds), []

    async def propose(self, state, n, avoid):
        self.seen_avoid.append(set(avoid))
        moves = self.rounds.pop(0) if self.rounds else []
        return [m for m in moves if m.fingerprint() not in avoid][:n]


class FakeExecutor:
    def __init__(self, results):  # {fingerprint-or-label: (ok, text)}
        self.results, self.ran = results, []

    async def run(self, move):
        self.ran.append(move.label())
        ok, text = self.results.get(move.label(), (True, "ok"))
        return Observation(move, ok, text)


CATALOG = {
    s.name: s
    for s in (
        ActionSpec("dir_explorer", "look in a folder", '{"path": "..."}'),
        ActionSpec("file_read", "read a file", '{"path": "..."}'),
        ActionSpec("file_write", "write a file", '{"path": "...", "content": "..."}', read_only=False),
        ActionSpec("shell", "run a command", '{"command": "..."}', read_only=False),
    )
}


class ScriptedEnvironment:
    """The smallest environment the engine needs: a tool table and a probe."""

    name = "scripted"

    def __init__(self, executor, catalog=None):
        self._executor, self._catalog = executor, catalog or CATALOG

    def tools(self):
        return self._catalog

    def is_read_only(self, action):
        spec = self._catalog.get(action.tool)
        return None if spec is None else spec.read_only

    async def probe(self, action):
        return await self._executor.run(action)


class ScriptedEvaluator:
    def __init__(self, table):  # {label: Evaluation}
        self.table = table

    async def evaluate(self, state, outcomes):
        return [self.table.get(o.move.label(), Evaluation()) if o.ok else Evaluation() for o in outcomes]


async def collect(engine, goal=GOAL):
    return [e async for e in engine.run(goal)]


def engine(proposer, executor, evaluator, catalog=None, simulator=None, **budget):
    return StateEngine(
        ScriptedEnvironment(executor, catalog), proposer=proposer,
        evaluator=evaluator, simulator=simulator, budget=EngineBudget(**budget) if budget else None,
    )


@pytest.mark.asyncio
async def test_one_step_done_returns_a_grounded_answer():
    a = mv(path="/a")
    ev = await collect(engine(ScriptedProposer([a]), FakeExecutor({}),
                              ScriptedEvaluator({a.label(): Evaluation(1.0, True, "3 files", "found")})))
    assert [e.kind for e in ev][-1] == "done" and ev[-1].data["answer"] == "3 files"


@pytest.mark.asyncio
async def test_no_progress_backtracks_and_never_repeats_a_failed_move():
    a, b, c = mv(path="/a"), mv(path="/b"), mv(path="/c")
    prop = ScriptedProposer([a], [b], [a, c])  # depth0: a (progress) ; depth1: b (stalls) ; back at depth0: a is now failed
    evalr = ScriptedEvaluator({
        a.label(): Evaluation(0.4), b.label(): Evaluation(0.1), c.label(): Evaluation(1.0, True, "ans"),
    })
    ev = await collect(engine(prop, FakeExecutor({}), evalr))
    kinds = [e.kind for e in ev]
    assert "backtrack" in kinds and kinds[-1] == "done"
    assert a.fingerprint() in prop.seen_avoid[-1]  # the move that led nowhere is remembered


@pytest.mark.asyncio
async def test_failed_probes_are_not_progress_and_the_stop_is_honest():
    a = mv(path="/nope")
    ev = await collect(engine(ScriptedProposer([a]), FakeExecutor({a.label(): (False, "not found")}),
                              ScriptedEvaluator({}), max_backtracks=0))
    assert ev[-1].kind == "stopped" and ev[-1].data["settled"] is False and ev[-1].data["reason"] == "no_progress"


@pytest.mark.asyncio
async def test_a_move_that_is_not_read_only_is_never_executed():
    w = Move("file_write", {"path": "/x", "content": "y"}, "create it")
    ex = FakeExecutor({})
    ev = await collect(engine(ScriptedProposer([w]), ex, ScriptedEvaluator({})))
    assert ex.ran == []
    assert any(e.kind == "needs_confirmation" for e in ev)


@pytest.mark.asyncio
async def test_unknown_tools_are_dropped_and_remembered():
    ghost = Move("teleport", {}, "?")
    prop = ScriptedProposer([ghost])
    ev = await collect(engine(prop, FakeExecutor({}), ScriptedEvaluator({})))
    assert ev[-1].kind == "stopped" and ev[-1].data["reason"] == "no_moves"


@pytest.mark.asyncio
async def test_depth_budget_stops_honestly_with_what_is_known():
    rounds = [[mv(path=f"/{i}")] for i in range(10)]
    evalr = ScriptedEvaluator({m[0].label(): Evaluation(0.1 * (i + 1)) for i, m in enumerate(rounds)})
    ev = await collect(engine(ScriptedProposer(*rounds), FakeExecutor({}), evalr, max_depth=3))
    last = ev[-1]
    assert last.kind == "stopped" and last.data["reason"] == "budget" and len(last.data["facts"]) == 3


@pytest.mark.asyncio
async def test_unselected_probes_still_teach_facts():
    a, b = mv(path="/a"), mv(path="/b")
    ev = await collect(engine(ScriptedProposer([a, b]), FakeExecutor({b.label(): (True, "the name is Foo")}),
                              ScriptedEvaluator({a.label(): Evaluation(1.0, True, "x"), b.label(): Evaluation(0.5)})))
    assert ev[-1].kind == "done"
    st = next(e for e in reversed(ev) if e.kind == "state")
    assert st.data["facts"] == 2  # the winner's fact + the runner-up's real observation


def test_state_is_immutable_and_render_is_bounded():
    s0 = AgentState(GOAL)
    s1 = s0.apply(Observation(mv(), True, "x" * 5000), Evaluation(0.5))
    assert s0.depth == 0 and s1.depth == 1 and s0.facts == ()
    assert len(s1.render()) < 900 and s1.progress == 0.5
    assert mv(path="/a").fingerprint() == mv(path="/a").fingerprint() != mv(path="/b").fingerprint()


def test_parse_json_survives_fences_and_prose():
    assert parse_json('sure!\n```json\n{"moves": []}\n```') == {"moves": []}
    assert parse_json("no json here") is None


class _Port:
    """A model port that returns whatever the test tells it to."""

    def __init__(self, text):
        self.text, self.prompts = text, []

    async def complete(self, prompt, *, max_chars=4000):
        self.prompts.append(prompt)
        return self.text


@pytest.mark.asyncio
async def test_llm_proposer_parses_dedupes_and_respects_avoid():
    a = mv(path="/a")
    text = ('{"moves": [{"tool": "dir_explorer", "args": {"path": "/a"}, "why": "1"},'
            ' {"tool": "dir_explorer", "args": {"path": "/a"}, "why": "dup"},'
            ' {"tool": "file_task", "args": {"path": "/b"}, "why": "2"}, "junk"]}')
    got = await LLMMoveProposer(_Port(text), CATALOG).propose(AgentState(GOAL), 3, set())
    assert [m.tool for m in got] == ["dir_explorer", "file_task"]
    got = await LLMMoveProposer(_Port(text), CATALOG).propose(AgentState(GOAL), 3, {a.fingerprint()})
    assert [m.tool for m in got] == ["file_task"]


@pytest.mark.asyncio
async def test_llm_evaluator_guards_failed_probes_and_answerless_done():
    ok, bad, noans = (Observation(mv(path=p), k, "t") for p, k in (("/a", True), ("/b", False), ("/c", True)))
    text = ('{"evals": [{"i": 0, "progress": 0.7, "done": true, "answer": "yes"},'
            ' {"i": 1, "progress": 0.9, "done": true, "answer": "lie"},'
            ' {"i": 2, "progress": 0.8, "done": true, "answer": ""}]}')
    e = await LLMEvaluator(_Port(text)).evaluate(AgentState(GOAL), [ok, bad, noans])
    assert (e[0].done, e[0].answer) == (True, "yes")
    assert (e[1].progress, e[1].done) == (0.0, False)  # a failed probe never counts, whatever the model says
    assert e[2].done is False  # "done" needs a grounded answer


@pytest.mark.asyncio
async def test_registry_executor_reports_unknown_tool_as_a_failed_observation():
    prop = ScriptedProposer([mv(tool="teleport", path="/x")])
    ev = await collect(engine(prop, FakeExecutor({}), ScriptedEvaluator({})))
    assert not any(e.kind == "probe" for e in ev)  # never probed...
    assert ev[-1].kind == "stopped" and ev[-1].data["reason"] in ("no_moves", "budget")


# ── The event contract any interface consumes ──────────────────────────────


@pytest.mark.asyncio
async def test_events_carry_tree_ids_sequence_clock_and_excerpts():
    a, b = mv(path="/a"), mv(path="/b")
    prop = ScriptedProposer([a], [b])
    evalr = ScriptedEvaluator({a.label(): Evaluation(0.3), b.label(): Evaluation(1.0, True, "ok", "settled")})
    ev = await collect(engine(prop, FakeExecutor({a.label(): (True, "alpha  text")}), evalr))
    assert [e.seq for e in ev] == list(range(1, len(ev) + 1))
    assert all(ev[i].t_ms <= ev[i + 1].t_ms for i in range(len(ev) - 1))
    states = [e for e in ev if e.kind == "state"]
    assert [s.data["node"] for s in states] == ["n0", "n1", "n2"]
    assert [s.data["parent"] for s in states] == [None, "n0", "n1"]
    assert states[0].data["goal"] == GOAL.text
    probe = next(e for e in ev if e.kind == "probe")
    assert probe.data["excerpt"] == "alpha text" and probe.data["fp"] == a.fingerprint() and probe.data["at"] == "n0"
    cand = next(e for e in ev if e.kind == "candidates")
    assert cand.data["moves"][0]["fp"] == a.fingerprint() and "why" in cand.data["moves"][0]
    assert ev[0].to_dict()["kind"] == "state" and ev[-1].to_dict()["answer"] == "ok"


@pytest.mark.asyncio
async def test_backtrack_event_names_the_node_it_returns_to():
    a, b, c = mv(path="/a"), mv(path="/b"), mv(path="/c")
    prop = ScriptedProposer([a], [b], [c])
    evalr = ScriptedEvaluator({a.label(): Evaluation(0.4), b.label(): Evaluation(0.1), c.label(): Evaluation(1.0, True, "x")})
    ev = await collect(engine(prop, FakeExecutor({}), evalr))
    bt = next(e for e in ev if e.kind == "backtrack")
    assert bt.data["node"] == "n0"
    later = [e for e in ev if e.seq > bt.seq and e.kind == "candidates"]
    assert later and later[0].data["at"] == "n0"  # the next fan hangs off the node we returned to


@pytest.mark.asyncio
async def test_a_state_carries_what_it_knows_so_a_ui_can_read_the_search():
    """The state is the point of this engine: the explorer shows its facts, what it ruled out, and its path."""
    a, b = mv(path="/a"), mv(path="/b")
    prop = ScriptedProposer([a], [b])
    evalr = ScriptedEvaluator({a.label(): Evaluation(0.3), b.label(): Evaluation(1.0, True, "ok", "settled")})
    ev = await collect(engine(prop, FakeExecutor({a.label(): (True, "alpha  text")}), evalr))
    states = [e for e in ev if e.kind == "state"]

    first = states[0].data
    assert first["fact_list"] == [] and first["trail"] == []  # nothing learned before the first move
    last = states[-1].data
    assert last["facts"] == len(last["fact_list"]) == 2  # one real observation per applied move
    assert a.label() in last["fact_list"][0] and "alpha text" in last["fact_list"][0]
    assert last["trail"] == [a.label(), b.label()]  # the path of applied moves, in the same words the model sees


@pytest.mark.asyncio
async def test_a_failed_probe_is_remembered_as_failed_even_when_the_round_succeeds():
    a, missing, good = mv(path="/a"), mv(path="/missing"), mv(path="/good")
    prop = ScriptedProposer([a], [missing, good])
    evalr = ScriptedEvaluator({a.label(): Evaluation(0.2), good.label(): Evaluation(1.0, True, "ok", "settled")})
    ex = FakeExecutor({a.label(): (True, "a"), missing.label(): (False, "no such path"), good.label(): (True, "good")})
    ev = await collect(engine(prop, ex, evalr))
    states = [e for e in ev if e.kind == "state"]
    assert missing.fingerprint() in states[-1].data["failed_fps"]  # not lost just because something worked
    assert states[-1].data["failed"] == 1
    assert good.fingerprint() not in states[-1].data["failed_fps"]


# ─── The Simulator: predicting an action that must not be performed ──────────


class ScriptedSimulator:
    """Predicts whatever the test says, and remembers what it was asked about."""

    def __init__(self, ok=True, text="would create notes.md with three lines"):
        self.ok, self.text, self.asked = ok, text, []

    async def predict(self, state, action):
        self.asked.append(action.label())
        return Observation(action, self.ok, self.text, predicted=True)


def _write_move():
    return Move("file_write", {"path": "/tmp/notes.md", "content": "one\ntwo\nthree"}, "write the notes")


@pytest.mark.asyncio
async def test_a_simulated_action_is_predicted_and_never_performed():
    w = _write_move()
    ex, sim = FakeExecutor({w.label(): (True, "should not run")}), ScriptedSimulator()
    ev = await collect(
        engine(ScriptedProposer([w]), ex, ScriptedEvaluator({w.label(): Evaluation(0.8)}), simulator=sim)
    )
    assert ex.ran == []                     # the environment was never touched
    assert sim.asked == [w.label()]         # ... and the simulator was asked instead
    probe = next(e for e in ev if e.kind == "probe")
    assert probe.data["predicted"] is True and probe.data["ok"] is True
    assert not any(e.kind == "needs_confirmation" for e in ev)  # a simulator replaces the refusal


@pytest.mark.asyncio
async def test_without_a_simulator_a_write_is_still_only_offered_for_confirmation():
    w = _write_move()
    ex = FakeExecutor({})
    ev = await collect(engine(ScriptedProposer([w]), ex, ScriptedEvaluator({})))
    assert ex.ran == [] and any(e.kind == "needs_confirmation" for e in ev)


@pytest.mark.asyncio
async def test_a_prediction_is_never_learned_as_a_fact():
    w = _write_move()
    sim = ScriptedSimulator()
    states = [e for e in await collect(
        engine(ScriptedProposer([w]), FakeExecutor({}), ScriptedEvaluator({w.label(): Evaluation(0.8)}), simulator=sim)
    ) if e.kind == "state"]
    # The prediction was scored and selected, but nothing about it entered the state's knowledge.
    assert all(s.data["fact_list"] == [] for s in states)
    assert states[-1].data["facts"] == 0
    assert states[-1].data["progress"] == 0.0  # ... and it did not move progress either


@pytest.mark.asyncio
async def test_a_prediction_can_never_settle_the_goal():
    w = _write_move()
    sim = ScriptedSimulator()
    ev = await collect(
        engine(ScriptedProposer([w]), FakeExecutor({}),
               # the evaluator is fooled into saying "done" about the prediction
               ScriptedEvaluator({w.label(): Evaluation(1.0, True, "notes.md was written", "settled")}),
               simulator=sim, max_backtracks=0)
    )
    assert ev[-1].kind == "stopped" and ev[-1].data["settled"] is False
    assert ev[-1].data["reason"] == "needs_action"          # it says what only a real action could finish
    assert "file_write" in ev[-1].data["needs"]
    assert ev[-1].data["predicted"]["result"] == "would create notes.md with three lines"
    assert not any(e.kind == "done" for e in ev)


@pytest.mark.asyncio
async def test_a_failed_prediction_is_reported_honestly_and_the_action_remembers_it():
    w = _write_move()
    sim = ScriptedSimulator(ok=False, text="the path is not writable")
    ev = await collect(
        engine(ScriptedProposer([w]), FakeExecutor({}), ScriptedEvaluator({}), simulator=sim, max_backtracks=0)
    )
    probe = next(e for e in ev if e.kind == "probe")
    assert probe.data["ok"] is False and probe.data["predicted"] is True
    assert "not writable" in probe.data["excerpt"]
