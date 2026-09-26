"""The sidecar over its real socket: the tests the app's behavior depends on.

Everything here goes through `create_app` and aiohttp's test server — the same handlers the packaged
app speaks to. The model endpoint is the conftest's local fake, so a full run (engine, maze, proposer,
evaluator) happens inside these tests with no network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp import WSMsgType

from appserver import protocol


async def test_healthz_and_worlds_need_no_token(server):
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{server.url}/healthz") as resp:
            body = await resp.json()
            assert resp.status == 200 and body["ok"] is True and body["protocol"] == protocol.PROTOCOL
        async with session.get(f"{server.url}/worlds") as resp:
            names = {w["name"] for w in (await resp.json())["worlds"]}
            assert names == {"maze", "files", "chess", "browser"}


async def test_a_socket_without_the_token_never_reaches_the_run(server, client_factory):
    import aiohttp
    async with aiohttp.ClientSession() as session:
        ws = await session.ws_connect(server.ws_url("0" * 32))
        msg = await ws.receive(timeout=5)
        assert msg.type == WSMsgType.CLOSE and ws.close_code == 1008  # RFC 6455: policy violation
        await ws.close()
        await session.close()


async def test_a_goal_runs_to_its_settled_frame(server, client_factory):
    client = await client_factory()
    await client.send(type="goal", text="reach the exit of the maze from its entry", world="maze",
                      config={"base_url": f"{server.url}/v1", "model": "fake", "api_key_env": ""})
    settled = await client.settle()

    assert settled["answer"] == "the exit is at 1,6" and settled["reason"] is None
    assert settled["events"] == len(client.events) > 0
    assert "settled: the exit is at 1,6" in settled["summary"]
    kinds = [e["kind"] for e in client.events]
    assert kinds[0] == "state" and "probe" in kinds and kinds[-1] == "done"
    # Every fake round hands back a `usage` object; a hosted run's settled frame sums them all up.
    assert settled["usage"]["calls"] == server.endpoint.requests
    assert settled["usage"]["total_tokens"] == server.endpoint.requests * 10


async def test_a_builtin_run_settles_with_no_usage_to_report(server, client_factory):
    """The rule-based seats never call the fake endpoint, so there is nothing honest to show — the
    frame omits `usage` rather than a set of zeroes that would read as "this run cost nothing"."""
    client = await client_factory()
    await client.send(type="goal", text="reach the exit of the maze from its entry", world="maze",
                      config={"base_url": "", "model": "builtin", "api_key_env": ""},
                      budget={"max_depth": 40, "max_model_calls": 300, "max_backtracks": 20})
    settled = await client.settle()
    assert settled["usage"] is None


async def test_a_second_goal_while_running_is_an_error_frame_not_a_crash(server, client_factory):
    client = await client_factory()
    await client.send(type="goal", text="reach the exit of the maze from its entry", world="maze",
                      config={"base_url": f"{server.url}/v1", "model": "fake"})
    await client.drain_until("probe")  # the run is definitely in flight now
    await client.send(type="goal", text="another", world="maze",
                      config={"base_url": f"{server.url}/v1", "model": "fake"})
    err = await client.drain_until("error")
    assert "already in flight" in err["message"]
    await client.settle()  # the first run still finishes cleanly


async def test_an_unknown_world_and_a_bad_config_are_error_frames(server, client_factory):
    client = await client_factory()
    await client.send(type="goal", text="x", world="narnia", config={})
    err = await client.drain_until("error")
    assert "no world named" in err["message"]

    await client.send(type="goal", text="x", world="files", config={})
    err = await client.drain_until("error")
    assert "root" in err["message"]

    await client.send(type="goal", text="x", world="maze",
                      config={"base_url": "", "model": ""})
    err = await client.drain_until("error")
    assert "base_url and model" in err["message"]


async def test_an_unknown_frame_type_is_reported(server, client_factory):
    client = await client_factory()
    await client.ws.send_str(protocol.encode("teleport", destination="moon"))
    err = await client.drain_until("error")
    assert "teleport" in err["message"]
    # and the server is still alive
    await client.send(type="goal", text="x", world="files", config={})
    assert "root" in (await client.drain_until("error"))["message"]


async def test_a_stop_before_a_goal_and_malformed_frames_are_survivable(server, client_factory):
    client = await client_factory()
    await client.send(type="stop")  # nothing running
    err = await client.drain_until("error")
    assert "nothing is running" in err["message"]

    await client.ws.send_str("this is not json")
    await client.ws.send_str("")  # empty frame
    await client.send(type="goal", text="reach the exit of the maze from its entry", world="maze",
                      config={"base_url": f"{server.url}/v1", "model": "fake"})
    settled = await client.settle()
    assert settled["answer"] == "the exit is at 1,6"


async def test_a_second_socket_sees_the_same_server_and_worlds(server, client_factory):
    first = await client_factory()
    second = await client_factory()
    await second.send(type="goal", text="x", world="narnia", config={})
    err = await second.drain_until("error")
    assert "no world named" in err["message"]
    # the first socket is untouched by anything the second said
    await first.send(type="stop")
    err = await first.drain_until("error")
    assert "nothing is running" in err["message"]


async def test_a_run_can_be_recorded_to_a_jsonl_log(server, client_factory, tmp_path):
    log = tmp_path / "run.jsonl"
    client = await client_factory()
    await client.send(type="goal", text="reach the exit of the maze from its entry", world="maze",
                      config={"base_url": f"{server.url}/v1", "model": "fake"}, record=str(log))
    await client.settle()

    from ti_matrix.adapters.run_log import read, summarize
    events = read(log)
    assert len(events) == len(client.events)
    assert "settled: the exit is at 1,6" in summarize(events)


async def test_a_builtin_goal_runs_with_no_endpoint_at_all(server, client_factory):
    """The first run on a fresh machine: no base_url, no key, nothing listening anywhere.

    This is the case the app shipped broken. The window defaulted to a model name that most machines
    do not have pulled, so a run ended on its second event with `proposer_error` and every panel drew
    an empty state — correctly, because there was nothing to draw. `model: "builtin"` fills the seats
    with rules instead, and the run below makes real probes against the real maze and settles.
    """
    client = await client_factory()
    await client.send(type="goal", text="reach the exit of the maze from its entry", world="maze",
                      config={"base_url": "", "model": "builtin", "api_key_env": ""},
                      budget={"max_depth": 40, "max_model_calls": 300, "max_backtracks": 20})
    settled = await client.settle()

    assert settled["reason"] is None, settled["reason"]
    assert settled["answer"] and "1,6" in settled["answer"], settled["answer"]
    kinds = [e["kind"] for e in client.events]
    assert kinds[0] == "state" and kinds[-1] == "done"
    # A real search: many probes against the world, not one lucky guess.
    assert kinds.count("probe") >= 5, kinds
    # And not a single request reached the fake endpoint — the rules never asked anyone anything.
    assert server.endpoint.requests == 0


async def test_builtin_needs_no_base_url_but_a_named_model_still_does(server, client_factory):
    """The config check must stay strict for endpoints while letting the rules through."""
    client = await client_factory()
    # An empty config is still an error — "builtin" is a deliberate choice, not the fallback for a typo.
    await client.send(type="goal", text="x", world="maze", config={"base_url": "", "model": ""})
    err = await client.drain_until("error")
    assert "builtin" in err["message"], err["message"]


async def test_a_remembering_run_shows_the_model_the_recall_tool(server, client_factory, tmp_path):
    """`recall` is added by wrapping the environment, so the seats must be built after the wrap.

    They were not: `LLMMoveProposer` was constructed from `env.tools()` before `EngineTools` wrapped
    it, so the engine would answer a `recall` probe and the model was never told the action existed —
    the one tool that lets it ask what earlier runs established, invisible in the prompt.
    """
    from ti_matrix.adapters.maze import MazeEnvironment
    from ti_matrix.learning import Statistics
    from ti_matrix.tools import EngineTools

    raw = MazeEnvironment()
    assert "recall" not in raw.tools()
    assert "recall" in EngineTools(raw, memory=Statistics()).tools()

    # And end to end: a run that remembers leaves a record behind and says so.
    stats = tmp_path / "maze.json"
    client = await client_factory()
    await client.send(type="goal", text="reach the exit of the maze from its entry", world="maze",
                      config={"base_url": "", "model": "builtin"},
                      remember=str(stats),
                      budget={"max_depth": 40, "max_model_calls": 300, "max_backtracks": 20})
    settled = await client.settle()
    assert settled["reason"] is None, settled["reason"]
    assert settled["learned"] and "remembered" in settled["learned"], settled["learned"]
    assert stats.exists(), "the run remembered nothing"
