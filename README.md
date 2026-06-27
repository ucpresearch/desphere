# desphere

**Flatten a sphere.** `desphere` is a clean-room, MIT-licensed, zero-dependency
transcoder from **NIST SPHERE** audio (the `.sph` format used by TIMIT, WSJ,
Switchboard, and friends) to plain **RIFF/WAV**. The CLI is `sph2wav`.

> **No tooling, no upload:** there's a browser page that converts a `.sph` to
> `.wav` entirely client-side (WASM) — see [`web/`](web/index.html). Prefer
> `sph2pipe`/`ffmpeg`/`sox` if you have them; the page is for when you don't.

```bash
pip install desphere            # pure Python, zero deps, works anywhere
pip install "desphere[fast]"    # + optional Rust accelerator (big shorten files)

sph2wav utterance.sph             # -> utterance.wav
sph2wav utterance.sph out.wav
sph2wav --info utterance.sph      # inspect the SPHERE header
sph2wav utterance.sph -           # WAV to stdout
```

```python
from desphere import read_sphere, transcode, transcode_bytes

# Streaming API (the reference):
header, data = read_sphere("utterance.sph")
with open("utterance.wav", "wb") as f:
    transcode(header, data, f)

# One-shot bytes API — transparently uses the Rust accelerator if installed:
wav_bytes = transcode_bytes(open("utterance.sph", "rb").read())
```

The CLI passes a stray `.wav` through unchanged (with a warning), so pointing it
at an already-decoded file is harmless.

## Why

`libsndfile`/`soundfile` cannot read SPHERE (especially shorten-compressed
SPHERE), and the tools that can — `sph2pipe`, the original `shorten`, FFmpeg's
decoder — are GPL/LGPL or otherwise awkwardly licensed. `desphere` is a
permissively licensed, dependency-free reimplementation.

## Clean-room policy

`desphere` is implemented **only** from:

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
| `ulaw,embedded-shorten` (shorten type 8), incl. bitshift | ✅ supported (Phase C) — byte-exact vs sph2pipe (real CALLHOME) |
| shorten QLPC (LPC) blocks           | ✅ supported (Phase C) — byte-exact vs shorten encoder + ffmpeg (orders 1–20) |

Adding a coding means registering a decoder in `desphere/codecs.py`; until then
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

## Rust, WASM, and consumers

The Python in `src/desphere` is the reference **spec**; [`rust/`](rust/) is a
Rust port that reproduces it **bit-for-bit** (same fixtures), for speed and for
the web. It builds three ways from one crate:

- a **Rust library** — a Rust client (praatfan is a likely consumer) imports it
  via a path/git dependency;
- **WASM** (`wasm-pack build rust --target web --features wasm`) — a WASM web app
  and the `web/` page consume it; nothing is sent to a server;
- a **Python extension** `desphere-native` (pyo3/maturin) — the optional
  `desphere[fast]` accelerator above.

Because the consumers live in the same `ucpresearch` org, they depend on desphere
directly (path/git); publishing to **crates.io / npm is not required** (and is
skipped). **PyPI** is the one registry we target (the pure-Python `desphere`,
plus the optional `desphere-native` wheels).

## Development

The virtualenv lives **outside** the (Syncthing-synced) repo and is symlinked in:

```bash
uv venv ~/local/scr/venvs/desphere
ln -s ~/local/scr/venvs/desphere .venv
uv pip install -e ".[dev]"
pytest

# Rust port:
cd rust && cargo test            # byte-exact vs the same fixtures
```

## Roadmap

- **Phase A** (done): SPHERE header + 16/32-bit PCM, lossless.
- **Phase B** (done): μ-law / a-law decode (ITU-T G.711).
- **Phase C** (done): embedded-shorten of 16-bit PCM, lossless μ-law (type 8,
  including the non-linear BITSHIFT remap), and QLPC (LPC) blocks — validated
  byte-for-byte vs ffmpeg / sph2pipe / the `shorten` encoder on real and
  synthetic streams, mono and stereo. Remaining (low priority): 8/24-bit linear
  PCM. See `docs/STATUS.md` and `docs/SHORTEN.md`.
- **Eventually → Rust** (for a Rust client / WASM, and for speed), mirroring
  `praatfan-core-clean`'s Python-first-then-Rust path. The Python implementation
  stays as the readable reference. Porting guidance: `docs/RUST_PORT.md`.
