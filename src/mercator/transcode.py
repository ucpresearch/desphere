"""High-level SPHERE -> WAV orchestration."""

from __future__ import annotations

from .codecs import resolve_codec
from .errors import SphereHeaderError
from .sphere import SphereHeader
from .wav import write_wav


def read_sphere(path) -> "tuple[SphereHeader, bytes]":
    """Parse a SPHERE file, returning ``(header, raw_audio_bytes)``."""
    return SphereHeader.from_file(path)


def transcode(header: SphereHeader, data: bytes, out) -> None:
    """Decode ``data`` per ``header`` and write a PCM WAV to stream ``out``.

    Validates that the payload is at least as long as the header claims; a
    short payload is a hard error (we will not pad audio with silence). Any
    trailing bytes beyond the declared sample count (padding, seek tables) are
    ignored for PCM.
    """
    expected = header.expected_data_bytes
    if len(data) < expected:
        raise SphereHeaderError(
            f"audio payload truncated: header declares {expected} bytes "
            f"({header.sample_count} samples x {header.channel_count} ch x "
            f"{header.sample_n_bytes} byte), but only {len(data)} bytes present"
        )
    if len(data) > expected:
        data = data[:expected]

    codec = resolve_codec(header)
    bits_per_sample, pcm = codec.decode(header, data)

    write_wav(
        out,
        channels=header.channel_count,
        sample_rate=header.sample_rate,
        bits_per_sample=bits_per_sample,
        data=pcm,
    )


def sph_to_wav(in_path, out) -> SphereHeader:
    """Transcode a SPHERE file at ``in_path`` to WAV stream ``out``.

    Returns the parsed header (handy for callers/CLI reporting).
    """
    header, data = read_sphere(in_path)
    transcode(header, data, out)
    return header
