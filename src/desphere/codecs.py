"""Sample-coding decoders and the capability gate.

``sample_coding`` in a SPHERE header looks like ``pcm``, ``ulaw``, ``alaw``, or
a base coding plus a compression token, e.g. ``pcm,embedded-shorten-v2.00``.

:func:`resolve_codec` is the single place that decides whether we can handle a
file. The design goal (per project intent) is: support the obvious, clearly
documented, lossless path first, and **fail loudly** on everything else so we
never emit a plausible-but-wrong WAV. New variants slot in by registering a
decoder; until then the gate raises a precise error.
"""

from __future__ import annotations

import struct
from typing import Tuple

from . import g711, shorten
from .errors import (
    DesphereError,
    SphereHeaderError,
    UnsupportedCoding,
    UnsupportedFormat,
)
from .sphere import SphereHeader

# Optional Rust accelerator. Only the heavy numeric kernels (shorten decode and
# G.711 expansion) are delegated; the typed validation/error checks stay here, so
# behavior is identical with or without it. PCM byte-reorder stays pure (the
# strided slice is already C-speed). pip install desphere[fast] to enable.
try:
    import desphere_native as _native
except ImportError:  # pragma: no cover - native is optional
    _native = None

# Map NIST sample_byte_format -> endianness of the stored samples.
#   "01" = low byte first  (little-endian)
#   "10" = high byte first  (big-endian)
#   "1"  = single byte      (order irrelevant)
_BYTE_ORDER = {
    "1": "little",
    "01": "little",
    "10": "big",
}


def _to_little_endian(raw: bytes, n_bytes: int, order: str) -> bytes:
    """Return ``raw`` with each ``n_bytes``-wide sample in little-endian order."""
    if n_bytes == 1 or order == "little":
        return raw
    # Reverse byte order within every n_bytes-sized group using strided slice
    # assignment (C-speed, no numpy dependency).
    out = bytearray(len(raw))
    for i in range(n_bytes):
        out[i::n_bytes] = raw[n_bytes - 1 - i::n_bytes]
    return bytes(out)


class PcmCodec:
    """Linear PCM: a lossless byte-order normalization to little-endian WAV.

    Supports 16-bit and 32-bit samples (the overwhelming majority of SPHERE
    corpora). 8-bit and 24-bit are deliberately rejected for now: their sign
    and packing conventions have not been validated against an oracle, and a
    wrong guess would silently corrupt audio.
    """

    name = "pcm"
    supported_n_bytes = (2, 4)

    @classmethod
    def decode(cls, header: SphereHeader, data: bytes) -> Tuple[int, bytes]:
        n_bytes = header.sample_n_bytes
        if n_bytes not in cls.supported_n_bytes:
            raise UnsupportedFormat(
                f"{n_bytes * 8}-bit PCM not supported yet "
                f"(supported: {[n * 8 for n in cls.supported_n_bytes]} bit)"
            )

        order = _BYTE_ORDER.get(header.sample_byte_format)
        if order is None:
            raise UnsupportedFormat(
                f"unrecognized sample_byte_format {header.sample_byte_format!r} "
                "(supported: '1', '01', '10')"
            )

        little = _to_little_endian(data, n_bytes, order)
        return n_bytes * 8, little


class _G711Codec:
    """Base for the two ITU-T G.711 companding laws (8-bit in, 16-bit out)."""

    name = "g711"
    table: list = []

    @classmethod
    def decode(cls, header: SphereHeader, data: bytes) -> Tuple[int, bytes]:
        if header.sample_n_bytes != 1:
            raise UnsupportedFormat(
                f"{cls.name} expects 1-byte samples, got "
                f"sample_n_bytes={header.sample_n_bytes}"
            )
        if _native is not None:
            return 16, bytes(_native.g711_expand(bytes(data), cls.name == "alaw"))
        return 16, g711.expand(data, cls.table)


class UlawCodec(_G711Codec):
    name = "ulaw"
    table = g711.ULAW_TABLE


