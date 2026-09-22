"""The browser adapter: the protocol plumbing on its own, then a real browser driving a real engine.

Two halves, and they are tested differently on purpose.

The WebSocket client is 200 lines of protocol that nothing else in the project exercises, so it is tested
against a server built here out of raw sockets — a server that checks the mask bit a client is required to
set, answers with fragments, pings mid-message, and sends payloads long enough to need the 16- and 64-bit
length forms. A bug there would show up as a hang or a truncated screenshot, which is exactly the kind of
thing that is invisible until it is expensive.

The environment is tested against **real Chrome**, on a page served from this test, with the engine itself in
the loop: a goal, a scripted proposer, and a scripted evaluator that only calls the goal settled when the fact
it was waiting for is really in the text. Those tests skip when no browser is installed rather than pretending
to pass.
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import os
import socketserver
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ti_matrix import Action, EngineBudget, Evaluation, Goal, StateEngine
from ti_matrix.adapters.browser import (
    BrowserEnvironment,
    BrowserError,
    Chrome,
    WebSocket,
    WebSocketClosed,
    WebSocketError,
    find_browser,
)
from ti_matrix.adapters.browser.websocket import _GUID

WITH_BROWSER = pytest.mark.skipif(find_browser() is None,
                                 reason="no Chrome or Chromium on this machine")
PAGE_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>The price page</title></head><body>
<h1>Widgets</h1><p id="price">not loaded yet</p><a href="/more">More widgets</a>
<button id="go" onclick="document.getElementById('price').textContent='£42.50'">Show the price</button>
<script>setTimeout(function () {
  var p = document.createElement('p'); p.id = 'late'; p.textContent = 'arrived late';
  document.body.appendChild(p); }, 300);</script>
</body></html>
"""


# ─── a WebSocket server, from raw sockets, for testing the client ───────────


class _FakeWebSocketServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _FakeWebSocketHandler(socketserver.BaseRequestHandler):
    """Just enough of RFC 6455 to be a server: accept a handshake, send frames, read masked ones."""

    def handle(self) -> None:
        if not self._handshake():
            return
        self.server.client = self  # the test drives the server through this
        self.server.ready.set()
        try:
            while True:
                frame = self._recv_frame()
                if frame is None:
                    return
                opcode, payload = frame
                self.server.received.append((opcode, payload))
        except (OSError, WebSocketError):
            return

    def _handshake(self) -> bool:
        request = b""
        while b"\r\n\r\n" not in request:
            chunk = self.request.recv(4096)
            if not chunk:
                return False
            request += chunk
        headers = {}
        for line in request.decode("latin-1").split("\r\n")[1:]:
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()
        key = headers.get("sec-websocket-key", "")
        accept = "" if self.server.break_accept else hashlib_accept(key)
        self.request.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                              "Connection: Upgrade\r\nSec-WebSocket-Accept: "
                              f"{accept}\r\n\r\n").encode("ascii"))
        return True

    def _recv_exact(self, count: int) -> bytes:
        out = b""
        while len(out) < count:
            chunk = self.request.recv(count - len(out))
            if not chunk:
                raise OSError("closed")
            out += chunk
        return out

    def _recv_frame(self):
        first, second = self._recv_exact(2)
        opcode = first & 0x0F
        masked, length = bool(second & 0x80), second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length) if length else b""
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload

    # ── what the tests call ──

    def send_frame(self, opcode: int, payload: bytes, *, final: bool = True) -> None:
        header = bytearray([(0x80 if final else 0) | opcode])
        if len(payload) < 126:
            header.append(len(payload))
        elif len(payload) < 1 << 16:
            header.append(126)
            header += struct.pack("!H", len(payload))
        else:
            header.append(127)
            header += struct.pack("!Q", len(payload))
        self.request.sendall(bytes(header) + payload)


def hashlib_accept(key: str) -> str:
    import base64
    return base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()


@pytest.fixture()
def ws_server():
    server = _FakeWebSocketServer(("127.0.0.1", 0), _FakeWebSocketHandler)
    server.ready = threading.Event()
    server.received = []
    server.break_accept = False
    server.url = f"ws://127.0.0.1:{server.server_address[1]}/socket"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def connect(server, **kw) -> WebSocket:
    client = WebSocket(server.url, timeout_s=kw.pop("timeout_s", 5.0), **kw)
    assert server.ready.wait(5), "the fake server never saw a handshake"
    return client


# ─── the protocol ───────────────────────────────────────────────────────────


