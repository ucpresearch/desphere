# mercator

**Flatten a sphere.** `mercator` is a clean-room, MIT-licensed, zero-dependency
transcoder from **NIST SPHERE** audio (the `.sph` format used by TIMIT, WSJ,
Switchboard, and friends) to plain **RIFF/WAV**. The CLI is `sph2wav`.

```bash
sph2wav utterance.sph             # -> utterance.wav
sph2wav utterance.sph out.wav
sph2wav --info utterance.sph      # inspect the SPHERE header
sph2wav utterance.sph -           # WAV to stdout
```

```python
from mercator import read_sphere, transcode

header, data = read_sphere("utterance.sph")
with open("utterance.wav", "wb") as f:
    transcode(header, data, f)
```

## Why

`libsndfile`/`soundfile` cannot read SPHERE (especially shorten-compressed
SPHERE), and the tools that can — `sph2pipe`, the original `shorten`, FFmpeg's
decoder — are GPL/LGPL or otherwise awkwardly licensed. `mercator` is a
permissively licensed, dependency-free reimplementation.

## Clean-room policy

`mercator` is implemented **only** from:

- The **public NIST SPHERE** format description (ASCII header, typed object fields).
- **ITU-T G.711** for μ-law / a-law.
- Tony Robinson (1994), *SHORTEN: Simple lossless and near-lossless waveform
  compression* (CUED/F-INFENG/TR.156) for the shorten algorithm.
- **Black-box testing**: running `sox` / `ffmpeg` / `sph2pipe` as binaries and
  comparing only their **output** — never reading their source.

Copyright protects source code, not file formats or algorithms (the
idea/expression dichotomy), so consulting *prose/tabular* descriptions of a
format — even third-party ones — is fine. The one rule we never break: **we do
not read GPL/LGPL source code, and we do not use writeups that embed verbatim
GPL source.** Authoritative non-source references (the TR, ITU specs, NIST docs)
are the primary sources; prose writeups are at most a cross-check.

## Supported matrix

The design principle is **support the obvious lossless path first, and fail
loudly on anything not yet validated** — never emit a plausible-but-wrong WAV.

| Coding | Status |
|--------|--------|
| `pcm`, 16-bit, `01`/`10` byte order | ✅ supported |
| `pcm`, 32-bit, `01`/`10` byte order | ✅ supported |
| `pcm`, multi-channel (interleaved)  | ✅ supported (validate against an oracle for exotic files) |
| `pcm`, 8-bit / 24-bit               | ⛔ rejected (`UnsupportedFormat`) — sign/packing not yet validated |
| `ulaw` / `alaw` (G.711, 8-bit)      | ✅ supported (Phase B) — verified byte-exact vs ffmpeg on all 256 codes |
| `pcm,embedded-shorten-v2.00` (16-bit) | ✅ supported (Phase C) — byte-exact vs ffmpeg, mono & stereo |
| `ulaw,embedded-shorten` (shorten type 8) | ⛔ rejected (`UnsupportedFormat`) — lossless-μ-law shorten mode, future work |
| shorten QLPC blocks                 | ⛔ rejected (`UnsupportedFormat`) — LPC-predicted blocks, future work |

Adding a coding means registering a decoder in `mercator/codecs.py`; until then
the gate raises a precise error.

## Test fixtures (the "zoo")

We don't depend on real corpus files to test: `tools/make_fixtures.py`
*generates* a zoo of SPHERE variants — every byte order, bit depth, and channel
count — and commits them under `tests/fixtures/` with a manifest recording the
exact expected output. Harder codings (μ-law/a-law, eventually shorten) are
produced best-effort by driving `sox`/`ffmpeg`/`shorten` as black-box binaries.

```bash
python tools/make_fixtures.py     # regenerate fixtures + manifest
pytest                            # validate everything
```

## Development

The virtualenv lives **outside** the (Syncthing-synced) repo and is symlinked in:

```bash
uv venv ~/local/scr/venvs/mercator
ln -s ~/local/scr/venvs/mercator .venv
uv pip install -e ".[dev]"
pytest
```

## Roadmap

- **Phase A** (done): SPHERE header + 16/32-bit PCM, lossless.
- **Phase B** (done): μ-law / a-law decode (ITU-T G.711).
- **Phase C** (done): embedded-shorten decode of 16-bit PCM (from TR.156 +
  black-box ffmpeg oracle) — validated byte-for-byte on real corpus `.sph`
  files, mono and stereo. Remaining: shorten's lossless-μ-law mode (type 8) and
  QLPC blocks.
