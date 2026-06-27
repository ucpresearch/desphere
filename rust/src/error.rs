//! Error type for the desphere decoder.
//!
//! Mirrors the Python exception hierarchy (`DesphereError` / `SphereHeaderError`
//! vs `UnsupportedFormat` / `UnsupportedCoding`) collapsed to the two families
//! the decoder needs: corrupt/truncated input vs a structurally-valid-but-
//! unsupported layout. WASM-friendly: the decoder returns these, never panics.

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DecodeError {
    /// Bad magic, truncation, or structural corruption (Python `DesphereError` /
    /// `SphereHeaderError`).
    Corrupt(String),
    /// A structurally valid field describes a layout we have not validated
    /// (Python `UnsupportedFormat` / `UnsupportedCoding`).
    Unsupported(String),
}

impl fmt::Display for DecodeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DecodeError::Corrupt(m) | DecodeError::Unsupported(m) => f.write_str(m),
        }
    }
}

impl std::error::Error for DecodeError {}
