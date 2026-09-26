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
---
## ADR-4: A world is probed from a state, concurrently — what that forces on every world (2026-09-23)
- **Status:** accepted
- **Context:** Before opening worlds up to users, the contract a world must satisfy has to be written
  down, because it is not obvious from the `Environment` protocol and the project keeps getting it
  wrong. The protocol looks trivial — `name`, `tools()`, `probe()`, `is_read_only()` — and reads like
  "answer these calls". The engine does something stricter than that:

  ```python
  timed = await asyncio.gather(*(self._probe(m, predicted.get(m.fingerprint())) for m in runnable))
  ```

  Every candidate in a fan is probed **concurrently, from one state, before any of them is applied**.
  Most are then discarded. The maze was built for this and says so in its own docstring — *"a fan is
  probed all at once, so anything a probe could clobber would come back wrong — a `goto` sharing a fan
  has exactly that problem"* — and the browser world, which holds one page and one current URL, has
  precisely the named problem and shipped anyway.
- **Decision:** Four rules, and they are the contract a custom world is held to as much as a shipped one.
  1. **An action carries its own position; the world holds no cursor the engine can disturb.**
     `step(cell, direction)` names where it starts from. `move(fen, "e2e4")` would name the position.
     `next()` advancing an internal pointer is broken here, and will look like the model hallucinating
     rather than like the world misbehaving — which is the expensive kind of bug.
  2. **What a world remembers only ever grows.** The maze's `_seen` is a monotonic set: a sibling probe
     cannot clobber it, and growing it on a probe nobody selected is not a leak, because the engine
     already treats a real observation from an unselected probe as a fact (`AgentState.learn`).
  3. **`probe` returns an `Observation`, never raises.** A failed probe is information the search uses —
     bad arguments, a refusal, a missing file are all things a run should be able to learn from and
     route around. An exception is a crashed run.
  4. **`read_only` is the safety boundary, and it is the world's own declaration.** An action that is
     not read-only is never performed speculatively: it is predicted by a Simulator, or surfaced to a
     Confirmer, or named and skipped. A world that quietly mutates inside a "read" has broken the one
     guarantee the fan depends on.
- **Consequences:**
  - **The observation's text is the interface.** Facts are strings — `"label -> ok: <text>"` — and that
    is all the engine, the model and the rule-based seats ever see. `MazeKnowledge` and `FilesReasoner`
    both parse those strings back. So a world author's real work is writing observation text that is
    stable, parseable and complete enough to act on; a pretty message that omits the cell id is a world
    nothing can reason about.
  - Concurrency is not theoretical, and the damage is not a stale cursor. Demonstrated on the shipped
    browser world: probing `goto(example.com)` and `goto(iana.org)` in one fan returned **"loaded
    https://www.iana.org/..." for both**, so the fact recorded against the first action names a page it
    never visited. Rule 1 is not hygiene — breaking it writes false facts into the state, and a false
    fact is the one thing an app built on "check whether to believe it" cannot survive. B-2026-09-23-10.
  - Any custom-world mechanism must state these four rules in its own documentation, and should make
    rule 1 hard to get wrong rather than merely documented.
---
## ADR-5: A fact is true *as of* a moment, and a run may end because it could not keep up (2026-09-24)
- **Status:** accepted — the contract below. The mechanism (declared vs measured staleness) is
  deliberately left open and is the open question in
  `plans/a-world-that-moves-brief.md`.
- **Context:** Every shipped world holds still. The maze does not move, a filesystem does not change
  mid-run, chess waits its turn. So the loop's assumption has never been tested: **observe → the state
  is true → decide → act**. A live market breaks the link between observe and act — the fact was true
  when it was probed and is false when it is applied — and the same is true, less dramatically, of a
  file being written while a directory is read, a page that reloads, or a ledger another agent is
  editing. The still worlds are the unusual ones.

  The engine already measures the time. `EngineEvent.t_ms` stamps every event and every probe records
  its own duration. What it does not do is *keep* it: `AgentState.facts` is a tuple of bare strings, so
  the state knows what it learned and never when. The within-run memory shipped in `76a0590` inherits
  the same blindness — `recall` returns a fact from forty seconds ago with exactly the confidence of
  one from now.
