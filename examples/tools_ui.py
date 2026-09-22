"""Play with the engine driving several worlds at once — in a browser, from one file.

    python examples/tools_ui.py --vault ~/code/my-project --root ~/code

Three sources of actions, resolved into the one set the model is shown: a project's Context Ledger (ours), the
engine's own `recall` (the engine's), and the tools in this file marked as yours — one of which deliberately
replaces one of ours, so the panel shows a real resolution: what was kept, what was shadowed, what was renamed.
Change `prefer` to "builtin" and watch the roles reverse.

That resolution is what this example is about. A name decides (two tools sharing one are the same tool to any
model), preference is declared rather than guessed, and the outcome is a record you can read instead of
wondering which tool the model was actually given.
"""
from __future__ import annotations

from pathlib import Path

from ti_matrix import Action, ActionSpec, Observation
from ti_matrix.adapters.context_ledger import LedgerEnvironment, LedgerVault
from ti_matrix.tools import CompositeEnvironment, EngineTools

TITLE = "Ti Matrix — several worlds, one tool set"
ENV_NOTE = ("Two shipped environments and one of your own, resolved into a single tool set by declared rules. "
            "The tools below marked *yours* replace one of ours on purpose, and the resolution is printed under "
            "the button after each run. Everything here reads: no action in this example can change anything.")
FIELDS = [
    {"name": "vault", "label": "Project holding .context_ledger/", "default": ".",
     "placeholder": "~/code/my-project", "group": "env"},
    {"name": "root", "label": "Your tools count files under", "default": "~/code",
     "placeholder": "/home/you/code", "group": "env"},
    {"name": "prefer", "label": "When two sources offer one tool, prefer: user | builtin",
     "default": "user", "placeholder": "user", "group": "env"},
]


class MyTools:
    """The seam: your own adapter, as a tool source. Two tools, one of them a deliberate collision.

    `count_files` is a capability neither shipped environment has. `search_memory` is the interesting one: it
    supersedes the ledger's own search with a stricter one — case-sensitive, exact substring, over the whole
    memory including closed offices — so the resolution below has something real to report. Point `prefer` at
    "builtin" and the ledger's search wins instead, and this source's tool is dropped entirely, because a tool
    declared to replace another was not meant to sit beside it.
    """

    name = "mine"

    def __init__(self, root: str, vault: LedgerVault) -> None:
        self.root = Path(root).expanduser()
        self._vault = vault
        self._tools = {
            "count_files": ActionSpec("count_files", "Count the files (not directories) under a directory.",
                                      '{"path": "<dir>"}'),
            "search_memory": ActionSpec("search_memory",
                                        "Search a project's memory for an EXACT, case-sensitive substring, "
                                        "including closed offices under history/.",
                                        '{"text": "<substring>"}', supersedes="search_memory"),
        }

    def tools(self) -> dict[str, ActionSpec]:
        return self._tools

    def is_read_only(self, action: Action):
        return None if action.tool not in self._tools else True

    async def probe(self, action: Action) -> Observation:
        try:
            return Observation(action, *getattr(self, f"_{action.tool}")(**action.args))
        except TypeError as exc:
            return Observation(action, False, f"bad arguments for {action.tool}: {exc}")
        except Exception as exc:  # noqa: BLE001 — a failed probe is an observation, never a crash
            return Observation(action, False, f"{type(exc).__name__}: {exc}"[:400])

    def _count_files(self, path: str = ".") -> tuple[bool, str]:
        directory = (self.root / str(path)).resolve()
        if not directory.is_dir():
            return False, f"not a directory: {directory}"
        return True, f"{sum(1 for p in directory.rglob('*') if p.is_file())} file(s) under {directory}"

    def _search_memory(self, text: str = "") -> tuple[bool, str]:
        if not str(text).strip():
            return False, "search_memory needs a non-empty 'text'"
        hits, _total = self._vault.search(str(text), scope="all")
        exact = [(rel, line_no, line) for rel, line_no, line in hits if str(text) in line]
        if not exact:
            return True, f"no exact (case-sensitive) line contains {text!r}"
        return True, (f"{len(exact)} exact line(s):\n"
                      + "\n".join(f"{rel}:{n}: {line}" for rel, n, line in exact[:15]))


