# The Office Roster — who is in the room right now

<!-- One row per session, added at check-in, removed at clock-out.
     Codenames are `S<NNN>`, the next free number in agents/sessions.md.
     Never reuse a name while a live row holds it: two Johns on one board is how a peer's
     work gets mistaken for yours. Check `ledger-mem check` if in doubt. -->

| Name | Codename | Model | Doing | Status |
|---|---|---|---|---|
| Rosalind | S008 | deepseek-flash | Done — UI pass shipped (`7f36124`, `af746cf`, `dfa21a2`). S006 clocked out on the record, not on an order; adopted their answer card (`7f36124`) but did **not** finish their session — a third piece is open as B-2026-09-26-4. Awaiting the supervisor | Working |
| Faye | S010 | claude-sonnet-5 | Checked back in after clocking out — the supervisor picked B-2026-09-26-1 (the webmcp CLI version mismatch) next | Working |
| Odette | S011 | unknown | Live-testing on the real window with the supervisor: shipped the narrator + motion (`b1c7590`, `195776f`), the artifact verdict fix (`674c545`), and the silent-goal-drop fix (`6780dda`). Instance on :9334 stays up while the session is live | Working |
| Cordelia | S012 | glm-5.3-flash | Done — B-2026-09-23-7 shipped (`66b5f36`, `2dcd3c1`): the browser world's page captured beside every applied move, shown in a two-layer panel; also closed the sidecar's browser leak. Staying on the board | Done |
| Marlowe | S013 | claude-sonnet-5 | Checked in — the supervisor compared TiMatrix's files adapter against a sibling project (LocalMind)'s `system_search` tool live; porting its walk design (time-budget not entry-count, heavy-dir pruning during the walk, multi-token/glob matching, relaxed fallback) into `ti_matrix/adapters/files.py`, then auditing the files adapter for other architectural gaps found along the way | Working |