- **Decision:**
  1. **A fact carries the moment it was observed.** The state gains a clock. The engine's own claim is
     that everything it knows is a state; a state with no time cannot say when its knowledge stopped
     being knowledge.
  2. **"The agent adapts" means exactly one of three things, and nothing else counts.** Re-check the
     fact a decision rests on at the moment of acting; narrow the fan, trading breadth for freshness;
     or stop and say the information was too old. Anything that cannot be named as one of these is not
     a feature, it is a mood.
  3. **Ending because the world moves faster than the run can decide is a success, not a failure.** It
     joins `budget`, `no_moves` and `no_progress` as an honest ending. A version of this that always
     found a way to act would be a bug: 400ms of round-trip against a one-second tick is workable and
     against a hundred-millisecond tick is not, and no amount of noticing changes the physics.
  4. **Staleness is the same category of caveat as `predicted`.** A predicted outcome is already never
     learned as a fact. An aged fact is a fact that has stopped being one, and it should be marked in
     the record the same way rather than silently trusted.
  5. **Staleness belongs to the fact, not to the world** — *added the same day, see the amendment.*
- **Amendment (2026-09-24, same day, sharpening clause 5 — not a reversal):** the first draft of this
  decision and its brief treated "the world moves" as one property with one rate. A world does not have
  a rate. It has several at once, and the user's correction is the cleanest statement of it: *the world
  rotates and revolves.* Two motions, both real, orders of magnitude apart, running simultaneously.

  On the page that prompted this, all of these are facts about one world:

  | fact | good for |
  |---|---|
  | the last digit | about a second |
  | the digit frequencies | tens of seconds |
  | the account balance | until a trade settles |
  | which symbols exist | hours |

  A single shelf life is wrong in both directions at once: re-probe everything at the fastest rate and
  the budget is gone on facts that never move, or trust everything at the slowest and act on a price
  from a minute ago. **The rate is a property of the observation, not of the environment**, which also
  makes it measurable — "did *this* action's answer change between two probes" is a real question, where
  "how volatile is this world" is not.

  Two further consequences of taking the metaphor seriously:

  - **Some change is periodic, not drift.** A page that polls on a timer, a market session, a job on a
    schedule. A run that measured a period could time itself against it instead of racing it. Out of
    scope for a first pass; recorded so nobody designs it out.
  - **You do not feel the Earth turn.** A fact goes stale with no signal — no error, no exception, just
    a belief that quietly stopped being true. That is exactly the browser false-facts bug fixed in
    `9daf9a4`, and it is the argument for measuring rather than trusting a declaration.
- **Consequences:**
  - `AgentState` is engine core, under `test_boundary` and 278 tests. Prefer an **additive** shape —
    the observation times alongside the facts — over changing `facts` itself, because every reader in
    the repo parses that tuple (`render`, `to_dict`, `MazeKnowledge`, `FilesReasoner`,
    `BrowserReasoner`, `ChessReasoner`, `RunMemory`) and worlds are about to open to users. The same
    reasoning that made `Counting` optional rather than a protocol change applies here.
  - **`recall` must say how old.** In a still world the within-run memory is right to be append-only;
    in a moving one, handing back an old reading unqualified is the engine asserting something it has
    no evidence for.
  - The browser world's fan race, fixed in `9daf9a4`, was this same problem *inside* a single fan —
    two navigations, one page, observations about a world that had already moved. That was fixed by
    making each observation name its own page. This is the across-steps version, and the fix has the
    same shape: say what the observation is about, including when.
  - A world that moves also makes the **maze and chess the unrepresentative cases**. Any future claim
    that the engine "handles a world" should say which kind.
