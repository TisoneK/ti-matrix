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
| Rosalind (ZCode) | deepseek-flash | 2026-09-26 | 2026-09-26 | 1 |

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

Concrete, evidence-based capabilities and limits — things demonstrated
in this repo's sessions, not marketing claims or self-assessment.
Update in place when a newer session contradicts an old observation.

<!-- TEMPLATE — one bullet per observation:
- **<agent> / <model>:** <what was observed — concrete and checkable, e.g. "Read tool truncates files >500 lines; needs offset/limit", "SSRF fix shipped with regression test, verified green"> (YYYY-MM-DD)
-->
