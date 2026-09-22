"""The browser you already automate with, as a source of actions for the engine.

``agent-browser`` is a complete browser-automation CLI: an accessibility-tree snapshot with ``@eN`` refs so a
model can act without parsing HTML, semantic locators, tabs, cookies and storage, network interception, console
and error capture, axe-core audits, Web Vitals, tracing, React inspection. Reimplementing that natively would
mean rewriting axe-core and the React DevTools protocol, which is not a thing to do — so this adapter does not
reimplement it. It *exposes* it, as an environment, which is what ``ti_matrix.tools`` exists for.

Where the native ``BrowserEnvironment`` and this one differ, and why you might want either:

  - the native one is standard library only, so it works anywhere, and it has no daemon to leak: it starts
    Chrome, does the work, and stops it. Its seventeen actions cover reading a page and acting on it.
  - this one is everything else — the whole CLI surface — at the cost of a dependency this package does not
    ship and cannot install. It is here for a host that already has ``agent-browser``, which is most of the
    value of having it.
  - both can be in the same tool set. ``CompositeEnvironment`` resolves them by name and reports which one
    won each collision; ``supersedes`` decides it explicitly where the names differ but the job does not.

Two things this adapter is careful about. **Sessions**: the CLI's default session is shared with anything else
on the machine and outlives the command, so every action here runs with ``--session`` set to a name the host
chose — a run cannot hijack a browser a person left open. And **the boundary**: the same read/write split as
the native environment, on the same rule. Reads (snapshots, text, state, screenshots, audits) are performed;
anything that changes a page (click, fill, select, drag, upload) is refused unless the host names it in
``perform``.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import threading
from dataclasses import replace
from typing import Any, Optional

from ti_matrix.protocols import Action, ActionSpec, Observation

_MAX_OBS = 2600  # an observation the evaluator can see whole (its view is 2800)
_MAX_ERROR = 600
_DEFAULT_TIMEOUT_S = 60.0
_LONG_TIMEOUT_S = 180.0  # `open` and `wait` are allowed to take their time

# What a run may do to a page unasked. Everything else in the table below changes something.
READS = frozenset({
    "snapshot", "read", "get", "is_state", "find", "wait", "screenshot", "pdf", "tabs", "console", "errors",
    "vitals", "a11y", "cookies_get", "storage_get", "diff_snapshot", "open", "back", "forward", "reload",
    "scroll", "scroll_to",
})


# The action name is not always the subcommand: these are the ones that differ, as token lists so a
# two-word subcommand works. Everything else is its own name.
_SUBCOMMAND: dict[str, list[str]] = {
    "tabs": ["tab"], "is_state": ["is"], "cookies_get": ["cookies", "get"], "storage_get": ["storage"],
    "diff_snapshot": ["diff", "snapshot"], "scroll_to": ["scrollintoview"],
}


def _flag(parts: list[str], name: str, value: Any) -> None:
    """Add ``--name value`` when the caller actually supplied one."""
    if value not in (None, "", False):
        parts += [name, str(value)]


def _spot(parts: list[str], value: Any) -> None:
    if value not in (None, ""):
        parts.append(str(value))


def _build(name: str, args: dict) -> list[str]:
    """The argv for one action: a fixed list, never a shell string, so nothing here can be injected."""
    p: list[str] = []
    if name == "snapshot":
        if args.get("interactive", True):
            p.append("-i")
        if args.get("compact", True):
            p.append("-c")
        _flag(p, "-d", args.get("depth"))
        _flag(p, "-s", args.get("selector"))
        if args.get("with_urls"):
            p.append("-u")
        if args.get("json"):
            p.append("--json")
    elif name == "read":
        _spot(p, args.get("url"))
    elif name == "get":
        _spot(p, args.get("what"))
        _spot(p, args.get("selector"))
    elif name == "is_state":
        _spot(p, args.get("what"))
        _spot(p, args.get("selector"))
    elif name == "find":
        for key in ("locator", "value", "action", "text"):
            _spot(p, args.get(key))
    elif name == "wait":
        _flag(p, "--load", args.get("load"))
        if args.get("target") not in (None, ""):
            _spot(p, args.get("target"))
        if args.get("timeout_ms"):
            _flag(p, "--timeout", args.get("timeout_ms"))
    elif name == "screenshot":
        if args.get("full_page"):
            p.append("--full-page")
        _spot(p, args.get("path"))
    elif name == "pdf":
        _spot(p, args.get("path"))
    elif name == "tabs":
        _spot(p, args.get("action"))
    elif name == "vitals":
        _spot(p, args.get("url"))
    elif name == "a11y":
        _flag(p, "--tags", args.get("tags"))
        _flag(p, "--selector", args.get("selector"))
        _spot(p, args.get("url"))
    elif name in ("cookies_get", "storage_get"):
        if name == "storage_get":
            _spot(p, args.get("action"))
    elif name == "diff_snapshot":
        pass
    elif name in ("open", "pushstate"):
        _spot(p, args.get("url"))
    elif name in ("back", "forward", "reload", "scroll_to"):
        _spot(p, args.get("selector"))
    elif name == "scroll":
        _spot(p, args.get("direction"))
        _spot(p, args.get("pixels"))
    elif name == "click" or name == "dblclick" or name == "hover" or name == "focus":
        _spot(p, args.get("selector"))
    elif name == "type" or name == "fill":
        _spot(p, args.get("selector"))
        _spot(p, args.get("text"))
    elif name in ("check", "uncheck"):
        _spot(p, args.get("selector"))
    elif name == "press":
        _spot(p, args.get("key"))
    elif name == "keyboard":
        _spot(p, args.get("action"))
        _spot(p, args.get("text"))
    elif name == "select":
        _spot(p, args.get("selector"))
        values = args.get("values")
        if isinstance(values, str):
            values = [values]
        for value in values or []:
            _spot(p, value)
    elif name == "drag":
        _spot(p, args.get("source"))
        _spot(p, args.get("target"))
    elif name == "upload":
        _spot(p, args.get("selector"))
        files = args.get("files")
        if isinstance(files, str):
            files = [files]
        for path in files or []:
            _spot(p, path)
    elif name == "eval":
        _spot(p, args.get("js"))
    elif name == "close":
        p.append("--all")
    return p


def _agent_browser_actions(perform: frozenset[str]) -> dict[str, ActionSpec]:
    """The command table. `read_only` is decided by what the host allows itself to perform."""
    specs = [
        # ── reading ──
        ActionSpec("snapshot", "The page as an accessibility tree, with @eN refs to act on. Do this first, and "
                               "again after anything changes the page: refs go stale.",
                   '{"interactive": true, "compact": true}'),
        ActionSpec("read", "A URL's text, fetched through the browser.", '{"url": "https://example.com"}'),
        ActionSpec("get", "One thing about the page or an element: text, html, value, attr, title, url, "
                          "count, box, styles.", '{"what": "value", "selector": "@e1"}'),
        ActionSpec("is_state", "Whether an element is visible, enabled or checked.",
                   '{"what": "visible", "selector": "@e3"}'),
        ActionSpec("find", "Locate by meaning rather than markup — role, text, label, placeholder, alt, title, "
                           "testid, first, last, nth — optionally acting on it.",
                   '{"locator": "role", "value": "button", "action": "click"}'),
        ActionSpec("wait", "Wait for an element, a number of milliseconds, or a load state.",
                   '{"load": "networkidle"}'),
        ActionSpec("screenshot", "Save a PNG for a person to look at.",
                   '{"path": "page.png", "full_page": false}'),
        ActionSpec("pdf", "Save the page as a PDF.", '{"path": "page.pdf"}'),
        ActionSpec("tabs", "List the tabs, or switch to one.", '{"action": "list"}'),
        ActionSpec("console", "The page's console output.", "{}"),
        ActionSpec("errors", "The page's errors.", "{}"),
        ActionSpec("vitals", "Core Web Vitals for the page.", '{"url": "https://example.com"}'),
        ActionSpec("a11y", "An axe-core accessibility audit: WCAG violations with selectors.",
                   '{"tags": "wcag2a,wcag2aa"}'),
        ActionSpec("cookies_get", "The browser's cookies for this page.", "{}"),
        ActionSpec("storage_get", "The page's local or session storage.", '{"action": "local"}'),
        ActionSpec("diff_snapshot", "What changed in the page since the last snapshot.", "{}"),
        ActionSpec("open", "Navigate to a URL.", '{"url": "https://example.com"}'),
        ActionSpec("back", "Go back.", "{}"),
        ActionSpec("forward", "Go forward.", "{}"),
        ActionSpec("reload", "Reload the page.", "{}"),
        ActionSpec("scroll", "Scroll the page.", '{"direction": "down", "pixels": 600}'),
        ActionSpec("scroll_to", "Scroll an element into view.", '{"selector": "@e9"}'),
        # ── changing something: declared, and never performed unasked ──
        ActionSpec("click", "Click an element, by @ref or selector.", '{"selector": "@e3"}', read_only=False),
        ActionSpec("dblclick", "Double-click an element.", '{"selector": "@e3"}', read_only=False),
        ActionSpec("hover", "Hover an element, which can open menus.", '{"selector": "@e4"}', read_only=False),
        ActionSpec("focus", "Focus an element.", '{"selector": "@e2"}', read_only=False),
        ActionSpec("type", "Type text into an element, keeping what is there.",
                   '{"selector": "@e1", "text": "hello"}', read_only=False),
        ActionSpec("fill", "Clear an element and fill it.", '{"selector": "@e1", "text": "hello"}',
                   read_only=False),
        ActionSpec("press", "Press a key in whatever has focus.", '{"key": "Enter"}', read_only=False),
        ActionSpec("keyboard", "Type into the focused element, with or without key events.",
                   '{"action": "type", "text": "hello"}', read_only=False),
        ActionSpec("check", "Check a checkbox.", '{"selector": "@e7"}', read_only=False),
        ActionSpec("uncheck", "Uncheck a checkbox.", '{"selector": "@e7"}', read_only=False),
        ActionSpec("select", "Choose an option in a dropdown.",
                   '{"selector": "@e5", "values": ["one"]}', read_only=False),
        ActionSpec("drag", "Drag one element onto another.", '{"source": "@e1", "target": "@e2"}',
                   read_only=False),
        ActionSpec("upload", "Put files into a file input.", '{"selector": "@e1", "files": ["/tmp/a.pdf"]}',
                   read_only=False),
        ActionSpec("eval", "Run JavaScript in the page. Arbitrary code, so not a read.",
                   '{"js": "document.title"}', read_only=False),
        ActionSpec("pushstate", "Client-side navigation for a single-page app.", '{"url": "/settings"}',
                   read_only=False),
        ActionSpec("close", "Close every tab of this session.", "{}", read_only=False),
    ]
    return {s.name: replace(s, read_only=s.name in perform) for s in specs}


class AgentBrowser:
    """`agent-browser` as an environment: its whole command surface, as actions a run can search over.

    ``session`` defaults to a name of its own — ``"ti-matrix"`` — because the CLI's unnamed default session is
    shared with every other user of the machine and outlives the command, so a run in it can navigate away
    from a page somebody left open. Pass ``session=None`` deliberately if you want that, and pass a different
    name per run if two runs should not share a browser.
    """

    name = "agent-browser"

    def __init__(
        self,
        *,
        command: str = "agent-browser",
        session: Optional[str] = "ti-matrix",
        profile: Optional[str] = None,
        perform: Optional[set[str] | tuple[str, ...]] = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self.command = command
        self.session = session
        self.profile = profile
        self.timeout_s = timeout_s
        self.perform = frozenset(READS | set(perform or ()))
        self._actions = _agent_browser_actions(self.perform)
        self._lock = threading.Lock()  # one session, one command at a time, however wide the fan is

    # ── the contract ──

    def tools(self) -> dict[str, ActionSpec]:
        return self._actions

    def is_read_only(self, action: Action) -> Optional[bool]:
        spec = self._actions.get(action.tool)
        return None if spec is None else spec.read_only

    async def probe(self, action: Action) -> Observation:
        if action.tool not in self._actions:
            return Observation(action, False, f"no agent-browser action called {action.tool!r}")
        if not self._actions[action.tool].read_only:
            return Observation(action, False, (
                f"{action.tool} would change the page or the browser, and this environment is not allowed to "
                f"perform it (pass perform={{{action.tool!r}}} to allow it, or confirm it and do it yourself)"))
        try:
            argv = _build(action.tool, action.args)
        except TypeError as exc:
            return Observation(action, False, f"bad arguments for {action.tool}: {exc}")
        return await asyncio.to_thread(self._run, action, argv)

    # ── running the CLI ──

    def argv(self, tool: str, args: dict) -> list[str]:
        """The command line this action becomes — public so a host can print it or audit it."""
        base = [self.command]
        if self.session:
            base += ["--session", self.session]
        if self.profile:
            base += ["--profile", self.profile]
        return base + _SUBCOMMAND.get(tool, [tool]) + _build(tool, args)

    def available(self) -> bool:
        """Whether the CLI this adapter needs is actually here — nothing is installed on its behalf."""
        return shutil.which(self.command) is not None

    def _run(self, action: Action, argv: list[str]) -> Observation:
        command = self.argv(action.tool, action.args)
        timeout = _LONG_TIMEOUT_S if action.tool in ("open", "wait", "read") else self.timeout_s
        with self._lock:  # one session: two commands at once would interleave on one browser
            try:
                done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
            except FileNotFoundError:
                return Observation(action, False, (
                    f"{self.command} is not installed — this adapter drives an existing tool rather than "
                    f"shipping one (npm i -g agent-browser)"))
            except subprocess.TimeoutExpired:
                return Observation(action, False, f"{' '.join(command[:3])} … did not finish in {timeout:.0f}s")
        out = " ".join((done.stdout or "").split())
        if done.returncode != 0:
            why = " ".join((done.stderr or done.stdout or "").split())[:_MAX_ERROR] or "no output"
            return Observation(action, False, f"exit {done.returncode}: {why}")
        if not out:
            return Observation(action, True, "ok (no output)")
        return Observation(action, True, out[:_MAX_OBS])


__all__ = ["AgentBrowser", "READS"]
