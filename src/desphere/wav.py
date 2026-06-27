"""Minimal canonical RIFF/WAVE (PCM) writer.

Pure stdlib ``struct``; emits the standard 44-byte header (RIFF / ``fmt `` /
``data``) with little-endian integer PCM samples. The WAV format is an open,
publicly documented container (Microsoft/IBM RIFF spec); no GPL source involved.
"""

from __future__ import annotations

import struct

from .errors import DesphereError

PCM_FORMAT = 1  # WAVE_FORMAT_PCM


def write_wav(
    out,
    *,
    channels: int,
    sample_rate: int,
    bits_per_sample: int,
    data: bytes,
) -> None:
    """Write a canonical PCM WAV to the binary stream ``out``.

    ``data`` must already be little-endian, interleaved PCM at the given
    ``bits_per_sample``.
    """
    if bits_per_sample % 8 != 0:
        raise ValueError(f"bits_per_sample must be a multiple of 8, got {bits_per_sample}")

    bytes_per_sample = bits_per_sample // 8
    block_align = channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    data_size = len(data)
    pad = data_size & 1  # data chunk must be word-aligned

    riff_size = 4 + (8 + 16) + (8 + data_size + pad)

    # RIFF/WAV stores sizes in unsigned 32-bit fields. Fail loud BEFORE writing
    # any bytes (so we never leave a truncated "RIFF" stub) rather than letting
    # struct.pack raise an opaque struct.error mid-write. riff_size >= data_size,
    # so this one check covers both 32-bit size fields.
    if riff_size > 0xFFFFFFFF:
        raise DesphereError(
            "output exceeds the 4 GB RIFF/WAV size limit "
            f"({data_size} bytes of PCM overflow the 32-bit size fields)"
        )

    out.write(b"RIFF")
    out.write(struct.pack("<I", riff_size))
    out.write(b"WAVE")

    out.write(b"fmt ")
    out.write(
        struct.pack(
            "<IHHIIHH",
            16,               # fmt chunk size
            PCM_FORMAT,       # audio format
            channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
        )
    )

    out.write(b"data")
    out.write(struct.pack("<I", data_size))
    out.write(data)
    if pad:
        out.write(b"\x00")
