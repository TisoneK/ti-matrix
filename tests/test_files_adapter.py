"""Adapter #2 — a read-only filesystem — must work with no host application present."""
from __future__ import annotations

import asyncio
import time

import pytest

from ti_matrix.adapters import files as files_adapter
from ti_matrix.adapters.files import FilesEnvironment
from ti_matrix.protocols import Action


@pytest.fixture()
def env(tmp_path):
    (tmp_path / "a.txt").write_text("hello world")
    (tmp_path / "notes.md").write_text("note")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.py").write_text("x = 1")
    return FilesEnvironment(), tmp_path


def test_every_action_it_offers_is_read_only(env):
    env_, _ = env
    assert env_.tools() and all(spec.read_only for spec in env_.tools().values())
    assert env_.is_read_only(Action("list_dir", {"path": "/"})) is True
    assert env_.is_read_only(Action("delete_everything", {})) is None  # not an action here


@pytest.mark.asyncio
async def test_it_reports_real_facts_and_real_failures(env):
    env_, d = env
    listing = await env_.probe(Action("list_dir", {"path": str(d)}))
    assert listing.ok and "a.txt" in listing.text and "sub" in listing.text
    assert listing.predicted is False  # a real probe, never a prediction

    text = await env_.probe(Action("read_file", {"path": str(d / "a.txt")}))
    assert text.ok and text.text == "hello world"

    stat = await env_.probe(Action("stat_path", {"path": str(d / "a.txt")}))
    assert stat.ok and "11 bytes" in stat.text

    found = await env_.probe(Action("find_files", {"path": str(d), "contains": ".py"}))
    assert found.ok and "deep.py" in found.text

    missing = await env_.probe(Action("read_file", {"path": str(d / "nope.txt")}))
    assert missing.ok is False and "not a file" in missing.text

    bad = await env_.probe(Action("list_dir", {"wrong_argument": "x"}))
    assert bad.ok is False and "bad arguments" in bad.text


@pytest.mark.asyncio
async def test_a_name_search_can_return_a_directory(env):
    """A repository is a *directory*, and this action could never return one.

    It filtered its walk to `is_file()`, so a goal naming a folder had no way to be answered by search at
    all: the folder sat in the tree, one level down, invisible to the only action that searches for
    anything. Found on a real run that answered with a runtime directory while the checkout the goal meant
    was a directory the search could not return — and the supervisor spotted it in the panel that lists
    what the run saw, which showed the files and both halves of the path but never the folder itself.
    """
    env_, d = env
    wanted = d / "Dev" / "acme"
    (wanted / ".git").mkdir(parents=True)
    (wanted / "readme.md").write_text("x")

    found = await env_.probe(Action("find_files", {"path": str(d), "contains": "acme"}))
    assert found.ok
    assert str(wanted) in found.text, found.text
    assert "path(s)" in found.text, found.text
    # Which kind each hit is has to be readable from the observation: a goal that asks for a folder and one
    # that asks for a file cannot be told apart if the answer looks the same for both.
    assert f"{wanted}/" in found.text, found.text
    assert "1 directory, 0 file(s)" in found.text, found.text

    # And the empty answer says what it always said, in the words that are still true.
    none = await env_.probe(Action("find_files", {"path": str(d), "contains": "nothing-like-this"}))
    assert none.ok and "no file or directory under" in none.text, none.text


@pytest.mark.asyncio
async def test_a_name_search_is_bounded_and_says_so(env, monkeypatch):
    """A search that stopped must not read as a search that found nothing.

    The bound exists because this action walks whatever tree it is pointed at, and the files world now
    begins at the home directory — `find_files` over a real profile did not finish inside five minutes.
    """
    env_, d = env
    for i in range(6):
        (d / f"file{i}.txt").write_text("x")

    # Well under the tree's size: the walk must stop, and admit it.
    monkeypatch.setattr(files_adapter, "_WALK_MAX_ENTRIES", 4)
    stopped = await env_.probe(Action("find_files", {"path": str(d), "contains": "nomatch"}))
    assert stopped.ok
    assert "stopped at the 4-path limit" in stopped.text, stopped.text
    assert "paths searched" in stopped.text

    # And when nothing interrupted it, the answer is a plain one with no such caveat.
    monkeypatch.setattr(files_adapter, "_WALK_MAX_ENTRIES", 10_000)
    whole = await env_.probe(Action("find_files", {"path": str(d), "contains": "nomatch"}))
    assert whole.ok and "stopped at" not in whole.text, whole.text


@pytest.mark.asyncio
async def test_a_name_search_does_not_walk_past_its_depth(env, monkeypatch):
    env_, d = env
    deep = d / "one" / "two" / "three"
    deep.mkdir(parents=True)
    (deep / "wanted.txt").write_text("x")

    monkeypatch.setattr(files_adapter, "_WALK_MAX_DEPTH", 1)
    shallow = await env_.probe(Action("find_files", {"path": str(d), "contains": "wanted"}))
    assert shallow.ok and "no file or directory under" in shallow.text

    monkeypatch.setattr(files_adapter, "_WALK_MAX_DEPTH", 6)
    reached = await env_.probe(Action("find_files", {"path": str(d), "contains": "wanted"}))
    assert reached.ok and "wanted.txt" in reached.text


@pytest.mark.asyncio
async def test_a_slow_probe_does_not_freeze_the_callers_event_loop(env, monkeypatch):
    """The reason this matters is not tidiness: the host awaits a probe on the loop it serves the run's
    own control channel from, so a probe that blocks it stops a run being reported on — or stopped."""
    env_, d = env
    monkeypatch.setattr(FilesEnvironment, "_list_dir", lambda self, path: (time.sleep(0.3), (True, "slow"))[1])

    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    obs = await env_.probe(Action("list_dir", {"path": str(d)}))
    beat.cancel()
    assert obs.ok and obs.text == "slow"
    assert ticks >= 3, f"the event loop was starved while the probe ran ({ticks} beats in 300ms)"
