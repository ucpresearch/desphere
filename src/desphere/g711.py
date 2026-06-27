"""ITU-T G.711 mu-law / a-law expansion to 16-bit linear PCM.

Implemented from the **ITU-T G.711** recommendation (a public telecom standard
that defines the companding tables); no GPL/LGPL source was consulted. The
decode is a fixed 256-entry table, so we precompute it once at import.

Both laws expand an 8-bit companded code to a signed 16-bit linear sample.
"""

from __future__ import annotations

import array
import sys
from typing import List

_BIAS = 0x84  # 132; the mu-law magnitude bias


def _ulaw_to_linear(u_val: int) -> int:
    """Expand one mu-law byte to a signed 16-bit sample (ITU-T G.711)."""
    u_val = ~u_val & 0xFF
    t = ((u_val & 0x0F) << 3) + _BIAS
    t <<= (u_val & 0x70) >> 4
    return (_BIAS - t) if (u_val & 0x80) else (t - _BIAS)


def _alaw_to_linear(a_val: int) -> int:
    """Expand one a-law byte to a signed 16-bit sample (ITU-T G.711)."""
    a_val ^= 0x55
    mantissa = a_val & 0x0F
    segment = (a_val & 0x70) >> 4
    if segment == 0:
        t = (mantissa << 4) + 8
    else:
        t = ((mantissa << 4) + 0x108) << (segment - 1)
    return t if (a_val & 0x80) else -t


# Precomputed expansion tables: code (0..255) -> signed 16-bit sample.
ULAW_TABLE: List[int] = [_ulaw_to_linear(i) for i in range(256)]
ALAW_TABLE: List[int] = [_alaw_to_linear(i) for i in range(256)]


def expand(data: bytes, table: List[int]) -> bytes:
    """Expand companded ``data`` to little-endian 16-bit PCM via ``table``."""
    samples = array.array("h", [table[b] for b in data])
    if sys.byteorder == "big":
        samples.byteswap()  # WAV/RIFF is little-endian
    return samples.tobytes()
