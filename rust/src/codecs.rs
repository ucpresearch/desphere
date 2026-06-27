//! Sample-coding decoders + capability gate — Rust twin of `src/desphere/codecs.py`.
//!
//! `decode` is the single place that decides whether we can handle a file:
//! support the obvious lossless path, fail loud on anything unvalidated.

use crate::error::DecodeError;
use crate::sphere::SphereHeader;
use crate::{g711, shorten};

/// NIST `sample_byte_format` -> endianness of the stored samples.
fn byte_order(fmt: &str) -> Option<&'static str> {
    match fmt {
        "1" | "01" => Some("little"),
        "10" => Some("big"),
        _ => None,
    }
}

/// Reverse byte order within each `n_bytes`-wide sample for big-endian input.
fn to_little_endian(raw: &[u8], n_bytes: usize, order: &str) -> Vec<u8> {
    if n_bytes == 1 || order == "little" {
        return raw.to_vec();
    }
    let mut out = raw.to_vec();
    for chunk in out.chunks_exact_mut(n_bytes) {
        chunk.reverse();
    }
    out
}

fn pcm_table_to_le(values: &[i16]) -> Vec<u8> {
    let mut out = Vec::with_capacity(values.len() * 2);
    for &v in values {
        out.extend_from_slice(&v.to_le_bytes());
    }
    out
}

/// Decode a payload per its header. Returns `(bits_per_sample, little_endian_pcm)`.
pub fn decode(h: &SphereHeader, data: &[u8]) -> Result<(u16, Vec<u8>), DecodeError> {
    let coding = h.sample_coding();
    let tokens: Vec<String> = coding
        .split(',')
        .map(|t| t.trim().to_ascii_lowercase())
        .collect();
    let base = tokens[0].as_str();
    let compression = if tokens.len() > 1 && !tokens[1].is_empty() {
        Some(tokens[1].as_str())
    } else {
        None
    };

    if let Some(comp) = compression {
        if comp != "embedded-shorten-v2.00" {
            return Err(DecodeError::Unsupported(format!(
                "compressed coding {coding:?} not supported yet (compression: {comp:?})"
            )));
        }
        return decode_shorten(h, data);
    }

    match base {
        "pcm" => decode_pcm(h, data),
        "ulaw" | "mu-law" | "mulaw" => decode_g711(h, data, false),
        "alaw" | "a-law" => decode_g711(h, data, true),
        other => Err(DecodeError::Unsupported(format!(
            "sample_coding {other:?} not supported yet"
        ))),
    }
}

fn decode_pcm(h: &SphereHeader, data: &[u8]) -> Result<(u16, Vec<u8>), DecodeError> {
    let n = h.sample_n_bytes()? as usize;
    if n != 2 && n != 4 {
        return Err(DecodeError::Unsupported(format!(
            "{}-bit PCM not supported yet (supported: 16, 32 bit)",
            n * 8
        )));
    }
    let fmt = h.sample_byte_format();
    let order = byte_order(fmt).ok_or_else(|| {
        DecodeError::Unsupported(format!(
            "unrecognized sample_byte_format {fmt:?} (supported: '1', '01', '10')"
        ))
    })?;
    Ok(((n * 8) as u16, to_little_endian(data, n, order)))
}

/// Expand G.711 companded bytes to little-endian 16-bit PCM. The heavy kernel,
/// shared by the codec and the Python binding (`alaw` selects a-law vs mu-law).
pub fn g711_expand(data: &[u8], alaw: bool) -> Vec<u8> {
    let table = if alaw {
        g711::alaw_table()
    } else {
        g711::ulaw_table()
    };
    let mut out = Vec::with_capacity(data.len() * 2);
    for &b in data {
        out.extend_from_slice(&table[b as usize].to_le_bytes());
    }
    out
}

fn decode_g711(h: &SphereHeader, data: &[u8], alaw: bool) -> Result<(u16, Vec<u8>), DecodeError> {
    if h.sample_n_bytes()? != 1 {
        let name = if alaw { "alaw" } else { "ulaw" };
        return Err(DecodeError::Unsupported(format!(
            "{name} expects 1-byte samples, got sample_n_bytes={}",
            h.sample_n_bytes()?
        )));
    }
    Ok((16, g711_expand(data, alaw)))
}

/// Decode an embedded-shorten stream to little-endian 16-bit PCM, WITHOUT the
/// header cross-checks. Returns `(channel_count, is_ulaw, pcm)`. The heavy
/// kernel, shared by the codec and the Python binding; callers cross-check the
/// length/channels against their header.
pub fn shorten_to_pcm(data: &[u8]) -> Result<(usize, bool, Vec<u8>), DecodeError> {
    let (values, kind, nchan) = shorten::decode(data)?;
    let pcm = match kind {
        shorten::Kind::Ulaw => {
            let table = g711::ulaw_table();
            let expanded: Vec<i16> = values.iter().map(|&v| table[(v as u8) as usize]).collect();
            pcm_table_to_le(&expanded)
        }
        shorten::Kind::Pcm16 => {
            let clipped: Vec<i16> = values
                .iter()
                .map(|&v| v.clamp(-32768, 32767) as i16)
                .collect();
            pcm_table_to_le(&clipped)
        }
    };
    Ok((nchan, kind == shorten::Kind::Ulaw, pcm))
}

fn decode_shorten(h: &SphereHeader, data: &[u8]) -> Result<(u16, Vec<u8>), DecodeError> {
    let (nchan, _is_ulaw, pcm) = shorten_to_pcm(data)?;
    if nchan as i64 != h.channel_count()? {
        return Err(DecodeError::Unsupported(format!(
            "shorten channel count {nchan} disagrees with SPHERE header channel_count {}",
            h.channel_count()?
        )));
    }
    // Cross-check sample count on the emitted PCM (2 bytes/sample).
    let expected = (h.sample_count()? * nchan as i64) as usize * 2;
    if pcm.len() < expected {
        return Err(DecodeError::Corrupt(format!(
            "shorten stream decoded {} samples/channel, but the SPHERE header declares {} (truncated or QUIT came early)",
            pcm.len() / 2 / nchan,
            h.sample_count()?
        )));
    }
    let pcm = if pcm.len() > expected {
        pcm[..expected].to_vec()
    } else {
        pcm
    };
    Ok((16, pcm))
}
