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
        "ulaw" | "mu-law" | "mulaw" => decode_g711(h, data, &g711::ulaw_table(), "ulaw"),
        "alaw" | "a-law" => decode_g711(h, data, &g711::alaw_table(), "alaw"),
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

fn decode_g711(
    h: &SphereHeader,
    data: &[u8],
    table: &[i16; 256],
    name: &str,
) -> Result<(u16, Vec<u8>), DecodeError> {
    if h.sample_n_bytes()? != 1 {
        return Err(DecodeError::Unsupported(format!(
            "{name} expects 1-byte samples, got sample_n_bytes={}",
            h.sample_n_bytes()?
        )));
    }
    let mut out = Vec::with_capacity(data.len() * 2);
    for &b in data {
        out.extend_from_slice(&table[b as usize].to_le_bytes());
    }
    Ok((16, out))
}

fn decode_shorten(h: &SphereHeader, data: &[u8]) -> Result<(u16, Vec<u8>), DecodeError> {
    let (values, kind, nchan) = shorten::decode(data)?;
    if nchan as i64 != h.channel_count()? {
        return Err(DecodeError::Unsupported(format!(
            "shorten channel count {nchan} disagrees with SPHERE header channel_count {}",
            h.channel_count()?
        )));
    }
    let expected = (h.sample_count()? * nchan as i64) as usize;
    let values: Vec<i64> = if values.len() < expected {
        return Err(DecodeError::Corrupt(format!(
            "shorten stream decoded {} samples/channel, but the SPHERE header declares {} (truncated or QUIT came early)",
            values.len() / nchan,
            h.sample_count()?
        )));
    } else if values.len() > expected {
        values[..expected].to_vec()
    } else {
        values
    };

    match kind {
        shorten::Kind::Ulaw => {
            let table = g711::ulaw_table();
            let expanded: Vec<i16> = values.iter().map(|&v| table[(v as u8) as usize]).collect();
            Ok((16, pcm_table_to_le(&expanded)))
        }
        shorten::Kind::Pcm16 => {
            let clipped: Vec<i16> = values
                .iter()
                .map(|&v| v.clamp(-32768, 32767) as i16)
                .collect();
            Ok((16, pcm_table_to_le(&clipped)))
        }
    }
}
