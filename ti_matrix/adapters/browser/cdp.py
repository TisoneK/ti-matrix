"""Driving a real browser: start Chrome, speak its protocol, and do things on a page.

Two objects. ``Chrome`` is the browser — where it is listening, what pages it has, how to stop it. ``Page``
is one tab and one connection, and its methods are the verbs the environment turns into actions.

Everything here is a thin wrapper over the DevTools Protocol, with no framework in between, because that is
what keeps the promise this project makes about dependencies: a launch is a ``subprocess`` call, discovery is
an HTTP GET, and the protocol itself is JSON over the socket that ``websocket.py`` carries.

Two decisions worth knowing:

  - **Loading is polled, not awaited by event.** Waiting for ``document.readyState == "complete"`` costs one
    round trip per poll and needs no event subscription, no per-domain ``enable``, and no bookkeeping of
    which navigation a load event belonged to. For a single-page app it completes earlier than the content
    appears, which is what ``wait_for(selector)`` is for.
  - **A page that raises is an error here, not an observation.** ``evaluate`` turns a page exception into a
    ``CdpError``; the *environment* above is what turns that into a failed probe the search can use.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Optional

from ti_matrix.adapters.browser.websocket import WebSocket, WebSocketError

_DEFAULT_TIMEOUT_S = 30.0
_POLL_S = 0.05
_MAX_TEXT = 200_000  # a page's text, bounded: an observation is not a download

# Where a browser usually is. A host that has one somewhere else passes `binary=`.
_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

# The keys a text field actually needs. Anything else is dispatched as a bare key code, which is enough to
# be ignored by a page or to work by accident — and the caller can always type the text instead.
_KEYS: dict[str, tuple[int, str, str]] = {
    "Enter": (13, "Enter", "\r"), "Tab": (9, "Tab", "\t"), "Escape": (27, "Escape", ""),
    "Backspace": (8, "Backspace", ""), "Delete": (46, "Delete", ""), " ": (32, "Space", " "),
    "ArrowUp": (38, "ArrowUp", ""), "ArrowDown": (40, "ArrowDown", ""),
    "ArrowLeft": (37, "ArrowLeft", ""), "ArrowRight": (39, "ArrowRight", ""),
    "Home": (36, "Home", ""), "End": (35, "End", ""), "PageUp": (33, "PageUp", ""),
    "PageDown": (34, "PageDown", ""),
}


class BrowserError(RuntimeError):
    """The browser could not be started, reached, or understood."""


class CdpError(BrowserError):
    """The browser understood the command and refused it, or the page raised."""


def find_browser() -> Optional[str]:
    """The first browser on this machine that this adapter knows how to drive, if any."""
    for path in _CANDIDATES:
        if Path(path).is_file() and os.access(path, os.X_OK):
            return path
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):  # last resort: PATH
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(directory) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


class Chrome:
    """A browser to talk to: one this object started, or one already listening somewhere.

    Started with no arguments, it launches headless Chrome in a throwaway profile and stops it on
    :meth:`close` — so a run leaves nothing behind. Pass ``attach_to`` to drive a browser you started
    yourself (``--remote-debugging-port=9222``), which is what you want when you would rather watch it work.
    """

    def __init__(
        self,
        *,
        binary: Optional[str] = None,
        headless: bool = True,
        attach_to: Optional[str | int] = None,
        user_data_dir: Optional[str | Path] = None,
        extra_args: tuple[str, ...] = (),
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self.timeout_s = timeout_s
        self.headless = headless
        self.binary = binary
        self._proc: Optional[subprocess.Popen] = None
        self._profile: Optional[Path] = None
        self._stderr: deque[str] = deque(maxlen=200)
        self._lock = threading.Lock()
        self.host, self.port = "127.0.0.1", 0
        if attach_to is None:
            self._launch(extra_args, user_data_dir)
        else:
            where = str(attach_to)
            self.host, _, port = where.rpartition(":")
            self.host = self.host or "127.0.0.1"
            if not port.isdigit():
                raise BrowserError(f"attach_to wants host:port (or a port), not {where!r}")
            self.port = int(port)
            self._check_reachable()

    # ── starting and stopping ──

    def _launch(self, extra_args: tuple[str, ...], user_data_dir: Optional[str | Path]) -> None:
        self.binary = self.binary or find_browser()
        if not self.binary:
            raise BrowserError("no Chrome or Chromium found — install one, or pass binary=/path/to/chrome")
        self._profile = Path(user_data_dir).expanduser() if user_data_dir else Path(
            tempfile.mkdtemp(prefix="ti-matrix-browser-"))
        args = [
            self.binary, "--remote-debugging-port=0", f"--user-data-dir={self._profile}",
            "--no-first-run", "--no-default-browser-check", "--disable-gpu", "--disable-dev-shm-usage",
            "--disable-background-networking", "--disable-sync", "--mute-audio", "--no-service-autorun",
            *(["--headless"] if self.headless else []), *extra_args, "about:blank",
        ]
        try:
            self._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except OSError as exc:
            raise BrowserError(f"could not start {self.binary}: {exc}") from exc
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        listening = self._await_devtools_url()
        host, _, port = listening.rpartition(":")
        self.host, self.port = host or "127.0.0.1", int(port)
        self._check_reachable()

    def _drain_stderr(self) -> None:
        """Chrome writes its DevTools URL to stderr and will block if nobody reads it."""
        assert self._proc is not None and self._proc.stderr is not None
        for raw in self._proc.stderr:
            self._stderr.append(raw.decode("utf-8", errors="replace").rstrip())

    def _await_devtools_url(self) -> str:
        assert self._proc is not None
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            for line in list(self._stderr):
                if "DevTools listening on ws://" in line:
                    return line.split("DevTools listening on ws://", 1)[1].strip().rstrip("/").split("/")[0]
            if self._proc.poll() is not None:
                raise BrowserError(f"the browser exited at once ({self._proc.returncode}): "
                                   + " | ".join(list(self._stderr)[-3:]))
            time.sleep(_POLL_S)
        raise BrowserError(f"the browser did not report a DevTools URL within {self.timeout_s}s: "
                           + " | ".join(list(self._stderr)[-3:]))

    def _check_reachable(self) -> None:
        try:
            self._get("/json/version")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise BrowserError(f"nothing is speaking DevTools on {self.host}:{self.port}: {exc}") from exc

    def close(self) -> None:
        """Stop the browser this object started, and forget its throwaway profile."""
        with self._lock:
            proc, profile = self._proc, self._profile
            self._proc, self._profile = None, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        if profile is not None and str(profile).startswith(tempfile.gettempdir()):
            _remove_tree(profile)

    def __enter__(self) -> "Chrome":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── what pages it has ──

    def _get(self, path: str) -> Any:
        url = f"http://{self.host}:{self.port}{path}"
        with urllib.request.urlopen(url, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def version(self) -> dict:
        return self._get("/json/version")

    def targets(self) -> list[dict]:
        return self._get("/json/list")

    def pages(self) -> list[dict]:
        """The tabs that can be driven — a page target with a socket of its own."""
        return [t for t in self.targets()
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]

    def page(self, *, url: Optional[str] = None, timeout_s: Optional[float] = None) -> "Page":
        """Connect to a tab: a new one when a URL is given, otherwise the browser's first page."""
        if url is not None:
            return Page(self._open_tab(url)["webSocketDebuggerUrl"], timeout_s=timeout_s or self.timeout_s)
        pages = self.pages()
        if not pages:
            return Page(self._open_tab("about:blank")["webSocketDebuggerUrl"],
                        timeout_s=timeout_s or self.timeout_s)
        return Page(pages[0]["webSocketDebuggerUrl"], timeout_s=timeout_s or self.timeout_s)

    def _open_tab(self, url: str) -> dict:
        """A new tab. Modern Chrome only accepts PUT here, older ones only GET, so both are tried."""
        query = urllib.parse.quote(url, safe="")
        last: Optional[Exception] = None
        for method in ("PUT", "GET"):
            try:
                request = urllib.request.Request(f"http://{self.host}:{self.port}/json/new?{query}",
                                                 method=method)
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    return json.loads(response.read().decode("utf-8"))
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError) as exc:
                last = exc
        raise BrowserError(f"could not open a tab at {url}: {last}")


