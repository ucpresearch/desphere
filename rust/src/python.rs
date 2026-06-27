//! Python bindings (pyo3) — thin wrappers over the pure-Rust core, built with
//! maturin into the extension module `desphere_native`.
//!
//! Clean-room provenance: this only re-exposes `desphere`'s own functions (a
//! translation of the MIT Python reference in ../src/desphere, built from public
//! NIST/ITU/TR.156 specs + black-box oracle testing — no GPL/LGPL source was
//! ever read). See ../../PROVENANCE.md.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyBytes;

fn to_py(e: crate::DecodeError) -> PyErr {
    PyValueError::new_err(e.to_string())
}

/// Transcode a NIST SPHERE file (bytes) to RIFF/WAV bytes.
#[pyfunction]
fn transcode<'py>(py: Python<'py>, sph: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    let wav = crate::transcode(sph).map_err(to_py)?;
    Ok(PyBytes::new(py, &wav))
}

/// Decode the payload to interleaved little-endian PCM (the WAV data chunk).
#[pyfunction]
fn decode_pcm<'py>(py: Python<'py>, sph: &[u8]) -> PyResult<Bound<'py, PyBytes>> {
    let (header, data) = crate::sphere::SphereHeader::read(sph).map_err(to_py)?;
    let (_bits, pcm) = crate::decode_payload(&header, data).map_err(to_py)?;
    Ok(PyBytes::new(py, &pcm))
}

/// Codec-level kernels, so the Python streaming API accelerates too. These do
/// the heavy number-crunching only and return PCM bytes; the Python codecs keep
/// their (typed) header cross-checks around these.

/// Decode an embedded-shorten stream to LE 16-bit PCM (no header cross-checks).
/// Returns `(channel_count, is_ulaw, pcm_bytes)`.
#[pyfunction]
fn shorten_to_pcm<'py>(
    py: Python<'py>,
    stream: &[u8],
) -> PyResult<(usize, bool, Bound<'py, PyBytes>)> {
    let (nchan, is_ulaw, pcm) = crate::codecs::shorten_to_pcm(stream).map_err(to_py)?;
    Ok((nchan, is_ulaw, PyBytes::new(py, &pcm)))
}

/// Expand G.711 companded bytes to LE 16-bit PCM (`alaw` = a-law, else mu-law).
#[pyfunction]
fn g711_expand<'py>(py: Python<'py>, data: &[u8], alaw: bool) -> PyResult<Bound<'py, PyBytes>> {
    Ok(PyBytes::new(py, &crate::codecs::g711_expand(data, alaw)))
}

#[pymodule]
fn desphere_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(transcode, m)?)?;
    m.add_function(wrap_pyfunction!(decode_pcm, m)?)?;
    m.add_function(wrap_pyfunction!(shorten_to_pcm, m)?)?;
    m.add_function(wrap_pyfunction!(g711_expand, m)?)?;
    Ok(())
}