def build_environment(config: dict[str, str], stats) -> CompositeEnvironment:
    """This example's world: several sources of actions, resolved into one set."""
    vault = LedgerVault(config.get("vault") or ".")
    if not vault.exists():
        raise RuntimeError(f"no Context Ledger at {vault} — bootstrap one in that project first, or point "
                           f"--vault at a project that has .context_ledger/")
    prefer = "builtin" if str(config.get("prefer", "")).strip().lower().startswith("b") else "user"
    return CompositeEnvironment(
        EngineTools(LedgerEnvironment(vault), memory=stats),   # ours, plus the engine's own recall
        MyTools(config.get("root") or "~", vault),             # yours
        prefer=prefer,
    )


def epilogue(play, env, config: dict[str, str]) -> None:
    """Show the decision the tool set made — the thing this example exists to make visible."""
    play.note(f"prefer={config.get('prefer', 'user')}")
    play.note(*env.inner.resolution().to_text().splitlines())  # env is the cache wrapped round the composite


# ═══ the playground shell ════════════════════════════════════════════════════════════════════════════════
# Identical in every example here, and asserted so by tests/test_examples.py. Edit one, edit them all.
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
import webbrowser  # noqa: E402
from typing import Any, Optional  # noqa: E402

from ti_matrix import EngineBudget, Goal, LLMEvaluator, LLMMoveProposer, LLMSimulator, StateEngine  # noqa: E402
from ti_matrix.adapters.openai_compat import OpenAICompatModel  # noqa: E402
from ti_matrix.learning import CachingEnvironment, LearningProposer, Statistics  # noqa: E402

SHARED_FIELDS = [
    {"name": "base_url", "label": "Model endpoint (any OpenAI-compatible one)",
     "default": "http://localhost:11434/v1", "placeholder": "http://localhost:11434/v1"},
    {"name": "model", "label": "Model", "default": "qwen2.5:7b", "placeholder": "qwen2.5:7b"},
    {"name": "api_key_env", "label": "API key: the NAME of the env var holding it, never the key itself",
     "default": "OPENAI_API_KEY", "placeholder": "OPENAI_API_KEY"},
    {"name": "budget_calls", "label": "Model calls the run may spend", "default": "12", "placeholder": "12"},
]

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Ti Matrix playground</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0e1015;--panel:#161a22;--line:#242a36;--fg:#e6e8ef;--dim:#98a1b0;--blue:#2f81f7;
      --ok:#3fb950;--bad:#f85149;--sel:#d29922;--bt:#a371f7}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;
     display:flex;flex-direction:column;height:100vh;overflow:hidden}
header{flex:0 0 auto;padding:14px 20px;border-bottom:1px solid var(--line)}
h1{margin:0 0 4px;font-size:15px;font-weight:600}
.note{color:var(--dim);font-size:12px;max-width:100ch}
main{flex:1 1 auto;min-height:0;display:grid;grid-template-columns:minmax(300px,360px) 1fr}
.col{overflow:auto;padding:16px 20px}
.left{border-right:1px solid var(--line)}
label{display:block;margin:12px 0 4px;color:var(--dim);font-size:12px}
input,textarea{width:100%;background:var(--panel);color:var(--fg);border:1px solid var(--line);
               border-radius:6px;padding:7px 8px;font:inherit}
textarea{min-height:76px;resize:vertical}
button{margin-top:14px;width:100%;padding:9px;background:var(--blue);color:#fff;border:0;border-radius:6px;
       font:inherit;cursor:pointer}
