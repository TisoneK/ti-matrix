# Brief — show the page the browser world is actually driving, and what the run saw of it

**Raised by the user, 2026-09-23.** Written by Mara (S004) after checking what already
exists, which is most of it.

> also the browser should show actually what its driving in the ui?

Yes. Today the app can start a real Chrome, drive it for minutes, and show the viewer a
few lines of prose about it. The map panel earns its place in the maze world because it
draws the thing the run is moving through; the browser world has no equivalent and it is
the one world where the "thing" is already a picture.

## Most of this exists — do not rebuild it

- `ti_matrix/adapters/browser/cdp.py` → `screenshot(path, full_page=False)`, over
  `Page.captureScreenshot`. Written, working, standard library only.
- `BrowserEnvironment(..., screenshot_dir=...)` already accepts a directory.
- There is already a `screenshot` **action** the agent can propose, and its `ActionSpec`
  says it plainly: *"Save a PNG of the page for a person to look at."*
- `ti_matrix/adapters/browser/cli.py` already exposes it as `--shots DIR`, and its help
  text already draws the distinction this whole feature turns on: *"they are for you: the
  engine reads text."*

**The gap is one call site.** `server/appserver/worlds.py::_browser_world` constructs
`BrowserEnvironment(url, headless=...)` and never passes `screenshot_dir`. So the app
runs a browser and captures nothing, and there is no panel that would show it if it did.

## The honesty requirement — this is the crux, not a detail

**The agent does not see the page. It reads text.** `page_text`, `html`, `links`, `find`
— every browser probe returns a string. Pixels never reach the proposer or the evaluator.

So a panel that shows a screenshot and nothing else would quietly tell the viewer the
agent saw what they are looking at. That is precisely the unearned trust this product
exists to prevent, and it would be the worst possible place to introduce it — the app's
own headline is *"watch an AI agent think — and check whether to believe it."*

The panel must therefore carry two layers and keep them distinguishable:

1. **The page**, as a person would see it — the screenshot at this cursor position.
2. **What the run actually observed** — the text it extracted, the selector it matched,
   the element it clicked — drawn *over* the shot where a position is known, and listed
   beside it where one is not.

Done properly this is the browser world's best feature, not a nicety: it is the one view
in the app where you can catch the agent missing something that is plainly visible —
a cookie banner it never read, a button it never found, a price rendered in an image.
The maze map shows fog. This shows the gap between what was on screen and what was read.

## Design

**One frame per applied decision, not one per probe.** A fan probes several candidates;
only the selected one becomes state. Capturing every probe multiplies the cost and the
disk for frames nobody scrubs to. Capture after the engine applies a move.

**Frames go on disk beside the run, not inside the artifact.** The run directory already
holds `run.json`, `meta.json` and `events.jsonl` (`app/main/index.ts`); add
`frames/<seq>.jpg`. The event carries the *path*, not the bytes.

That matters: base64 PNGs inside `run.json` would put 100–300KB per step into a file the
main process caps at 64MB and the renderer parses whole on every library open. A 30-step
run would be ~10MB of JSON. JPEG at ~1000px wide keeps a frame to tens of KB, and out of
the artifact entirely it costs the artifact nothing.

**The renderer has no filesystem**, so reading a frame needs a new `window.tm` channel
alongside the existing `runs*` ones — and it must validate the run id and the frame name
against the same strict pattern `runDir()` already applies, then resolve inside the runs
directory before touching anything. The rule there is unchanged: the renderer is never
trusted with a path.

**The panel is a fold over `(events, cursor)`** like every other one — ADR-1. It reads
the frame path from the event at the cursor; scrubbing moves the picture. Nothing about
playback, bookmarks or comparison needs to change, and comparison then gets something
genuinely good for free: two runs of the same goal, side by side, as pictures.

**When there is no frame** — the run predates this, capture failed, the tab had closed —
the panel says which of those it is. An empty frame that looks like a blank page would be
a lie about what the browser was showing.

## Watch out for

- **Headless.** `_browser_world` passes `headless=False` deliberately, so a person can
  watch. Frames must be captured in both modes; headless is the case where this panel is
  the *only* way to see anything, so it is the one to test.
- **Size on disk.** A long run in the library is now frames plus JSON. `tm:run-delete`
  already removes the directory recursively, so deletion is covered — but the library
  row should show the real size, or a user will wonder where their disk went.
- **Secrets on screen.** A screenshot of a logged-in page is a copy of whatever was on it.
  These are already written under the app's own user-data directory, same as everything
  else, and nothing uploads them — but say so in the UI, because "the app took pictures
  of my browser" deserves to be stated rather than discovered.

## Relationship to the existing backlog

This sharpens **B-2026-09-23-2** (the prose worlds' panels are thinner than the views they
replaced) for the browser specifically. Doing this does not close that row — files and
ledger still need their surfaces — but it is the most valuable third of it, and the only
third where the engine has already written the hard part.
