# Architectural Decisions (append-only, ADR-style)

Decisions already made — future agents respect these rather than
relitigating them. To reverse one, append a new ADR that supersedes it.

<!-- TEMPLATE — copy below the last entry:
---
## ADR-N: <short title> (YYYY-MM-DD)
- **Status:** accepted | superseded by ADR-M
- **Context:** <what forced the decision>
- **Decision:** <what was decided>
- **Consequences:** <trade-offs accepted; what future agents must respect>
-->
---
## ADR-1: The renderer is a projection of `(events, cursor)` (2026-09-23)
- **Status:** accepted
- **Context:** The first renderer drew four world views and an event stream, each holding its own state.
  That shape cannot answer the question the app exists for — *what did the agent believe, and where did
  that belief come from* — and it cannot support playback, comparison or scrubbing without replaying a
  recording. It also could not be tested: the views were React components with sockets inside them.
- **Decision:** The run is an event log; a cursor is a decision index; and the map, the tree, the ledger
  and the confidence curve are all pure functions of `(events, cursor)` (`app/renderer/core/project.ts`).
  No panel holds derived state, no panel sees a socket. The renderer has no filesystem, so run artifacts
  are read and written only through `window.tm` channels implemented in the Electron main process, which
  validates every run id before it touches a path.
- **Consequences:** Playback, bookmarks, comparison and the library all fall out of moving one number —
  new panels must be written as folds over events, not as components that keep state. The folds are
  covered by `npm run test` with no test runner. Cost is O(events) per projection per render, which is
  fine for runs of this size and is the first thing to revisit if runs get much longer.
---
## ADR-2: File inspection ships inside `ti_matrix`, and pays for it in standard library (2026-09-23)
- **Status:** accepted
- **Context:** The next feature is duplicate detection across every file family — audio, images,
  video, documents, archives, text — which is a big package. It could have lived under `server/`,
  which already depends on aiohttp and is free to use Pillow, mutagen and pypdf, with the engine
  holding only a thin bridge. **The user chose `ti_matrix` explicitly, so that it ships with the pip
  package**: someone who installs `ti-matrix` and imports it gets the inspector, not a feature that
  only exists inside this repo's desktop app.
- **Decision:** `ti_matrix/adapters/dedupe/` (not `inspect/` — that is a standard library module
  name, and shadowing it inside an engine whose rule is "standard library only" is a trap) — inside
  the engine distribution, and therefore bound by
  `tests/test_boundary.py::test_the_shipped_adapters_are_host_free`: **no third-party imports at all**,
  including deferred ones inside functions. The expensive rung talks to optional external binaries over
  `subprocess` instead of importing a library. This is not a new pattern — `ti_matrix/adapters/browser/`
  already drives a real Chrome this way, with `find_browser` locating the binary, `subprocess` starting
  it and a hand-written `websocket.py` speaking to it, all on the standard library. The root
  `pyproject.toml` states the same rule as intent: *"the engine is standard library only; adapters bring
  their own clients."*
- **Consequences accepted:**
  - **No Pillow, mutagen, numpy, pypdf or pyacoustid.** Container and metadata parsing is hand-written
    with `struct` — proven for ID3v2 in `plans/duplicate-files-spike.py`, and easy for `zipfile`-based
    formats (docx/xlsx/pptx/epub), text, PNG (`zlib` + unfilter) and MP4 atoms.
  - **JPEG pixels are the one genuinely expensive gap.** EXIF is easy (it is TIFF), and payload hashing
    needs no decode, but a baseline JPEG decoder in pure Python is Huffman + IDCT and several hundred
    lines. Do not write it: reach for the optional binary instead.
  - **One optional external binary covers the whole expensive rung.** `ffmpeg` decodes audio, video
    *and* still images, so "is ffmpeg on PATH" is the single capability question rather than one per
    family. Mirror `find_browser` with a `find_decoder`.
  - **Absence is reported, never hidden.** With no decoder present, `perceive` returns a failed
    `Observation` naming the reason, the search settles on payload-hash evidence, and the run says that
    is what it did. A silently skipped probe would make the answer dishonest rather than merely weaker.
  - Pure-Python perceptual hashing is slower than numpy, which is acceptable only because the
    fingerprints are tiny — a 32×32 grid, not a spectrogram. If that stops being true, this ADR is the
    thing to revisit, not the boundary test.
---
## ADR-3: A name reaches the UI only if a stranger can act on it (2026-09-23)
- **Status:** accepted
- **Context:** The user kept finding internal vocabulary on screen, one term at a time: "Context Ledger"
  and "the vault" as a world nobody outside this repo's engineering protocol could read; "sidecar" —
  a deployment-pattern name — as the word for the thing that had stopped; `builtin`, a wire value,
  printed raw in the library's model column beside `deepseek-flash`; "Ledger" naming two unrelated
  things on one screen; and the same event called "retreat" in the tree header and "backtrack" in the
  legend directly below it. Each was found by a person looking at the window, never by a test — the
  typecheck and 149 renderer assertions passed through all of it.
- **Decision:** A name is allowed on screen only if someone who has never seen the codebase can act on
  it. Three questions, in order:
  1. **Did the user choose it or can they change it?** (a world, a model, a goal, a budget, a seed) →
     show it, in their words.
  2. **Must they react to it?** (the engine stopped, a run hit its budget, a probe was refused) → show
     it, and say what to do.
  3. **Does it name how we built it?** (sidecar, adapter, probe, fold, projection, TM1, `builtin`,
     event kinds) → internal. It belongs in code, comments and logs, not in the window.
  The failure mode is not "jargon" — it is **naming the mechanism instead of the thing**. "Sidecar"
  names our process topology; "the engine" names what it does for the person watching. Same process,
  and only one of them is actionable.
- **Consequences:**
  - **One concept, one word, everywhere it appears.** Wire values and event kinds keep their internal
    names (`backtrack`, `builtin`, `ledger`); the UI gets one label, applied through a helper
    (`modelLabel`, `FLAGS[...].label`) rather than by printing the raw value.
  - A raw identifier rendered straight into a cell is the tell. `{m.model}` printed `builtin`; it now
    goes through `modelLabel`. Look for this whenever a wire value meets a template.
  - **Worlds are named for the job, never the mechanism.** "The maze", "Local files", "Real browser"
    are the strongest vocabulary the product has and are the model to follow. The queued work is where
    this will be tested: the file-deduplication world is named for finding duplicates, not for
    `dedupe/`, `inspect/` or hashing; chess is "Chess".
  - **This cannot be tested, so it has to be looked at.** Every instance above survived a green suite.
    A visual pass in the real window is part of finishing a UI change, not an optional extra.