button:disabled{opacity:.45;cursor:default}
.ev{border-left:3px solid var(--line);background:var(--panel);border-radius:0 6px 6px 0;padding:6px 10px;
    margin:6px 0;white-space:pre-wrap;word-break:break-word}
.ev .h{color:var(--dim)}
.k-probe{border-color:var(--ok)} .k-probe.bad{border-color:var(--bad)} .k-selected{border-color:var(--sel)}
.k-backtrack{border-color:var(--bt)} .k-candidates{border-color:var(--blue)}
.k-done{border-color:var(--ok);background:#12261a} .k-stopped{border-color:var(--bad);background:#2a1518}
.k-error{border-color:var(--bad);background:#2a1518}
.dim{color:var(--dim)} .pred{color:var(--bt)} .good{color:var(--ok)} .bad{color:var(--bad)}
.status{display:inline-block;margin-top:14px;padding:2px 9px;border:1px solid var(--line);border-radius:999px;
        background:var(--panel);font-size:12px}
.check{display:flex;gap:8px;align-items:flex-start;margin:14px 0 0;color:var(--fg);font-size:12px}
.check input{width:auto;margin-top:2px}
#outcome:not(:empty){border:1px solid var(--line);border-radius:8px;padding:12px;margin-bottom:14px}
#notes{margin-top:14px;font-size:12px}
#notes div{padding:2px 0;border-bottom:1px dotted var(--line)}
h2{font-size:13px;margin:16px 0 4px;color:var(--dim);font-weight:600;text-transform:uppercase;letter-spacing:.06em}
</style></head><body>
<header><h1 id="title">Ti Matrix playground</h1><div class="note" id="envnote"></div></header>
<main>
  <div class="col left">
    <div id="envfields"></div>
    <label for="goal">Goal</label>
    <textarea id="goal" placeholder="what did I change most recently, and what is in the README?"></textarea>
    <div id="modelfields"></div>
    <button id="run">Run the engine</button>
    <div class="status" id="status">idle</div>
    <div id="notes"></div>
  </div>
  <div class="col right">
    <div id="outcome"></div>
    <h2>What the engine did</h2>
    <div id="events"><span class="dim">Nothing yet. Configure the model above and run a goal.</span></div>
  </div>
</main>
<script>
const $ = (id) => document.getElementById(id);
let seen = 0, timer = null, lastFacts = [];

const esc = (v) => String(v === null || v === undefined ? '' : v)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

let built = false;
function fieldHtml(f) {
  if (f.type === 'checkbox')
    return '<label class="check"><input type="checkbox" id="f-' + f.name + '"' +
           (f.default === 'on' ? ' checked' : '') + '><span>' + esc(f.label) + '</span></label>';
  return '<label>' + esc(f.label) + '</label><input id="f-' + f.name + '" value="' + esc(f.default) +
         '" placeholder="' + esc(f.placeholder || '') + '">';
}
function buildFields(fields) {
  if (built) return;
  // A field marked group "env" describes the world; the rest describe the model. That is the whole
  // difference between the three examples' panels, so it is data rather than markup.
  const isEnv = (f) => f.group === 'env';
  $('envfields').innerHTML = fields.filter(isEnv).map(fieldHtml).join('');
  $('modelfields').innerHTML = fields.filter(f => !isEnv(f)).map(fieldHtml).join('');
  built = true;
}

function config() {
  const c = {goal: $('goal').value};
  document.querySelectorAll('input').forEach(el => {
    if (!el.id.startsWith('f-')) return;
    c[el.id.slice(2)] = el.type === 'checkbox' ? (el.checked ? 'on' : 'off') : el.value;
  });
  return c;
}

function evRow(e) {
  const d = e.data || {}, cls = 'ev k-' + (e.kind === 'probe' && !d.ok ? 'probe bad' : e.kind);
  let body = '';
  switch (e.kind) {
    case 'state':   body = 'depth ' + d.depth + ' · progress ' + d.progress +
                           ' · facts ' + (d.fact_list || []).length + (d.parent ? ' · back to ' + d.parent : '');
                    break;
    case 'candidates': body = (d.moves || []).map(m => m.label + '  <span class="dim">' + esc(m.why) + '</span>')
                           .join('<br>') || '<span class="dim">nothing</span>'; break;
    case 'probe':   body = (d.ok ? '<span class="good">ok</span>' : '<span class="bad">failed</span>') +
                           (d.predicted ? ' <span class="pred">predicted, not performed</span>' : '') +
                           ' · ' + d.ms + ' ms<br><span class="dim">' + esc(d.excerpt) + '</span>'; break;
    case 'evaluation': body = 'progress ' + d.progress + (d.done ? ' · <span class="good">settles it</span>' : '') +
                              '<br><span class="dim">' + esc(d.reason) + '</span>'; break;
    case 'selected':   body = 'took ' + esc(d.move) + ' → progress ' + d.progress; break;
    case 'backtrack':  body = 'backed out to depth ' + d.to_depth + ' keeping every real fact'; break;
    case 'needs_confirmation': body = esc(d.move) + '<br><span class="dim">the engine will not perform this — ' +
                              'it needs a person or a simulator</span>'; break;
    case 'done':       body = '<span class="good">settled</span> in ' + d.model_calls + ' model calls'; break;
    case 'stopped':    body = '<span class="bad">not settled</span> — ' + esc(d.reason) + ' · ' +
                              d.model_calls + ' model calls' +
                              (d.needs ? '<br>it would need: ' + esc(d.needs) : ''); break;
    case 'error':      body = '<span class="bad">' + esc(d.error) + '</span>'; break;
    default:           body = esc(JSON.stringify(d));
  }
  const label = d.move || d.reason || '';
  return '<div class="' + cls + '"><span class="h">' + e.seq + ' ' + e.kind + '</span>' +
         (label && !['state','candidates','done','stopped','error'].includes(e.kind)
            ? ' <b>' + esc(label) + '</b>' : '') + '<br>' + body + '</div>';
}

function outcome(o) {
  // A settled run's payload carries the answer but not the facts behind it; the last state it drew does.
  const facts = (o.facts || lastFacts).map(f => '<li>' + esc(f) + '</li>').join('');
  if (o.settled) return '<h2>Settled</h2><pre>' + esc(o.answer) + '</pre>' +
                        '<h2>Facts it established</h2><ul>' + (facts || '<li class="dim">nothing</li>') + '</ul>';
  const partial = o.partial_answer
    ? '<h2>Best answer from what it read</h2><pre>' + esc(o.partial_answer) + '</pre>' +
      '<div class="dim">' + esc(o.answer_basis || 'not verified') + '</div>'
    : '';
  return '<h2>Not settled</h2><div class="bad">The goal was not settled: ' + esc(o.reason) + '.</div>' +
         (o.needs ? '<div>It would need: <b>' + esc(o.needs) + '</b></div>' : '') + partial +
         '<h2>What it did establish</h2><ul>' + (facts || '<li class="dim">nothing</li>') + '</ul>';
}

function render(s, append) {
  // Events first, then the outcome: the outcome of a settled run is drawn from the facts the last state
  // event carried, and both arrive in the same snapshot.
  if (append && s.events.length) {
    if (seen === 0) $('events').innerHTML = '';
    for (const e of s.events) if (e.kind === 'state' && e.data.fact_list) lastFacts = e.data.fact_list;
    $('events').insertAdjacentHTML('beforeend', s.events.map(evRow).join(''));
  }
  if (s.outcome) $('outcome').innerHTML = outcome(s.outcome);
  seen = s.next;
  $('status').textContent = s.status;
  $('notes').innerHTML = (s.notes || []).map(n => '<div>' + esc(n) + '</div>').join('');
}

async function poll() {
  const s = await (await fetch('/api/state?since=' + seen)).json();
  render(s, true);
  if (s.status === 'running') timer = setTimeout(poll, 300);
  else { timer = null; $('run').disabled = false; }
}

async function start() {
  $('run').disabled = true; $('events').innerHTML = ''; $('outcome').innerHTML = ''; seen = 0;
  const r = await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json'},
                                     body: JSON.stringify(config())});
  if (!r.ok) { $('outcome').innerHTML = '<div class="bad">could not start: ' + esc(await r.text()) + '</div>';
               $('run').disabled = false; return; }
  poll();
}