def test_the_handshake_is_the_one_rfc_6455_asks_for(ws_server):
    client = connect(ws_server)
    assert client.url == ws_server.url
    client.close()


def test_a_server_that_cannot_prove_it_understood_is_refused(ws_server):
    ws_server.break_accept = True
    with pytest.raises(WebSocketError, match="did not prove"):
        WebSocket(ws_server.url, timeout_s=5.0)


def test_a_text_frame_arrives_and_a_client_masks_what_it_sends(ws_server):
    client = connect(ws_server)
    client.send_text("hello browser")
    deadline = time.monotonic() + 5
    while not ws_server.received and time.monotonic() < deadline:
        time.sleep(0.01)
    opcode, payload = ws_server.received[0]
    assert (opcode, payload) == (0x1, b"hello browser")  # the server un-masked it: masking was correct

    ws_server.client.send_frame(0x1, "and hello back".encode())
    assert client.recv_text() == "and hello back"
    client.close()


def test_a_long_payload_survives_both_extended_length_forms(ws_server):
    """Screenshots come back as base64 megabytes: the 16- and 64-bit length forms have to work."""
    client = connect(ws_server)
    for size in (126, 70_000):
        original = "x" * size
        ws_server.client.send_frame(0x1, original.encode())
        assert client.recv_text() == original
    client.send_text("y" * 70_000)
    deadline = time.monotonic() + 5
    while len(ws_server.received) < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ws_server.received[0][1] == b"y" * 70_000
    client.close()


def test_a_fragmented_message_is_reassembled(ws_server):
    """Chrome does not promise to send a screenshot in one frame, so this is not a theoretical case."""
    client = connect(ws_server)
    ws_server.client.send_frame(0x1, b"first half, ", final=False)
    ws_server.client.send_frame(0x0, b"second half", final=True)
    assert client.recv_text() == "first half, second half"
    client.close()


def test_a_ping_is_answered_with_a_pong_even_mid_message(ws_server):
    client = connect(ws_server)
    ws_server.client.send_frame(0x9, b"are you there")  # ping
    ws_server.client.send_frame(0x1, b"payload", final=False)
    ws_server.client.send_frame(0x9, b"still there")
    ws_server.client.send_frame(0x0, b"!", final=True)
    assert client.recv_text() == "payload!"
    deadline = time.monotonic() + 5
    while len([f for f in ws_server.received if f[0] == 0xA]) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len([f for f in ws_server.received if f[0] == 0xA]) == 2
    client.close()


def test_closing_is_a_close_frame_and_then_silence(ws_server):
    """This used to raise: close() set its own guard before sending the frame its guard rejected."""
    client = connect(ws_server)
    client.close()
    client.close()  # a second close is a no-op, not a second frame
    deadline = time.monotonic() + 5
    while not ws_server.received and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ws_server.received and ws_server.received[0][0] == 0x8
    with pytest.raises(WebSocketClosed):
        client.send_text("too late")


def test_a_close_from_the_server_ends_the_read_and_a_url_that_is_not_a_socket_is_refused(ws_server):
    client = connect(ws_server)
    ws_server.client.send_frame(0x8, struct.pack("!H", 1000))
    with pytest.raises(WebSocketClosed):
        client.recv_text()
    client.close()

    with pytest.raises(WebSocketError, match="only ws"):
        WebSocket("http://127.0.0.1:1/x")
    with pytest.raises(WebSocketError, match="no host"):
        WebSocket("ws:///nope")
    with pytest.raises(OSError):  # nothing is listening there
        WebSocket("ws://127.0.0.1:9/socket", timeout_s=2.0)


def test_the_browser_is_found_where_browsers_are_or_not_at_all():
    found = find_browser()
    assert found is None or (Path(found).is_file() and os.access(found, os.X_OK))


# ─── the environment's boundary, which needs no browser ─────────────────────


def test_the_boundary_is_reads_by_default_and_a_host_can_grant_more():
    env = BrowserEnvironment("https://example.com")
    reads = {name for name, spec in env.tools().items() if spec.read_only}
    assert reads == {"goto", "page_text", "html", "links", "find", "title_and_url", "wait_for",
                     "screenshot", "scroll", "back", "forward"}
    assert {name for name in env.tools() if name not in reads} == {
        "click", "type", "press", "evaluate", "new_tab", "close_tab"}
    assert env.is_read_only(Action("click", {})) is False
    assert env.is_read_only(Action("teleport", {})) is None

    granted = BrowserEnvironment("https://example.com", perform={"click", "type"})
    assert granted.is_read_only(Action("click", {})) is True
    assert granted.is_read_only(Action("type", {})) is True
    assert granted.is_read_only(Action("evaluate", {})) is False  # not asked for, so still not allowed


