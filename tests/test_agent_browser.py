"""`agent-browser` as a source of actions: the commands it becomes, the boundary, and the runner.

Most of this needs no browser and no `agent-browser`: a fake CLI written into a temp file stands in for the
real one, which is what makes the runner testable on a machine that has neither. The last tests drive the real
tool when it is installed, and skip themselves when it is not.
"""
from __future__ import annotations

import os
import shutil
import stat

import pytest

from ti_matrix import Action, CompositeEnvironment, EngineBudget, Evaluation, Goal, StateEngine
from ti_matrix.adapters.browser import BrowserEnvironment
from ti_matrix.adapters.browser.agent_browser import READS, AgentBrowser

HAS_CLI = shutil.which("agent-browser") is not None
FAKE_CLI = '''#!{python}
"""A stand-in for agent-browser: it says what it was asked, and can be told to misbehave."""
import sys

argv = sys.argv[1:]
tail = [a for a in argv if not a.startswith("-")]
if "boom" in argv:
    print("something went wrong", file=sys.stderr)
    sys.exit(3)
if "long" in argv:
    print("x" * 9000)
elif "quiet" in argv:
    pass
else:
    print("Page: Fake page")
    print("URL: about:blank")
    print("@e1 [button] \\"Go\\"")
    print("argv: " + " ".join(tail))
'''


@pytest.fixture()
def fake_cli(tmp_path):
    """A script that behaves enough like the CLI to test how this adapter calls it.

    Windows will not execute a shebang script (it wants a real executable, or a `.cmd` naming one), so there the
    script is written as a module with a `.cmd` shim beside it. Either way the adapter is handed one `command`
    and runs it argv-style, which is the contract under test."""
    import sys

    body = FAKE_CLI.format(python=sys.executable)
    if os.name == "nt":
        script = tmp_path / "fake-agent-browser.py"
        script.write_text(body)
        shim = tmp_path / "fake-agent-browser.cmd"
        shim.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0{script.name}" %*\r\n')
        return str(shim)
    path = tmp_path / "fake-agent-browser"
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


# ─── the command each action becomes ────────────────────────────────────────


