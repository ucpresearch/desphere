//! Minimal canonical RIFF/WAVE (PCM) writer — Rust twin of `src/desphere/wav.py`.
//! Emits the standard 44-byte header (RIFF / `fmt ` / `data`) + little-endian PCM.

use crate::error::DecodeError;

const PCM_FORMAT: u16 = 1;

/// Build a canonical PCM WAV. `data` must already be little-endian interleaved
/// PCM at `bits_per_sample`.
pub fn write_wav(
    channels: u16,
    sample_rate: u32,
    bits_per_sample: u16,
    data: &[u8],
) -> Result<Vec<u8>, DecodeError> {
    if bits_per_sample & 7 != 0 {
        return Err(DecodeError::Corrupt(format!(
            "bits_per_sample must be a multiple of 8, got {bits_per_sample}"
        )));
    }
    let bytes_per_sample = (bits_per_sample / 8) as u32;
    let block_align = channels as u32 * bytes_per_sample; // <= 65535*4, fits u32
                                                          // u64 math so the size checks are real on 32-bit targets (wasm32: usize=u32).
    let byte_rate = sample_rate as u64 * block_align as u64;
    if byte_rate > u32::MAX as u64 {
        return Err(DecodeError::Corrupt(
            "WAV byte_rate exceeds 32-bit field".into(),
        ));
    }
    let data_size = data.len();
    let pad = data_size & 1; // data chunk must be word-aligned

    let riff_size = 4u64 + (8 + 16) + (8 + data_size as u64 + pad as u64);
    if riff_size > 0xFFFF_FFFF {
        return Err(DecodeError::Corrupt(format!(
            "output exceeds the 4 GB RIFF/WAV size limit ({data_size} bytes of PCM)"
        )));
    }

    let mut out = Vec::with_capacity(44 + data_size + pad);
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&(riff_size as u32).to_le_bytes());
    out.extend_from_slice(b"WAVE");
    out.extend_from_slice(b"fmt ");
    out.extend_from_slice(&16u32.to_le_bytes()); // fmt chunk size
    out.extend_from_slice(&PCM_FORMAT.to_le_bytes());
    out.extend_from_slice(&channels.to_le_bytes());
    out.extend_from_slice(&sample_rate.to_le_bytes());
    out.extend_from_slice(&(byte_rate as u32).to_le_bytes());
    out.extend_from_slice(&(block_align as u16).to_le_bytes());
    out.extend_from_slice(&bits_per_sample.to_le_bytes());
    out.extend_from_slice(b"data");
    out.extend_from_slice(&(data_size as u32).to_le_bytes());
    out.extend_from_slice(data);
    if pad == 1 {
        out.push(0);
    }
    Ok(out)
}
