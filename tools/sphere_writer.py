"""Write NIST SPHERE files from raw PCM samples.

This is *tooling*, not part of the desphere library (desphere only reads
SPHERE). It exists so we can synthesize a whole zoo of test fixtures from a
known signal — every byte order, bit depth, channel count — without needing
real corpus files. Built from the public NIST header description only.

For codings we cannot synthesize by hand (mu-law/a-law/shorten), see
``make_fixtures.py``, which drives external encoders (sox / ffmpeg / shorten)
as black-box binaries.
"""

from __future__ import annotations

import struct
from typing import List, Sequence

HEADER_SIZE = 1024

# byte_format -> ('big'|'little') for struct packing of integer samples
_ORDER = {"01": "little", "10": "big", "1": "little"}


def build_sphere_header(
    *,
    sample_count: int,
    sample_rate: int,
    channel_count: int,
    sample_n_bytes: int,
    sample_byte_format: str,
    sample_coding: str = "pcm",
    sample_sig_bits: int | None = None,
    header_size: int = HEADER_SIZE,
) -> bytes:
    """Return a padded ``header_size``-byte NIST SPHERE header."""
    if sample_sig_bits is None:
        sample_sig_bits = sample_n_bytes * 8

    lines = ["NIST_1A", str(header_size)]
    # -i integer, -s<N> string. Field order is not significant to parsers.
    lines.append(f"sample_count -i {sample_count}")
    lines.append(f"sample_rate -i {sample_rate}")
    lines.append(f"channel_count -i {channel_count}")
    lines.append(f"sample_n_bytes -i {sample_n_bytes}")
    lines.append(f"sample_byte_format -s{len(sample_byte_format)} {sample_byte_format}")
    lines.append(f"sample_sig_bits -i {sample_sig_bits}")
    lines.append(f"sample_coding -s{len(sample_coding)} {sample_coding}")
    lines.append("end_head")

    text = "\n".join(lines) + "\n"
    raw = text.encode("ascii")
    if len(raw) > header_size:
        raise ValueError(
            f"header is {len(raw)} bytes, exceeds header_size {header_size}"
        )
    return raw + b" " * (header_size - len(raw))


def pack_pcm(samples: Sequence[int], sample_n_bytes: int, byte_order: str) -> bytes:
    """Pack interleaved integer ``samples`` into raw PCM bytes."""
    order = _ORDER[byte_order]
    out = bytearray()
    for s in samples:
        out += int(s).to_bytes(sample_n_bytes, order, signed=True)
    return bytes(out)


def write_sphere_pcm(
    path,
    samples: Sequence[int],
    *,
    sample_rate: int,
    channel_count: int = 1,
    sample_n_bytes: int = 2,
    sample_byte_format: str = "01",
    sample_coding: str = "pcm",
    header_size: int = HEADER_SIZE,
) -> None:
    """Write a PCM SPHERE file with interleaved integer ``samples``."""
    if len(samples) % channel_count != 0:
        raise ValueError("len(samples) must be a multiple of channel_count")
    sample_count = len(samples) // channel_count
    header = build_sphere_header(
        sample_count=sample_count,
        sample_rate=sample_rate,
        channel_count=channel_count,
        sample_n_bytes=sample_n_bytes,
        sample_byte_format=sample_byte_format,
        sample_coding=sample_coding,
        header_size=header_size,
    )
    body = pack_pcm(samples, sample_n_bytes, sample_byte_format)
    with open(path, "wb") as f:
        f.write(header)
        f.write(body)


def write_sphere_raw(
    path,
    payload: bytes,
    *,
    sample_count: int,
    sample_rate: int,
    channel_count: int,
    sample_n_bytes: int,
    sample_byte_format: str,
    sample_coding: str,
    header_size: int = HEADER_SIZE,
) -> None:
    """Write a SPHERE file with an already-encoded ``payload`` (e.g. G.711)."""
    header = build_sphere_header(
        sample_count=sample_count,
        sample_rate=sample_rate,
        channel_count=channel_count,
        sample_n_bytes=sample_n_bytes,
        sample_byte_format=sample_byte_format,
        sample_coding=sample_coding,
        header_size=header_size,
    )
    with open(path, "wb") as f:
        f.write(header)
        f.write(payload)


def sine_samples(
    n_frames: int,
    sample_rate: int,
    *,
    freq: float = 220.0,
    amplitude: int = 10000,
    channels: int = 1,
) -> List[int]:
    """Deterministic interleaved integer sine wave (one freq per channel)."""
    import math

    out: List[int] = []
    for i in range(n_frames):
        for ch in range(channels):
            f = freq * (ch + 1)
            out.append(int(round(amplitude * math.sin(2 * math.pi * f * i / sample_rate))))
    return out
