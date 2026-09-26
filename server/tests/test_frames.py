"""The sidecar's page frames: a picture of the browser world beside every applied move.

The capture is host work — the sidecar takes the picture while the engine is paused inside its own
`async for`, keyed on the `state` event the engine emits exactly after applying a move. A fake
environment stands in for a real Chrome here: the point is what the *sidecar* does — when it captures,
where the file goes, what the event says, and that a failed capture never ends a run. The last two
tests drive the real websocket server end to end, with the world registry patched to hand out the
fake browser — the wiring, not the browser, is what is under test.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from appserver.main import _maybe_capture
from ti_matrix.protocols import ActionSpec, Observation


class FakeEnv:
    """Stands in for the browser environment: writes a real file, or fails on demand."""

    name = "browser"

    def __init__(self, frames_dir: Path | None = None, fail: bool = False) -> None:
        self.frames_dir = frames_dir
        self.fail = fail
        self.asked: list[Path] = []

    def tools(self) -> dict[str, ActionSpec]:
        return {"look": ActionSpec("look", "Read whatever the page offers.", "{}")}

    def is_read_only(self, action) -> bool:
        return True

    def close(self) -> None:
        pass

    async def probe(self, action) -> Observation:
        return Observation(action, True, "the page says hello")

    def capture_frame(self, path) -> tuple[bool, str]:
        self.asked.append(Path(path))
        if self.fail:
            return False, "CdpError: the tab went away"
        Path(path).write_bytes(b"\xff\xd8 fake jpeg")
        return True, "1280x720"


def state_event(seq: int, depth: int = 1) -> dict:
    return {"kind": "state", "seq": seq, "depth": depth}


def test_a_frame_is_captured_beside_each_applied_move_and_named_by_its_event_seq(tmp_path):
    env = FakeEnv(frames_dir=tmp_path)
    frame = state_event(7)
    _maybe_capture(frame, env)
    assert env.asked == [tmp_path / "7.jpg"]
    assert (tmp_path / "7.jpg").exists()
    assert frame["frame"] == str(tmp_path / "7.jpg")
    assert "frame_error" not in frame


def test_the_depth_zero_state_is_the_runs_opening_not_a_move(tmp_path):
    env = FakeEnv(frames_dir=tmp_path)
    frame = state_event(1, depth=0)
    _maybe_capture(frame, env)
    assert env.asked == []
    assert "frame" not in frame


def test_non_state_events_capture_nothing(tmp_path):
    env = FakeEnv(frames_dir=tmp_path)
    frame = {"kind": "probe", "seq": 3, "depth": 2}
    _maybe_capture(frame, env)
    assert env.asked == []


def test_an_environment_without_a_frames_dir_is_a_no_op():
    """The maze, files and chess worlds carry neither a frames dir nor a capture hook — every one of
    their events, and every event of a browser run whose host never asked, must pass through untouched."""
    env = FakeEnv()
    frame = state_event(2)
    _maybe_capture(frame, env)
    assert "frame" not in frame and "frame_error" not in frame


def test_a_failed_capture_is_recorded_not_fatal(tmp_path):
    env = FakeEnv(frames_dir=tmp_path, fail=True)
    frame = state_event(9)
    _maybe_capture(frame, env)  # must not raise — the run must not end over a picture
    assert "frame" not in frame
    assert "capture failed this step" in frame["frame_error"]
    assert not (tmp_path / "9.jpg").exists()


def test_a_raising_capture_is_caught_and_recorded(tmp_path):
    class Boom(FakeEnv):
        def capture_frame(self, path):
            raise RuntimeError("the browser is gone")

    env = Boom(frames_dir=tmp_path)
    frame = state_event(4)
    _maybe_capture(frame, env)
    assert "RuntimeError" in frame["frame_error"]
    assert "frame" not in frame


# ── the whole loop, over the real websocket ─────────────────────────────────


def _look_round(done: bool):
    move = {"tool": "look", "args": {}, "why": "because"}
    evals = [{"i": 0, "progress": 0.9 if done else 0.2, "done": done,
              "answer": "the page says hello" if done else "", "reason": ""}]
    return ([move], evals)


@pytest.mark.asyncio
async def test_a_browser_run_streams_its_frames_beside_the_moves(server, client_factory, monkeypatch, tmp_path):
    """End to end: goal in, events out, and every applied move's `state` event names a JPEG that is
    really on disk in this run's frames directory — written while the engine was paused mid-run."""
    from appserver import worlds as worlds_mod

    env = FakeEnv()
    monkeypatch.setattr(worlds_mod, "build", lambda name, config: env)
    env.frames_dir = tmp_path
    server.endpoint.rounds = [_look_round(True)]

    client = await client_factory()
    await client.send(type="goal", text="look at the page", world="browser",
                      config={"model": "fake-small", "base_url": server.url + "/v1",
                              "frames_dir": str(tmp_path)})
    settled = await client.settle()
    states = [e for e in client.events if e.get("kind") == "state" and int(e.get("depth", 0)) > 0]
    assert states, "a settling run applied at least one move"
    for state in states:
        path = Path(state["frame"])
        assert path.parent == tmp_path and path.name.endswith(".jpg")
        assert path.read_bytes().startswith(b"\xff\xd8")
    assert settled["answer"] == "the page says hello"


@pytest.mark.asyncio
async def test_a_failed_capture_rides_along_and_the_run_still_settles(server, client_factory, monkeypatch, tmp_path):
    from appserver import worlds as worlds_mod

    env = FakeEnv(fail=True)
    monkeypatch.setattr(worlds_mod, "build", lambda name, config: env)
    env.frames_dir = tmp_path
    server.endpoint.rounds = [_look_round(True)]

    client = await client_factory()
    await client.send(type="goal", text="look at the page", world="browser",
                      config={"model": "fake-small", "base_url": server.url + "/v1",
                              "frames_dir": str(tmp_path)})
    settled = await client.settle()
    states = [e for e in client.events if e.get("kind") == "state" and int(e.get("depth", 0)) > 0]
    assert states and all("frame_error" in e and "frame" not in e for e in states)
    assert not list(tmp_path.glob("*.jpg"))
    assert settled["answer"] == "the page says hello"  # the run ended well anyway
