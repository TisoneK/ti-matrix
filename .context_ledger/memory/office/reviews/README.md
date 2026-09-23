# Reviews (one file per session)

Session review reports. One file per session, named `YYYY-MM-DD-review.md`
so they sort chronologically. Role-overlay sessions (see
`.context_ledger/core/roles/`) use `YYYY-MM-DD-<role>-review.md`, e.g.
`2026-07-11-security-review.md` — except the reviewer role, which keeps
the plain name (its report *is* the review). If two same-named sessions
land on the same day, suffix the later one: `YYYY-MM-DD-review-2.md`.
Never edit a past report — a correction goes in the next report (or an
appended "Correction" section citing the session that found the error).

Report shape — a suggestion, not a form: write for the project's owner
in plain sentences, lead with what happened, and keep it as short as the
work allows. A reader outside the session's chat should understand the
report in one pass. Cover what happened → what you found → what you
changed → what's still open → what to do next, in whatever structure
fits; headings only when the report needs them, and severity labels
(Critical / High / Medium / Low / Nice to Have) only on findings that
carry one.

Even a session with no findings writes a report — one plain line
("reviewed `<area>`; baseline healthy; nothing needed") — the next
agent needs to know the review happened.

Reports migrated from the legacy `docs/report/` location keep their
original filenames.
