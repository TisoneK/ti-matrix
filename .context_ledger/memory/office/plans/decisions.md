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
