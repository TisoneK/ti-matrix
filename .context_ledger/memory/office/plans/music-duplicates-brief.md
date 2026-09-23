# Brief — the files world, pointed at a real job: which of these songs are the same song?

**Raised by the user, 2026-09-23, for the next session.** Written by Mara (S004) after
a spike; the risky claim in it is proven, not assumed.

## The job, in the user's words

> next session focuses on file not maze eg a user wants to identify duplicate songs —
> the app should not see just file name but listen like 2 minutes of the song and
> compare hashes, metadata etc

So: a music library with duplicates in it, and an agent that decides *which* of them
are genuinely the same recording. Filename comparison is the thing it must beat, not
the thing it does.

## Why this is the right world to move to

The maze is a toy that exists to make the engine search, and it has now been solved in
85ms by rules that need no model at all. Nothing is left to learn from it. This job has
the property the maze was standing in for, and it has it honestly:

**Probes have wildly different costs.** Reading a tag is microseconds. Decoding two
minutes of audio is seconds and real CPU. A library of 5,000 songs cannot be fully
fingerprinted on a whim. So *which probe to spend on next* is a real decision with a
real budget behind it — which is exactly what `StateEngine`, `EngineBudget` and the
two seats are for. In the maze, the budget was an artificial ceiling; here it is the
actual constraint.

**Be honest about what the agent adds.** Duplicate detection has a known-good
deterministic algorithm: fingerprint everything, cluster by distance. An agent does not
beat that at clustering and must not pretend to. What it adds is *triage and
adjudication with provenance* — deciding metadata alone settles this pair, this one
needs ears, this one is a live version and not a duplicate at all — and producing a
ledger that says why, which is this product's entire pitch. If the next session finds
itself writing a worse clustering algorithm and calling it reasoning, it has taken a
wrong turn.

## The hard constraint, read it before designing anything

`tests/test_boundary.py::test_the_shipped_adapters_are_host_free` asserts that **every
file under `ti_matrix/adapters/` imports nothing outside the standard library and
`ti_matrix` itself.** It walks the whole AST, so a deferred `import mutagen` inside a
function fails it too. There is no allowlist.

That kills the obvious plan. No `mutagen`, no `pydub`, no `numpy`, no `pyacoustid`.
And two stdlib escape hatches do not work either:

- `audioop` was removed in Python 3.13 (PEP 594). CI runs 3.10–3.13, so it is unusable.
- `wave` reads PCM only. Real libraries are mp3/m4a/flac; `wave` cannot open them.

On this machine, `ffmpeg`, `ffprobe` and `fpcalc` are all **not installed** — so a
design that assumes a decoder is present will fail on the very machine it ships from.

## Two tiers. The first needs nothing; the second needs a decoder.

### Tier 1 — stdlib only, always available. **Proven.**

Parse container metadata by hand (`struct`) and hash the *audio payload* rather than
the file, so tags do not change the answer. Spiked and confirmed:

| file | file sha | stream sha | verdict |
|---|---|---|---|
| `a.mp3` | `4190569f…` | `6bd3c28f…` | |
| `a-retagged.mp3` (same audio, retagged) | `59e98266…` **differs** | `6bd3c28f…` **matches** | duplicate — caught |
| `b-impostor.mp3` (identical tags, other audio) | `988e99b6…` | `a5627eca…` **differs** | not a duplicate — rejected |

That is the common real-world case (same rip, different tags) which filename *and*
whole-file-hash comparison both miss, and the impostor case that tag comparison alone
gets wrong. Working spike, stdlib only, ~40 lines:
`.context_ledger/memory/office/plans/music-duplicates-spike.py`.

Scope for Tier 1: ID3v2.3/2.4 (mp3), Vorbis comments (flac/ogg), MP4 atoms (m4a). All
openly documented, all parseable with `struct`. Also derive duration and bitrate from
the first frame header — two files whose durations differ by more than a second or so
are not the same recording, and that is a very cheap way to rule pairs out.

### Tier 2 — "listen to two minutes". Needs an external decoder.

