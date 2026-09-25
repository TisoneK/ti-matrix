---
## 2026-09-23 — Session 4 (making the window actually run something, then fixing the rail)
- **Agent:** Mara | **Model:** claude-opus-5 | **Platform:** bao's Mac — macOS (darwin 24.6.0), Node 24.17.0, Python 3.10.20 (.venv) | **Role:** engineer | **Core:** 2.0.4
- **Task:** the user's report that the app is "a beautiful system that does nothing" — UI and backend detached, "sidecar gone", nothing observable. Then, mid-session, that the top-right nav buttons were "misfunctioning eg opening something else".
- **Commits:** 2 product commits (`2de25ce`, `09adcff`) plus ledger commits (check-in, STATE, this close)
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
- **Not pushed to main:** the standing push policy is "push to main directly after each commit", and `origin/main` is a clean fast-forward from this branch (`git push origin app-ui-rebuild:main`). The sandbox's classifier blocked that push both times, so both commits are on `origin/app-ui-rebuild` only. **The next session, or the user, should complete the fast-forward.**
- **Open items:** B-2026-09-23-5 (the endpoint-backed path is weak on small models — the proposer never sees which cells the run has entered, and a run whose first probe succeeds can still stop on `no_progress` at depth 0), B-2026-09-23-2 (the prose worlds' panels), B-2026-09-23-3 (a run against a large hosted model — session 3's DeepSeek runs stand; this session only drove a small local one)
- **Notes:** .context_ledger/memory/office/sessions/2026-09-23-4/notes.md — driving the real Electron window over CDP, and the persisted-default trap that no test could see
- **Report:** none (not a review task)
