//! WebAssembly bindings (wasm-bindgen) — thin wrappers over the pure-Rust core.
//!
//! Clean-room provenance: this only re-exposes `desphere`'s own functions (a
//! translation of the MIT Python reference in ../src/desphere, built from public
//! specs + black-box oracle testing — no GPL/LGPL source was ever read). See
//! ../../PROVENANCE.md.
//!
//! Build:  wasm-pack build rust --target web --features wasm

use wasm_bindgen::prelude::*;

/// Transcode a NIST SPHERE file (bytes) to a RIFF/WAV byte array.
/// Throws a JS error (the precise fail-loud message) on malformed input.
#[wasm_bindgen]
pub fn transcode(sph: &[u8]) -> Result<Vec<u8>, JsError> {
    crate::transcode(sph).map_err(|e| JsError::new(&e.to_string()))
}

/// Decode the embedded-shorten / PCM / G.711 payload to interleaved little-endian
/// 16- or 32-bit PCM (the WAV data chunk, without the RIFF header). Returns the
/// PCM bytes; query bit depth via [`transcode`]'s WAV header if needed.
#[wasm_bindgen]
pub fn decode_pcm(sph: &[u8]) -> Result<Vec<u8>, JsError> {
    let (header, data) = crate::sphere::SphereHeader::read(sph).map_err(js)?;
    let (_bits, pcm) = crate::decode_payload(&header, data).map_err(js)?;
    Ok(pcm)
}

fn js(e: crate::DecodeError) -> JsError {
    JsError::new(&e.to_string())
}