class AlawCodec(_G711Codec):
    name = "alaw"
    table = g711.ALAW_TABLE


class ShortenCodec:
    """Embedded-shorten (v2) lossless decompression to little-endian PCM.

    Handles 16-bit PCM shorten types, the lossless mu-law mode (type 8, including
    BITSHIFT, expanded to 16-bit PCM via G.711), and QLPC (LPC-predicted) blocks.
    Only unsupported shorten sample types raise a precise error.
    """

    name = "embedded-shorten-v2.00"

    @classmethod
    def decode(cls, header: SphereHeader, data: bytes) -> Tuple[int, bytes]:
        if _native is not None:
            # Native does the heavy decode+expand and returns PCM bytes; we keep
            # the same typed header cross-checks (on the emitted PCM, 2 B/sample).
            try:
                nchan, _is_ulaw, pcm = _native.shorten_to_pcm(bytes(data))
            except ValueError as exc:
                raise DesphereError(str(exc)) from exc
            pcm = bytes(pcm)
            if nchan != header.channel_count:
                raise UnsupportedFormat(
                    f"shorten channel count {nchan} disagrees with SPHERE header "
                    f"channel_count {header.channel_count}"
                )
            expected = header.sample_count * nchan  # in samples
            got = len(pcm) // 2
            if got < expected:
                raise SphereHeaderError(
                    f"shorten stream decoded {got // nchan} samples/channel, "
                    f"but the SPHERE header declares {header.sample_count} "
                    "(stream truncated or QUIT came early)"
                )
            return 16, (pcm[: expected * 2] if got > expected else pcm)

        values, kind, nchan = shorten.decode(data)
        if nchan != header.channel_count:
            raise UnsupportedFormat(
                f"shorten channel count {nchan} disagrees with SPHERE header "
                f"channel_count {header.channel_count}"
            )
        # Cross-check the decoded length against the header, mirroring the PCM
        # path's truncation guard: a stream that QUITs early would otherwise yield
        # a silently-short WAV. Excess (final-block padding) is trimmed.
        expected = header.sample_count * nchan
        if len(values) < expected:
            raise SphereHeaderError(
                f"shorten stream decoded {len(values) // nchan} samples/channel, "
                f"but the SPHERE header declares {header.sample_count} "
                "(stream truncated or QUIT came early)"
            )
        if len(values) > expected:
            values = values[:expected]
        if kind == "ulaw":
            return 16, g711.expand(bytes(values), g711.ULAW_TABLE)
        # kind == "pcm16": signed 16-bit little-endian
        lo, hi = -32768, 32767
        clipped = [lo if v < lo else hi if v > hi else v for v in values]
        return 16, struct.pack("<%dh" % len(clipped), *clipped)


# Registry of base codings we can decode. Compression tokens are gated
# separately so unsupported compressions fail with a clear message.
# Aliases cover the spellings different encoders write into the header.
_BASE_CODECS = {
    "pcm": PcmCodec,
    "ulaw": UlawCodec,
    "mu-law": UlawCodec,
    "mulaw": UlawCodec,
    "alaw": AlawCodec,
    "a-law": AlawCodec,
}
_COMPRESSORS = {
    "embedded-shorten-v2.00": ShortenCodec,
}


def resolve_codec(header: SphereHeader):
    """Return a codec for ``header`` or raise a precise Unsupported* error."""
    tokens = [t.strip().lower() for t in header.sample_coding.split(",")]
    base = tokens[0]
    compression = tokens[1] if len(tokens) > 1 else None

    if compression:
        if compression not in _COMPRESSORS:
            raise UnsupportedCoding(
                f"compressed coding {header.sample_coding!r} not supported yet "
                f"(compression: {compression!r})"
            )
        # Future: return a decoder that decompresses, then applies the base codec.
        return _COMPRESSORS[compression]

    codec = _BASE_CODECS.get(base)
    if codec is None:
        raise UnsupportedCoding(
            f"sample_coding {base!r} not supported yet "
            f"(supported: {sorted(_BASE_CODECS)})"
        )
    return codec