def test_every_action_becomes_the_command_it_says():
    """The action names are the API, the argv is the contract with the CLI, and they differ in places."""
    env = AgentBrowser(session="t1")
    cases = [
        ("snapshot", {}, "snapshot -i -c"),
        ("snapshot", {"depth": 3, "with_urls": True, "interactive": False}, "snapshot -c -d 3 -u"),
        ("snapshot", {"selector": "#main", "json": True}, "snapshot -i -c -s #main --json"),
        ("read", {"url": "https://x.test"}, "read https://x.test"),
        ("get", {"what": "value", "selector": "@e1"}, "get value @e1"),
        ("is_state", {"what": "visible", "selector": "@e2"}, "is visible @e2"),
        ("find", {"locator": "role", "value": "button", "action": "click"}, "find role button click"),
        ("wait", {"load": "networkidle"}, "wait --load networkidle"),
        ("wait", {"target": "500"}, "wait 500"),
        ("screenshot", {"full_page": True}, "screenshot --full-page"),
        ("pdf", {"path": "p.pdf"}, "pdf p.pdf"),
        ("tabs", {"action": "list"}, "tab list"),
        ("cookies_get", {}, "cookies get"),
        ("storage_get", {"kind": "local"}, "storage local"),
        ("storage_get", {"kind": "session", "key": "token"}, "storage session token"),
        ("storage_set", {"kind": "local", "key": "t", "value": "v"}, "storage local set t v"),
        ("storage_clear", {"kind": "session"}, "storage session clear"),
        ("vitals", {"url": "https://x.test"}, "vitals https://x.test"),
        ("a11y", {"tags": "wcag2a,wcag2aa", "selector": "#main"}, "a11y --tags wcag2a,wcag2aa --selector #main"),
        ("network_requests", {"filter": "**/api/**", "status": "4xx"}, "network requests --filter **/api/** --status 4xx"),
        ("network_request", {"id": "r42"}, "network request r42"),
        ("network_route", {"url": "**/api/users", "body": '{"users":[]}'}, 'network route **/api/users --body {"users":[]}'),
        ("network_route", {"url": "**/track", "abort": True}, "network route **/track --abort"),
        ("network_unroute", {"url": "**/api/**"}, "network unroute **/api/**"),
        ("har", {"action": "stop", "path": "/tmp/t.har"}, "network har stop /tmp/t.har"),
        ("trace", {"action": "start"}, "trace start"),
        ("profiler", {"action": "stop", "path": "p.json"}, "profiler stop p.json"),
        ("record", {"action": "start", "path": "run.webm", "url": "https://x.test"}, "record start run.webm https://x.test"),
        ("react", {"action": "renders", "id": "stop"}, "react renders stop"),
        ("react", {"action": "suspense", "only_dynamic": True}, "react suspense --only-dynamic"),
        ("webmcp_list", {}, "webmcp list"),
        ("webmcp_result", {"id": "i1"}, "webmcp result i1"),
        ("webmcp_invoke", {"tool": "search", "params": '{"q":"x"}', "detach": True},
         'webmcp invoke search --params {"q":"x"} --detach'),
        ("session", {"action": "list"}, "session list"),
        ("plugins", {}, "plugin list"),
        ("plugin_show", {"name": "vault"}, "plugin show vault"),
        ("plugin_add", {"ref": "agent-browser-plugin-vault", "name": "vault"},
         "plugin add agent-browser-plugin-vault --name vault"),
        ("plugin_run", {"name": "c", "request": "c.solve", "payload": "{}"}, "plugin run c c.solve --payload {}"),
        ("diff_snapshot", {"baseline": "b.txt"}, "diff snapshot --baseline b.txt"),
        ("diff_screenshot", {"baseline": "b.png"}, "diff screenshot --baseline b.png"),
        ("diff_url", {"first": "https://a", "second": "https://b"}, "diff url https://a https://b"),
        ("configure", {"setting": "viewport", "value": 1920, "second": 1080}, "set viewport 1920 1080"),
        ("configure", {"setting": "offline", "value": "on"}, "set offline on"),
        ("mouse", {"action": "move", "x": 0, "y": 100}, "mouse move 0 100"),
        ("mouse", {"action": "wheel", "dy": 600}, "mouse wheel 600"),
        ("mouse", {"action": "down", "button": "right"}, "mouse down right"),
        ("cookies_set", {"name": "s", "value": "v", "domain": ".x.test", "secure": True, "http_only": True},
         "cookies set s v --domain .x.test --httpOnly --secure"),
        ("cookies_clear", {}, "cookies clear"),
        ("auth_list", {}, "auth list"),
        ("auth_show", {"name": "app"}, "auth show app"),
        ("auth_save", {"name": "app", "username": "me", "password_env": "APP_PW"},
         "auth save app --username me --password-stdin"),
        ("auth_login", {"name": "app", "credential_provider": "vault", "item": "My App"},
         "auth login app --credential-provider vault --item My App"),
        ("auth_delete", {"name": "app"}, "auth delete app"),
        ("clipboard_read", {}, "clipboard read"),
        ("clipboard_write", {"text": "hi there"}, "clipboard write hi there"),
        ("clipboard_paste", {}, "clipboard paste"),
        ("removeinitscript", {"id": "s1"}, "removeinitscript s1"),
        ("batch", {"commands": ["open https://x", "snapshot -i"], "bail": True},
         "batch --bail open https://x snapshot -i"),
        ("confirm", {"id": "c_123"}, "confirm c_123"),
        ("deny", {"id": "c_123"}, "deny c_123"),
        ("pushstate", {"url": "/settings"}, "pushstate /settings"),
        ("highlight", {"selector": "@e5"}, "highlight @e5"),
        ("diff_snapshot", {}, "diff snapshot"),
        ("open", {"url": "about:blank"}, "open about:blank"),
        ("scroll", {"direction": "down", "pixels": 600}, "scroll down 600"),
        ("scroll_to", {"selector": "#f"}, "scrollintoview #f"),
        ("click", {"selector": "@e3"}, "click @e3"),
        ("type", {"selector": "@e1", "text": "hi there"}, "type @e1 hi there"),
        ("select", {"selector": "@e5", "values": ["a", "b"]}, "select @e5 a b"),
        ("upload", {"selector": "#f", "files": ["/tmp/a.pdf"]}, "upload #f /tmp/a.pdf"),
        ("close", {}, "close --all"),
    ]
    for tool, args, expected in cases:
        assert " ".join(env.argv(tool, args)[3:]) == expected, tool  # [3:] drops the binary and session
    assert env.argv("snapshot", {})[:4] == ["agent-browser", "--session", "t1", "snapshot"]
    assert env.argv("click", {"selector": "@e3"})[0] == "agent-browser"


