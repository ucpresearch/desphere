# Changelog

All notable changes to desphere (the Python package and the Rust crate) are
recorded here. Format loosely follows [Keep a Changelog]; versions are shared
across the Python `desphere`, the Rust crate `desphere`, and the pyo3 module
`desphere-native`.

## [0.1.0] — first release

First public release. NIST SPHERE → RIFF/WAV transcoder, clean-room and
MIT-licensed (see `PROVENANCE.md`).

### Decoding (Python reference + Rust port, byte-for-byte identical)
- PCM 16/32-bit, byte order `01`/`10`, mono & multi-channel.
- G.711 μ-law / a-law (ITU-T G.711).
- Embedded-shorten v2:
  - 16-bit PCM (DIFF0–3, ZERO, VERBATIM, BLOCKSIZE).
  - Lossless μ-law (type 8), including the non-linear **BITSHIFT** code-space
    remap (validated on real CALLHOME audio).
  - **QLPC** (LPC-predicted) blocks (validated vs the shorten encoder + ffmpeg,
    orders 1–20, mono & stereo).
- Fail-loud on everything unvalidated (8/24-bit PCM, QLPC-less unknown codings,
  corrupt/truncated streams) — never emits a plausible-but-wrong WAV, never
  panics (safe for WASM).

### Packaging
- Python package `desphere` with the `sph2wav` CLI (pure Python, zero deps).
- Rust crate `desphere` (dependency-free core).
- WASM bindings via `wasm-bindgen` (opt-in `wasm` feature).
- Python-native module `desphere-native` via pyo3/maturin (opt-in `python`
  feature) for `formantwise-pipe` to import.

[Keep a Changelog]: https://keepachangelog.com/en/1.1.0/