def _remove_tree(path: Path) -> None:
    try:
        for child in sorted(path.rglob("*"), reverse=True):
            child.unlink(missing_ok=True) if child.is_file() else child.rmdir()
        path.rmdir()
    except OSError:
        pass  # a leftover profile in /tmp is not worth failing a run over


class Page:
    """One tab: commands in, replies out, and the handful of verbs an agent needs.

    Every call is synchronous and takes a lock, because the engine probes a whole fan of actions at once and
    the protocol has one socket with numbered replies — so concurrent actions queue here rather than
    interleave on the wire.
    """

    def __init__(self, websocket_url: str, *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self.websocket_url = websocket_url
        self.timeout_s = timeout_s
        self._ws = WebSocket(websocket_url, timeout_s=timeout_s)
        self._lock = threading.RLock()
        self._next_id = 0

    def call(self, method: str, **params: Any) -> dict:
        """One protocol command, waiting for the reply that matches it (events are skipped)."""
        with self._lock:
            self._next_id += 1
            wanted = self._next_id
            try:
                self._ws.send_text(json.dumps({"id": wanted, "method": method, "params": params}))
            except WebSocketError as exc:
                raise CdpError(f"the connection to the page failed while sending {method}: {exc}") from exc
            deadline = time.monotonic() + self.timeout_s
            while time.monotonic() < deadline:
                try:
                    message = json.loads(self._ws.recv_text())
                except WebSocketError as exc:
                    raise CdpError(f"the page stopped answering {method}: {exc}") from exc
                if message.get("id") != wanted:
                    continue  # an event, or a reply to something already given up on
                if "error" in message:
                    error = message["error"] or {}
                    raise CdpError(f"{method} refused: {error.get('message') or error}")
                return message.get("result") or {}
            raise CdpError(f"{method} did not answer within {self.timeout_s}s")

    def close(self) -> None:
        self._ws.close()

    # ── reading the page ──

    def evaluate(self, expression: str) -> Any:
        """Run one expression in the page and bring back its value. A page exception becomes a CdpError."""
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True,
                           awaitPromise=True, userGesture=True)
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raised = (details.get("exception") or {}).get("description") or details.get("text")
            raise CdpError(f"the page raised: {str(raised).splitlines()[0]}")
        remote = result.get("result") or {}
        if "value" in remote:
            return remote["value"]
        return remote.get("description") or remote.get("type")

    def url(self) -> str:
        return str(self.evaluate("location.href"))

    def title(self) -> str:
        return str(self.evaluate("document.title"))

    def text(self, selector: Optional[str] = None) -> str:
        """The visible text of the page, or of one element. Bounded — an observation is not a download."""
        target = f"document.querySelector({json.dumps(selector)})" if selector else "document.body"
        value = self.evaluate(f"(() => {{ const e = {target}; return e ? (e.innerText || e.textContent || '')"
                              f" : null; }})()")
        if value is None:
            raise CdpError(f"nothing on this page matches {selector!r}")
        text = str(value)
        if len(text) > _MAX_TEXT:
            return text[:_MAX_TEXT] + "\n… (truncated)"
        return text

    def html(self, selector: Optional[str] = None, *, max_chars: int = 20_000) -> str:
        target = f"document.querySelector({json.dumps(selector)})" if selector else "document.documentElement"
        value = self.evaluate(f"(() => {{ const e = {target}; return e ? e.outerHTML : null; }})()")
        if value is None:
            raise CdpError(f"nothing on this page matches {selector!r}")
        text = str(value)
        return text[:max_chars] + ("… (truncated)" if len(text) > max_chars else "")

    def links(self, *, limit: int = 100) -> list[dict]:
        return list(self.evaluate(
            "Array.from(document.querySelectorAll('a[href]')).slice(0, %d).map(a => ({"
            "text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 100),"
            "href: a.href}))" % limit) or [])

    def find(self, selector: str) -> Optional[dict]:
        """Whether a selector matches, and what the first match is: its box, its tag, its text."""
        return self.evaluate(
            "(() => { const all = document.querySelectorAll(%s); if (!all.length) return null;"
            "  const e = all[0], r = e.getBoundingClientRect();"
            "  return {count: all.length, tag: e.tagName.toLowerCase(), id: e.id || '',"
            "    text: (e.innerText || e.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200),"
            "    box: {x: r.left + r.width / 2, y: r.top + r.height / 2, w: Math.round(r.width),"
            "          h: Math.round(r.height)}}; })()" % json.dumps(selector))

    def wait_for(self, selector: str, *, timeout_ms: int = 5000) -> dict:
        """Wait until a selector matches, and return what it found — the tool for anything dynamic."""
        deadline = time.monotonic() + max(1, timeout_ms) / 1000
        while True:
            found = self.find(selector)
            if found:
                return found
            if time.monotonic() >= deadline:
                raise CdpError(f"nothing matched {selector!r} within {timeout_ms} ms")
            time.sleep(_POLL_S)

    def wait_for_load(self, *, timeout_s: Optional[float] = None) -> None:
        deadline = time.monotonic() + (timeout_s or self.timeout_s)
        while True:
            try:
                if self.evaluate("document.readyState") == "complete":
                    return
            except CdpError:
                pass  # mid-navigation the execution context can vanish for a moment; ask again
            if time.monotonic() >= deadline:
                raise CdpError("the page did not finish loading")
            time.sleep(_POLL_S)

    # ── changing the page ──

    def goto(self, url: str, *, timeout_s: Optional[float] = None) -> str:
        result = self.call("Page.navigate", url=url)
        if result.get("errorText"):
            raise CdpError(f"could not navigate to {url}: {result['errorText']}")
        self.wait_for_load(timeout_s=timeout_s)
        return self.url()

    def click(self, selector: str, *, timeout_ms: int = 5000) -> dict:
        """Click the middle of an element with real mouse events, so pages listening for them hear it."""
        found = self.wait_for(selector, timeout_ms=timeout_ms)
        self.evaluate(f"document.querySelector({json.dumps(selector)}).scrollIntoView({{block: 'center'}})")
        found = self.find(selector) or found  # the box again, once it is on screen
        x, y = float(found["box"]["x"]), float(found["box"]["y"])
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left",
                      buttons=1 if kind == "mousePressed" else 0, clickCount=1 if kind != "mouseMoved" else 0)
        return found

    def type_text(self, selector: str, text: str, *, clear: bool = True, submit: bool = False) -> None:
        """Focus a field and put text in it, then optionally press Enter."""
        self.wait_for(selector)
        if clear:
            self.evaluate(f"(() => {{ const e = document.querySelector({json.dumps(selector)});"
                          f" e.focus(); if ('value' in e) e.value = ''; }})()")
        else:
            self.evaluate(f"document.querySelector({json.dumps(selector)}).focus()")
        self.call("Input.insertText", text=text)
        if submit:
            self.press("Enter")

    def press(self, key: str) -> None:
        """One keystroke, dispatched the way a keyboard does it: down, the character, up."""
        code, name, text = _KEYS.get(key, (ord(key[0]) if key else 0, key, key if len(key) == 1 else ""))
        common = {"key": name, "code": name, "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code}
        self.call("Input.dispatchKeyEvent", type="rawKeyDown", **common)
        if text:
            self.call("Input.dispatchKeyEvent", type="char", text=text, **common)
        self.call("Input.dispatchKeyEvent", type="keyUp", **common)

    def scroll(self, *, delta_x: int = 0, delta_y: int = 600) -> None:
        self.call("Input.dispatchMouseEvent", type="mouseWheel", x=10, y=10,
                  deltaX=delta_x, deltaY=delta_y, button="none", buttons=0)

    def screenshot(self, path: str | Path, *, full_page: bool = False) -> tuple[Path, int, int]:
        """Write a PNG and say what size it is — the one thing here a text-only model cannot read itself."""
        result = self.call("Page.captureScreenshot", format="png", captureBeyondViewport=full_page)
        data = result.get("data")
        if not data:
            raise CdpError("the browser returned no screenshot data")
        metrics = self.call("Page.getLayoutMetrics")
        viewport = metrics.get("cssLayoutViewport") or metrics.get("layoutViewport") or {}
        width, height = int(viewport.get("clientWidth") or 0), int(viewport.get("clientHeight") or 0)
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(data))
        return target, width, height


__all__ = ["BrowserError", "CdpError", "Chrome", "Page", "find_browser"]