def test_a_run_gets_its_own_session_unless_it_is_told_otherwise():
    """The CLI's default session is shared with everything else on the machine, so a run should not use it."""
    assert "--session" in AgentBrowser().argv("snapshot", {})
    assert AgentBrowser(session="run-7").argv("snapshot", {})[2] == "run-7"
    assert "--session" not in AgentBrowser(session=None).argv("snapshot", {})
    assert AgentBrowser(session="s", profile="Default").argv("snapshot", {})[:5] == [
        "agent-browser", "--session", "s", "--profile", "Default"]


def test_no_action_can_smuggle_an_argument_into_the_command():
    """Values become their own argv entries: a selector full of shell syntax is a selector, not a command."""
    env = AgentBrowser()
    argv = env.argv("click", {"selector": "@e1; rm -rf / #"})
    assert argv[-1] == "@e1; rm -rf / #"  # one argv entry, not a shell string
    assert argv.count("@e1; rm -rf / #") == 1 and " " not in argv[-2]
    assert argv == ["agent-browser", "--session", "ti-matrix", "click", "@e1; rm -rf / #"]


def test_the_read_set_and_the_table_agree():
    """Two invariants that a 78-row table invites breaking.

    A name in READS with no spec is unreachable — a read nothing can call. And an action whose name is not
    mapped to a subcommand reaches the CLI as `auth_save`, which it does not know: with no arguments, the only
    tokens left after the session are subcommand tokens, and the CLI's subcommands never contain an
    underscore.
    """
    env = AgentBrowser()
    offered = set(env.tools())
    assert set(READS) <= offered, f"declared as reads but not offered: {sorted(set(READS) - offered)}"
    for name in sorted(offered):
        after_binary = env.argv(name, {})[3:]  # drop the binary, --session and its value
        assert after_binary, f"{name} produces no subcommand"
        assert "_" not in " ".join(after_binary), f"{name} is not mapped to a real subcommand: {after_binary}"


def test_a_grant_widens_and_the_only_set_narrows():
    base = AgentBrowser()
    assert sum(1 for s in base.tools().values() if s.read_only) == len(READS)
    assert base.is_read_only(Action("click", {})) is False

    one = AgentBrowser(perform={"click"})
    assert one.is_read_only(Action("click", {})) is True
    assert one.is_read_only(Action("fill", {})) is False  # a grant is specific, never a mood

    everything = AgentBrowser(perform={"all"})
    assert all(spec.read_only for spec in everything.tools().values())
    assert len(everything.tools()) == len(base.tools())  # the same surface, all of it performable

    narrow = AgentBrowser(only={"snapshot", "get", "click"})
    assert sorted(narrow.tools()) == ["click", "get", "snapshot"]
    assert narrow.is_read_only(Action("click", {})) is False  # narrowing does not grant


def test_the_cli_keeps_its_own_confirmation_queue_and_a_host_can_answer_it():
    """`--confirm-actions` makes the CLI hold certain actions; confirm and deny answer it. Same idea as the
    engine's needs_confirmation, one layer down, and a host running the CLI that way needs these."""
    env = AgentBrowser(perform={"confirm", "deny"})
    assert env.argv("confirm", {"id": "c_8f3a1234"})[3:] == ["confirm", "c_8f3a1234"]
    assert env.argv("deny", {"id": "c_8f3a1234"})[3:] == ["deny", "c_8f3a1234"]
    assert AgentBrowser().is_read_only(Action("confirm", {})) is False  # approving is not a read


