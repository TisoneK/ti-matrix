# archive/ — cold storage of closed offices

Older closed offices, one gzipped tarball each (`office-<NNN>.tar.gz`),
produced automatically by `ledger-history` when `../history/` exceeds its
readable-keep window. Each tarball contains the whole frozen office
directory — roster, session registry, notes, tasks, plans, flaw and
inefficiency logs, reviews — preserved verbatim. Cold storage: extract one
only for a deep lookback.

**Not read at session start**, and never by default.

This zone is capped. When it exceeds `archive_keep` tarballs (default 12),
`ledger-history gc --confirm` deletes the oldest first, down to the cap —
a forced, consistent rule so `archive/` cannot grow unbounded either.
Deletion removes the tarball from the working tree only; it stays
recoverable in git history. And nothing is ever truly forgotten: each
office's permanent accomplishments record lives in
`../history/office-<NNN>.md` forever, naming what the office achieved and
where its history went.
