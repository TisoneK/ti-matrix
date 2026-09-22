"""The engine driving a real browser: read anything, change nothing unless the host says so.

Chrome's DevTools Protocol is JSON over a WebSocket, and neither of those is in the standard library — so the
two files below are the protocol plumbing this project had to own rather than depend on, and the third is the
environment the engine actually sees:

    websocket.py     the opening handshake and the frame format, RFC 6455, no dependencies
    cdp.py           Chrome: start it, find its pages, drive one (navigate, click, type, screenshot, …)
    environment.py   BrowserEnvironment — the actions, and which of them a run may perform unasked

The promise this keeps is the project's own: no runtime dependencies, standard library only. A launch is a
``subprocess`` call, discovery is an HTTP GET, and the protocol rides the socket above.

The promise it makes about safety is the other half. Eleven of the seventeen actions read — text, links, markup,
a selector's presence, a screenshot for a human to look at — and the search performs those freely. Six can
change the world (`click`, `type`, `press`, `evaluate`, and the two that alter the browser's own state), and by
default a run may not perform any of them: it predicts them with a Simulator, or stops and names the one it
would need. ``perform={"click"}`` is how a host says what this engine is allowed to do here.
"""
from ti_matrix.adapters.browser.cdp import BrowserError, CdpError, Chrome, Page, find_browser
from ti_matrix.adapters.browser.environment import BrowserEnvironment
from ti_matrix.adapters.browser.websocket import WebSocket, WebSocketClosed, WebSocketError

__all__ = [
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
