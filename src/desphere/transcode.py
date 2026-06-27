"""High-level SPHERE -> WAV orchestration."""

from __future__ import annotations

import io

from .codecs import resolve_codec
from .errors import DesphereError, SphereHeaderError
from .sphere import SphereHeader
from .wav import write_wav

# Optional Rust accelerator (pip install desphere[fast]). The pure-Python path
# below is the reference and always works; the native module just makes the slow
# path (shorten on large files) fast. Same byte-for-byte output.
try:
    import desphere_native as _native
except ImportError:  # pragma: no cover - native is optional
    _native = None


def read_sphere(path) -> "tuple[SphereHeader, bytes]":
    """Parse a SPHERE file, returning ``(header, raw_audio_bytes)``."""
    return SphereHeader.from_file(path)


def transcode_bytes(sph_bytes: bytes) -> bytes:
    """Transcode a whole SPHERE file (bytes) to WAV bytes.

    Uses the native (Rust) accelerator when installed, otherwise the pure-Python
    reference — identical output either way. Raises :class:`DesphereError` on
    malformed input. (Strict: SPHERE in only; the CLI handles a stray WAV.)
    """
    if _native is not None:
        try:
            return _native.transcode(sph_bytes)
        except ValueError as exc:
            # Normalize the native error to our hierarchy so callers catch one type.
            raise DesphereError(str(exc)) from exc
    header = SphereHeader.parse(sph_bytes)
    data = sph_bytes[header.header_size:]
    buf = io.BytesIO()
    transcode(header, data, buf)
    return buf.getvalue()


def native_available() -> bool:
    """True if the Rust accelerator (desphere-native) is importable."""
    return _native is not None


def transcode(header: SphereHeader, data: bytes, out) -> None:
    """Decode ``data`` per ``header`` and write a PCM WAV to stream ``out``.

    Validates that the payload is at least as long as the header claims; a
    short payload is a hard error (we will not pad audio with silence). Any
    trailing bytes beyond the declared sample count (padding, seek tables) are
    ignored for PCM.
    """
    # Compressed codings (e.g. embedded-shorten) carry a bitstream whose length
    # is unrelated to the uncompressed sample count, so only length-check raw PCM.
    # Mirror resolve_codec's tokenization: a coding is compressed only when it has
    # a non-empty second token. A bare "pcm," is plain PCM and must still be
    # length-validated (a raw `"," in coding` test would wrongly skip the guard).
    tokens = [t.strip().lower() for t in header.sample_coding.split(",")]
    compressed = len(tokens) > 1 and bool(tokens[1])
    if not compressed:
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
