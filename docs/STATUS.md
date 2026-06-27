# mercator — status & handoff

Snapshot for resuming work in a fresh session. Read this + `CLAUDE.md` +
`docs/SHORTEN.md` + `memories/MEMORY.md` to get oriented.

## What mercator is

MIT-licensed, **clean-room** NIST SPHERE → RIFF/WAV transcoder. Reads `.sph`
(TIMIT, WSJ, Switchboard, CALLHOME, …), optionally shorten-compressed, and emits
WAV. CLI: `sph2wav`. Pure Python today (zero deps); see "Roadmap" for the Rust
intent.

## Capability matrix (everything ✅ is byte-exact vs an oracle)

| Coding | Status |
|--------|--------|
| PCM 16/32-bit, byte order `01`/`10`, mono & stereo | ✅ (incl. real TIMIT) |
| PCM 8-bit / 24-bit | ⛔ `UnsupportedFormat` (sign/packing unvalidated) |
| μ-law / a-law (G.711) | ✅ (incl. real CALLHOME stereo, sph2pipe a-law) |
| PCM embedded-shorten (16-bit) | ✅ vs ffmpeg, mono & stereo |
| μ-law embedded-shorten (type 8), **no bitshift** | ✅ vs w_decode + sph2pipe |
| μ-law embedded-shorten **with bitshift** | ⛔ fail-loud — **the open problem** |
| shorten QLPC blocks | ⛔ `UnsupportedFormat` |

39 tests pass (`pytest`). All "✅" verified byte-for-byte against a black-box
oracle (never reading decoder source).

## The one open problem: type-8 + BITSHIFT

Loud real speech (CALLHOME, Switchboard) shorten-encodes μ-law with `FN_BITSHIFT`,
and our reconstruction diverges. Full evidence + how to resume in
`docs/SHORTEN.md` → "OPEN PROBLEM". Short version: the true index can be **odd**
while `v << bitshift` is always even, so the bitshift semantics and the
full-range `v→μ-law` table are entangled and need disentangling against the
`sph2pipe` oracle (which decodes these files fine). Until solved we **fail loud**.

This is the natural next task. It does **not** block the common cases (plain
TIMIT/CALLHOME μ-law, PCM-shorten, quiet μ-law-shorten all work).

## Key files

```
src/mercator/
  sphere.py     SPHERE header parser
  codecs.py     capability gate (resolve_codec) + Pcm/Ulaw/Alaw/Shorten codecs
  g711.py       ITU-T G.711 μ-law/a-law tables
  shorten.py    embedded-shorten v2 decoder  <-- the algorithm lives here
  wav.py        RIFF/PCM writer
  transcode.py  orchestration
  cli.py        sph2wav
docs/SHORTEN.md   clean-room shorten algorithm reference (READ THIS to resume)
tests/            pytest; test_shorten_local.py gates on local-fixtures/
```

## Validation / oracles (black-box only — never read their source)

Binaries are in `oracles/` (gitignored, synced; see `oracles/README.md`):
- `oracles/sph2pipe` — robust, decodes everything incl. CALLHOME type-8+bitshift.
- `oracles/w_decode` — type-8 on small files (corrupts on large ones).
- system `ffmpeg` — PCM-shorten + plain PCM/G.711 (not type-8 ulaw-shorten).

Real corpus `.sph` files (license-restricted) live in `local-fixtures/`
(gitignored, synced): `sph2pipe/` (the 123_* test set), `timit/`, `ldc/`.

Dev decoders/experiments are in `scratch/` (gitignored, synced):
`shn_decode.py` (standalone reference decoder used during reverse-engineering),
`shn_probe.py` (encoder probe), `build_w_decode.sh`.

## How to run / develop

```bash
# venv lives OUT of the synced repo, symlinked in (see CLAUDE.md):
uv venv ~/local/scr/venvs/mercator --python 3.12
ln -s ~/local/scr/venvs/mercator .venv
VIRTUAL_ENV=$HOME/local/scr/venvs/mercator uv pip install -e ".[dev]"
.venv/bin/python -m pytest

# transcode:
.venv/bin/sph2wav input.sph output.wav
```

## Roadmap

- **Now → Python.** Develop and debug in Python (this repo). Keep the Python
  implementation as the readable reference and for most use — it stays.
- **Next acoustic-feature work: type-8 + bitshift** (see above).
- **Eventually → Rust.** Port to a Rust library (mirroring `praatfan-core-clean`'s
  Python-first-then-Rust approach) so that **`formantwise-core` can import it**.
  The Python decoder is the spec the Rust port validates against; both check
  against the same oracle outputs. Rust also fixes the perf gap (the pure-Python
  shorten decoder is slow on multi-minute files — CALLHOME's 14 M samples take
  minutes).
