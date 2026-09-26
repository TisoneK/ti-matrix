# Brief — duplicate files of any kind, judged by content rather than by name

**Raised by the user, 2026-09-23, for the next session.** Written by Mara (S004) after a
spike and a check of where a package this size can live. The claim that could have sunk
it — that the stdlib-only tier actually works — is verified below, not assumed. Where the
package lives is settled: **ADR-2**, inside `ti_matrix`, so it ships with the pip package.

## The job

> next session focuses on file not maze eg a user wants to identify duplicate songs —
> the app should not see just file name but listen like 2 minutes of the song and
> compare hashes, metadata etc
>
> its not just music, any kind of file type so the module or package is big

A library of files with duplicates in it, and an agent that decides which are genuinely
the same content. Songs are the motivating case, not the scope. Filename comparison is
the thing it must beat, not the thing it does.

"The package is big" is the right instinct and it is the main design problem here: every
file family is read a different way, and the thing that makes them one feature is a
common **ladder from cheap to expensive**, not a common parser.

## Why this beats the maze as the world to build on

The maze exists to make the engine search, and rules now solve it in 85ms. Nothing is
left to learn from it. This job has the property the maze was standing in for, honestly:

**Probes have wildly different costs.** Stat a file: microseconds. Read its tags:
milliseconds. Hash its payload: proportional to size. Decode two minutes of audio or
perceptually hash a thousand images: seconds and real CPU. A library of 50,000 files
cannot be fully fingerprinted on a whim — so *which probe to spend on next* is a real
decision against a real budget, which is exactly what `StateEngine` and `EngineBudget`
are for. In the maze the budget was an artificial ceiling; here it is the constraint.

**Be honest about what the agent adds.** Exact-duplicate detection is a solved
deterministic problem — hash everything, group. An agent does not beat that and must
not pretend to. What it adds is *triage and adjudication with provenance*: deciding
that this pair is settled by metadata, this one needs the expensive probe, and this one
is a live version, a crop, a draft or a different export rather than a duplicate — and
producing a ledger that says why. If the next session finds itself writing a worse
grouping algorithm and calling it reasoning, it has taken a wrong turn.

## The ladder, which is the actual design

Every family implements the same four rungs. The registry maps a file to its family by
magic bytes first and extension second — extensions lie, and a renamed file is exactly
the case this feature exists to catch.

| rung | cost | what it establishes |
|---|---|---|
| `identify` | ~0 | family, real format, size, mtime |
| `describe` | cheap | the format's own metadata: tags, EXIF, page count, duration, dimensions |
| `content_hash` | O(size) | hash of the **payload**, with metadata excluded — see below |
| `perceive` | **expensive** | a perceptual/structural fingerprint that survives re-encoding |

**Rung 3 is the one that earns its keep and the one everybody skips.** Hashing the file
answers "are these the same bytes", which is nearly useless — retagging a song, rotating
an image's EXIF, or re-saving a PDF changes every such hash while the content is
identical. Hashing the *payload* answers "is this the same content, differently
labelled". Spiked and confirmed on audio, stdlib only:

| file | file sha | payload sha | verdict |
|---|---|---|---|
| `a.mp3` | `4190569f…` | `6bd3c28f…` | |
| `a-retagged.mp3` — same audio, new tags | `59e98266…` **differs** | `6bd3c28f…` **matches** | duplicate, caught |
| `b-impostor.mp3` — same tags, other audio | `988e99b6…` | `a5627eca…` **differs** | not a duplicate, rejected |

That is the common real-world case which filename *and* whole-file-hash both miss, plus
the impostor case that tag comparison alone gets wrong. Working spike beside this file:
`duplicate-files-spike.py` (~40 lines, stdlib, runs standalone). The pattern it shows —
*find where the payload begins, hash from there* — is the same move for every family.

Rung 4 is what the user meant by "listen to two minutes": the same recording at a
different bitrate, the same photo re-exported at a different quality, where every byte
differs and rung 3 correctly says "not identical" while a person says "same thing".

## What is actually feasible with no dependencies

The engine's hard rule — `tests/test_boundary.py::test_the_shipped_adapters_are_host_free`
— is that **every file under `ti_matrix/` imports nothing outside the standard library**.
It walks the whole AST, so a deferred `import` inside a function fails too. No allowlist.
That rules out Pillow, mutagen, numpy, pypdf and pyacoustid *inside the engine*.

Honest per-family assessment, because this is where a session burns a week:

| family | rungs 1–3, stdlib | rung 4, stdlib |
|---|---|---|
| **zip-based** (docx, xlsx, pptx, epub, jar) | **easy** — `zipfile` is stdlib; read the XML inside | text shingling: easy |
| **text / code** | **easy** | normalise whitespace, shingle, minhash: easy |
| **audio** (mp3, flac, m4a, ogg) | **proven** — hand-parse ID3v2 / Vorbis / MP4 atoms with `struct` | needs a decoder |
| **PNG / BMP / PPM** | **easy** — `zlib` + unfilter gives real pixels | perceptual hash: feasible |
| **GIF** | moderate — LZW by hand | feasible once decoded |
| **PDF** | moderate — `zlib` for FlateDecode; structural hashing yes, faithful text extraction no | partial |
| **JPEG** | metadata easy (EXIF is just TIFF); pixels need Huffman + IDCT, ~400+ lines | **hard** |
| **video** (mp4, mkv) | container parsing doable | **needs a decoder** |

