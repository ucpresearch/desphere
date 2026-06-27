# PROVENANCE — clean-room record for desphere

This document is the paper trail establishing that **desphere contains no
GPL/LGPL-derived code** and may be licensed under the MIT License. It applies to
both the Python reference (`src/desphere/`) and the Rust port (`rust/`).

## Summary

desphere is a NIST SPHERE → RIFF/WAV transcoder (PCM, G.711 μ-law/a-law, and
embedded-shorten v2 including QLPC and lossless μ-law type-8 with bitshift). It
was implemented **only** from public specifications and **black-box** testing of
existing tools. **No GPL/LGPL source code was ever read** at any point.

Copyright protects source code — not file formats, facts, or algorithms (the
idea/expression dichotomy). Building a decoder from a published format/algorithm
description, and checking it by comparing the *output* of existing binaries, does
not create a derivative work of those binaries.

## Permitted sources actually used

- **NIST SPHERE format** — public NIST documentation (the ASCII `NIST_1A` header,
  typed object fields). Used for `sphere.py` / `rust/src/sphere.rs`.
- **ITU-T G.711** — the public telecom standard defining the μ-law / a-law
  companding tables. Used for `g711.py` / `rust/src/g711.rs`.
- **Tony Robinson (1994), _SHORTEN: Simple lossless and near-lossless waveform
  compression_, CUED/F-INFENG/TR.156** — the published academic report describing
  the shorten algorithm (Rice/uvar coding, polynomial vs LPC prediction). A copy
  was read; it describes the *algorithm*, not anyone's source code. Used for the
  shorten decoder design.
- **Microsoft/IBM RIFF/WAVE** — the public container spec. Used for `wav.py` /
  `rust/src/wav.rs`.
- **Black-box oracle testing** — `ffmpeg`, `sox`, `sph2pipe`, NIST `w_decode`, and
  the `shorten` encoder were run **as binaries**; only their *output bytes* were
  compared against desphere's output. Running a binary is not reading its source.

## Never read (hard rule, no exceptions)

- FFmpeg's NIST/shorten decoder (LGPL)
- the original `shorten` C sources and `sph2pipe` sources
- any GPL/LGPL codebase, **including the author's own praatfan GPL siblings**

The `shorten` **encoder** (Tony Robinson's `drtonyr/shorten`, a non-FOSS license)
was *downloaded and compiled* to generate test fixtures and act as a second
black-box oracle (`oracles/build_shorten.sh`). Its `.c/.h` source was **never
opened**; the build needed only a modern-stdarg shim written from scratch. The
build script documents this. Compiling ≠ reading source.

## How the hard parts were derived (reverse-engineering, from oracle output only)

The non-obvious shorten details were recovered by comparing reconstructed values
to oracle output, never by reading a decoder:

- The Rice parameter quirk (`k = energy + 1`), the running-mean offset, and bit
  order: validated byte-exact against ffmpeg/sph2pipe output.
- **Type-8 μ-law + BITSHIFT**: derived as a code-space remap by tabulating
  `sph2pipe -u` (true μ-law bytes) against desphere's reconstructed values; the
  closed form was confirmed by mu-law segment geometry (a G.711 fact) and
  validated byte-exact on real CALLHOME audio. See `docs/SHORTEN.md`.
- **QLPC**: no corpus file uses it, so the `shorten` encoder (compiled, not read)
  was driven on known synthetic input to produce QLPC streams, and the decode
  was reverse-engineered by matching desphere's output to the known input and to
  `ffmpeg`/`shorten -x`. See `docs/SHORTEN.md` → "QLPC blocks".

The git history is itself part of the trail: commits record the oracle
comparisons, the "never reading decoder source" methodology, and that the encoder
was "compiled, never reading source."

## The Rust port

`rust/` is a direct translation of desphere's **own MIT Python** (`src/desphere/`,
which is the spec), guided by `docs/RUST_PORT.md`. It is validated bit-for-bit
against the same committed fixtures and shown byte-identical to the Python
`sph2wav`. No GPL/LGPL source — and no third-party Rust decoder — was consulted.
The `praatfan-core-clean` sibling was used only for high-level project *layout*
conventions (a `rust/` crate with `examples/`, pyo3, maturin); its source was not
read.

## Licensing

desphere is MIT-licensed (`LICENSE`). The permitted sources above impose no
copyleft obligation on an independent implementation: file formats and algorithms
are not copyrightable, ITU/NIST/RIFF specs are public standards, and black-box
output comparison is not derivation. The non-FOSS `shorten` encoder is a build/
test tool only — it is not linked into, vendored by, or read for desphere.
