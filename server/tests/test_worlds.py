"""The world registry: what the app can be pointed at, and how a bad config fails.

Every world is a name, a form, and a factory. These tests hold the registry to what the app renders:
a description per world, a build per name, and ValueErrors — frames, never crashes — for an unknown
name or a config a world cannot use.
"""
from __future__ import annotations

import pytest

from appserver.worlds import RootedFiles, build, describe
from ti_matrix.adapters.maze import MazeEnvironment
from ti_matrix.protocols import Action


def test_the_registry_describes_every_world_with_its_form():
    worlds = {w["name"]: w for w in describe()}
    assert set(worlds) == {"maze", "files", "chess", "browser"}
    assert {f["name"] for f in worlds["maze"]["fields"]} == {"width", "height", "seed"}
    assert {f["name"] for f in worlds["files"]["fields"]} == {"root"}
    assert {f["name"] for f in worlds["browser"]["fields"]} == {"url", "headless"}
    assert all(isinstance(w["note"], str) and w["note"] for w in worlds.values())


def test_the_maze_builds_with_no_config_and_every_action_reads():
    env = build("maze", {})
    assert isinstance(env, MazeEnvironment)
    assert all(spec.read_only for spec in env.tools().values())


@pytest.mark.asyncio
async def test_the_files_world_is_read_only_and_confined_to_its_root(tmp_path):
    (tmp_path / "inside.txt").write_text("hello", encoding="utf-8")
    env: RootedFiles = build("files", {"root": str(tmp_path)})

    assert (await env.probe(Action("read_file", {"path": "inside.txt"}))).ok
    outside = tmp_path.parent / "elsewhere.txt"
    outside.write_text("secret", encoding="utf-8")
    refused = await env.probe(Action("read_file", {"path": str(outside)}))
    assert refused.ok is False and "refused" in refused.text
    # ...and an absolute path inside the root still works, rewritten only for the read itself
    assert (await env.probe(Action("read_file", {"path": str(tmp_path / "inside.txt")}))).ok


def test_a_bad_config_is_a_valueerror_with_a_message_a_form_can_show():
    with pytest.raises(ValueError, match="no world named"):
        build("narnia", {})
    with pytest.raises(ValueError, match="root"):
        build("files", {})
    # The Context Ledger world was removed from the picker; asking for it by name is now a plain
    # unknown-world error, which is the behaviour a stale saved config will actually hit.
    with pytest.raises(ValueError, match="no world named"):
        build("ledger", {})


def test_the_ledger_adapter_still_ships_even_though_the_app_no_longer_offers_it(tmp_path):
    """Dropping the world from the picker must not delete the adapter — `ledger_cli` still drives it."""
    from ti_matrix.adapters.context_ledger import LedgerEnvironment

    (tmp_path / ".context_ledger" / "memory" / "office").mkdir(parents=True)
    env = LedgerEnvironment(str(tmp_path))
    assert env.name == "context-ledger"
    # the writes are declared, so the engine reasons about them, and never performs one itself
    assert not all(spec.read_only for spec in env.tools().values())


def test_the_browser_world_builds_without_starting_a_browser():
    from ti_matrix.adapters.browser import BrowserEnvironment

    env = build("browser", {"url": "https://example.com"})
    assert isinstance(env, BrowserEnvironment)
    assert env.start_url == "https://example.com"
