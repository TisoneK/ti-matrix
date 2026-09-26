# Agent Sessions (append-only within the current office)

One entry per agent session in the **current office**, newest at the bottom.
Never edit or delete past entries — append corrections instead. This is not
append-only *forever*: when the office reaches `office_size` sessions (or a
milestone), `ledger-history close` freezes this whole office verbatim into
`.context_ledger/history/office-<NNN>/` (roster, registry, notes, logs —
nothing trimmed), writes the permanent accomplishments record
`.context_ledger/history/office-<NNN>.md`, and opens a fresh empty office
here. Closed offices in `history/` and `archive/` are never read at session
start. Before closing, note which open threads still matter — they are
re-seeded into the new office explicitly, and nothing else carries over.

<!-- TEMPLATE — copy below the last entry and FILL IN every placeholder:
---
## YYYY-MM-DD — Session N
- **Agent:** <name> | **Model:** <model id> | **Platform:** <machine/sandbox + OS> | **Role:** <engineer, or overlay from .context_ledger/core/roles/> | **Core:** <version from .context_ledger/core/VERSION>
- **Task:** <what this session set out to do>
- **Commits:** <count> (<first-sha>..<last-sha>)
- **Outcome:** <done / partial / blocked — one line>
- **Open items:** <pointers into tasks/backlog.md (actionable) or tasks/parking-lot.md (findings/questions), or "none">
- **Notes:** .context_ledger/memory/office/sessions/<date>-<N>/notes.md  (or "none")
- **Report:** .context_ledger/memory/office/reviews/YYYY-MM-DD-review.md
-->