This is the part the user actually asked for, and it is what catches a **re-encode**:
the same recording at a different bitrate, or in a different format, where every byte
differs and Tier 1 correctly says "not identical" while a human would say "same song."

Shell out with `subprocess` (stdlib, so the boundary test is satisfied — the browser
adapter already sets the precedent of talking to an external program over a documented
protocol rather than importing a library):

```
ffmpeg -i <path> -t 120 -ac 1 -ar 8000 -f s16le -    # 2 minutes, mono, 8kHz, raw PCM
```

Then compute a perceptual hash over that PCM in pure Python — a coarse spectral
fingerprint is enough and does not need numpy at this resolution: frame the signal,
take band energies, and emit one bit per band per frame for whether energy rose or
fell. Compare with Hamming distance. This is the shape chromaprint uses; it does not
have to be chromaprint-compatible, it has to be stable under re-encoding.

**When the decoder is missing, do not crash and do not silently skip.** Return a failed
`Observation` saying so — "cannot listen: no decoder on this machine; install ffmpeg" —
because a failed probe is information the search uses, and the run should then settle
on Tier 1 evidence and *say* that is what it did. That is this engine's own idiom and
it is the difference between a degraded answer and a dishonest one.

## The world

A new `ti_matrix/adapters/music.py`, registered in `server/appserver/worlds.py`
alongside the existing rows. Rooted like `RootedFiles` is — every path resolves under
one directory and anything escaping it is a refused probe, not a crash. All actions
read; nothing here ever deletes a file, and deletion should not be an action at all in
the first version.

| action | cost | returns |
|---|---|---|
| `scan(dir)` | cheap | the audio files under a directory: path, size, extension |
| `tags(path)` | cheap | title/artist/album/duration/bitrate, and where the payload starts |
| `stream_hash(path)` | medium | sha256 of the audio payload, tags excluded |
| `listen(path, seconds=120)` | **expensive** | the perceptual fingerprint, or a refusal if no decoder |
| `compare(a, b)` | cheap | tag similarity, duration delta, hash equality, fingerprint distance |

`compare` is what makes the ledger readable: one probe whose observation is the whole
case for or against a pair, in the world's own words.

## A `MusicReasoner`, so it runs with no model

`ti_matrix/adapters/builtin.py` already has `reasoner_for(world, specs)` returning
`MazeReasoner` or the generic `SurveyReasoner`. `SurveyReasoner` would be poor here —
it proposes each action once with no arguments and cannot carry a path. Add a
`MusicReasoner` that encodes the cheap-first policy: scan, then tags, then stream hash
for pairs whose duration and title are close, then `listen` only for pairs that Tier 1
could not settle. Wire it into `reasoner_for`. Then the whole feature works out of the
box with no endpoint, exactly as the maze now does, and the model becomes the upgrade
that handles the judgement calls rules are bad at — "Live at Wembley" versus the studio
cut, a radio edit, a remaster.

## Tests

Ship **no audio files in the repo.** Synthesize fixtures in the test itself — `wave`
writes a tone in a few lines and hand-built ID3 frames are a dozen more; the spike does
both. Build the three cases above (original, retagged, impostor) plus a fourth that
only Tier 2 can settle, and mark that one to skip when no decoder is on PATH, so the
suite stays green on a machine without ffmpeg.

## Open questions for the user — ask before building, they change the design

1. **What is the deliverable when it finds duplicates?** A report the user acts on, or
   does the app offer to move duplicates to a folder? Deleting or moving a music file
   is destructive and irreversible, and the confirmer exists for exactly this; v1
   should almost certainly report only.
2. **Is a live version a duplicate?** A remaster, a radio edit, the same song on an
   album and a greatest-hits? These are the calls a model is genuinely better at than a
   hash, and the answer decides whether this is a hashing feature or a reasoning one.
3. **How big is the real library?** 200 songs and 50,000 songs are different products;
   the second needs the pairwise comparison bounded by blocking on duration/tags before
   the search ever starts.