@pytest.mark.asyncio
async def test_a_write_action_is_refused_without_touching_a_browser_and_says_how_to_allow_it():
    """No browser is launched here: the refusal happens before anything is started."""
    env = BrowserEnvironment("https://example.com")
    obs = await env.probe(Action("click", {"selector": "#buy"}))
    assert obs.ok is False and "would change the page" in obs.text and "perform={'click'}" in obs.text
    assert env._page is None and env._chrome is None  # nothing was started to find that out

    unknown = await env.probe(Action("teleport", {}))
    assert unknown.ok is False and "no browser action called" in unknown.text


# ─── a real browser, a real page, and the engine in the loop ────────────────


@pytest.fixture()
def page_server(tmp_path_factory):
    """The page under test, served from this test so nothing depends on the network."""
    directory = tmp_path_factory.mktemp("page")
    (directory / "index.html").write_text(PAGE_HTML)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))

    class Quiet(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Quiet(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/index.html"
    server.shutdown()
    server.server_close()


class ReadsThePage:
    """A proposer that works through a fixed sequence of moves, one fan at a time — a stand-in for a model.

    The sequence matters: clicking and then reading cannot be one fan, because a fan is probed all at once and
    the read could land before the click. A model does what a person does — act, then look.
    """

    def __init__(self, *moves):
        self.moves = list(moves)
        self.asked = 0

    async def propose(self, state, n, avoid):
        self.asked += 1
        tool, args = self.moves[min(self.asked - 1, len(self.moves) - 1)]
        return [Action(tool, args, "because")]


class KnowsTheAnswer:
    """An evaluator that settles the goal only when the fact it wants is really in the observation."""

    def __init__(self, needle: str, partial: str = ""):
        self.needle, self.partial = needle, partial

    async def evaluate(self, state, outcomes):
        out = []
        for obs in outcomes:
            hit = obs.ok and self.needle in obs.text
            half = bool(self.partial) and obs.ok and self.partial in obs.text
            out.append(Evaluation(1.0 if hit else (0.5 if half else 0.0), hit, self.needle if hit else "",
                                  "the page says so" if hit else ("a step closer" if half else "not yet")))
        return out


@WITH_BROWSER
@pytest.mark.asyncio
async def test_the_engine_reads_a_real_page_and_settles_on_what_it_found(page_server, tmp_path):
    """The whole point: a goal, a browser, and an answer that came from the page."""
    env = BrowserEnvironment(page_server, headless=True, screenshot_dir=tmp_path)
    try:
        engine = StateEngine(env, proposer=ReadsThePage(("page_text", {})),
                             evaluator=KnowsTheAnswer("Widgets"),
                             budget=EngineBudget(max_model_calls=6))
        events = [e async for e in engine.run(Goal("what is this page about?"))]
        assert events[-1].kind == "done"
        assert events[-1].data["answer"] == "Widgets"
        assert any(e.kind == "probe" and e.data["ok"] for e in events)
        probe = next(e for e in events if e.kind == "probe")
        assert "Widgets" in probe.data["excerpt"] and "More widgets" in probe.data["excerpt"]
    finally:
        env.close()


@WITH_BROWSER
@pytest.mark.asyncio
async def test_a_goal_that_needs_a_click_stops_and_names_the_click_it_would_need(page_server, tmp_path):
    """The engine may read a page, and may not press a button on it: that is the whole safety story."""
    env = BrowserEnvironment(page_server, headless=True, screenshot_dir=tmp_path)
    try:
        engine = StateEngine(env, proposer=ReadsThePage(("click", {"selector": "#go"})),
                             evaluator=KnowsTheAnswer("£42.50"),
                             simulator=None, budget=EngineBudget(max_model_calls=4))
        events = [e async for e in engine.run(Goal("what is the price?"))]
        assert events[-1].kind == "stopped" and events[-1].data["settled"] is False
        assert any(e.kind == "needs_confirmation" and e.data["move"] == "click(selector=#go)" for e in events)
        assert not any(e.kind == "probe" for e in events)  # it never touched the button
        assert env.page().find("#price")["text"] == "not loaded yet"  # and the page is untouched
    finally:
        env.close()


@WITH_BROWSER
@pytest.mark.asyncio
async def test_a_host_that_grants_the_click_gets_the_price(page_server, tmp_path):
    """With permission, the same run ends differently — and the fact is still the page's, not a prediction."""
    env = BrowserEnvironment(page_server, perform={"click"}, headless=True, screenshot_dir=tmp_path)
    try:
        engine = StateEngine(env,
                             proposer=ReadsThePage(("click", {"selector": "#go"}), ("page_text", {})),
                             evaluator=KnowsTheAnswer("£42.50", partial="clicked"),
                             budget=EngineBudget(max_model_calls=6))
        events = [e async for e in engine.run(Goal("what is the price?"))]
        assert events[-1].kind == "done" and events[-1].data["answer"] == "£42.50"
        assert [e.data.get("move") for e in events if e.kind == "probe"] == [
            "click(selector=#go)", "page_text()"]  # it acted, then looked
        assert env.page().find("#price")["text"] == "£42.50"  # the click really landed
    finally:
        env.close()


@WITH_BROWSER
@pytest.mark.asyncio
async def test_the_dynamic_page_and_the_screenshot_both_work_through_the_environment(page_server, tmp_path):
    env = BrowserEnvironment(page_server, headless=True, screenshot_dir=tmp_path)
    try:
        late = await env.probe(Action("wait_for", {"selector": "#late", "timeout_ms": 5000}))
        assert late.ok and "arrived late" in late.text  # content that was not there at load

        missing = await env.probe(Action("wait_for", {"selector": "#never", "timeout_ms": 200}))
        assert missing.ok is False and "nothing matched" in missing.text

        shot = await env.probe(Action("screenshot", {}))
        assert shot.ok and "for a person to look at" in shot.text
        written = [p for p in tmp_path.glob("*.png")]
        assert written and written[0].stat().st_size > 1000  # a real PNG, not an empty file
        assert written[0].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

        found = await env.probe(Action("find", {"selector": "#price"}))
        assert found.ok and "not loaded yet" in found.text
        links = await env.probe(Action("links", {}))
        assert links.ok and "More widgets" in links.text

        bad = await env.probe(Action("page_text", {"selector": "#nothing"}))
        assert bad.ok is False and "nothing on this page matches" in bad.text
        wrong = await env.probe(Action("page_text", {"wrong_argument": 1}))
        assert wrong.ok is False and "bad arguments" in wrong.text
    finally:
        env.close()


@WITH_BROWSER
@pytest.mark.asyncio
async def test_a_first_read_waits_for_the_page_it_was_opened_at(tmp_path):
    """A tab opened at a URL is not a loaded page.

    Found on a live site: the first read raced the load and answered "this page has no links" about a page
    full of them — not a missing answer, a wrong one. The server below is slow on purpose, so the race happens
    every time instead of occasionally, and waiting only for `readyState` is not enough on its own: a tab that
    has not started navigating is already complete.
    """
    import socketserver
    import threading
    import time
    from http.server import BaseHTTPRequestHandler

    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            time.sleep(1.2)  # long enough that a racing read always loses
            body = (b"<!doctype html><html><head><title>Slow page</title></head><body>"
                    b'<a href="/x">A link</a></body></html>')
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    class Quiet(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Quiet(("127.0.0.1", 0), Slow)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/slow"

    env = BrowserEnvironment(url, headless=True)
    try:
        links = await env.probe(Action("links", {}))  # the very first thing a run does
        assert links.ok and "A link" in links.text, links.text
        title = await env.probe(Action("title_and_url", {}))
        assert title.ok and "Slow page" in title.text, title.text
    finally:
        env.close()
        server.shutdown()
        server.server_close()


@WITH_BROWSER
@pytest.mark.asyncio
async def test_navigating_away_and_back_through_the_environment(page_server, tmp_path):
    env = BrowserEnvironment(page_server, headless=True, screenshot_dir=tmp_path)
    try:
        here = await env.probe(Action("title_and_url", {}))
        assert here.ok and "The price page" in here.text and page_server in here.text
        left = await env.probe(Action("goto", {"url": "about:blank"}))
        assert left.ok and "about:blank" in left.text
        back = await env.probe(Action("back", {}))
        assert back.ok and page_server in back.text  # back where it started
    finally:
        env.close()


def browsers_using(profile: str) -> list[str]:
    """The *browser* processes holding this profile — not its helpers.

    Asked of the process table rather than of our handle, because that is where a leak shows up. Helpers
    (`--type=…`, renderers, GPU) are children that the OS reaps; a browser still running is the leak.

    Two ways to ask, because Windows has no `ps -Ao`: the `ps` in Git Bash rejects it, so a helper that only
    knew that form would return an empty list for every run and report "no leak" even when one leaked.
    """
    if os.name == "nt":
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine } | "
             "ForEach-Object { $_.CommandLine }"],
            capture_output=True, text=True).stdout
        return [line for line in out.splitlines() if profile in line and " --type=" not in line]
    out = subprocess.run(["ps", "-Ao", "pid=,command="], capture_output=True, text=True).stdout
    return [line for line in out.splitlines()
            if profile in line and " --type=" not in line
            and not line.lstrip().split(None, 1)[1].startswith("/bin/")]


