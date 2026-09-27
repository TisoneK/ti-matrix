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
| Greer | S013 | claude-sonnet-5 | Checked back in — the tree panel goes dead during a model's propose/evaluate calls (15-45s each) with zero visual feedback beyond the narrator's text line; building a live fan-preview (ghost stubs on `candidates`, filled in as `probe`/`evaluation` land, winner animates into the tree) in `TreePanel.tsx`/`decisions.ts`/`tree.ts`. Approved via mockup + AskUserQuestion. A left-rail layout restructure + reskin is queued next, deliberately not mixed into this change | Working |
