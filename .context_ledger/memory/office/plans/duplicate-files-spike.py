"""Spike (Mara, S004, 2026-09-23) — kept because it proves the one risky claim in the brief.

Question: can code that may import NOTHING outside the standard library
(tests/test_boundary.py) tell "same content, different metadata" from "different content"?

Answer: yes, and this is the whole move — find where the PAYLOAD begins, and hash from
there instead of hashing the file. Metadata stops mattering; the content decides. Shown
here on audio because that was the motivating case, but it is the same move for every
family in the brief: skip the ID3 tag, the EXIF block, the zip's timestamps.

Run it with SP=<some writable dir> python duplicate-files-spike.py.

What it does NOT do is the expensive rung — telling a re-encode of something from a
different something. That needs a decoder, and this machine has no ffmpeg; see the brief.
"""
import hashlib, math, os, struct, wave

OUT = os.environ.get("SP", ".")

def synth(path, freq=440.0, secs=3, rate=8000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(12000*math.sin(2*math.pi*freq*t/rate)))
                          for t in range(rate*secs))
        w.writeframes(frames)

def id3v2(tags: dict) -> bytes:
    """A minimal, real ID3v2.3 tag: header + TIT2/TPE1 text frames, synchsafe size."""
    body = b""
    for fid, val in tags.items():
        payload = b"\x00" + val.encode("latin-1")     # 0x00 = ISO-8859-1
        body += fid.encode() + struct.pack(">I", len(payload)) + b"\x00\x00" + payload
    n = len(body)
    syncsafe = bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])
    return b"ID3" + b"\x03\x00" + b"\x00" + syncsafe + body

def read_id3v2(raw: bytes):
    """Parse the tag back, and say where the audio payload starts."""
    if raw[:3] != b"ID3":
        return {}, 0
    size = 0
    for b in raw[6:10]:
        size = (size << 7) | (b & 0x7F)
    out, i, end = {}, 10, 10 + size
    while i + 10 <= end:
        fid = raw[i:i+4]
        if not fid.strip(b"\x00"):
            break
        fsize = struct.unpack(">I", raw[i+4:i+8])[0]
        out[fid.decode()] = raw[i+10+1:i+10+fsize].decode("latin-1")
        i += 10 + fsize
    return out, end

def stream_hash(raw: bytes) -> str:
    """Hash the AUDIO, not the file: skip the tag, hash what is left."""
    _, start = read_id3v2(raw)
    return hashlib.sha256(raw[start:]).hexdigest()[:16]

# Build three "songs": A, A-retagged (same audio, different metadata), B (different audio).
synth(f"{OUT}/a.wav", 440)
synth(f"{OUT}/b.wav", 523)
audio_a = open(f"{OUT}/a.wav","rb").read()
audio_b = open(f"{OUT}/b.wav","rb").read()

song_a  = id3v2({"TIT2":"Song One","TPE1":"Artist"}) + audio_a
song_a2 = id3v2({"TIT2":"song one (remaster)","TPE1":"Artist","TALB":"Best Of"}) + audio_a
song_b  = id3v2({"TIT2":"Song One","TPE1":"Artist"}) + audio_b   # same tags, different audio!

for name, raw in (("a.mp3", song_a), ("a-retagged.mp3", song_a2), ("b-impostor.mp3", song_b)):
    tags, _ = read_id3v2(raw)
    print(f"{name:16} file-sha={hashlib.sha256(raw).hexdigest()[:16]}  "
          f"stream-sha={stream_hash(raw)}  tags={tags}")

print()
print("file hash says a == a-retagged ? ", hashlib.sha256(song_a).digest()==hashlib.sha256(song_a2).digest())
print("STREAM hash says a == a-retagged? ", stream_hash(song_a)==stream_hash(song_a2), " <- the duplicate filenames miss")
print("STREAM hash says a == b-impostor? ", stream_hash(song_a)==stream_hash(song_b), " <- identical tags, not the same recording")