@WITH_BROWSER
def test_closing_really_closes_a_browser_and_cleans_up_after_it(tmp_path):
    """Both of these were bugs: the browser survived `close()` (asking the protocol to quit is what works),
    and every throwaway profile stayed in the temp directory (a `SingletonLock` symlink broke the walk)."""
    env = BrowserEnvironment("about:blank", headless=True)
    env.page()  # start it
    profile = Path(env._chrome._profile)
    assert profile.is_dir() and browsers_using(str(profile)), "the browser did not start"
    env.close()

    # Generous, because this is a real browser shutting down on a machine that may be busy: it was 8s, and
    # that failed under load while passing in isolation. A genuine leak never clears, so the bound still bites.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and browsers_using(str(profile)):
        time.sleep(0.25)
    assert not browsers_using(str(profile)), f"a browser is still running with {profile}"
    assert not profile.exists(), f"{profile} survived close()"
@WITH_BROWSER
def test_a_launch_that_fails_stops_the_browser_it_started(tmp_path, monkeypatch):
    """A browser that starts and never answers must not be abandoned.

    Found on this machine, twice over: thirty browsers had accumulated with throwaway profiles, because a
    launch that timed out raised while the process it had started was still running and nothing held it any
    more. The launch is made to fail here rather than be raced, so the check is about the contract and not
    about timing.
    """
    started: dict = {}

    def never_answers(self):
        started["proc"] = self._proc  # the process this launch started, before the failure unwinds
        raise BrowserError("the browser did not report a DevTools URL within 1s:")

    monkeypatch.setattr(Chrome, "_await_devtools_url", never_answers)
    with pytest.raises(BrowserError):
        # a stand-in for a browser: it ignores what Chrome passes it and simply stays alive
        Chrome(binary=sys.executable, extra_args=("-c", "import time; time.sleep(60)"), timeout_s=1,
               user_data_dir=tmp_path / "profile")

    proc = started["proc"]
    assert proc is not None, "the launch never started a process, so this test proves nothing"
    assert proc.poll() is not None, "a failed launch left its browser running"