---
## 2026-09-23 — Session 1 (bootstrap + the desktop app's skeleton)
- **Agent:** Buffy | **Model:** unknown | **Platform:** Lameck — Windows, Git Bash | **Role:** engineer | **Core:** 2.0.4
- **Task:** bootstrap `.context_ledger/` from the package clone (`sh ../context-ledger/core/bin/ledger-sync bootstrap .`) and fill the memory skeleton; then build the desktop-app skeleton per the approved plan — `server/` (the `ti-matrix-server` sidecar: TM1 protocol, event streaming, WS confirmer, world registry, seeded scenario generator, 33 tests) and `app/` (Electron main with sidecar lifecycle, minimal preload, React run-inspector with the confirmer dialog; typecheck + Vite build + subprocess smoke green) — and the CI matrix (pytest 3.10–3.13 × 3 OS, both wheels, PyInstaller sidecar, electron-builder artifacts)
- **Commits:** 3, pushed (48190e7 project surface — server/, app/, CI, .gitignore; e16237d ledger bootstrap; 2fa0699 merge with four remote commits that arrived mid-push, .gitignore conflict resolved, both suites re-verified after)
- **Outcome:** done and pushed — the `ti_matrix` wheel untouched (197 passed, 2 skipped before the merge; 204 passed, 2 skipped after integrating the remote's engine changes), sidecar suite 33 passed, app typecheck green
- **Open items:** `npm run dev:electron` not yet run against a live window (needs the user at the keyboard); PyInstaller bundle not yet built locally; codesigning/notarization and auto-update deliberately deferred; ledger write-back checkbox exists but is only exercised by unit tests
- **Notes:** none
- **Report:** none
---
## 2026-09-23 — Session 3 (the app UI, rebuilt from the ground up)
- **Agent:** Nadia | **Model:** deepseek-flash | **Platform:** bao's Mac — macOS (darwin 24.6.0), Node 24.17.0, Python 3.10.20 (.venv) | **Role:** engineer | **Core:** 2.0.4
- **Task:** discard the renderer and rebuild it as a visualization-first run inspector — a fog-of-war map drawn only from what a run observed, the search tree, a ledger of every decision with the belief behind it, playback (scrub/step/speed/bookmarks over one cursor), comparison of two runs, a persisted session library, and config demoted to a collapsible drawer
- **Commits:** 1 product commit (`7348350` — the renderer rebuild, the new `tm.runs*` IPC in `app/main` + `app/preload`, the docs) plus ledger commits (`bb09e33` check-in, `888895a` peer merge, `c260f95` STATE, and the closing memory commit)
- **Outcome:** done and pushed — typecheck green, 129 renderer assertions, engine 207 passed, sidecar 34 passed, Vite build green; a real run driven end to end in a browser harness against the real sidecar (102 events, 14 decisions, 6 retreats) and 11 defects found on screen and fixed (two pane-nesting layout bugs, two accessibility bugs, the map legend, the missing way back from a rewound finished run, a knowledge-precedence bug where an inferred wall erased a known corridor). **Follow-up, same session:** the rail became the window's title bar (macOS keeps its traffic lights; every other platform gets the rail's own controls over new `tm:window-*` channels) — and launching the real Electron window to check it found that the library IPC handlers had never been registered, a bug the stubbed harness had hidden. Fixed and verified in the real window; `main` fast-forwarded to this branch per the standing push policy. **Third pass, same session:** two real runs against the DeepSeek API through the app's own window (6 decisions/3m29s, then 10/6m37s after the fix below), which exposed that the window never sent a run budget — the goal frame always accepted one — so every real run stopped at the engine's default depth of six with nothing on screen to change it; the budget is now four fields in the config drawer and the second run passed the old ceiling. Both runs are saved in the library with real numbers
- **Open items:** B-2026-09-23-1 (no real Electron window was launched — the renderer was driven with `window.tm` stubbed), B-2026-09-23-2 (the prose worlds' panels are thinner than the views they replaced), B-2026-09-23-3 (no run against a real LLM yet)
- **Collaboration:** light path with the peer on the board (Wren, S002, idle on `main`): session `S003`, issue `ui-rebuild`, a `note` and a `claim` at start, a `release` citing `7348350` at close (events under `memory/collaboration/events/`). No agreement was needed — the scopes never overlapped.
- **Notes:** .context_ledger/memory/office/sessions/2026-09-23-3/notes.md — the browser-harness recipe that made the visual checks possible without a window, and the order of work that fit it in one session
- **Report:** .context_ledger/memory/office/reviews/2026-09-23-review-2.md

---
## 2026-09-23 — Session 4 (making the window actually run something, then fixing the rail)
- **Agent:** Mara | **Model:** claude-opus-5 | **Platform:** bao's Mac — macOS (darwin 24.6.0), Node 24.17.0, Python 3.10.20 (.venv) | **Role:** engineer | **Core:** 2.0.4
- **Task:** the user's report that the app is "a beautiful system that does nothing" — UI and backend detached, "sidecar gone", nothing observable. Then, mid-session, that the top-right nav buttons were "misfunctioning eg opening something else", and then that no UI *improvement* had been done — only bug fixing.
- **Commits:** 4 product commits (`2de25ce`, `09adcff`, `b835821`, `a8e8e15`) plus ledger commits (check-in, STATE, this close)
- **Outcome:** done — both reports fixed and verified in the real window. See *Not pushed to main* below.

### What was actually wrong (report 1)

Not the sidecar. It spawned, handshook and answered `/healthz` in every launch of this
session. Two separate faults were being read as one:

1. **No run could produce events.** The engine's proposer and evaluator seats only ever held
   `LLMMoveProposer`/`LLMEvaluator`, so every run needed a reachable OpenAI-compatible endpoint —
   and the app shipped defaulting to `qwen2.5:7b` on a local Ollama. Reproduced over the real
   socket: 2 events, `stopped: proposer_error: 404 model 'qwen2.5:7b' not found`. Every panel then
   drew its empty state correctly; there was genuinely nothing to draw.
2. **"sidecar gone" was the renderer's own word for a socket with no retry.** `Sidecar.connect`
   set `crashed` on the first close and never tried again.

This is *not* only a missing-model problem. Verified against a real local `phi4-mini:latest`: one
proposer call took 48s and returned moves naming cell `0,0` (a wall), the evaluator scored a
successful `entry()` probe at 0.0, and the run stopped at 9 events on `no_progress`. Logged as
B-2026-09-23-5; deliberately not fixed here.

**Fixed:** `ti_matrix/adapters/builtin.py` — the two seats filled by rules (`MazeReasoner` walks the
frontier from the run's own facts; `SurveyReasoner` is the generic fallback), selected by
`model: "builtin"`, now the default, with its own larger budget. Settings migrate the old default
pair once. Socket reconnects (8 attempts, 400ms→6s, a `reconnecting` status); a sidecar that exited
turns Run into **Reconnect**, which respawns the child under the same window via a new
`tm:sidecar-restart`. Also: `tm:connection` hung forever on a failed boot instead of rejecting, the
sidecar-exit listener stacked one handler per effect run, and a browser tab with no preload was
told to "restart the app" it was not inside.

### What was actually wrong (report 2 — the rail)

The view and the setup sheet are not independent — the sheet is only drawn on the run view
(`configOpen && view !== "compare"`) — but they were two `useState` calls updated by two handlers
that did not know about each other. `config` pressed on Compare flipped the caret to ▴, set
`configOpen` true and rendered nothing; the state then sat there until the next view change, so
pressing **Run** opened the setup sheet. A button that does nothing and a button that does
something else were one bug seen one click apart.

**Fixed:** the transition is now a pure function of (where you are, what you pressed) in
`app/renderer/core/nav.ts`. Also in the same area: bare-letter shortcuts (`l`, `c`) fired behind the
confirmer, which blocks a run and must be answered — they now stand down while the confirmer, the
sheet or the welcome is up. And the rail's five readouts described a run that was not there
(`step — · progress 0% · elapsed 0ms` above an empty run view, and above Compare, where there are
two runs and no single answer to "step"); they now appear only when there is something to measure.

### The welcome screen (report 3)

The user's standing critique from before this session: the first screen is a flat card
grid — three identical numbered boxes — making the claim "watch it think" in prose with
no evidence of what it looks like, in one accent blue. Their own suggested fix was text
on one side and a muted ghost preview of the real Map/Tree/Ledger on the other, with the
steps as a thin numbered list over it. That is what `b835821` builds.

The preview's flag glyph paths are imported from `core/flags` rather than redrawn, so the
illustration cannot drift from what a live run draws — and the run's palette (green held,
red refused, violet retreated, amber a hunch) is on screen before the first run instead of
after it. It is `aria-hidden`, has no focusable children and takes no pointer events: it is
a picture of the product, not the product.

One thing worth remembering for any future small-scale map drawing: at 12px cells the map
needs *three* distinguishable weights plus a hairline on the walls. Without the hairline the
panel renders as a black rectangle with a line through it — the maze stops reading as a maze.

### The wordmark, and the bug it found (report 4)

"TiMatrix should display as one but Ti to have different color than Matrix." One
`Wordmark` component for the rail and the welcome, the same markup hand-written in
`splash.html` (plain HTML, cannot import it). Mixed case, not uppercased — uppercased
the halves run together into TIMATRIX and only colour distinguishes them.

Screenshotting the run view to check it caught a bug I had shipped one commit earlier:
the welcome's preview container took the bare class `.ghost`, which also matches
`.btn.ghost` — the modifier every `IconButton` in the app carries. For the length of
`b835821`, every icon button in the window inherited `width: 100%`, `overflow: hidden`
and `pointer-events: none`. The map's zoom controls wrapped out of their toolbar and
**the whole transport bar was unclickable**. Fixed in `a8e8e15` by scoping to
`.ghost-run`.

**Worth carrying forward:** this repo's stylesheet is one flat global file with short,
generic, meaning-bearing class names (`.ghost`, `.pick`, `.row`, `.tab`, `.mark`,
`.spacer`). A new bare single-word class is a live collision risk every time, and the
typecheck and all 168 renderer assertions passed while the transport was dead — none
of them render CSS. Prefix new component classes, and look at the surface in a real
window before calling a visual change done.

### Verification

Driven in the real Electron window over the Chrome DevTools Protocol with dispatched mouse and key
events — not `.click()`, and not a stubbed `window.tm` (which is what open item B-2026-09-23-1 was
about). A run end to end: 31/31 steps, 100% coverage, 39 cells, 1 retreat, 31 decisions, 85ms,
saved to the library. Then the sidecar killed mid-session — the window reported "the engine exited
(code signal)", Reconnect pressed, fresh child spawned, another run completed (33/33, 193ms). For
the rail: each tab lands on its own view; config from Compare lands on Run with the sheet actually
open; sheet open on Run → Compare → Run leaves it closed; `c` switches views normally but not with
the sheet up; the readouts disappear on Compare and return on a run.

- **Tests:** 225 engine (18 new, `tests/test_builtin_reasoner.py`), 36 sidecar (2 new), 168 renderer (39 new — `app/renderer/protocol.test.ts`, `app/renderer/core/nav.test.ts`), typecheck green, `pre-commit` gate passed before both commits. `test_boundary` caught the reasoner sitting in engine core on the first attempt and it was moved under `adapters/` where it belongs — the dependency runs adapter → engine, and a reasoner that knows the maze's vocabulary is the same kind of thing as the maze.
- **Pushed to main:** per the standing push policy, `origin/main` was fast-forwarded to this branch at the user's go-ahead — both refs are at `7fabe60`. The sandbox classifier blocked `git push origin app-ui-rebuild:main` on the first two attempts mid-session; it succeeded on retry. Note for the next session: a blocked push here is a *local* permission refusal, not an auth failure — git uses the `osxkeychain` helper and is authenticated independently of the `gh` CLI, which is currently signed out and was never the cause.
- **Open items:** B-2026-09-23-5 (the endpoint-backed path is weak on small models — the proposer never sees which cells the run has entered, and a run whose first probe succeeds can still stop on `no_progress` at depth 0), B-2026-09-23-2 (the prose worlds' panels), B-2026-09-23-3 (a run against a large hosted model — session 3's DeepSeek runs stand; this session only drove a small local one)
- **Notes:** .context_ledger/memory/office/sessions/2026-09-23-4/notes.md — driving the real Electron window over CDP, and the persisted-default trap that no test could see
- **Report:** none (not a review task)

---
## 2026-09-25 — Session 5 (civilization-world question, then step 1 of the moving-world contract)
- **Agent:** Marlowe | **Model:** claude-sonnet-5 | **Platform:** bao's Mac — macOS (darwin 24.6.0) | **Role:** engineer | **Core:** 2.0.4
- **Task:** started advisory — user asked "should we build civilization worlds?" (a Civ-style world: cities, tech trees, diplomacy, long time horizons, as a new `Environment`) and then "which worlds should we build as a foundation for this system?" Checked in, merged a large batch of remote history the local clone hadn't seen (chess world, ADR-5/world-that-moves, within-run recall, browser/rail/welcome fixes — S002 Wren through S004 Mara), oriented from `STATE.md` and the four shipped-worlds contract (ADR-4), answered both questions, then — asked to "continue building it," confirmed via `AskUserQuestion` as the moving-world foundation — implemented **step 1 of B-2026-09-24-2** (report staleness, spend no probes) per `a-world-that-moves-brief.md`.
- **Commits:** 5, pushed. Ledger-only: merge commit resolving a roster.md conflict (kept Wren's S002 row, added this session's row), `chore(ledger): regenerate STATE.md at check-in`, `chore(ledger): park the civilization-world question (P-2026-09-25-1)`, `chore(ledger): Marlowe (S005) clocks out` (later extended — see below), `chore(ledger): Marlowe (S005) checks back in`. Product: `6cb8e73` "A fact carries the moment it was observed" — `ti_matrix/state.py` (`AgentState.fact_times`, threaded through `apply`/`learn`/`retreat_to`, surfaced in `to_dict()` as `fact_ages_ms`), `ti_matrix/search.py` (per-probe `observed_at` timing, `fact_ages_ms` on `stopped`/`needs_action` events), `ti_matrix/tools/engine_tools.py` (`RunMemory` ages every `recall` line), plus 7 new tests in `tests/test_engine.py` and `tests/test_builtin_reasoner.py`.
- **Outcome:** done and pushed. Advisory: leaned toward not shipping civilization as a fifth first-party world yet (too large a scope jump from maze/chess/files/browser; better as the flagship example for bring-your-own-world, B-2026-09-23-11, once that loader ships) and toward proving the moving-world and structural-recall contracts on something small first. Code: step 1 of B-2026-09-24-2 shipped — purely additive and diagnostic, no reader of `facts` had to change, no new stop reason, no re-probing. **Caught by the repo's own boundary test on the first pass**: `test_the_engine_core_cites_no_external_record_system` failed because my first draft's comments cited "ADR-5" directly inside the pip-shipped engine core — fixed by rewriting those comments in self-contained prose. All gates green: pre-commit, integration (321 tests), exit (284 tests, typecheck, app build).
- **Open items:** B-2026-09-24-2 updated in place with what step 1 shipped and what's still open (declared-vs-measured per-action shelf life was NOT added; steps 2/3; "prefer the slow facts"; a fast-but-free test world for the suite). P-2026-09-25-1 (civilization worlds) still parked, no owner. Existing backlog otherwise untouched (B-2026-09-23-6/7/11/12, B-2026-09-24-3).
- **Notes:** none
- **Report:** none (not a review task)

---
## 2026-09-25 — Session 6 (model balance / token-usage tracking, then run the worlds)
- **Agent:** Sable | **Model:** claude-sonnet-5 | **Platform:** bao's Mac — macOS (darwin 24.6.0) | **Role:** engineer | **Core:** 2.0.4
- **Task:** user asked to implement model balance tracking and token usage staging first, then try running the shipped worlds end to end and fixing what surfaces.
- **Commits:** 4 product so far, pushed — `eeafb8e` (`OpenAICompatModel` gains `usage_snapshot()`, `fetch_balance()`/`describe_balance()` for DeepSeek's `/user/balance`, 11 new tests), `f3cacec` (the sidecar's `settled` frame carries a hosted run's `usage`, omitted rather than zeroed for `builtin` or a provider that sends none), `3f3d89d` (the app's top rail shows a `tokens` readout once a run settles with something to report), `151606e` (`Session.seats()` routes `files_cli`/`ledger_cli`/`browser/cli` through the builtin reasoner for `--model builtin` — B-2026-09-24-3, previously all three built a live `OpenAICompatModel` regardless and `--model builtin` still dialled nothing; plus `--root` for `files_cli` since the reasoner cannot invent a starting path the way a real model can, and `--balance`/a usage note on all three).
- **Outcome:** in progress — all four gates (pre-commit, integration, exit) green after each commit. **Found live, not from a report:** `ledger_cli` crashed on every invocation before this session — `Session(..., ask=a.ask)` referenced an argument `_args()` never defines (the CLI deliberately has no `--ask`; its own comment says why). Fixed alongside the builtin routing. Verified all four shipped worlds end to end with the builtin reasoner and no crashes: maze (existing sidecar test), files (real read against this repo, needs `--root`), ledger (read-only against this project's own `.context_ledger/`, stops honestly `no_moves` — `SurveyReasoner` has no synthesizer), chess (real python-chess opponent, several moves played, stops `budget`), browser (real headless Chrome against a static page, stops `no_moves`). None of these are bugs — builtin never gets a synthesizer, so a rule-driven run that does not hit an evaluator's `done` reports facts and no answer rather than inventing one, same as a hosted run would.
- **Verified live:** the user supplied a real DeepSeek key (from their separate `LocalMind` project's own settings, copied into this project's `secrets/`, never committed or printed) and `files_cli --model deepseek-chat --balance` ran a real goal end to end against the live API — settled in 2 model calls, real usage (1061+320=1381 tokens) and real balance ($1.89 USD) both reported correctly. Confirms stage 1 works outside the fake test endpoint.
- **Then the user ran the app themselves and hit two real bugs**, both found by driving the actual running `npm run dev` window over its own CDP endpoint (`--remote-debugging-port`, real `Input.dispatchMouseEvent`/`Runtime.evaluate` — not a stub) rather than guessing from a description:
  1. **No paste in any text field** (`ad2b7bb`). Electron draws no context menu of its own and this app never wired one up, so right-click did nothing. Added `attachEditContextMenu` in `app/main/index.ts` — Cut/Copy/Paste/Select All, gated on `params.isEditable`/`editFlags`.
  2. **"The app that does nothing" recurred, different cause this time** (`bdfa52a`). Reproduced exactly: pick "A language model", leave Model blank, type a goal, hit Run. The sidecar rejects the config before `engine.run()` starts (a bare `error` frame, zero events). `App.tsx`'s `lamp` checked `events.length === 0` *before* `done.error`, so the one case that most needed to say something rendered nothing — no message, every panel still idle, identical to never having clicked. Reordered the check (shows the real message now) and added a client-side guard: Run disables with "type a model name (or switch to Built-in rules)" before the bad config ever reaches the sidecar. Verified both the before (silent) and after (button disabled with the real reason) states live over CDP with screenshots.
- **The user then asked for the models to auto-fetch** ("just selects a model" instead of typing one from memory) — shipped (`1f7677e`): `OpenAICompatModel.list_models()` (`GET /models`), a `list-models`/`models`/`models-error` TM1 frame trio independent of `RunState`, and the config drawer debounces field changes and offers a quick-pick `<select>` beside Model once the endpoint answers. Verified against the real DeepSeek account: real base URL + real key produced the account's actual two models in the dropdown, and picking one filled the field.
- **The user then asked, bluntly, whether any of this had actually been clicked and watched** — drove a full builtin maze run over CDP live and sent the resulting screenshot: 31 steps, exit found, map/tree/decisions fully populated, "settled".
- **The user then called the whole UI "developed by a backend developer"** — scoped to "the entire ui" when asked. Surveyed every major screen on a second, independent Electron instance (own `--user-data-dir` and sidecar, so the user's live window was never restarted or touched) rather than guess from the CSS: the welcome screen, map/tree and library already carry real design intent from earlier sessions; the config drawer was the one genuinely flat, ungrouped screen, matching what the user had named twice. Shipped (`1152c4a`): fixed a real bug found along the way — `Welcome`'s `onConfigure` opened the drawer but never called `setWelcomeSeen`, so "Open setup" left the welcome screen and the drawer stacked with no scrim between them — and restructured the drawer into titled sections (`§ Endpoint & model`, `§ <world name>`) with the four rarely-touched budget fields collapsed behind a disclosure instead of open by default. Verified live via CDP screenshots, sent to the user.
- **The user clarified they meant the main window, and reported "click Run, button changes, goes back to Run, nothing happens."** Diagnosed live on their actual window (a debug port on their real process, a real click, not a stub) rather than guessed further: the run genuinely succeeds — `builtin` solves an 11×9 maze in ~230ms — and lands straight at its final, fully-settled state (map 100% seen, tree fully drawn, 31+ decisions logged). A search that resolves before a human eye can register any change is indistinguishable from a click that did nothing — this is what the report actually was. Fixed (`ea79e0d`): the timeline effect in `App.tsx` now autoplays the recorded decisions once when a run's last event lands under 1.5s of real elapsed time (`AUTO_REPLAY_MS`), reusing `usePlayback`'s existing "press play at the end replays from the start" behavior rather than adding a new mechanism; a run slow enough to have streamed live (any real network call reliably clears the threshold) is left where it landed. Verified live: the maze now visibly steps 1/31 → 2/31 → … with the map filling in cell by cell.
- **The user then asked for a real, non-canned task rather than another hardcoded scenario.** Ran a genuine multi-step goal against the real DeepSeek API on a second, independent Electron instance (own `--user-data-dir`/sidecar, so the user's window stayed untouched): "how many Python files are directly in `ti_matrix/adapters`, and what does `openai_compat.py` do, in one sentence?", files world. Real reasoning, real reads, real backtracking — and it surfaced a genuine gap: a run that stopped without cleanly settling (`no_progress`, real facts gathered, real tokens spent) got no answer back at all. `_build_engine` in the sidecar never wired an `LLMSynthesizer` for a real model — every CLI on `adapters/session.py` already does, and the renderer already expects and renders `partial_answer` (`core/decisions.ts`) — so this was a missing wire, not a missing feature. Fixed (`6061180`). Re-verified live: the same real goal, re-run, settled cleanly (`done=true`, 95% progress, 5.1k tokens) — no regression on the already-working path.
- **Open items:** B-2026-09-23-5 and B-2026-09-23-2 are older, still-open findings this session did not touch; whether the drawer pass and the auto-replay fix together satisfy "the entire ui" is still open with the user.
- **Notes:** none
- **Report:** none (not a review task)

---
## 2026-09-26 — Session 7 (the pull, the dependencies, and the browser hang they uncovered)
- **Agent:** Ines | **Model:** deepseek-flash | **Platform:** the user's desktop — Windows 11 (DESKTOP-2VPR9IB), Git Bash, Python 3.14.2 (uv venv) | **Role:** engineer | **Core:** 2.0.4
- **Task:** "pull" — bring this clone up to date with `origin/main`. Then, because the tree it produced could not run its own tests here, "Install" — make the suite actually runnable on this machine. No product goal was set beyond that; everything below was found on the way to those two.
- **Commits:** 4 authored + 3 merges, pushed. Ledger: `7a4cab7` (check-in as S007), `7b7f128` (STATE at check-in), `4258869` (claim on the browser hang), and the closing memory commit. Product: `3d6c1e6` "Read what the CLI said from a file, because its daemon never closes a pipe". Merges (`c8fe88e`, `f170c28`, `8a9f186`) integrated remote history — including two batches Sable pushed *during* this session, the second of which arrived as a rejected push and was merged and re-pushed.
- **Outcome:** done and pushed, with one known red. **The pull:** local `main` had diverged — two commits origin had never seen (`48e044a` "Update browser adapter files" + a merge), which are now published for the first time, plus three commits from Marlowe/Sable. Reconciled by merge (never stash/discard), pushed. **The install:** this machine's venv is a *uv* venv with no `pip` at all, holding only pytest and `ti_matrix`; `aiohttp` and the `ti-matrix-server` package were missing, so `server/tests` could not even import. Installed the CI set with `uv pip install --python .venv/Scripts/python.exe -e ".[dev]" -e "server[dev]"`. **The hang:** with the suite finally able to run, the engine suite *never finished* — killed twice after 30+ minutes, both times parked in `test_the_real_cli_reads_a_real_page`. Root cause: `agent-browser` is a daemon-based tool (its own `--namespace` flag promises to "isolate daemon sockets"); the daemon owns the browser between invocations and inherits the handles the command was handed, and on Windows it does not let go of them — so `capture_output`'s pipe never reached end-of-file, and `timeout=` was no escape because `run()` kills the command then reads the very pipe the daemon still holds. Isolated it from the test: the identical `open` never returned in 150s through a pipe and returned in **3.675s** with the right page title when redirected to a file. `_run_cli()` now resolves the name through PATH and captures into files; `_run` keeps its shape; the sweep test uses the same helper so it cannot drift. **Engine suite went from never finishing to 294 passed, 1 failed, in 76s.** pre-commit PASSED, sidecar 38 passed, app build green.
- **The one red, deliberately left:** `test_every_read_action_is_a_command_the_real_cli_accepts` fails on two actions — the table declares four experimental `webmcp_*` actions that the installed `agent-browser` 0.35.1 answers with "Unknown command". Not this claim's defect and not fixed: WebMCP *is* documented on agent-browser.dev and npm's latest is 0.38.1, so the table (written from the docs, `43ca964`) is probably right and this machine's binary is old. The three candidate repairs and the reason each was left (chiefly: upgrading the global CLI has a blast radius beyond this session — other tooling here drives the same binary) are in correction `20260926T071641Z-Ines-ccfac202`; queued as **B-2026-09-26-1**. The test now names the CLI's version when it fails, so the drift is diagnosable at a glance.
- **Open items:** B-2026-09-26-1 (above). Nothing else touched — B-2026-09-23-6/7/11/12, B-2026-09-24-2 and Sable's B-2026-09-23-5/2 are as this session found them. This machine is new to `memory/system/environments.md` and now has a block: the uv-venv-without-pip trap, the exact install command, the verified green commands, and the stray-daemon-Chrome note.
- **Returned, same session:** asked to pull again. A clean fast-forward this time (`4b5b27d..3532cf7`, four commits — two of Sable's fixes plus their ledger notes), so there was nothing to reconcile. The diff touched only `server/appserver/main.py` and `app/renderer/App.tsx`, so the pre-commit gate is the one that covers it and it **PASSED** (sidecar 38, typecheck, 162 renderer assertions). No engine or test file was in the diff, so the 294-passed/one-known-red result above is unchanged by this pull rather than re-run. Both of Sable's fixes are real and both were found by driving the app instead of reading it: a hosted run that stopped without settling now gets an `LLMSynthesizer` the way the CLI sessions already did (the sidecar had never wired one, so a genuinely useful run spent its tokens and handed the person a bare fact list with no answer), and a run finishing under 1.5s now autoplays its recorded decisions once, because a search that resolves faster than the eye can register was indistinguishable from a click that did nothing — a fair complaint against a product whose whole premise is watching it happen.
- **Notes:** none
- **Report:** none (not a review task)
