# desphere (Rust)

Clean-room, dependency-free **NIST SPHERE (and Shorten) → RIFF/WAV** transcoder —
the Rust port of the Python reference in [`../src/desphere`](../src/desphere).
The Python is the spec; this reproduces its output **bit-for-bit**, validated
against the same committed fixtures.

```rust
let sph = std::fs::read("utt.sph")?;
let wav = desphere::transcode(&sph)?;   // RIFF/WAV bytes
std::fs::write("utt.wav", wav)?;
```

Supports PCM (16/32-bit, both byte orders), G.711 μ-law/a-law, and
embedded-shorten v2 — including **QLPC** (LPC) blocks and lossless **μ-law type-8
with the non-linear bitshift** remap. Unsupported/corrupt input fails loud
(`DecodeError`), never panics — safe for WASM.

## Build targets

```bash
cargo test                                   # core, byte-exact vs fixtures
wasm-pack build --target web --features wasm # WASM (rust/pkg/)
maturin develop -m pyproject.toml --features python   # Python module: desphere_native
```

The core library is **dependency-free**; the `wasm` (wasm-bindgen) and `python`
(pyo3) bindings are opt-in Cargo features that don't burden a plain Rust
dependant.

## Clean-room

Built only from public sources (NIST SPHERE docs, ITU-T G.711, Robinson 1994
TR.156) and black-box oracle testing — **no GPL/LGPL source was ever read**. See
[`../PROVENANCE.md`](../PROVENANCE.md). MIT-licensed.
