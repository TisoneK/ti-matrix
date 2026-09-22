"""A browser as the engine's world: it reads anything, and changes nothing unless you say so.

The engine performs only the actions an environment marks read-only, and here that boundary is the whole
point. Reading a page — its text, its links, whether a selector matches, a screenshot for a human to look at —
is safe to do on its own. Clicking, typing and running JavaScript are not: a click can post a form, send a
message or buy something, and an agent that may do those without being asked is an agent nobody should point
at their bank. So the seventeen actions below split into eleven reads, which the search performs, and six that
*matter* — `click`, `type`, `press`, `evaluate`, and the two that change the browser's own state — which it
will predict with a Simulator, or stop and name for a person, and never perform by itself.

That default is safe, not crippled. A host that means it grants more::

    BrowserEnvironment("https://example.com", perform={"click", "type"})   # this engine may click here

and `perform` can widen or narrow the reads too. What it cannot do is hide the decision: the resolution is in
the tool specs, the engine reports what it refused, and a run that needed a click says so in its own stop.

Two consequences worth knowing before you wire this in:

  - **Do not put it behind the cache.** ``CachingEnvironment`` remembers a probe whose world has not moved, and
    a page moves constantly; without a version token derived from the page, the second identical probe would be
    answered from the first. Use ``wait_for`` if what you need is the page to settle.
  - **A screenshot is for a person.** The engine's evaluator is a text model, so a screenshot's *fact* is its
    path and size — evidence a human can look at, not knowledge the search can reason over. A multimodal host
    can read the file itself; nothing here pretends a PNG is text.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Optional

from ti_matrix.adapters.browser.cdp import BrowserError, CdpError, Chrome
from ti_matrix.protocols import Action, ActionSpec, Observation

_MAX_OBS = 2600  # an observation the evaluator can see whole (its view is 2800)

# What a run may do to a page unasked. Everything else in the table is a write by nature, and a host has to
# name it in `perform` before the engine will carry it out.
READS = frozenset({"goto", "page_text", "html", "links", "find", "title_and_url", "wait_for",
                   "screenshot", "scroll", "back", "forward"})
_LINKS_SHOWN = 60


def _slug(text: str, *, limit: int = 48) -> str:
    """A filename that says what it is, from a URL or a title."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")
    return (cleaned[:limit] or "page").lower()


def _browser_actions(perform: frozenset[str]) -> dict[str, ActionSpec]:
    """The tool table, with `read_only` decided by what the host allows itself to perform.

    The table below says which actions are writes *by nature* — a click can submit, send or buy — and that is
    documentation for the model as much as anything. What the engine may actually do is `perform`, and only
    the host sets it: an action is read-only exactly when it is in that set.
    """
    specs = [
        # ── reads: performed by the search, on any page ──
        ActionSpec("goto", "Load a URL and wait for it to finish loading.",
                   '{"url": "https://example.com/docs"}'),
        ActionSpec("page_text", "The visible text of the page, or of one element.",
                   '{"selector": "main"}'),
        ActionSpec("html", "The markup of the page or one element, truncated.",
                   '{"selector": "#price", "max_chars": 4000}'),
        ActionSpec("links", "The page's links, as text and href.",
                   '{"limit": 40}'),
        ActionSpec("find", "Whether a CSS selector matches, and what the first match is: its tag, its text, "
                           "its size and where it sits.", '{"selector": "button.buy"}'),
        ActionSpec("title_and_url", "Where this page is and what it is called.", "{}"),
        ActionSpec("wait_for", "Wait until a selector matches — for content that arrives after the load.",
                   '{"selector": ".results", "timeout_ms": 5000}'),
        ActionSpec("screenshot", "Save a PNG of the page for a person to look at. The fact this returns is "
                                 "the file and its size.",
                   '{"full_page": false}'),
        ActionSpec("scroll", "Scroll the viewport.", '{"delta_y": 600}'),
        ActionSpec("back", "Go back in this tab's history.", "{}"),
        ActionSpec("forward", "Go forward in this tab's history.", "{}"),
        # ── actions that change something: declared, and never performed unasked ──
        ActionSpec("click", "Click the middle of an element. This can submit, send or buy.",
                   '{"selector": "button[type=submit]"}', read_only=False),
        ActionSpec("type", "Put text into a field, optionally pressing Enter.",
                   '{"selector": "#search", "text": "hello", "submit": true}', read_only=False),
        ActionSpec("press", "Press one key in whatever has focus.", '{"key": "Enter"}', read_only=False),
        ActionSpec("evaluate", "Run JavaScript in the page. Arbitrary code, so not a read.",
                   '{"expression": "document.title"}', read_only=False),
        ActionSpec("new_tab", "Open a new tab and switch to it.",
                   '{"url": "about:blank"}', read_only=False),
        ActionSpec("close_tab", "Close this tab.", "{}", read_only=False),
    ]
    return {s.name: replace(s, read_only=s.name in perform) for s in specs}


