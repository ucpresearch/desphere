# desphere — status & handoff

Snapshot for resuming work in a fresh session. Read this + `CLAUDE.md` +
`docs/SHORTEN.md` + `memories/MEMORY.md` to get oriented.

## What desphere is

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
| μ-law embedded-shorten **with bitshift** | ✅ vs sph2pipe (real CALLHOME, 14.4M samples) + shorten encoder (shift 0–3,12) |
| shorten QLPC blocks | ✅ vs shorten encoder + ffmpeg (orders 1–20) |

56 tests pass (`pytest`). All "✅" verified byte-for-byte against a black-box
oracle (never reading decoder source). A multi-agent review (see git log) then
hardened the fail-loud paths: a v2-only version gate, header/blocksize/bitshift
sanity caps (no decode-hang on corrupt input), a decoded-sample-count
cross-check, EOF→`DesphereError`, a 4 GB WAV-size guard, and atomic CLI output.

## type-8 + BITSHIFT — SOLVED

Loud real speech (CALLHOME `LDC96S34`) shorten-encodes μ-law with `FN_BITSHIFT`.
The fix: bitshift on type-8 is **not** a linear shift — it's a piecewise-linear
remap in mu-law **magnitude-code** space (slope `2^shift`, halving at each 16-code
segment boundary). Closed form + derivation in `docs/SHORTEN.md` → "Type 8 +
BITSHIFT — SOLVED". Byte-exact vs `sph2pipe` on the full CALLHOME file (both
channels). Also disproved the old red herring: the `v→μ-law` table was always
correct (it's the exact G.711 sort order across all 256 codes).

## QLPC — SOLVED

No `.sph` in the corpus uses QLPC (sph2pipe/NIST default to polynomial DIFF), so
we built the black-box `shorten` **encoder** (`oracles/build_shorten.sh`,
compiled never-reading-source) to synthesize QLPC streams from known input and
reverse-engineered the decode byte-exact (orders 1–20, vs the encoder + ffmpeg).
Algorithm in `docs/SHORTEN.md` → "QLPC blocks"; committed synthetic fixture
(`tools/make_qlpc_fixture.py`, `tests/test_qlpc.py`). The same encoder let us
push bitshift to 3/12 on nonzero codes, confirming the derived `a_j` formula and
removing the old shift≥3 fail-loud guard.

## What's left

- **8-bit / 24-bit linear PCM**: no such file in the corpus, and the sign/packing
  conventions are genuinely ambiguous; common 8-bit SPHERE is μ-law/a-law (already
  supported). Could synthesize + check against ffmpeg, but that only proves
  self-consistency, not the real-corpus convention. Low priority.

All shorten paths now work: PCM-shorten, μ-law-shorten (type 8) with/without
bitshift, and QLPC.

## Key files

```
src/desphere/
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
- `oracles/shorten` — the **encoder** (build via `oracles/build_shorten.sh`), used
  to synthesize QLPC + high-bitshift test files; also a 2nd decoder via `-x`.
- system `ffmpeg` — PCM-shorten + plain PCM/G.711 + QLPC (not type-8 ulaw-shorten).

Real corpus `.sph` files (license-restricted) live in `local-fixtures/`
(gitignored, synced): `sph2pipe/` (the 123_* test set), `timit/`, `ldc/`.

Dev decoders/experiments are in `scratch/` (gitignored, synced):
`shn_decode.py` (standalone reference decoder used during reverse-engineering),
`shn_probe.py` (encoder probe), `build_w_decode.sh`.

## How to run / develop

```bash
# venv lives OUT of the synced repo, symlinked in (see CLAUDE.md):
uv venv ~/local/scr/venvs/desphere --python 3.12
ln -s ~/local/scr/venvs/desphere .venv
VIRTUAL_ENV=$HOME/local/scr/venvs/desphere uv pip install -e ".[dev]"
.venv/bin/python -m pytest

# transcode:
.venv/bin/sph2wav input.sph output.wav
```

## Roadmap

- **Now → Python.** Develop and debug in Python (this repo). Keep the Python
  implementation as the readable reference and for most use — it stays.
- **Next (optional, low priority):** 8/24-bit linear PCM (see above).
- **Eventually → Rust** (for `formantwise-pipe` / WASM, and for speed), mirroring
  `praatfan-core-clean`'s Python-first-then-Rust approach. The Python decoder is
  the spec the Rust port validates against; both check against the same oracle
  outputs / committed fixtures. Rust also fixes the perf gap (the pure-Python
  shorten decoder is slow on multi-minute files — CALLHOME's 14 M samples take
  minutes). Concrete porting guidance — integer widths, shift/division
  semantics, EOF/overflow policy, fixture-based validation — is in
  `docs/RUST_PORT.md`.