# ─── the boundary, the same rule as the native environment ──────────────────


def test_the_boundary_matches_the_native_environment():
    env = AgentBrowser()
    reads = {name for name, spec in env.tools().items() if spec.read_only}
    assert reads == set(READS)
    assert {"click", "fill", "select", "drag", "upload", "eval", "close"} <= set(env.tools()) - reads
    assert env.is_read_only(Action("snapshot", {})) is True
    assert env.is_read_only(Action("click", {})) is False
    assert env.is_read_only(Action("teleport", {})) is None

    granted = AgentBrowser(perform={"click", "fill"})
    assert granted.is_read_only(Action("click", {})) is True
    assert granted.is_read_only(Action("fill", {})) is True
    assert granted.is_read_only(Action("upload", {})) is False


@pytest.mark.asyncio
async def test_a_write_is_refused_before_anything_is_run(fake_cli):
    env = AgentBrowser(command=fake_cli)
    obs = await env.probe(Action("click", {"selector": "@e3"}))
    assert obs.ok is False and "would change the page" in obs.text and "perform={'click'}" in obs.text
    assert (await env.probe(Action("teleport", {}))).ok is False


@pytest.mark.asyncio
async def test_a_cli_that_is_not_installed_says_so_rather_than_failing_oddly():
    env = AgentBrowser(command="definitely-not-a-real-browser-cli")
    assert env.available() is False
    obs = await env.probe(Action("snapshot", {}))
    assert obs.ok is False and "npm i -g agent-browser" in obs.text


# ─── the runner ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_output_comes_back_and_the_arguments_really_reached_the_cli(fake_cli):
    env = AgentBrowser(command=fake_cli, session="t2")
    obs = await env.probe(Action("snapshot", {}))
    assert obs.ok and "@e1 [button]" in obs.text
    # the fake echoes the arguments that came after the flags, so this proves they really arrived
    assert "argv: t2 snapshot" in obs.text

    state = await env.probe(Action("is_state", {"what": "visible", "selector": "@e2"}))
    assert state.ok and "argv: t2 is visible @e2" in state.text


@pytest.mark.asyncio
async def test_a_nonzero_exit_is_a_failed_observation_carrying_what_the_cli_said(fake_cli):
    env = AgentBrowser(command=fake_cli)
    obs = await env.probe(Action("wait", {"target": "boom"}))
    assert obs.ok is False and "exit 3" in obs.text and "something went wrong" in obs.text


@pytest.mark.asyncio
async def test_a_long_answer_is_truncated_to_what_a_model_can_read(fake_cli):
    env = AgentBrowser(command=fake_cli)
    obs = await env.probe(Action("read", {"url": "long"}))
    assert obs.ok and len(obs.text) < 3000  # an observation, not a download

    empty = await env.probe(Action("read", {"url": "quiet"}))  # the fake prints nothing for this
    assert empty.ok and empty.text == "ok (no output)"


# ─── the engine over the CLI, and over both sources at once ─────────────────


class OneMove:
    """A proposer that asks for one action — a stand-in for a model."""

    def __init__(self, tool: str, args: dict):
        self.tool, self.args = tool, args

    async def propose(self, state, n, avoid):
        return [Action(self.tool, self.args, "because")]


class Until:
    """An evaluator that settles the goal when the fact it is waiting for appears."""

    def __init__(self, needle: str):
        self.needle = needle

    async def evaluate(self, state, outcomes):
        out = []
        for obs in outcomes:
            hit = obs.ok and self.needle in obs.text
            out.append(Evaluation(1.0 if hit else 0.0, hit, self.needle if hit else "",
                                  "it is there" if hit else "not yet"))
        return out


