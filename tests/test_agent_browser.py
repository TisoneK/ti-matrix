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
    """A script that behaves enough like the CLI to test how this adapter calls it."""
    import sys

    path = tmp_path / "fake-agent-browser"
    path.write_text(FAKE_CLI.format(python=sys.executable))
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
        ("storage_get", {"action": "local"}, "storage local"),
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
        await env.probe(Action("open", {"url": "about:blank"}))
        AgentBrowser(session=f"ti-matrix-test-{os.getpid()}")._run(Action("close", {}), [])
        server.shutdown()
