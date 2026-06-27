//! desphere — clean-room NIST SPHERE (and Shorten) → RIFF/WAV transcoder.
//!
//! Rust port of the Python reference in `../src/desphere`. The Python is the
//! spec; this reproduces its output bit-for-bit (validated against the same
//! committed fixtures). For `formantwise-pipe` to import, and for WASM/speed.
//! See `../docs/RUST_PORT.md`.
//!
//! Status: core shorten decoder + bit reader + G.711 ported & fixture-validated.
//! Next: SPHERE header parser, capability gate, WAV writer, and pyo3/wasm
//! bindings (mirroring praatfan-core-clean's layout).

pub mod bitreader;
pub mod error;
pub mod g711;
pub mod shorten;

pub use error::DecodeError;
pub use shorten::{decode as decode_shorten, Kind};
