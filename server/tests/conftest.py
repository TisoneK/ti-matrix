"""Fixtures for the sidecar's tests: an in-process server, a scripted model endpoint, frame helpers.

The sidecar is tested the way the app uses it — over its real HTTP + WebSocket surface, through
`create_app` — with one exception: the model endpoint is a local fake, so a run is driven end-to-end
(engine, maze, proposer, evaluator) without any network or model.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiohttp
import pytest
from aiohttp import WSMsgType, web

from appserver import protocol
from appserver.main import create_app

# ── a scripted stand-in for any OpenAI-compatible endpoint ──────────────────


class FakeEndpoint:
    """Serves POST /chat/completions from a script: proposer JSON per round, then evaluator JSON."""

    def __init__(self, *rounds) -> None:
        self.rounds = list(rounds)
        self.i = 0
        self.requests = 0

    async def handle(self, request: web.Request) -> web.Response:
        self.requests += 1
        moves, evals = self.rounds[min(self.i, len(self.rounds) - 1)]
        body = await request.json()
        prompt = body.get("messages", [{}])[-1].get("content", "")
        # The same tell ScriptedPort uses: the evaluator's prompt is the one that says "evals".
        if '"evals"' in prompt:
            self.i += 1
            content = json.dumps({"evals": evals})
        else:
            content = json.dumps({"moves": moves})
        return web.json_response({"choices": [{"message": {"role": "assistant", "content": content},
                                               "finish_reason": "stop"}],
                                  "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}})


def maze_rounds():
    """One step south per round, the exit announced on the last — the shortest maze conversation."""
    def step(cell, direction):
        return {"tool": "step", "args": {"cell": cell, "direction": direction}, "why": "walk"}

    def scored(progress, done=False, answer=""):
        return [{"i": 0, "progress": progress, "done": done, "answer": answer, "reason": ""}]

    route = [("1,1", "south"), ("1,2", "south"), ("1,3", "south"), ("1,4", "south"), ("1,5", "south")]
    rounds = []
    for i, (cell, direction) in enumerate(route):
        last = i == len(route) - 1
        rounds.append(([step(cell, direction)],
                       scored(1.0, True, "the exit is at 1,6") if last else scored(0.2 * (i + 1))))
    return rounds


# ── the server, in process ──────────────────────────────────────────────────


class Server:
    """`create_app` on a real ephemeral port, plus the frames it has sent (for the never-connected case)."""

    def __init__(self, token: str, port: int, runner: web.AppRunner) -> None:
        self.token, self.port, self.runner = token, port, runner
        self.sent: list[dict] = []
        self.worlds_frame: list[dict] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def ws_url(self, token: str | None = None) -> str:
        return f"ws://127.0.0.1:{self.port}/ws" + (f"?token={token}" if token else "")

    async def stop(self) -> None:
        await self.runner.cleanup()


@pytest.fixture()
async def server(monkeypatch):
    """One server per test, fresh token, real port; the handshake line asserted once, here."""
    from appserver import main as main_mod

    token = protocol.new_token()
    app = create_app(token)

    real_send = main_mod._send_frame

    async def spy(ws, frame):
        server.sent.append(json.loads(frame))  # what the app would see, even after a disconnect
        await real_send(ws, frame)

    monkeypatch.setattr(main_mod, "_send_frame", spy)

    # The fake model endpoint rides on the sidecar's own port under /v1 — so a test's base_url is
    # just server.url + "/v1", and a full run (engine, maze, proposer, evaluator) needs no network.
    endpoint = FakeEndpoint(*maze_rounds())
    app.router.add_post("/v1/chat/completions", endpoint.handle)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    server = Server(token, port, runner)
    server.endpoint = endpoint
    line = protocol.handshake_line(port, token)
    parsed = protocol.parse_handshake(line)
    assert parsed is not None and parsed[0] == protocol.PROTOCOL and parsed[2] == token
    yield server
    await server.stop()


# ── a WebSocket client that speaks the protocol ─────────────────────────────


class Client:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.events: list[dict] = []

    async def recv(self, timeout: float = 5.0) -> dict | None:
        msg = await asyncio.wait_for(self.ws.receive(), timeout)
        if msg.type != WSMsgType.TEXT:
            raise AssertionError(f"socket closed: type={msg.type} code={self.ws.close_code} extra={msg.data!r}")
        return json.loads(msg.data)

    async def drain_until(self, kind: str, timeout: float = 10.0) -> dict:
        """Frames until one of `kind` arrives; events are kept on `self.events`, everything else returned."""
        while True:
            frame = await self.recv(timeout)
            assert frame is not None, f"the socket closed before a {kind!r} frame arrived"
            if frame.get("type") == "event":
                self.events.append(frame)
                if frame.get("kind") == kind:
                    return frame
            elif frame.get("type") == kind:
                return frame

    async def settle(self, timeout: float = 15.0) -> dict:
        frame = await self.drain_until("settled", timeout)
        return frame

    async def send(self, **frame) -> None:
        await self.ws.send_str(protocol.encode(frame.pop("type"), **frame))


@pytest.fixture()
async def client_factory(server):
    clients: list[Client] = []

    async def make(token: str | None = None) -> Client:
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(server.ws_url(token or server.token))
        client = Client(ws)
        client.session = session
        clients.append(client)
        first = await client.recv()
        assert first and first.get("type") == "worlds"
        return client

    yield make

    for client in clients:
        await client.ws.close()
        await client.session.close()
