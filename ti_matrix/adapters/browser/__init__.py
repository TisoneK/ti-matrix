"""The engine driving a real browser: read anything, change nothing unless the host says so.

Chrome's DevTools Protocol is JSON over a WebSocket, and neither of those is in the standard library — so the
two files below are the protocol plumbing this project had to own rather than depend on, and the third is the
environment the engine actually sees:

    websocket.py      the opening handshake and the frame format, RFC 6455, no dependencies
    cdp.py            Chrome: start it, find its pages, drive one (navigate, click, type, screenshot, …)
    environment.py    BrowserEnvironment — the actions, and which of them a run may perform unasked
    agent_browser.py  AgentBrowser — the `agent-browser` CLI as a source of actions, for a host that has it

The promise this keeps is the project's own: no runtime dependencies, standard library only. A launch is a
``subprocess`` call, discovery is an HTTP GET, and the protocol rides the socket above.

The promise it makes about safety is the other half. Eleven of the seventeen actions read — text, links, markup,
a selector's presence, a screenshot for a human to look at — and the search performs those freely. Six can
change the world (`click`, `type`, `press`, `evaluate`, and the two that alter the browser's own state), and by
default a run may not perform any of them: it predicts them with a Simulator, or stops and names the one it
would need. ``perform={"click"}`` is how a host says what this engine is allowed to do here. ``AgentBrowser``
follows the same rule over a much larger surface.

Two ways to drive a browser, and they compose:

  - ``BrowserEnvironment`` is this package's own, standard library only. It covers reading a page and acting on
    it — and it has no daemon to leak, because it starts Chrome, does the work, and stops it.
  - ``AgentBrowser`` drives the ``agent-browser`` CLI when a host already has it: accessibility-tree snapshots
    with refs, semantic locators, tabs, cookies, network, console, axe-core audits, Web Vitals, tracing. Not
    reimplemented here, because axe-core and the React DevTools protocol are not things to rewrite.

Put both in one ``CompositeEnvironment`` and the tool set resolves the overlap by name, reporting which source
won each collision — or mark one ``builtin`` and let ``prefer`` decide.
"""
from ti_matrix.adapters.browser.agent_browser import READS as AGENT_BROWSER_READS
from ti_matrix.adapters.browser.agent_browser import AgentBrowser
from ti_matrix.adapters.browser.cdp import BrowserError, CdpError, Chrome, Page, find_browser
from ti_matrix.adapters.browser.environment import BrowserEnvironment
from ti_matrix.adapters.browser.websocket import WebSocket, WebSocketClosed, WebSocketError

__all__ = [
    "AGENT_BROWSER_READS",
    "AgentBrowser",
    "BrowserEnvironment",
    "BrowserError",
    "CdpError",
    "Chrome",
    "Page",
    "WebSocket",
    "WebSocketClosed",
    "WebSocketError",
    "find_browser",
]
