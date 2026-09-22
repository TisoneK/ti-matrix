"""The examples must actually work — served, driven over HTTP, and honest about what they cannot do.

Each example is one file with a browser page on top of a real engine run, so "it works" means more than "it
imports": these tests start the server each example starts, fetch the page and the state the page polls, POST a
goal, and let a canned model endpoint drive a real run to an honest end. Nothing here needs a network or a key.

The shell is the same in all three by design (so each example stands alone), and one test holds it that way:
the duplicated part cannot drift without failing the build.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ti_matrix import Action

EXAMPLES = pathlib.Path(__file__).resolve().parent.parent / "examples"
SHELL_MARKER = "# ═══ the playground shell"


def load(name: str):
    """Import an example by path — `examples/` is not a package, and each file is meant to stand alone."""
    spec = importlib.util.spec_from_file_location(f"example_{name}", EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ─── a model endpoint that says exactly one true thing ──────────────────────


class Canned(BaseHTTPRequestHandler):
    """The smallest OpenAI-compatible endpoint: one move, one score, and a prediction for a Simulator."""

    move: str = "list_dir"
    args: dict = {"path": "."}
    answer: str = "there are files here"

    def do_POST(self):  # noqa: N802
        prompt = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["messages"][0]["content"]
        if '"ok": true, "result"' in prompt:
            content = {"ok": True, "result": "it would produce something", "why": "predicted"}
        elif '"evals"' in prompt:
            content = {"evals": [{"i": 0, "progress": 1.0, "done": True, "answer": self.answer,
                                  "reason": "the probe settled it"}]}
        else:
            content = {"moves": [{"tool": self.move, "args": self.args, "why": "the obvious first look"}]}
        body = json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def model_endpoint():
    """A local endpoint standing in for a real model, at a URL the examples can be pointed at."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Canned)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()


@pytest.fixture()
def page(request):
    """The example's own server, running on a loopback port, ready to be driven like a browser would."""
    module = load(request.param)
    play = module.Play(module.build_environment, module.epilogue, {})
    module.Handler.play = play
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield module, base
    server.shutdown()


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def post(url: str, payload: dict) -> tuple[int, str]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def state(base: str, since: int = 0) -> dict:
    return json.loads(get(f"{base}/api/state?since={since}")[1])


def run_to_end(base: str, config: dict, *, timeout_s: float = 15.0) -> dict:
    """POST a goal, then poll exactly as the page does, until the run stops being 'running'."""
    status, body = post(f"{base}/api/run", config)
    assert status == 200, f"the run would not start: {body}"
    deadline = time.time() + timeout_s
    seen, events = 0, []
    while time.time() < deadline:
        snapshot = state(base, seen)
        events += snapshot["events"]
        seen = snapshot["next"]
        if snapshot["status"] != "running":
            snapshot["events"] = events
            return snapshot
        time.sleep(0.05)
    raise AssertionError("the run never finished")


# ─── the page and its state ─────────────────────────────────────────────────


@pytest.mark.parametrize("page", ["ledger_ui"], indirect=True)
def test_it_serves_the_page_and_the_state_the_page_polls(page):
    module, base = page
    status, html = get(base + "/")
    assert status == 200 and "<title>" in html and "api/run" in html
    snapshot = state(base)
    assert snapshot["status"] == "idle" and snapshot["events"] == [] and snapshot["outcome"] is None
    assert snapshot["title"] == module.TITLE and snapshot["env_note"] == module.ENV_NOTE
    names = [f["name"] for f in snapshot["fields"]]
    assert names[:len(module.FIELDS)] == [f["name"] for f in module.FIELDS]
    assert "base_url" in names and "model" in names and "api_key_env" in names
    assert all("label" in f and "default" in f for f in snapshot["fields"])


@pytest.mark.parametrize("page", ["files_ui"], indirect=True)
def test_an_unknown_route_and_an_empty_goal_are_refused(page):
    _, base = page
    assert get(base + "/api/nonsense")[0] == 404
    assert post(base + "/api/run", {"goal": "   "})[0] == 400
    assert post(base + "/api/nothing", {})[0] == 404


