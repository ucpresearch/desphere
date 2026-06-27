//! High-level SPHERE -> WAV orchestration — Rust twin of `src/desphere/transcode.py`.

use crate::codecs;
use crate::error::DecodeError;
use crate::sphere::SphereHeader;
use crate::wav;

/// Decode a payload to `(bits_per_sample, little_endian_pcm)`, validating the
/// payload length for non-compressed codings (mirrors the Python guard).
pub fn decode_payload(header: &SphereHeader, data: &[u8]) -> Result<(u16, Vec<u8>), DecodeError> {
    // Compressed iff a non-empty second token (so "pcm," is still plain PCM).
    let tokens: Vec<&str> = header.sample_coding().split(',').map(str::trim).collect();
    let compressed = tokens.len() > 1 && !tokens[1].is_empty();

    let data: &[u8] = if compressed {
        data
    } else {
        let expected = header.expected_data_bytes()?;
        if data.len() < expected {
            return Err(DecodeError::Corrupt(format!(
                "audio payload truncated: header declares {expected} bytes but only {} present",
                data.len()
            )));
        }
        &data[..expected]
    };
    codecs::decode(header, data)
}

/// Parse a full SPHERE file blob and transcode it to a WAV byte vector.
pub fn transcode(sph_bytes: &[u8]) -> Result<Vec<u8>, DecodeError> {
    let (header, data) = SphereHeader::read(sph_bytes)?;
    let (bits, pcm) = decode_payload(&header, data)?;
    wav::write_wav(
        header.channel_count()? as u16,
        header.sample_rate()? as u32,
        bits,
        &pcm,
    )
}
