# Flaws Log (append-only — flows to the protocol package)

Friction caused by the `.context_ledger/` system or the protocol itself. See
`README.md` in this directory for the split between `flaws/` and
`inefficiencies/`.

Append-only, but compactable — the log never grows without bound:

- **Resolved entries move verbatim** to cold storage: once an entry is
  explicitly marked `RESOLVED` / `superseded` / fixed, cut it unchanged
  into `archive.md` in this directory so startup reads only the live
  entries. Age alone never makes an entry eligible — an unresolved flaw
  stays here as a live trap.
- **Repeats roll up:** when 3+ entries describe the same recurring
  protocol trap, append ONE consolidated `Recurring` entry — the pattern,
  how many times, the current workaround — and move the individual
  entries verbatim into `archive.md`. The live log keeps the pattern, not
  the repeats.

`ledger-mem prune` reports log sizes, archive-eligible entries (`--list`
names them), and roll-up candidates.

<!-- TEMPLATE — copy below the last entry:
---
## YYYY-MM-DD — <agent> / <model> (Session N)

- **Flaw:** <what in the protocol or .context_ledger/ system didn't work>
- **Symptom:** <what happened to the agent — the observable friction>
- **Root cause:** <why the protocol/.context_ledger/ let this happen>
- **Suggested fix:** <concrete change to the package — a step, a pitfall,
  a template, a rule>
- **Status:** open | fixed in package <commit-sha or date>
-->

---
## 2026-09-26 — Ines / deepseek-flash (Session 7)

- **Flaw:** `ledger-mem check`'s forgotten-clock-out audit cannot fire on this project's roster format, so a stale row is invisible to the tool that exists to flag it.
- **Symptom:** Wren's (S002) row sat on the board marked `Working` for three days after that session had released its claim and left. Every session that checked in between (S003 through S007) read the board and saw a live peer who was not in the room — the exact collision the board exists to prevent. It was caught by the supervisor saying "Wren is just stale", not by the check.
- **Root cause:** the audit matches a roster row's *Session N* against `agents/sessions.md`. The roster this project bootstrapped from has no Session column — its columns are Name, Codename, Model, Doing, Status — and the codename `S<NNN>` is the row's only session reference, so the check has nothing to match on. It then reports `memory check passed`, which reads as "the board is fine" rather than "this audit did not run". Wren also has no `sessions.md` entry at all (this office's log runs 1, 3, 4, 5, 6, 7 — Session 2 was never written), so even a codename-aware match would have found no entry to hit. Two independent reasons the audit is blind here, and neither is visible from its output.
- **Suggested fix:** for the package — key the audit on the codename cell instead of a Session-N column (codenames are unique in the office by rule and are already the roster's session handle), and add an age-based signal needing no matching entry at all: warn when a roster row's check-in commit is older than the office's newest session entry. Print "no forgotten clock-outs (0 rows checked)" so a silent audit is distinguishable from a passing one. Worth stating in the schema and kickoff as well — nothing currently says who may clear a stale row, and it cannot be the row's own session, which is gone by definition; on the supervisor's word any arriving session may remove it.
- **Workaround, used here:** cleared by hand, with the evidence recorded (the row's release event `20260923T145847Z-Wren-eb33e108` citing `3e9bf2c`, Session 3's own "idle on `main`" note from the same day, and the absent Session 2 entry). Nothing is lost by the removal — the schema puts the duty log in the roster file's own git history as well as in `sessions.md`. The gap this entry closes is that the *reason* would otherwise have died with this office: `sessions.md` is frozen and never read at session start once the office closes, while this log is durable.
- **Status:** open

---
## 2026-09-26 — Rosalind / deepseek-flash (Session 8)

- **Flaw:** the same blind audit, a second instance the same day, and this time the stale row cost more than a bad read — it changed a live session's behaviour.
- **Symptom:** Sable's (S006) row read `Working` for four hours after that session had stopped, having run out of session tokens mid-write. I came through the door, read the board, and did exactly what the protocol tells a session to do with a live row I did not write: I treated the abandoned work in the tree as work in flight, did not clear `tasks/current.md` (it held their in-progress task), and described five orphaned renderer files as "unattributable" in my claim and my session entry. Every one of those was the protocol working as written and producing the wrong answer, because the ghost on the board was indistinguishable from a peer who was thinking. It was corrected only by the supervisor saying, in chat, "that is S006, they ran out of session tokens."
- **Evidence, since the row itself could not be dated by the audit:** Sable's last recorded act is `3532cf7` at 00:36:37 local; the orphaned files carry mtimes of 00:40–00:41; their only coordination event is a `note` with no `claim` and no `release`. Four minutes between a ledger commit and a hand that stopped, with nothing after it — a signature no tool currently looks for.
- **Root cause:** the audit's blindness is Ines's entry above, and needs no restating. What is new is the *consequence*, which is not about the audit: **"a live row you did not write means a peer is in the office, so coordinate" and "a row whose owner has stopped means take the work over" are the same observation from the inside, and the protocol only ever tells a session which one to assume.** It resolves toward deferral, because deferring is the safe error when the peer really is there — so a stopped session's half-finished work is preserved, its task slot is left occupied, and its authorship goes unrecorded, all by agents being careful. There is also a **preservation trap** in the working tree: I found dirty files I had not written and correctly declined to discard them (as Phase 1 requires), which locked a red test into a tree I could not commit from until I either adopted or reverted someone else's work. "Don't touch a peer's tree" and "every change must be committed and pushed" cannot both be satisfied when the peer is gone and has left the tree dirty.
- **Suggested fix:** for the package — (1) the age-based roster signal Ines proposed, and (2) make the *age* of a roster row visible at the door rather than only in a tool: the roster's own check-in commit date is enough, and a row has no reason not to carry it. (3) State the hand-over rule the schema is silent on, in the edition rather than in project overrides, since every project hits it: a session that finds a dirty tree its owner has abandoned may adopt the work and record the adoption, and the adopting session owns the fix. (4) Worth a pitfall line of its own: **token exhaustion is not a graceful exit** — the failure signature is a tree that is dirty, red, and plausibly finished, committed to by nobody. An arriving session should check the last commit time against the tree's mtimes before deciding how careful to be, which is a two-command check and would have told me everything the supervisor had to.
- **Status:** open
