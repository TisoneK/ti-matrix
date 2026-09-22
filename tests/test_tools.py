"""Tool sets: who wins a collision, how a shadow is expressed, and how actions find their way home.

The precedence rules are the whole point of this module's existence, so they are tested as rules — declared
preference, declared supersession, and a resolution a caller can read — rather than through any one caller's
convenience.
"""
from __future__ import annotations

import pytest

from ti_matrix import (
    Action,
    ActionSpec,
    CompositeEnvironment,
    EngineTools,
    Observation,
    Statistics,
    ToolSet,
    ToolSetError,
    ToolSource,
)


def spec(name, read_only=True, **kw):
    return ActionSpec(name, f"does {name}", '{"x": 1}', read_only, **kw)


class FakeEnv:
    """The smallest environment that can answer: a tool table and a probe that says who served it."""

    def __init__(self, name, names, *, builtin=False):
        self.name, self.builtin = name, builtin
        self._tools = {n: spec(n) for n in names}
        self.asked = []

    def tools(self):
        return self._tools

    def is_read_only(self, action):
        found = self._tools.get(action.tool)
        return None if found is None else found.read_only

    async def probe(self, action):
        self.asked.append(action.label())
        return Observation(action, True, f"{self.name!r} answered {action.tool}")


# ─── the precedence rules ───────────────────────────────────────────────────


def test_a_user_tool_shadows_a_builtin_of_the_same_name_and_the_resolution_says_so():
    ours = ToolSource("engine", {"read_file": spec("read_file")}, builtin=True)
    theirs = ToolSource("app", {"read_file": spec("read_file")})
    resolved = ToolSet(ours, theirs)

    assert list(resolved.tools()) == ["read_file"]
    assert resolved.provider_of("read_file") == "app"  # the user's tool, not ours
    resolution = resolved.resolution()
    assert resolution.kept == ("read_file",)
    assert ("engine:read_file", "shadowed by app:read_file") in resolution.dropped
    assert "dropped engine:read_file" in resolution.to_text()


def test_the_preference_can_be_flipped_and_says_which_way_it_went():
    ours = ToolSource("engine", {"read_file": spec("read_file")}, builtin=True)
    theirs = ToolSource("app", {"read_file": spec("read_file")})

    keep_ours = ToolSet(ours, theirs, prefer="builtin")
    assert keep_ours.provider_of("read_file") == "engine"
    assert keep_ours.resolution().dropped == (("app:read_file", "shadowed by engine:read_file"),)


def test_supersedes_puts_a_differently_named_replacement_under_the_canonical_name():
    ours = ToolSource("engine", {"read_file": spec("read_file")}, builtin=True)
    theirs = ToolSource("app", {"read_local_file": spec("read_local_file", supersedes="read_file")})
    resolved = ToolSet(ours, theirs)

    # One tool, under the name the model already knew — and no second slot under the name its source gave
    # it, because one tool has one identity: the fingerprint every later record is keyed by.
    assert list(resolved.tools()) == ["read_file"]
    assert "read_local_file" not in resolved.tools()
    assert resolved.source_name("read_file") == "read_local_file"  # the app still knows its own name
    assert resolved.resolution().renamed == (("read_file", "read_local_file"),)
    assert resolved.resolution().dropped == (("engine:read_file", "shadowed by app:read_local_file"),)


def test_a_losing_superseder_is_absent_entirely():
    """It declared it replaces ours; being blocked is the outcome, not sitting beside it under a new name."""
    ours = ToolSource("engine", {"read_file": spec("read_file")}, builtin=True)
    theirs = ToolSource("app", {"read_local_file": spec("read_local_file", supersedes="read_file")})
    resolved = ToolSet(ours, theirs, prefer="builtin")

    assert list(resolved.tools()) == ["read_file"]
    assert resolved.provider_of("read_file") == "engine"
    assert "read_local_file" not in resolved.tools()


def test_two_user_tools_of_the_same_name_are_decided_by_the_order_they_were_given():
    first = ToolSource("app-a", {"open": spec("open")})
    second = ToolSource("app-b", {"open": spec("open")})
    assert ToolSet(first, second).provider_of("open") == "app-a"
    assert ToolSet(second, first).provider_of("open") == "app-b"


def test_an_unknown_preference_is_refused_rather_than_guessed():
    with pytest.raises(ToolSetError, match="prefer must be"):
        ToolSet(ToolSource("app", {"open": spec("open")}), prefer="maybe")