class BrowserEnvironment:
    """Actions on a real browser. Reads run; anything that changes the world waits to be asked.

    ``perform`` names what this run may *do* rather than only reason about, on top of the reads, which are
    always allowed. Pass ``perform={"click"}`` and a click becomes an ordinary action. A name that is not an
    action is ignored rather than silently accepted as one.

    Without arguments each run starts a browser in a throwaway profile and :meth:`close` deletes it. Pass
    ``user_data_dir`` to keep one instead — which is what you want for a site you are signed in to — and it
    becomes yours to look after, because this cleans up only after itself.
    """

    name = "browser"

    def __init__(
        self,
        url: Optional[str] = None,
        *,
        perform: Optional[set[str] | tuple[str, ...]] = None,
        only: Optional[set[str] | tuple[str, ...]] = None,
        chrome: Optional[Chrome] = None,
        binary: Optional[str] = None,
        headless: bool = True,
        attach_to: Optional[str | int] = None,
        user_data_dir: Optional[str | Path] = None,
        screenshot_dir: Optional[str | Path] = None,
        extra_args: tuple[str, ...] = (),
        timeout_s: float = 30.0,
    ) -> None:
        self.start_url = url
        self.timeout_s = timeout_s
        self.screenshot_dir = Path(screenshot_dir).expanduser() if screenshot_dir else None
        self._chrome = chrome
        self._chrome_args = {"binary": binary, "headless": headless, "attach_to": attach_to,
                             "user_data_dir": user_data_dir, "extra_args": extra_args,
                             "timeout_s": timeout_s}
        self._page = None
        self._owns_chrome = chrome is None
        self.perform = frozenset(READS | set(perform or ()))
        self._actions = _browser_actions(self.perform)
        if only:  # every action in the prompt costs a model time on every call, so a host can trim it
            self._actions = {name: spec for name, spec in self._actions.items() if name in set(only)}

    # ── the contract ──

    def tools(self) -> dict[str, ActionSpec]:
        return self._actions

    def is_read_only(self, action: Action) -> Optional[bool]:
        spec = self._actions.get(action.tool)
        return None if spec is None else spec.read_only

    async def probe(self, action: Action) -> Observation:
        if action.tool not in self._actions:
            return Observation(action, False, f"no browser action called {action.tool!r}")
        if not self._actions[action.tool].read_only:
            return Observation(action, False, (
                f"{action.tool} would change the page or the browser, and this environment is not allowed to "
                f"perform it (pass perform={{{action.tool!r}}} to allow it, or confirm it and do it yourself)"))
        try:
            # The protocol is blocking and the engine probes a fan at once; each call takes the page's lock.
            return Observation(action, *await asyncio.to_thread(self._run, action))
        except (CdpError, BrowserError, OSError) as exc:
            return Observation(action, False, f"{type(exc).__name__}: {exc}"[:400])
        except TypeError as exc:
            return Observation(action, False, f"bad arguments for {action.tool}: {exc}")
        except Exception as exc:  # noqa: BLE001 — a failed probe is an observation, never a crash
            return Observation(action, False, f"{type(exc).__name__}: {exc}"[:400])

    def close(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None
        if self._owns_chrome and self._chrome is not None:
            self._chrome.close()
            self._chrome = None

    def __enter__(self) -> "BrowserEnvironment":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── the page, started when it is first needed ──

    def page(self):
        if self._page is None:
            self._chrome = self._chrome or Chrome(**self._chrome_args)
            self._page = self._chrome.page(url=self.start_url)
            if self.start_url and self.start_url != "about:blank":
                # Opening a tab at a URL does not mean the page is there yet. Without this wait the first
                # read races the load and sees an empty document — which on a live site is not a missing
                # answer but a wrong one: "this page has no links" about a page full of them.
                self._page.wait_for_navigation(timeout_s=self.timeout_s)
        return self._page

    def _run(self, action: Action) -> tuple[bool, str]:
        """One action, performed. Raises for a real failure; the caller turns that into an observation."""
        return getattr(self, f"_{action.tool}")(**action.args)

    # ── the reads ──

    def _goto(self, url: str) -> tuple[bool, str]:
        landed = self.page().goto(str(url), timeout_s=self.timeout_s)
        return True, f"loaded {landed} — {self.page().title()}"

    def _page_text(self, selector: Optional[str] = None) -> tuple[bool, str]:
        text = " ".join(self.page().text(selector).split()) if selector else self.page().text()
        return True, text[:_MAX_OBS]

    def _html(self, selector: Optional[str] = None, max_chars: int = 8000) -> tuple[bool, str]:
        return True, self.page().html(selector, max_chars=max(200, min(int(max_chars), 40_000)))

    def _links(self, limit: int = _LINKS_SHOWN) -> tuple[bool, str]:
        found = self.page().links(limit=max(1, min(int(limit), 200)))
        if not found:
            return True, "this page has no links"
        return True, "\n".join(f"- {l.get('text') or '(no text)'} — {l.get('href')}" for l in found)[:_MAX_OBS]

    def _find(self, selector: str) -> tuple[bool, str]:
        found = self.page().find(str(selector))
        if not found:
            return False, f"nothing on this page matches {selector!r}"
        box = found.get("box") or {}
        return True, (f"{found['count']} match(es); the first is <{found['tag']}"
                      f"{'#' + found['id'] if found.get('id') else ''}> "
                      f"at {box.get('w')}x{box.get('h')} ({box.get('x')},{box.get('y')}) — "
                      f"{found.get('text') or '(no text)'}")

    def _title_and_url(self) -> tuple[bool, str]:
        page = self.page()
        return True, f"{page.title()} — {page.url()}"

    def _wait_for(self, selector: str, timeout_ms: int = 5000) -> tuple[bool, str]:
        found = self.page().wait_for(str(selector), timeout_ms=max(50, min(int(timeout_ms), 60_000)))
        return True, f"{selector!r} appeared after waiting: {found.get('text') or '(no text)'}"

    def _screenshot(self, full_page: bool = False) -> tuple[bool, str]:
        page = self.page()
        where = self.screenshot_dir or Path(tempfile.gettempdir()) / "ti-matrix-shots"
        digest = hashlib.sha1(page.url().encode("utf-8")).hexdigest()[:6]
        name = f"{_slug(page.title() or page.url())}-{digest}.png"
        path, width, height = page.screenshot(where / name, full_page=bool(full_page))
        return True, (f"saved a screenshot of {page.url()} to {path} ({width}x{height}) — for a person to "
                      f"look at, since this is a picture and not text")

    def _scroll(self, delta_y: int = 600, delta_x: int = 0) -> tuple[bool, str]:
        self.page().scroll(delta_y=int(delta_y), delta_x=int(delta_x))
        return True, f"scrolled by {delta_y}"

    def _back(self) -> tuple[bool, str]:
        self.page().evaluate("history.back()")
        self.page().wait_for_load(timeout_s=self.timeout_s)
        return True, f"went back to {self.page().url()}"

    def _forward(self) -> tuple[bool, str]:
        self.page().evaluate("history.forward()")
        self.page().wait_for_load(timeout_s=self.timeout_s)
        return True, f"went forward to {self.page().url()}"

    # ── the actions a host has to allow ──
    # They exist so the model can be given them, be judged on them, and be stopped — see the docstring. The
    # guard in `probe` means these only run when `perform` names them.

    def _click(self, selector: str) -> tuple[bool, str]:
        found = self.page().click(str(selector))
        return True, f"clicked <{found['tag']}> {found.get('text') or ''}".strip()

    def _type(self, selector: str, text: str, clear: bool = True, submit: bool = False) -> tuple[bool, str]:
        self.page().type_text(str(selector), str(text), clear=bool(clear), submit=bool(submit))
        return True, f"typed {len(str(text))} character(s) into {selector}" + (" and pressed Enter"
                                                                              if submit else "")

    def _press(self, key: str) -> tuple[bool, str]:
        self.page().press(str(key))
        return True, f"pressed {key}"

    def _evaluate(self, expression: str) -> tuple[bool, str]:
        value = self.page().evaluate(str(expression))
        return True, f"{expression} -> {value}"[:_MAX_OBS]

    def _new_tab(self, url: str = "about:blank") -> tuple[bool, str]:
        self.page()  # a browser has to be running before there is a tab to open
        if self._page is not None:
            self._page.close()
        self._page = self._chrome.page(url=str(url))
        return True, f"opened a new tab at {self._page.url()}"

    def _close_tab(self) -> tuple[bool, str]:
        page = self.page()
        url = page.url()
        page.call("Page.close")
        page.close()
        self._page = None
        return True, f"closed the tab that was on {url}"


__all__ = ["BrowserEnvironment"]