$('run').addEventListener('click', start);
fetch('/api/state?since=0').then(r => r.json()).then(s => {
  $('title').textContent = s.title; $('envnote').textContent = s.env_note;
  buildFields(s.fields); render(s, false);
});
</script></body></html>
"""


class Play:
    """One run at a time, and everything a page needs to draw it. `build_environment` is the example's half."""

    def __init__(self, build_environment, epilogue=None, defaults=None) -> None:
        self.build_environment = build_environment
        self.epilogue = epilogue
        self.defaults = dict(defaults or {})  # what the command line said, so the page opens on it
        self.stats = Statistics()  # carried across runs in this session, so a second run can be better
        self._lock = threading.Lock()
        self.events: list[dict] = []   # what the page draws (plain dicts)
        self.raw: list[Any] = []       # the same events, as the engine emitted them
        self.notes: list[str] = []
        self.outcome: Optional[dict] = None
        self.status = "idle"
        self.thread: Optional[threading.Thread] = None

    # ── what the page asks for ──

    def snapshot(self, since: int) -> dict[str, Any]:
        fields = [{**f, "default": self.defaults.get(f["name"], f["default"])}
                  for f in FIELDS + SHARED_FIELDS]
        with self._lock:
            return {"title": TITLE, "env_note": ENV_NOTE, "fields": fields,
                    "status": self.status, "next": len(self.events), "events": self.events[since:],
                    "outcome": self.outcome, "notes": self.notes[-8:]}

    def note(self, *lines: str) -> None:
        with self._lock:
            self.notes.extend(lines)

    def _emit(self, kind: str, data: dict) -> None:
        with self._lock:
            self.events.append({"seq": len(self.events) + 1, "kind": kind, "data": data})

    # ── running the thing ──

    def start(self, config: dict[str, str]) -> None:
        with self._lock:
            if self.status == "running":
                raise RuntimeError("a run is already going — wait for it, or restart the example")
            self.status, self.outcome, self.events, self.raw, self.notes = "running", None, [], [], []
        self.thread = threading.Thread(target=self._work, args=(config,), daemon=True)
        self.thread.start()

    def _work(self, config: dict[str, str]) -> None:
        try:
            asyncio.run(self._drive(config))
            self.status = "done"
        except Exception as exc:  # noqa: BLE001 — a playground reports what went wrong, it does not crash
            self._emit("error", {"error": f"{type(exc).__name__}: {exc}"})
            self.status = "error"

    async def _drive(self, config: dict[str, str]) -> None:
        port = OpenAICompatModel(config["base_url"], config["model"],
                                 api_key_env=(config.get("api_key_env") or "").strip() or None)
        self.note(f"model: {config['model']} at {config['base_url']}",
                  "key: " + (f"read from ${config['api_key_env']}" if os.environ.get(config.get("api_key_env", ""))
                             else "none found (fine for a local model, a 401 if yours needs one)"))
        # The environment is built per run: a cache that outlived the run would outlive the world it cached.
        env = CachingEnvironment(self.build_environment(config, self.stats), version=None)
        engine = StateEngine(
            env,
            proposer=LearningProposer(LLMMoveProposer(port, env.tools()), self.stats),
            evaluator=LLMEvaluator(port),
            simulator=LLMSimulator(port),
            budget=EngineBudget(max_model_calls=_int(config.get("budget_calls"), 12)),
        )
        try:
            async for event in engine.run(Goal(config.get("goal", "").strip())):
                self._emit(event.kind, event.data)
                self.raw.append(event)
                self.stats.observe(event)  # the record grows as the run goes, for the next one
                if event.kind in ("done", "stopped"):
                    # `stopped` carries settled=false; a `done` payload does not carry it at all, and the page
                    # should not have to know which event it is looking at.
                    self.outcome = {"settled": event.kind == "done", **event.data}
            self.note(f"probes: {env.stats()}")
            self.note("what this session has learned: " + _summary(self.stats))
            if self.epilogue is not None:
                self.epilogue(self, env, config)
        finally:
            # An environment may hold something a run has to give back — a browser, a connection, a file. The
            # engine's protocol says nothing about it, so this asks politely and does nothing when there is
            # nothing to ask.
            closer = getattr(getattr(env, "inner", env), "close", None)
            if callable(closer):
                closer()


