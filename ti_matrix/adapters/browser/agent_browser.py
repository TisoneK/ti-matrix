"""The browser you already automate with, as a source of actions for the engine.

``agent-browser`` is a complete browser-automation CLI: an accessibility-tree snapshot with ``@eN`` refs so a
model can act without parsing HTML, semantic locators, tabs, cookies and storage, network interception, console
and error capture, axe-core audits, Web Vitals, tracing, profiling, video, React inspection. Reimplementing that
natively would mean rewriting axe-core and the React DevTools protocol, which is not a thing to do — so this
adapter does not reimplement it. It *exposes* it, as an environment, which is what ``ti_matrix.tools`` is for.

Where the native ``BrowserEnvironment`` and this one differ:

  - the native one is standard library only, so it works anywhere, and it has no daemon: it starts Chrome, does
    the work, and stops it. Its seventeen actions cover reading a page and acting on it.
  - this one is everything else — the CLI's whole surface — at the cost of a dependency this package does not
    ship and cannot install.
  - both can be in the same tool set. ``CompositeEnvironment`` resolves them by name and reports which one won
    each collision; mark one ``builtin`` and ``prefer`` decides.

Reading and writing
--------------------

Every action carries the same boundary as the rest of this project, decided by one question: **does performing
it hand the run something it can observe, or does it change the world it is observing?** So a snapshot, a
screenshot, an audit, a HAR file, a trace, a console dump and a page comparison are reads — they observe. And
these are not:

  - anything that acts on the page: ``click``, ``fill``, ``select``, ``drag``, ``eval``, ``pushstate``, the
    mouse, the clipboard, ``batch`` (whatever it contains).
  - anything that configures the browser rather than observing it: ``configure`` (viewport, offline, headers,
    geolocation, credentials), ``network_route``, cookie and storage writes, init scripts.
  - anything that reaches outside the browser: ``auth_save``/``auth_login`` (credentials), ``plugin_add`` and
    ``plugin_run`` (installs and runs code), ``clipboard_read`` (your clipboard is not the page's).
  - anything that answers the CLI's own confirmation queue: ``confirm`` and ``deny``.

``perform`` names what this run may do. ``perform={"all"}`` means all of it, and that name is not an
afterthought — you are handing an engine the machine. ``only`` narrows the other way, which matters when a run
needs four tools and not seventy.

Two smaller things worth knowing. Every action runs with ``--session`` set to a name of its own, because the
CLI's unnamed session is shared with everything else on the machine and outlives the command. And a password
never travels through an action's arguments: ``auth_save`` takes the *name of an environment variable* and
pipes the value in on stdin, so it reaches neither the model, nor the event log, nor ``ps``.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import threading
from dataclasses import replace
from typing import Any, Optional

from ti_matrix.protocols import Action, ActionSpec, Observation

_MAX_OBS = 2600  # an observation the evaluator can see whole (its view is 2800)
_MAX_ERROR = 600
_DEFAULT_TIMEOUT_S = 60.0
_LONG_TIMEOUT_S = 300.0  # these are allowed to take their time: navigation, waiting, recording, auditing
_LONG = frozenset({"open", "wait", "read", "har", "trace", "profiler", "record", "a11y", "vitals",
                   "diff_url", "react", "network_requests"})

# The actions a run may perform unasked. Everything in the table below that is not here changes something.
READS = frozenset({
    # reading a page
    "snapshot", "read", "get", "is_state", "find", "wait", "screenshot", "pdf", "tabs", "console", "errors",
    "vitals", "a11y", "highlight", "storage_get", "cookies_get",
    # navigation and the viewport
    "open", "back", "forward", "reload", "scroll", "scroll_to",
    # comparing
    "diff_snapshot", "diff_screenshot", "diff_url",
    # observing rather than changing: traffic, profiles, sessions, plugins
    "network_requests", "network_request", "har", "trace", "profiler", "record", "react", "webmcp_list",
    "webmcp_result", "session", "plugins", "plugin_show", "auth_list", "auth_show",
})

# The action name is not always the subcommand: these differ, as token lists so a two-word one works.
_SUBCOMMAND: dict[str, list[str]] = {
    "tabs": ["tab"], "is_state": ["is"], "configure": ["set"], "mouse": ["mouse"], "har": ["network", "har"],
    "auth_list": ["auth", "list"], "auth_show": ["auth", "show"], "auth_save": ["auth", "save"],
    "auth_login": ["auth", "login"], "auth_delete": ["auth", "delete"],
    "clipboard_read": ["clipboard", "read"], "clipboard_write": ["clipboard", "write"],
    "clipboard_copy": ["clipboard", "copy"], "clipboard_paste": ["clipboard", "paste"],
    "cookies_get": ["cookies", "get"], "cookies_set": ["cookies", "set"], "cookies_clear": ["cookies", "clear"],
    "storage_get": ["storage"], "storage_set": ["storage"], "storage_clear": ["storage"],
    "network_requests": ["network", "requests"], "network_request": ["network", "request"],
    "network_route": ["network", "route"], "network_unroute": ["network", "unroute"],
    "diff_snapshot": ["diff", "snapshot"], "diff_screenshot": ["diff", "screenshot"], "diff_url": ["diff", "url"],
    "scroll_to": ["scrollintoview"],
    "session": ["session"],
    "plugins": ["plugin", "list"], "plugin_show": ["plugin", "show"], "plugin_add": ["plugin", "add"],
    "plugin_run": ["plugin", "run"],
    "webmcp_list": ["webmcp", "list"], "webmcp_invoke": ["webmcp", "invoke"], "webmcp_result": ["webmcp", "result"],
    "webmcp_cancel": ["webmcp", "cancel"],
}


def _spot(parts: list[str], value: Any) -> None:
    """Append a value when one was actually supplied. Zero is a value: it is a coordinate, or a count."""
    if value is not None and value != "":
        parts.append(str(value))


def _flag(parts: list[str], name: str, value: Any) -> None:
    """Add ``--name value`` when the caller supplied one."""
    if value is not None and value != "":
        parts += [name, str(value)]


def _many(parts: list[str], values: Any) -> None:
    """Append a list as separate argv entries, so one of them can never be read as several."""
    if isinstance(values, str):
        values = [values]
    for value in values or []:
        _spot(parts, value)


def _build(name: str, args: dict) -> list[str]:
    """The arguments for one action, after the binary, the session and the subcommand.

    A fixed list of argv entries, never a shell string: a selector full of shell syntax stays a selector.
    """
    p: list[str] = []
    # ── reading a page ──
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
        _spot(p, args.get("target"))
        _flag(p, "--timeout", args.get("timeout_ms"))
    elif name == "screenshot":
        if args.get("full_page"):
            p.append("--full-page")
        _spot(p, args.get("path"))
    elif name == "pdf":
        _spot(p, args.get("path"))
    elif name == "tabs":
        _spot(p, args.get("action"))
    elif name == "highlight":
        _spot(p, args.get("selector"))
    elif name == "vitals":
        _spot(p, args.get("url"))
    elif name == "a11y":
        _flag(p, "--tags", args.get("tags"))
        _flag(p, "--selector", args.get("selector"))
        if args.get("json"):
            p.append("--json")
        _spot(p, args.get("url"))
    # ── observing traffic, models, profiles and sessions ──
    elif name == "network_requests":
        _flag(p, "--filter", args.get("filter"))
        _flag(p, "--type", args.get("resource_type"))
        _flag(p, "--method", args.get("method"))
        _flag(p, "--status", args.get("status"))
        if args.get("json"):
            p.append("--json")
    elif name == "network_request":
        _spot(p, args.get("id"))
    elif name == "har":
        _spot(p, args.get("action") or "start")
        _flag(p, "--content", args.get("content"))
        _spot(p, args.get("path"))
    elif name in ("trace", "profiler", "record"):
        _spot(p, args.get("action") or "start")
        _spot(p, args.get("path"))
        if name == "record":
            _spot(p, args.get("url"))
        if name == "profiler":
            _flag(p, "--categories", args.get("categories"))
    elif name == "react":
        _spot(p, args.get("action") or "tree")
        _spot(p, args.get("id"))
        if args.get("only_dynamic"):
            p.append("--only-dynamic")
        if args.get("json"):
            p.append("--json")
    elif name == "webmcp_list":
        pass
    elif name == "webmcp_result":
        _spot(p, args.get("id"))
        _flag(p, "--timeout", args.get("timeout_ms"))
    elif name == "session":
        _spot(p, args.get("action"))
        _flag(p, "--scope", args.get("scope"))
        _flag(p, "--prefix", args.get("prefix"))
    elif name == "plugins":
        if args.get("json"):
            p.append("--json")
    elif name == "plugin_show":
        _spot(p, args.get("name"))
    # ── comparing ──
    elif name == "diff_snapshot":
        _flag(p, "--baseline", args.get("baseline"))
        _flag(p, "-s", args.get("selector"))
        _flag(p, "-d", args.get("depth"))
    elif name == "diff_screenshot":
        _flag(p, "--baseline", args.get("baseline"))
        _flag(p, "--selector", args.get("selector"))
        _flag(p, "--threshold", args.get("threshold"))
    elif name == "diff_url":
        _spot(p, args.get("first"))
        _spot(p, args.get("second"))
    # ── navigation and the viewport ──
    elif name in ("open", "pushstate"):
        _spot(p, args.get("url"))
    elif name in ("back", "forward", "reload", "scroll_to"):
        _spot(p, args.get("selector"))
    elif name == "scroll":
        _spot(p, args.get("direction"))
        _spot(p, args.get("pixels"))
    # ── acting on the page ──
    elif name in ("click", "dblclick", "hover", "focus", "check", "uncheck"):
        _spot(p, args.get("selector"))
    elif name in ("type", "fill"):
        _spot(p, args.get("selector"))
        _spot(p, args.get("text"))
    elif name == "press":
        _spot(p, args.get("key"))
    elif name == "keyboard":
        _spot(p, args.get("action"))
        _spot(p, args.get("text"))
    elif name == "select":
        _spot(p, args.get("selector"))
        _many(p, args.get("values"))
    elif name == "drag":
        _spot(p, args.get("source"))
        _spot(p, args.get("target"))
    elif name == "upload":
        _spot(p, args.get("selector"))
        _many(p, args.get("files"))
    elif name == "eval":
        _spot(p, args.get("js"))
    elif name == "batch":
        if args.get("bail"):
            p.append("--bail")
        _many(p, args.get("commands"))
    # ── configuring the browser rather than observing it ──
    elif name == "configure":
        _spot(p, args.get("setting"))
        for key in ("value", "second", "third"):
            _spot(p, args.get(key))
    elif name == "mouse":
        action = str(args.get("action") or "")
        _spot(p, args.get("action"))
        if action == "wheel":
            _spot(p, args.get("dy"))
            _spot(p, args.get("dx"))
        else:
            _spot(p, args.get("x"))
            _spot(p, args.get("y"))
            _spot(p, args.get("button"))
    elif name == "network_route":
        _spot(p, args.get("url"))
        if args.get("abort"):
            p.append("--abort")
        _flag(p, "--body", args.get("body"))
        _flag(p, "--resource-type", args.get("resource_type"))
    elif name == "network_unroute":
        _spot(p, args.get("url"))
    elif name == "cookies_set":
        _spot(p, args.get("name"))
        _spot(p, args.get("value"))
        _flag(p, "--url", args.get("url"))
        _flag(p, "--domain", args.get("domain"))
        _flag(p, "--path", args.get("path"))
        _flag(p, "--sameSite", args.get("same_site"))
        _flag(p, "--expires", args.get("expires"))
        if args.get("http_only"):
            p.append("--httpOnly")
        if args.get("secure"):
            p.append("--secure")
    elif name == "cookies_clear":
        pass
    elif name in ("storage_get", "storage_set", "storage_clear"):
        _spot(p, args.get("kind"))
        if name != "storage_get":
            p.append("set" if name == "storage_set" else "clear")
        _spot(p, args.get("key"))
        if name == "storage_set":
            _spot(p, args.get("value"))
    elif name == "removeinitscript":
        _spot(p, args.get("id"))
    # ── reaching outside the browser ──
    elif name in ("auth_list", "auth_show", "auth_delete"):
        if name != "auth_list":
            _spot(p, args.get("name"))
    elif name in ("auth_save", "auth_login"):
        _spot(p, args.get("name"))
        _flag(p, "--url", args.get("url"))
        if name == "auth_save":
            _flag(p, "--username", args.get("username"))
            if args.get("password_env"):
                p.append("--password-stdin")  # the value goes in on stdin, never in argv
        else:
            _flag(p, "--credential-provider", args.get("credential_provider"))
            _flag(p, "--item", args.get("item"))
            _flag(p, "--username-selector", args.get("username_selector"))
            _flag(p, "--password-selector", args.get("password_selector"))
    elif name == "plugin_add":
        _spot(p, args.get("ref"))
        _flag(p, "--name", args.get("name"))
    elif name == "plugin_run":
        _spot(p, args.get("name"))
        _spot(p, args.get("request"))
        _flag(p, "--payload", args.get("payload"))
    elif name == "webmcp_invoke":
        _spot(p, args.get("tool"))
        _flag(p, "--params", args.get("params"))
        _flag(p, "--frame", args.get("frame"))
        _flag(p, "--timeout", args.get("timeout_ms"))
        if args.get("detach"):
            p.append("--detach")
    elif name == "webmcp_cancel":
        _spot(p, args.get("id"))
    elif name == "clipboard_write":
        _spot(p, args.get("text"))
    elif name in ("clipboard_read", "clipboard_copy", "clipboard_paste"):
        pass  # the operation is the subcommand
    elif name in ("confirm", "deny"):
        _spot(p, args.get("id"))
    elif name == "close":
        p.append("--all")
    return p


def _agent_browser_actions(perform: frozenset[str], only: Optional[frozenset[str]]) -> dict[str, ActionSpec]:
    """The command table. `read_only` is decided by what the host allows itself to perform."""
    specs = [
        # ── reading a page ──
        ActionSpec("snapshot", "The page as an accessibility tree with @eN refs. Do it first, and again after "
                               "anything changes the page: refs go stale.",
                   '{"interactive": true, "compact": true}'),
        ActionSpec("read", "A URL's text, fetched through the browser.", '{"url": "<the URL to read>"}'),
        ActionSpec("get", "One thing about the page or an element: text, html, value, attr, title, url, count, "
                          "box, styles.", '{"what": "value", "selector": "@e1"}'),
        ActionSpec("is_state", "Whether an element is visible, enabled or checked.",
                   '{"what": "visible", "selector": "@e3"}'),
        ActionSpec("find", "Locate by meaning rather than markup — role, text, label, placeholder, alt, title, "
                           "testid, first, last, nth — optionally acting on it.",
                   '{"locator": "role", "value": "button", "action": "click"}'),
        ActionSpec("wait", "Wait for an element, some milliseconds, or a load state.", '{"load": "networkidle"}'),
        ActionSpec("screenshot", "Save a PNG for a person to look at.",
                   '{"path": "page.png", "full_page": false}'),
        ActionSpec("pdf", "Save the page as a PDF.", '{"path": "page.pdf"}'),
        ActionSpec("tabs", "List the tabs, open one, close one, or switch to one.", '{"action": "list"}'),
        ActionSpec("highlight", "Draw attention to an element, for a human watching.", '{"selector": "@e5"}'),
        ActionSpec("console", "The page's console output.", "{}"),
        ActionSpec("errors", "The page's errors.", "{}"),
        ActionSpec("vitals", "Core Web Vitals for the page: LCP, CLS, TTFB, FCP, INP.",
                   '{"url": "<the page to measure; omit for the current one>"}'),
        ActionSpec("a11y", "An axe-core accessibility audit: WCAG violations, with selectors.",
                   '{"tags": "wcag2a,wcag2aa"}'),
        # ── observing traffic, models, profiles and sessions ──
        ActionSpec("network_requests", "The requests the page made, optionally filtered.",
                   '{"filter": "**/api/**", "status": "4xx"}'),
        ActionSpec("network_request", "One request in full, including its body.", '{"id": "<requestId>"}'),
        ActionSpec("har", "Record the page's traffic to a HAR file: start, then stop with a path.",
                   '{"action": "start"}'),
        ActionSpec("trace", "Record a Chrome DevTools trace: start, then stop with a path.",
                   '{"action": "start", "path": "trace.json"}'),
        ActionSpec("profiler", "Record a performance profile: start, then stop with a path.",
                   '{"action": "start", "categories": "devtools.timeline"}'),
        ActionSpec("record", "Record the browser to a WebM video: start with a path, then stop.",
                   '{"action": "start", "path": "run.webm"}'),
        ActionSpec("react", "A React app's component tree, one fiber's props and hooks, render profiling, or "
                            "Suspense boundaries.", '{"action": "tree"}'),
        ActionSpec("webmcp_list", "The tools the current page registers (experimental).", "{}"),
        ActionSpec("webmcp_result", "The result of a detached page-tool invocation.", '{"id": "..."}'),
        ActionSpec("session", "Which browser session this is, and what else is running.", '{"action": "list"}'),
        ActionSpec("plugins", "The plugins this CLI has configured.", "{}"),
        ActionSpec("plugin_show", "One configured plugin.", '{"name": "vault"}'),
        # ── comparing ──
        ActionSpec("diff_snapshot", "What changed in the page since the last snapshot.",
                   '{"baseline": "before.txt"}'),
        ActionSpec("diff_screenshot", "A visual pixel diff against a baseline image.",
                   '{"baseline": "before.png"}'),
        ActionSpec("diff_url", "Compare two pages.", '{"first": "<url>", "second": "<url>"}'),
        # ── navigation and the viewport ──
        ActionSpec("open", "Navigate to a URL. Propose this ON ITS OWN: a fan is probed all at once, so "
                            "navigating while other actions read the page leaves them reading whichever page "
                            "they happened to catch.", '{"url": "<the full URL to load>"}'),
        ActionSpec("back", "Go back.", "{}"),
        ActionSpec("forward", "Go forward.", "{}"),
        ActionSpec("reload", "Reload the page.", "{}"),
        ActionSpec("scroll", "Scroll the page.", '{"direction": "down", "pixels": 600}'),
        ActionSpec("scroll_to", "Scroll an element into view.", '{"selector": "@e9"}'),
        # ── acting on the page ──
        ActionSpec("click", "Click an element, by @ref or selector.", '{"selector": "@e3"}', read_only=False),
        ActionSpec("dblclick", "Double-click an element.", '{"selector": "@e3"}', read_only=False),
        ActionSpec("hover", "Hover an element, which can open menus.", '{"selector": "@e4"}', read_only=False),
        ActionSpec("focus", "Focus an element.", '{"selector": "@e2"}', read_only=False),
        ActionSpec("type", "Type into an element, keeping what is there.",
                   '{"selector": "@e1", "text": "hello"}', read_only=False),
        ActionSpec("fill", "Clear an element and fill it.", '{"selector": "@e1", "text": "hello"}',
                   read_only=False),
        ActionSpec("press", "Press a key in whatever has focus.", '{"key": "Enter"}', read_only=False),
        ActionSpec("keyboard", "Type into the focused element, with or without key events.",
                   '{"action": "type", "text": "hello"}', read_only=False),
        ActionSpec("check", "Check a checkbox.", '{"selector": "@e7"}', read_only=False),
        ActionSpec("uncheck", "Uncheck a checkbox.", '{"selector": "@e7"}', read_only=False),
        ActionSpec("select", "Choose options in a dropdown.", '{"selector": "@e5", "values": ["one"]}',
                   read_only=False),
        ActionSpec("drag", "Drag one element onto another.", '{"source": "@e1", "target": "@e2"}',
                   read_only=False),
        ActionSpec("upload", "Put files into a file input.", '{"selector": "@e1", "files": ["/tmp/a.pdf"]}',
                   read_only=False),
        ActionSpec("eval", "Run JavaScript in the page. Arbitrary code, so not a read.",
                   '{"js": "document.title"}', read_only=False),
        ActionSpec("pushstate", "Client-side navigation in a single-page app.", '{"url": "/settings"}',
                   read_only=False),
        ActionSpec("batch", "Run several commands in one action — whatever they are, so granting this grants "
                            "all of them.", '{"commands": ["open https://x", "snapshot -i"], "bail": true}',
                   read_only=False),
        # ── configuring the browser rather than observing it ──
        ActionSpec("configure", "Browser settings and emulation: viewport, device, geo, offline, headers, "
                                "credentials, media.",
                   '{"setting": "viewport", "value": 1920, "second": 1080}', read_only=False),
        ActionSpec("mouse", "Low-level mouse control. move needs x and y; wheel needs dy (and dx); down and "
                            "up take an optional button.",
                   '{"action": "move", "x": 100, "y": 200}', read_only=False),
        ActionSpec("network_route", "Intercept and mock or block requests: abort, or answer with a body.",
                   '{"url": "**/api/users", "body": "{\\"users\\": []}"}', read_only=False),
        ActionSpec("network_unroute", "Stop intercepting a pattern, or all of them.", '{"url": "**/api/**"}',
                   read_only=False),
        ActionSpec("cookies_get", "The browser's cookies.", "{}"),
        ActionSpec("cookies_set", "Set a cookie, with the flags a real one has.",
                   '{"name": "<cookie>", "value": "<value>", "domain": "<.your-domain>", "secure": true}',
                   read_only=False),
        ActionSpec("cookies_clear", "Clear every cookie.", "{}", read_only=False),
        ActionSpec("storage_get", "localStorage or sessionStorage, all of it or one key.",
                   '{"kind": "local", "key": "token"}'),
        ActionSpec("storage_set", "Write to local or session storage.",
                   '{"kind": "local", "key": "token", "value": "abc"}', read_only=False),
        ActionSpec("storage_clear", "Clear local or session storage.", '{"kind": "local"}', read_only=False),
        ActionSpec("removeinitscript", "Remove a script that was set to run on every page.", '{"id": "..."}',
                   read_only=False),
        # ── reaching outside the browser ──
        ActionSpec("auth_save", "Save credentials for a site. The password comes from an environment variable "
                                "you name, never through this action's value.",
                   '{"name": "<a label you choose>", "url": "<the login page>", "username": "<you>", '
                   '"password_env": "<THE_ENV_VAR_HOLDING_IT>"}', read_only=False),
        ActionSpec("auth_login", "Sign in with saved credentials, or a credential-provider plugin.",
                   '{"name": "app", "credential_provider": "vault", "item": "My App"}', read_only=False),
        ActionSpec("auth_list", "The saved auth profiles.", "{}"),
        ActionSpec("auth_show", "One auth profile's metadata. Never its password.", '{"name": "app"}'),
        ActionSpec("auth_delete", "Delete a saved auth profile.", '{"name": "app"}', read_only=False),
        ActionSpec("plugin_add", "Install a plugin from npm or GitHub. This installs code.",
                   '{"ref": "agent-browser-plugin-vault", "name": "vault"}', read_only=False),
        ActionSpec("plugin_run", "Run a plugin's command. External code, with your permissions.",
                   '{"name": "captcha", "request": "captcha.solve", "payload": "{\\"siteKey\\": \\"...\\"}"}',
                   read_only=False),
        ActionSpec("webmcp_invoke", "Invoke a tool the page itself registered (experimental).",
                   '{"tool": "search", "params": "{\\"q\\": \\"widgets\\"}"}', read_only=False),
        ActionSpec("webmcp_cancel", "Cancel a page-tool invocation.", '{"id": "..."}', read_only=False),
        ActionSpec("clipboard_read", "Read the system clipboard — which is not the page's, and may hold what "
                                     "the user last copied.", "{}", read_only=False),
        ActionSpec("clipboard_write", "Write to the system clipboard.", '{"text": "hello"}', read_only=False),
        ActionSpec("clipboard_copy", "Copy the current selection, as Ctrl+C would.", "{}", read_only=False),
        ActionSpec("clipboard_paste", "Paste into the page, as Ctrl+V would.", "{}", read_only=False),
        ActionSpec("confirm", "Approve an action the CLI is holding for confirmation.", '{"id": "c_8f3a1234"}',
                   read_only=False),
        ActionSpec("deny", "Refuse an action the CLI is holding for confirmation.", '{"id": "c_8f3a1234"}',
                   read_only=False),
        ActionSpec("close", "Close every tab of this session.", "{}", read_only=False),
    ]
    allowed = {spec.name for spec in specs if spec.name in READS or spec.name in perform}
    if "all" in perform:
        allowed = {spec.name for spec in specs}  # you asked for the machine; here it is
    return {spec.name: replace(spec, read_only=spec.name in allowed)
            for spec in specs if only is None or spec.name in only}


class AgentBrowser:
    """`agent-browser` as an environment: its whole command surface, as actions a run can search over.

    ``perform`` names the actions this run may carry out; ``{"all"}`` means every one of them. ``only``
    narrows the table itself, for a run that needs four tools rather than seventy.
    """

    name = "agent-browser"

    def __init__(
        self,
        *,
        command: str = "agent-browser",
        session: Optional[str] = "ti-matrix",
        profile: Optional[str] = None,
        perform: Optional[set[str] | tuple[str, ...]] = None,
        only: Optional[set[str] | tuple[str, ...]] = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self.command = command
        self.session = session
        self.profile = profile
        self.timeout_s = timeout_s
        self.perform = frozenset(perform or ())
        self._actions = _agent_browser_actions(self.perform, frozenset(only) if only else None)
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
                f"{action.tool} would change the page, the browser, or something outside it, and this "
                f"environment is not allowed to perform it (pass perform={{{action.tool!r}}} to allow it, "
                f"perform={{'all'}} for everything, or confirm it and do the work yourself)"))
        try:
            argv = _build(action.tool, action.args)
            stdin = self._stdin(action)
        except (TypeError, AttributeError) as exc:
            return Observation(action, False, f"bad arguments for {action.tool}: {exc}")
        return await asyncio.to_thread(self._run, action, argv, stdin)

    def _stdin(self, action: Action) -> Optional[str]:
        """The one thing that must not travel in an argument: a password, named by variable, piped in."""
        if action.tool != "auth_save":
            return None
        variable = str(action.args.get("password_env") or "")
        if not variable:
            return None
        value = os.environ.get(variable)
        if value is None:
            raise TypeError(f"${variable} is not set in this environment")
        return value + "\n"

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

    def _run(self, action: Action, argv: list[str], stdin: Optional[str]) -> Observation:
        command = self.argv(action.tool, action.args)
        timeout = _LONG_TIMEOUT_S if action.tool in _LONG else self.timeout_s
        with self._lock:  # one session: two commands at once would interleave on one browser
            try:
                done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, input=stdin)
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
