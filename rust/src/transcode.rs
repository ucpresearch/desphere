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
    // Range-check rather than silently truncate (`as u16`/`as u32`) into the WAV
    // header — fail loud on a header that can't be represented.
    let channels = u16::try_from(header.channel_count()?)
        .map_err(|_| DecodeError::Corrupt("channel_count too large for WAV".into()))?;
    let sample_rate = u32::try_from(header.sample_rate()?)
        .map_err(|_| DecodeError::Corrupt("sample_rate too large for WAV".into()))?;
    wav::write_wav(channels, sample_rate, bits, &pcm)
}