@pytest.mark.asyncio
async def test_the_engine_searches_over_the_clis_actions(fake_cli):
    """No browser and no agent-browser needed: the loop, the environment and the CLI contract, end to end."""
    env = AgentBrowser(command=fake_cli, session="t3")
    engine = StateEngine(env, proposer=OneMove("snapshot", {}), evaluator=Until("[button]"),
                         budget=EngineBudget(max_model_calls=4))
    events = [e async for e in engine.run(Goal("what is on the page?"))]
    assert events[-1].kind == "done" and events[-1].data["answer"] == "[button]"
    probe = next(e for e in events if e.kind == "probe")
    assert "@e1 [button]" in probe.data["excerpt"] and probe.data["ok"]


@pytest.mark.asyncio
async def test_a_run_that_would_need_a_click_is_stopped_rather_than_clicking(fake_cli):
    env = AgentBrowser(command=fake_cli)
    engine = StateEngine(env, proposer=OneMove("click", {"selector": "@e1"}), evaluator=Until("Go"),
                         budget=EngineBudget(max_model_calls=4))
    events = [e async for e in engine.run(Goal("press the button"))]
    assert events[-1].kind == "stopped" and events[-1].data["settled"] is False
    assert any(e.kind == "needs_confirmation" and e.data["move"] == "click(selector=@e1)" for e in events)
    assert not any(e.kind == "probe" for e in events)


class Ours(BrowserEnvironment):
    """The shipped browser environment, marked as ours — which is what makes preference mean anything."""

    builtin = True


def test_both_browser_sources_resolve_into_one_tool_set_and_it_says_which_won():
    """The two overlap on several names; the tool set decides, and the resolution is readable.

    They overlap on `click`, `screenshot`, `find`, `back`, `scroll` and more, and they are equal standing by
    default (both a host's own choice), so order decides. Mark ours builtin and the declared preference starts
    to matter: a user's tool replaces ours unless the host says otherwise.
    """
    native, cli = Ours("about:blank"), AgentBrowser()
    both = CompositeEnvironment(native, cli)

    resolution = both.resolution()
    assert both.tools()  # not empty, and no name appears twice
    assert len(both.tools()) == len(set(both.tools()))
    shadowed = dict(resolution.dropped)
    assert shadowed, "the two sources overlap, so one of each collision should be reported"
    for name in ("click", "screenshot", "find"):
        assert name in both.tools()  # still offered, by whichever source won
    assert any("shadowed by" in why for why in shadowed.values())

    # With preference in play the outcome really does change sides.
    ours_wins = CompositeEnvironment(native, cli, prefer="builtin")
    theirs_wins = CompositeEnvironment(native, cli, prefer="user")
    assert ours_wins.resolution().dropped != theirs_wins.resolution().dropped
    assert dict(ours_wins.resolution().dropped).get("agent-browser:click") == "shadowed by browser:click"
    assert dict(theirs_wins.resolution().dropped).get("browser:click") == "shadowed by agent-browser:click"
    assert all(name in ours_wins.tools() and name in theirs_wins.tools()
               for name in ("click", "snapshot", "get"))


# ─── against the real thing, when it is here ────────────────────────────────