@pytest.mark.parametrize("page", ["files_ui"], indirect=True)
def test_a_page_from_another_site_cannot_drive_the_run(page):
    """The endpoint reads your filesystem and spends your model budget; only its own page may start it."""
    _, base = page
    request = urllib.request.Request(f"{base}/api/run", data=b'{"goal":"x"}',
                                     headers={"Content-Type": "application/json",
                                              "Origin": "http://evil.example"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=5)
    assert caught.value.code == 403 and b"cross-origin" in caught.value.read()


def test_the_page_reads_exactly_what_the_state_provides():
    """The page is JavaScript this suite cannot run, so the one thing worth checking is the contract.

    A typo in `s.env_note` would leave the page half-drawn and every other test here still green.
    """
    module = load("files_ui")
    provided = set(module.Play(module.build_environment, module.epilogue, {}).snapshot(0))
    read = set(re.findall(r"\bs\.([a-z_]+)", module.PAGE))
    assert read, "the page does not read the state at all — did the script move?"
    assert read <= provided, f"the page reads {sorted(read - provided)}, which the state does not provide"


def test_the_three_examples_share_one_shell():
    """Self-containment is the point, so the duplication is deliberate — and held still by this test."""
    shells = {}
    for name in ("files_ui", "ledger_ui", "tools_ui"):
        text = (EXAMPLES / f"{name}.py").read_text()
        assert SHELL_MARKER in text, f"{name} does not use the shared shell"
        shells[name] = text[text.index(SHELL_MARKER):]
    assert len(set(shells.values())) == 1, "the examples' shared shell has drifted apart"


@pytest.mark.parametrize("name", ["files_ui", "ledger_ui", "tools_ui"])
def test_every_example_says_what_it_does_and_names_its_own_parts(name):
    module = load(name)
    doc = (EXAMPLES / f"{name}.py").read_text().split('"""')[1]
    assert doc.strip() and f"python examples/{name}.py" in doc  # the file says how to run it
    assert callable(module.build_environment) and module.TITLE and module.ENV_NOTE and module.FIELDS
    assert isinstance(module.PAGE, str) and module.PAGE.startswith("<!doctype html")
    # and it declares the command-line flags a shell needs from its own fields
    assert all(set(f) >= {"name", "label", "default"} for f in module.FIELDS)


# ─── a real run, through the environment each example builds ────────────────


@pytest.mark.parametrize("page", ["files_ui"], indirect=True)
def test_the_filesystem_example_runs_a_goal_and_settles_it(page, model_endpoint, tmp_path):
    module, base = page
    # A directory of this test's own: `tmp_path` is shared with the vault fixture, and a count of "files
    # under here" that quietly included the vault would be a test measuring the fixture.
    mine = tmp_path / "mine"
    mine.mkdir()
    (mine / "notes.md").write_text("hello")
    Canned.move, Canned.args, Canned.answer = "list_dir", {"path": "."}, "there are files here"
    snapshot = run_to_end(base, {"goal": "what is in this directory?", "root": str(mine),
                                 "base_url": model_endpoint, "model": "canned", "api_key_env": "",
                                 "budget_calls": "6"})
    kinds = [e["kind"] for e in snapshot["events"]]
    assert snapshot["status"] == "done", snapshot.get("notes")
    assert snapshot["outcome"]["settled"] is True
    assert snapshot["outcome"]["answer"] == "there are files here"
    assert kinds[0] == "state" and "candidates" in kinds and "probe" in kinds
    assert kinds[-1] == "done" and "needs_confirmation" not in kinds
    assert any("the engine's own" not in n for n in snapshot["notes"])  # the notes panel says something
    assert any(n.startswith("probes:") for n in snapshot["notes"])


@pytest.mark.parametrize("page", ["tools_ui"], indirect=True)
def test_the_tools_example_runs_a_goal_through_the_tool_your_source_provided(page, model_endpoint, tmp_path,
                                                                            project):
    """The composite, the resolution and the engine, end to end: the model is given *your* count_files."""
    module, base = page
    mine = tmp_path / "mine"  # this test's own directory, not the one the vault fixture is built in
    mine.mkdir()
    (mine / "a.txt").write_text("x")
    (mine / "b.txt").write_text("y")
    Canned.move, Canned.args, Canned.answer = "count_files", {"path": "."}, "2 files"
    snapshot = run_to_end(base, {"goal": "how many files are here?", "vault": str(project),
                                 "root": str(mine), "prefer": "user", "base_url": model_endpoint,
                                 "model": "canned", "api_key_env": "", "budget_calls": "6"})
    probes = [e["data"] for e in snapshot["events"] if e["kind"] == "probe"]
    assert snapshot["status"] == "done", snapshot.get("notes")
    assert snapshot["outcome"]["settled"] is True and snapshot["outcome"]["answer"] == "2 files"
    assert any("2 file(s) under" in p["excerpt"] for p in probes), \
        [(e["kind"], str(e["data"].get("excerpt") or e["data"].get("move"))[:70]) for e in snapshot["events"]]
    notes = " ".join(snapshot["notes"])
    assert "tool(s) the model will see" in notes  # the resolution, printed under the button
    assert "count_files" in notes  # your tool is in the set the model was given
    assert "shadowed by mine:search_memory" in notes  # and yours replaced one of ours, as declared


def test_running_while_a_run_is_going_is_refused_rather_than_interleaved(tmp_path):
    """Two runs into one page would interleave their events; the second is told to wait instead."""
    module = load("files_ui")
    play = module.Play(module.build_environment, module.epilogue, {})
    play.status = "running"  # as the first run would have left it
    with pytest.raises(RuntimeError, match="already going"):
        play.start({"goal": "x"})


# ─── the guards inside the examples themselves ──────────────────────────────


@pytest.mark.asyncio
async def test_the_filesystem_example_reads_inside_its_root_and_refuses_to_leave_it(tmp_path):
    module = load("files_ui")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("hello")
    env = module.build_environment({"root": str(tmp_path)}, None)

    inside = await env.probe(Action("read_file", {"path": "sub/a.txt"}))
    assert inside.ok and inside.text == "hello"  # a relative path resolves under the root
    assert inside.move.tool == "read_file"  # and the answer belongs to the action the engine proposed

    listing = await env.probe(Action("list_dir", {"path": "."}))
    assert listing.ok and "sub" in listing.text

    for escape in ("/etc/passwd", "../../../../etc/passwd", str(tmp_path.parent)):
        refused = await env.probe(Action("read_file", {"path": escape}))
        assert refused.ok is False and "refused" in refused.text and str(tmp_path) in refused.text
    assert (await env.probe(Action("list_dir", {}))).ok is False  # missing arguments, not a crash


@pytest.mark.asyncio
async def test_the_tools_example_resolves_yours_over_ours_and_can_flip_which_wins(project):
    module = load("tools_ui")
    config = {"vault": str(project), "root": str(project), "prefer": "user"}

    mine_wins = module.build_environment(config, None)
    assert mine_wins.registry.provider_of("search_memory") == "mine"
    assert mine_wins.registry.provider_of("count_files") == "mine"
    assert mine_wins.registry.provider_of("recall") == mine_wins.registry.provider_of("brief")  # ours

    ours_wins = module.build_environment({**config, "prefer": "builtin"}, None)
    assert ours_wins.registry.provider_of("search_memory") != "mine"
    dropped = dict(ours_wins.registry.resolution().dropped)
    assert "mine:search_memory" in dropped and "shadowed by" in dropped["mine:search_memory"]
    assert ours_wins.registry.provider_of("count_files") == "mine"  # it superseded nothing, so it stays

    # A mistyped preference falls back to the safe default rather than raising at run time.
    assert module.build_environment({**config, "prefer": "whatever"}, None).registry.prefer == "user"

    hit = await mine_wins.probe(Action("search_memory", {"text": "widen the beam"}))
    assert hit.ok and "exact line(s)" in hit.text  # your search really answers
    miss = await mine_wins.probe(Action("search_memory", {"text": "WIDEN THE BEAM"}))
    assert miss.ok and "no exact" in miss.text  # and it is case-sensitive, as it says it is
    assert (await mine_wins.probe(Action("count_files", {"path": "."}))).ok


@pytest.mark.asyncio
async def test_the_ledger_example_writes_back_only_when_it_is_asked(project):
    module = load("ledger_ui")
    notes = project / ".context_ledger" / "memory" / "office" / "sessions" / "notes.md"
    before = notes.read_text()
    play = module.Play(module.build_environment, module.epilogue, {})

    module.epilogue(play, None, {"vault": str(project), "record": "off", "model": "m", "goal": "g"})
    assert notes.read_text() == before  # the default touches nothing
    assert any("not recorded" in n for n in play.notes)

    await run_nothing(play, project)  # a run whose events the recorder will replay
    module.epilogue(play, None, {"vault": str(project), "record": "on", "model": "m",
                                 "goal": "what is in flight?"})
    after = notes.read_text()
    assert after.startswith(before) and "what is in flight?" in after  # appended, never rewritten
    assert "recorded" in " ".join(play.notes) or "wrote" in " ".join(play.notes)


async def run_nothing(play, project):
    """A real, tiny run whose events are worth replaying: the engine reads one probe and stops honestly."""
    from ti_matrix import EngineBudget, Goal, StateEngine

    class One:
        name = "one"

        async def propose(self, state, n, avoid):
            return [Action("brief", {}, "look")]

        async def evaluate(self, state, outcomes):
            from ti_matrix import Evaluation
            return [Evaluation(0.0, False, "", "nothing yet") for _ in outcomes]

    engine = StateEngine(play.build_environment({"vault": str(project)}, play.stats), proposer=One(),
                         evaluator=One(), budget=EngineBudget(max_model_calls=2))
    async for event in engine.run(Goal("what is in flight?")):
        play._emit(event.kind, event.data)
        play.raw.append(event)
        play.stats.observe(event)
