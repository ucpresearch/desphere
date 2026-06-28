# Changelog

All notable changes to desphere (the Python package and the Rust crate) are
recorded here. Format loosely follows [Keep a Changelog]; versions are shared
across the Python `desphere`, the Rust crate `desphere`, and the pyo3 module
`desphere-native`.

## [Unreleased]

### Web page (`web/`, client-side sph2wav)
- **Multi-file**: drop many `.sph` at once — one file downloads directly, several
  bundle into a single `.zip` (via vendored [fflate], MIT). Per-file errors are
  reported; successes still come through.
- **FLAC output** alongside WAV, encoded in-browser (lossless) via vendored
  [libflac.js] (MIT wrapper / Xiph BSD libFLAC), loaded lazily only when chosen;
  works in Chrome/Firefox/Safari. The encode path is oracle-tested (WAV → FLAC →
  ffmpeg decode → byte-identical PCM). All assets vendored — nothing fetched at
  runtime; nothing leaves the browser.
- Added a favicon, and a hint that the file chooser is the reliable input where a
  browser blocks file drag-drop (some Firefox/Linux setups reject file drops at
  the OS level regardless of the page).

[fflate]: https://github.com/101arrowz/fflate
[libflac.js]: https://github.com/mmig/libflac.js

## [0.1.0] — 2026-06-28 (first release)

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
- Python package `desphere` with the `sph2wav` CLI (pure Python, zero deps). The
  whole decode path — the streaming `transcode()`, the one-shot `transcode_bytes()`,
  and the CLI — transparently uses the optional Rust accelerator when installed
  (`pip install desphere[fast]` → `desphere-native`) and falls back to pure Python
  otherwise — same bytes either way. The accelerator delegates the heavy kernels
  (shorten decode, G.711 expansion); typed error checks stay in Python.
- Rust crate `desphere` (dependency-free core); Rust clients (e.g. praatfan)
  import it via a path/git dependency.
- WASM bindings via `wasm-bindgen` (opt-in `wasm` feature) + a self-contained
  client-side `sph2wav` web page (`web/`, deployed to GitHub Pages) — converts in
  the browser, nothing uploaded.
- Python-native module `desphere-native` via pyo3/maturin (opt-in `python`
  feature).
- The CLI and web page pass a stray RIFF/WAV input through unchanged, with a
  warning (the library API stays strict: SPHERE in, fail loud).
- Not published to crates.io / npm (consumers depend on the repo directly); PyPI
  is the target registry.

[Keep a Changelog]: https://keepachangelog.com/en/1.1.0/
