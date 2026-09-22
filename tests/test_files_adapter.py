"""Adapter #2 — a read-only filesystem — must work with no host application present."""
from __future__ import annotations

import pytest

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