Two stdlib escape hatches do **not** work: `audioop` was removed in 3.13 and CI runs
3.10–3.13; `wave` reads PCM only. And on this machine `ffmpeg`, `ffprobe` and `fpcalc`
are all **not installed**, so a design that assumes a decoder fails on the machine it
ships from.

## Where the package lives — **decided, do not relitigate**

`ti_matrix/adapters/dedupe/`, so it ships with the pip package. The user's call, recorded
as **ADR-2** in `plans/decisions.md`; read that before proposing anything else.

(Not `inspect/` — `inspect` is a standard library module, and a package with that name inside
an engine whose whole rule is "standard library only" is a confusion nobody needs to inherit.)

The consequence is the binding constraint on every line of this feature: inside `ti_matrix`,
`test_boundary` forbids **all** third-party imports, deferred ones included. No Pillow, no
mutagen, no numpy, no pypdf.

This is workable because it is already how this repo drives external software.
`ti_matrix/adapters/browser/` runs a real Chrome from inside the engine on nothing but the
standard library: `find_browser` locates the binary, `subprocess` starts it, and a
hand-written `websocket.py` (`socket`, `struct`, `base64`) speaks DevTools Protocol to it.
Do the same here — talk to the tool, do not import a library that wraps it.

**One optional binary covers the whole expensive rung.** `ffmpeg` decodes audio, video *and*
still images, so the capability question is "is ffmpeg on PATH" once, rather than a different
answer per family. Mirror `find_browser` with a `find_decoder`. It is not installed on this
machine, which makes the no-decoder path the default one to get right, not an afterthought.

When it is absent, `perceive` returns a **failed `Observation` saying so** — "no decoder on
this machine; install ffmpeg" — the search settles on payload-hash evidence, and the run
states that is what it did. A failed probe is information the search uses. A silently skipped
one would make the answer dishonest rather than merely weaker.

**The one gap to plan around: JPEG pixels.** EXIF is easy (it is TIFF) and payload hashing
needs no decode, so rungs 1–3 are fine. But a baseline JPEG decoder in pure Python is Huffman
plus IDCT and several hundred lines — do not write it. JPEG's expensive rung goes through
ffmpeg or waits.

## A reasoner, so it runs with no model

`ti_matrix/adapters/builtin.py` has `reasoner_for(world, specs)` returning `MazeReasoner`
or the generic `SurveyReasoner`. `SurveyReasoner` is poor here — it proposes each action
once with no arguments and cannot carry a path. Add a reasoner that encodes the ladder:
identify everything, describe, then hash only within candidate groups (same family,
similar size), then `perceive` only for pairs rung 3 could not settle. Wire it into
`reasoner_for`. Then the feature works out of the box with no endpoint, as the maze now
does, and the model becomes the upgrade that handles the judgement calls rules are bad
at — a live version, a crop, a draft, a different export of the same source.

**Bound the pairwise work before the search starts.** 50,000 files is 1.25 billion pairs.
Block on family and size first; the agent adjudicates *groups*, never the cross product.

## Tests

Ship **no binary fixtures.** Synthesize them: `wave` writes a tone in a few lines, hand-
built ID3 frames a dozen more, `zlib` makes a valid PNG, `zipfile` makes a docx. The
spike does the audio half already. Build the three cases above per family, plus one that
only rung 4 can settle, and skip that one when no decoder is on PATH so the suite stays
green on a bare machine.

## Decide retrieval before writing this world

A library of 50,000 files produces a fact set that cannot be shown whole, and "the last N facts" is the
axis that was just measured as wrong (`597b12d`). B-2026-09-23-12 covers the two options — a `Retriever`
port, or `recall` as an action the model proposes. Pick one before this world is written; retrofitting
produces a world shaped around whatever was convenient at the time.

## Questions for the user — ask before building, they change the design

1. **What happens when it finds duplicates?** A report, or does the app offer to move or
   delete them? Deleting a file is destructive and irreversible; the confirmer exists for
   exactly this, and v1 should almost certainly report only.
2. **Which families matter first?** The table above says audio and zip-based documents are
   cheap to do well and JPEG/video are expensive. Doing three families properly beats ten
   badly, and the user's own library decides which three.
3. **Is a near-duplicate a duplicate?** A live version, a crop, a resized export, a draft
   of a document. This is where a model beats a hash, and the answer decides whether this
   is a hashing feature with an agent bolted on or a reasoning feature.
4. **How big is the real library?** 200 files and 50,000 files are different products.