@pytest.mark.skipif(not HAS_CLI, reason="agent-browser is not installed")
@pytest.mark.asyncio
async def test_the_real_cli_reads_a_real_page(tmp_path):
    import functools
    import http.server
    import socketserver
    import threading

    directory = tmp_path / "site"
    directory.mkdir()
    (directory / "index.html").write_text(
        "<!doctype html><html><head><title>Ledger demo</title></head><body>"
        "<h1>Refunds</h1><p>Within 30 days, no questions asked.</p>"
        '<button id="buy">Buy now</button></body></html>')

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))

    class Quiet(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Quiet(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/index.html"

    env = AgentBrowser(session=f"ti-matrix-test-{os.getpid()}")
    try:
        opened = await env.probe(Action("open", {"url": url}))
        assert opened.ok, opened.text

        tree = await env.probe(Action("snapshot", {"interactive": False}))
        assert tree.ok and "Refunds" in tree.text

        text = await env.probe(Action("read", {}))
        assert text.ok or "30 days" in text.text  # `read` fetches by URL; either way it must not crash

        refused = await env.probe(Action("click", {"selector": "#buy"}))
        assert refused.ok is False and "would change the page" in refused.text
    finally:
        # closing is a write, so the host has to grant it — the same rule as everywhere else
        closer = AgentBrowser(session=f"ti-matrix-test-{os.getpid()}", perform={"close"})
        closed = await closer.probe(Action("close", {}))
        assert closed.ok, closed.text
        server.shutdown()


# The argv forms are written from the CLI's own help output, which is exactly where a wrong guess hides: a
# flag named `--same-site` instead of `--sameSite` reads perfectly and fails at run time. So every read action
# is fired at the real CLI and checked for the four things it says when it does not know what it was told.
_SYNTAX_MARKERS = ("Unknown command", "Unknown subcommand", "Valid options:", "Missing arguments for")
_READ_ARGS: dict[str, dict] = {
    "read": {"url": "{url}"}, "get": {"what": "text", "selector": "h1"},
    "is_state": {"what": "visible", "selector": "#buy"}, "find": {"locator": "text", "value": "Refunds"},
    "wait": {"target": "200"}, "tabs": {"action": "list"}, "highlight": {"selector": "#buy"},
    "network_request": {"id": "r1"}, "har": {"action": "start"}, "trace": {"action": "start"},
    "profiler": {"action": "start"}, "react": {"action": "tree"}, "webmcp_list": {},
    "webmcp_result": {"id": "i1"}, "session": {"action": "list"}, "plugins": {},
    "plugin_show": {"name": "nope"}, "diff_snapshot": {}, "diff_url": {"first": "{url}", "second": "{url}"},
    "open": {"url": "{url}"}, "scroll": {"direction": "down", "pixels": 100}, "scroll_to": {"selector": "#buy"},
    "vitals": {"url": "{url}"}, "a11y": {"url": "{url}"}, "storage_get": {"kind": "local"},
    "auth_show": {"name": "nope"}, "screenshot": {"path": "{tmp}/s.png"}, "pdf": {"path": "{tmp}/s.pdf"},
    "record": {"action": "start", "path": "{tmp}/r.webm"},
    "diff_screenshot": {"baseline": "{tmp}/s.png"},
}


@pytest.mark.skipif(not HAS_CLI, reason="agent-browser is not installed")
def test_every_read_action_is_a_command_the_real_cli_accepts(tmp_path):
    """The whole read surface, checked against the tool rather than against my reading of its docs."""
    import functools
    import http.server
    import socketserver
    import subprocess
    import threading

    directory = tmp_path / "site"
    directory.mkdir()
    (directory / "index.html").write_text(
        "<!doctype html><html><body><h1>Refunds</h1><button id=\"buy\">Buy</button></body></html>")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))

    class Quiet(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Quiet(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/index.html"

    env = AgentBrowser(session=f"ti-matrix-sweep-{os.getpid()}")
    replaced = {"url": url, "tmp": str(tmp_path)}
    try:
        subprocess.run(env.argv("open", {"url": url}), capture_output=True, text=True, timeout=120)
        rejected = []
        for name in sorted(READS):
            args = {k: (v.format(**replaced) if isinstance(v, str) else v)
                    for k, v in _READ_ARGS.get(name, {}).items()}
            done = subprocess.run(env.argv(name, args), capture_output=True, text=True, timeout=180)
            said = (done.stdout or "") + (done.stderr or "")
            hit = next((marker for marker in _SYNTAX_MARKERS if marker in said), None)
            if hit:
                rejected.append(f"{name}: {' '.join(env.argv(name, args)[3:])} -> {hit}")
        assert not rejected, "the CLI did not recognise these:\n" + "\n".join(rejected)
    finally:
        closing = AgentBrowser(session=f"ti-matrix-sweep-{os.getpid()}", perform={"close"})
        subprocess.run(closing.argv("close", {}), capture_output=True, text=True, timeout=120)
        server.shutdown()