def _int(value: Any, default: int) -> int:
    try:
        return max(1, int(str(value)))
    except (TypeError, ValueError):
        return default


def _summary(stats: Statistics) -> str:
    useful = [r for r in stats.by_tool.values() if r.selections]
    dead = [r for r in stats.by_tool.values() if r.hopeless()]
    parts = [f"{len(stats.by_tool)} tool(s), {len(stats.facts)} fact(s)"]
    if useful:
        parts.append("paid off: " + ", ".join(f"{r.tool} ×{r.selections}" for r in useful[:4]))
    if dead:
        parts.append("never worked: " + ", ".join(r.tool for r in dead[:4]))
    return " · ".join(parts)


class Handler(BaseHTTPRequestHandler):
    """Three routes: the page, the state, and the one thing a page can start."""

    play: Play

    def log_message(self, *args: Any) -> None:  # a playground does not need a request log
        pass

    def _send(self, code: int, body: bytes, kind: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:  # the page was closed mid-draw; the run carries on
            pass

    def do_GET(self) -> None:  # noqa: N802 — the name http.server calls
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path.startswith("/api/state"):
            since = 0  # a page that has drawn nothing asks from the beginning, which is a legitimate 0
            if "since=" in self.path:
                try:
                    since = max(0, int(self.path.split("since=", 1)[1].split("&", 1)[0]))
                except ValueError:
                    since = 0
            return self._send(200, json.dumps(self.play.snapshot(since)).encode(), "application/json")
        self._send(404, b"no such route", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/run":
            return self._send(404, b"no such route", "text/plain")
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin.split("//", 1)[-1] != host:  # a page on another site must not drive this
            return self._send(403, b"cross-origin requests are refused", "text/plain")
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 64 * 1024)
            config = json.loads(self.rfile.read(length) or b"{}")
            if not str(config.get("goal", "")).strip():
                return self._send(400, b"a goal is required", "text/plain")
            self.play.start({k: str(v) for k, v in config.items()})
        except RuntimeError as exc:
            return self._send(409, str(exc).encode(), "text/plain")
        except (ValueError, TypeError) as exc:
            return self._send(400, f"could not read that request: {exc}".encode(), "text/plain")
        self._send(200, b'{"started":true}', "application/json")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1", help="loopback by default; this page can start model runs")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the page in a browser")
    for field in FIELDS + SHARED_FIELDS:  # every field is also a flag, so a shell can script this
        ap.add_argument(f"--{field['name'].replace('_', '-')}", default=field["default"])
    args = ap.parse_args(argv)

    defaults = {f["name"]: getattr(args, f["name"]) for f in FIELDS + SHARED_FIELDS}
    play = Play(build_environment, epilogue, defaults)

    Handler.play = play
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"{TITLE}\n{url}\n\nctrl-c to stop")
    if args.open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