def test_require_names_what_is_missing_when_a_run_depends_on_a_tool():
    resolved = ToolSet(ToolSource("app", {"open": spec("open")}))
    resolved.require("open")  # present, so nothing happens
    with pytest.raises(ToolSetError, match=r"missing from this set: brief, recall"):
        resolved.require("brief", "recall")


# ─── routing: an action goes home, and the answer comes back under the engine's name ───


@pytest.mark.asyncio
async def test_a_composite_sends_each_action_to_the_environment_that_owns_it():
    files, ledger = FakeEnv("files", ["list_dir"]), FakeEnv("ledger", ["brief"])
    both = CompositeEnvironment(files, ledger)

    assert set(both.tools()) == {"list_dir", "brief"}
    assert both.name == "files+ledger"
    assert (await both.probe(Action("brief", {}))).text == "'ledger' answered brief"
    assert (await both.probe(Action("list_dir", {}))).text == "'files' answered list_dir"
    assert ledger.asked == ["brief()"] and files.asked == ["list_dir()"]


@pytest.mark.asyncio
async def test_a_composite_translates_a_renamed_tool_on_the_way_in_and_back_out():
    files = FakeEnv("files", ["read_file"], builtin=True)  # ours, so the app's replacement is preferred
    app = FakeEnv("app", ["read_local_file"])
    app._tools["read_local_file"] = spec("read_local_file", supersedes="read_file")
    both = CompositeEnvironment(files, app)

    seen = await both.probe(Action("read_file", {"x": 1}))
    assert app.asked == ["read_local_file(x=1)"]  # the app heard its own name
    assert seen.move.tool == "read_file"  # the engine's fingerprint stays the name the model proposed
    assert seen.ok and "app" in seen.text
    assert both.is_read_only(Action("read_file", {})) is True
    assert both.is_read_only(Action("delete_everything", {})) is None


@pytest.mark.asyncio
async def test_a_composite_reports_an_action_nobody_owns_instead_of_raising():
    both = CompositeEnvironment(FakeEnv("files", ["list_dir"]))
    obs = await both.probe(Action("nope", {}))
    assert obs.ok is False and "no environment here has an action called 'nope'" in obs.text


def test_a_composite_of_nothing_is_refused():
    with pytest.raises(ToolSetError, match="at least one environment"):
        CompositeEnvironment()


# ─── the engine's own tool ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_engine_tools_adds_recall_and_passes_every_other_call_straight_through():
    files = FakeEnv("files", ["list_dir"])
    stats = Statistics()
    stats.add_facts(["list_dir() -> ok: 3 entries"])
    tooled = EngineTools(files, memory=stats)

    assert set(tooled.tools()) == {"list_dir", "recall"}
    assert tooled.tools()["recall"].read_only is True
    assert tooled.builtin is True  # so a user's own `recall` would win, by the rule above
    assert tooled.is_read_only(Action("recall", {})) is True
    assert tooled.is_read_only(Action("list_dir", {})) is True
    assert tooled.is_read_only(Action("nope", {})) is None

    recalled = await tooled.probe(Action("recall", {"text": "3 entries"}))
    assert recalled.ok and "list_dir() -> ok: 3 entries" in recalled.text
    assert files.asked == []  # recall is answered by the engine, not by the environment
    assert (await tooled.probe(Action("list_dir", {}))).text == "'files' answered list_dir"


@pytest.mark.asyncio
async def test_recall_reports_bad_arguments_as_a_failure_never_a_crash():
    tooled = EngineTools(FakeEnv("files", []), memory=Statistics())
    obs = await tooled.probe(Action("recall", {"wrong": 1}))
    assert obs.ok is False and "bad arguments for recall" in obs.text

    class Broken:
        def recall(self, text="", limit=8):
            raise RuntimeError("the store went away")

    obs = await EngineTools(FakeEnv("files", []), memory=Broken()).probe(Action("recall", {}))
    assert obs.ok is False and "the store went away" in obs.text


def test_a_users_recall_wins_over_the_engines_by_the_same_rule_as_any_other_tool():
    tooled = EngineTools(FakeEnv("files", []), memory=Statistics())
    theirs = ToolSource("app", {"recall": spec("recall")})
    resolved = ToolSet(ToolSource(tooled.name, tooled.tools(), builtin=tooled.builtin), theirs)
    assert resolved.provider_of("recall") == "app"
