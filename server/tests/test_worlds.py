"""The world registry: what the app can be pointed at, and how a bad config fails.

Every world is a name, a form, and a factory. These tests hold the registry to what the app renders:
a description per world, a build per name, and ValueErrors — frames, never crashes — for an unknown
name or a config a world cannot use.
"""
from __future__ import annotations

from pathlib import Path

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


def test_the_files_world_tells_the_proposer_its_own_root(tmp_path):
    """A proposer told only 'path: <dir>' reaches for what it has seen most in training — '/',
    '/workspace', '/home' — and every one of those is refused the moment it lands outside the root
    (live, deepseek-flash, 2026-09-26: three refused guesses in one fan, zero progress). The tool
    descriptions now name the actual boundary and '.' as the way to start at it."""
    env: RootedFiles = build("files", {"root": str(tmp_path)})
    for spec in env.tools().values():
        assert str(tmp_path) in spec.description
        assert "'.'" in spec.description


def test_a_files_world_that_names_no_root_reads_from_home(monkeypatch, tmp_path):
    """An unnamed root is the home directory, not an error — a blank field still has to run.

    This matters because saved settings win over a field's default: an app that stored a blank root before
    the field shipped with a home default would otherwise never be able to run the files world at all."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # what expanduser reads on Windows...
    monkeypatch.setenv("HOME", str(tmp_path))         # ...and what it reads everywhere else
    home = Path(tmp_path).resolve()
    assert build("files", {}).root == home
    assert build("files", {"root": ""}).root == home
    assert build("files", {"root": "   "}).root == home


def test_the_form_is_sent_a_home_directory_it_can_actually_read(monkeypatch, tmp_path):
    """The registry states `~/`; the app is sent the directory that means, resolved when asked for.

    A literal `~` in the box is a path the person has to expand themselves, and on Windows into the other
    separator. Resolved per call, not at import, so it follows the environment the server is really in."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    fields = {f["name"]: f for f in {w["name"]: w for w in describe()}["files"]["fields"]}
    assert fields["root"]["default"] == str(Path(tmp_path).resolve())
    assert Path(fields["root"]["default"]).is_absolute()
    # ...and the world it describes agrees with the path it just showed
    assert str(build("files", {}).root) == fields["root"]["default"]


def test_a_bad_config_is_a_valueerror_with_a_message_a_form_can_show():
    with pytest.raises(ValueError, match="no world named"):
        build("narnia", {})
    with pytest.raises(ValueError, match="invalid literal"):
        build("maze", {"seed": "not-a-number"})
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
