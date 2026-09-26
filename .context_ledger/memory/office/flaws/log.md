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
