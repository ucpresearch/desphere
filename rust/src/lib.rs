//! desphere — clean-room NIST SPHERE (and Shorten) → RIFF/WAV transcoder.
//!
//! Rust port of the Python reference in `../src/desphere`. The Python is the
//! spec; this reproduces its output bit-for-bit (validated against the same
//! committed fixtures). For `formantwise-pipe` to import, and for WASM/speed.
//! See `../docs/RUST_PORT.md`.
//!
//! ```no_run
//! let sph = std::fs::read("utt.sph").unwrap();
//! let wav = desphere::transcode(&sph).unwrap();
//! std::fs::write("utt.wav", wav).unwrap();
//! ```
//!
//! Complete & fixture-validated: SPHERE header parser, capability gate (PCM
//! 16/32, G.711 mu-law/a-law, embedded-shorten incl. QLPC and type-8 bitshift),
//! WAV writer, end-to-end transcode, plus optional `wasm` (wasm-bindgen) and
//! `python` (pyo3) bindings. Corrupt input fails loud (`DecodeError`); the
//! decoder never panics (safe for WASM).

pub mod bitreader;
pub mod codecs;
pub mod error;
pub mod g711;
pub mod shorten;
pub mod sphere;
pub mod transcode;
pub mod wav;

#[cfg(feature = "wasm")]
pub mod wasm;

#[cfg(feature = "python")]
pub mod python;

pub use error::DecodeError;
pub use shorten::{decode as decode_shorten, Kind};
pub use sphere::SphereHeader;
pub use transcode::{decode_payload, transcode};