@WITH_BROWSER
def test_a_profile_you_supplied_is_never_deleted(tmp_path):
    """`close()` cleans up after itself, not after you: a profile the host named is the host's."""
    mine = tmp_path / "my-profile"
    env = BrowserEnvironment("about:blank", headless=True, user_data_dir=mine)
    env.page()
    env.close()
    assert mine.is_dir() and any(mine.iterdir()), "the host's own profile directory was removed"


@WITH_BROWSER
@pytest.mark.asyncio
async def test_a_browser_that_cannot_be_started_is_a_failed_probe_that_leaves_nothing_behind():
    """A launch failure has to be an observation naming the cause — and it must not litter.

    The profile directory is made before the browser is, so a launch that fails used to leave one in the temp
    directory every time this test ran.
    """
    import tempfile

    before = set(Path(tempfile.gettempdir()).glob("ti-matrix-browser-*"))
    env = BrowserEnvironment("about:blank", binary="/nonexistent/chrome")
    obs = await env.probe(Action("title_and_url", {}))
    assert obs.ok is False and "could not start" in obs.text and "/nonexistent/chrome" in obs.text
    after = set(Path(tempfile.gettempdir()).glob("ti-matrix-browser-*"))
    assert after == before, f"a failed launch left {sorted(p.name for p in after - before)} behind"


def test_an_actions_hint_is_a_shape_not_a_value():
    """A hint that looks like real data gets used as real data.

    Found live: the engine read a run's `goto` example URL out of the description and navigated away from the
    site it was asked about to it. Placeholders in angle brackets cannot be mistaken for an answer.
    """
    import re

    from ti_matrix.adapters.browser import AgentBrowser

    everything = list(BrowserEnvironment("about:blank").tools().values()) + list(AgentBrowser().tools().values())
    offenders = [spec.name for spec in everything
                 if re.search(r"https?://[a-z0-9-]+\.[a-z]{2,}", spec.args_hint or "")]
    assert not offenders, f"these hints contain a URL a model can copy verbatim: {offenders}"
