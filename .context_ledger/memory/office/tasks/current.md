# Current Task (overwrite each session)

Holds exactly one task — the one being worked on right now. Set it at
session start (protocol Step 3), clear it at session end (Step 15). If
you find a stale in-progress entry here, a prior session died mid-task —
its roster row (if left behind) says who was here; check the session
entry and backlog before starting.

- **Session:** 2026-09-23 — Mara / claude-opus-5 (S004)
- **Task:** made the window actually run something (rule-based seats, socket reconnect, engine restart), fixed the rail's config button, rebuilt the welcome around a preview of the product, one-word TiMatrix wordmark — done, committed, pushed to `app-ui-rebuild`
- **Status:** idle — but `origin/main` still needs the fast-forward from `app-ui-rebuild` (the sandbox blocked that push)
