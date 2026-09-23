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
