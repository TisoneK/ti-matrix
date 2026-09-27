# Agent + Model Registry (update in place)

Which agents and models have worked on this repo — and what they've
shown they can and can't do here. Update your row each session (last
seen + session count); add a row only if this **(agent, model) pair** is
new. The Observations section is how the user learns which agent to hand
which task, and how agents learn a predecessor's blind spots (and verify
its work accordingly).

> **Update in place — do NOT append a duplicate.** This is not an
> append-only log. There is exactly one row per (agent, model) pair: to
> correct a count, model note, or date, **edit that row** — its prior value
> is safe in git history, so you lose nothing. Never add a second row for a
> pair that already exists (that is how a registry ends up with two rows
> and conflicting counts). Different models for the same agent are separate
> rows — that is expected, not a duplicate. `sh .context_ledger/core/bin/ledger-mem
> check` (Windows: the `.ps1`) flags a duplicated (agent, model) key.

<!-- TEMPLATE — one row per agent+model pair:
| <agent name> | <model id> | YYYY-MM-DD | YYYY-MM-DD | <count> |
-->

| Agent | Model | First seen | Last seen | Sessions |
|---|---|---|---|---|
| Buffy (Freebuff host agent) | unknown | 2026-09-23 | 2026-09-23 | 1 |
| Nadia (ZCode) | deepseek-flash | 2026-09-23 | 2026-09-23 | 1 |
| Sable (ZCode) | claude-sonnet-5 | 2026-09-25 | 2026-09-26 | 2 |
| Rosalind (ZCode) | deepseek-flash | 2026-09-26 | 2026-09-26 | 1 |
| Odette (Freebuff host agent) | unknown | 2026-09-26 | 2026-09-26 | 1 |
| Cordelia (Freebuff host agent) | glm-5.3-flash | 2026-09-26 | 2026-09-26 | 1 |
| Greer (Claude Code) | claude-sonnet-5 | 2026-09-27 | 2026-09-27 | 1 |

## Observations

- **Nadia / deepseek-flash:** drove the whole renderer rebuild from screenshots taken through a browser
  harness rather than a window — the defects it found (panels laid out as page grid cells, a label
  swallowing its hint into the accessible name) were all invisible in the source and obvious on screen.
  Wrote the folds first and the panels second, which is why four panels could be rewritten in one session
  without breaking the others. (2026-09-23)
- **Rosalind / deepseek-flash:** the same lesson from the other direction. It read `styles.css` first and
  came away thinking the app was well designed — that file documents a real visual grammar — and only
  found the actual complaint (composition: empty panes as voids, a stat-block footer under the map, no
  type above 13.5px, meaning encoded in unlabelled glyphs) after driving the running window and measuring
  the layout. Re-verifying every change in the live window at four widths, rather than trusting the diff,
  is what caught the coverage readouts wrapping to a second ragged row and the Compare pane's clipped
  buttons. Needs the window, not the source, as its evidence. (2026-09-26)
- **Sable / claude-sonnet-5:** strong on this repo — the config-drawer design pass, model auto-fetch, the
  missing-synthesizer wire and the auto-replay fix were all found by driving the real app, and each shipped
  with its reasoning written down. Its limits are worth knowing for scheduling: **it does not stop at a
  clean boundary when its context runs out.** Its last session ended mid-write on 2026-09-26 — last commit
  `3532cf7` at 00:36:37, orphaned renderer files written at 00:40–00:41, no clock-out and no `release` — so
  it left an uncommitted red test in the tree, a roster row reading `Working` for four hours, and its own
  in-flight work attributed to nobody, which the next session (Rosalind, S008) could only correct after the
  supervisor said what had happened. Give it scoped work with a commit per step rather than long open-ended
  runs: it works well right up to the wall. (2026-09-26)
- **Greer / claude-sonnet-5 (Claude Code):** compared this repo's `files.py` against a sibling project's
  search tool line-by-line rather than guessing at what made it faster (a first guess — Spotlight/`mdfind` —
  was wrong and corrected once actually read: it's also a plain Python walk, just pruned better). Also
  caught a stale README claim (`--model builtin` "not wired to the CLIs") by checking the code
  (`session.py::Seats.seats()`) rather than trusting the doc — the wiring had shipped a day after the note
  was written and nobody updated it. Verified the shipped fix against the test suite AND a live run on a
  real home directory, not the suite alone. (2026-09-27)
- **Cordelia / glm-5.3-flash:** shipped B-2026-09-23-7 (the browser world's page surface) end to end with
  live verification — real Chrome through the real sidecar, then the panel driven over CDP in an isolated
  second instance — and the live passes caught two things every static check had already blessed: a
  leftover attribute shadowing the new `capture_frame` method (a silent no-op) and a stale `dist-electron`
  bundle that made a fresh preload API read `undefined` in a current-renderer window. Trusts the running
  system over the diff; will chase a live anomaly down a reflog to rule out its own hand before touching
  code. Watch for: one commit swept staged-unrelated files alongside its own (caught, disclosed in the
  session entry) — keep staging explicit per surface. (2026-09-26)

Concrete, evidence-based capabilities and limits — things demonstrated
in this repo's sessions, not marketing claims or self-assessment.
Update in place when a newer session contradicts an old observation.

<!-- TEMPLATE — one bullet per observation:
- **<agent> / <model>:** <what was observed — concrete and checkable, e.g. "Read tool truncates files >500 lines; needs offset/limit", "SSRF fix shipped with regression test, verified green"> (YYYY-MM-DD)
-->
