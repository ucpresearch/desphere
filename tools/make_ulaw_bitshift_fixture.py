#!/usr/bin/env python3
"""Generate a self-contained type-8 (mu-law) + BITSHIFT shorten test fixture.

shorten only emits FN_BITSHIFT for mu-law when the sorted-code values share low
zero bits, so we craft that: take a synthetic AR(2) signal, mu-law encode it
(ITU G.711), then round every sorted-code to a multiple of 8. Encoding the
result with `shorten -t ulaw` then produces blocks with bitshift up to 3 (and a
degenerate 12 on silence). Everything is synthetic, so the fixture is committable.

Writes (consumed by tests/test_ulaw_bitshift.py):
    tests/fixtures/ulaw_bitshift.ulaw   ground-truth mu-law bytes
    tests/fixtures/ulaw_bitshift.shn    shorten type-8 stream with bitshift
"""
from __future__ import annotations
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "src"))
from make_qlpc_fixture import ar2_signal  # synthetic deterministic signal
from mercator import g711

SHORTEN = os.path.join(ROOT, "oracles", "shorten")
OUT_DIR = os.path.join(ROOT, "tests", "fixtures")

_EXP_LUT = [0,0,1,1,2,2,2,2,3,3,3,3,3,3,3,3] + [4]*16 + [5]*32 + [6]*64 + [7]*128


def linear2ulaw(pcm):
    """ITU-T G.711 mu-law encoder (public standard)."""
    bias, clip = 0x84, 32635
    sign = 0x80 if pcm < 0 else 0
    if sign:
        pcm = -pcm
    if pcm > clip:
        pcm = clip
    pcm += bias
    exponent = _EXP_LUT[(pcm >> 7) & 0xFF]
    mantissa = (pcm >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF


def m_to_rank(m):
    return (255 - m) if m >= 128 else (m - 128)


def rank_to_m(r):
    r = max(-128, min(127, r))
    return (255 - r) if r >= 0 else (r + 128) & 0xFF


def main():
    if not os.path.exists(SHORTEN):
        sys.exit("need oracles/shorten (build via oracles/build_shorten.sh)")
    os.makedirs(OUT_DIR, exist_ok=True)
    raw = os.path.join(OUT_DIR, "ulaw_bitshift.ulaw")
    shn = os.path.join(OUT_DIR, "ulaw_bitshift.shn")
    # synthetic signal -> mu-law -> snap each code to a multiple of 8 (so shorten
    # finds 3 common low zero bits and emits bitshift).
    # n/drive chosen so per-block dynamic range makes shorten emit a mix of
    # bitshift 0..3 (a louder, longer signal than the QLPC fixture).
    data = bytearray()
    for s in ar2_signal(n=8192, drive=3000.0):
        m = linear2ulaw(s)
        data.append(rank_to_m(round(m_to_rank(m) / 8) * 8))
    with open(raw, "wb") as f:
        f.write(data)
    subprocess.run([SHORTEN, "-t", "ulaw", "-v2", raw, shn], check=True)
    print("wrote", raw, "and", shn, f"({os.path.getsize(shn)} bytes)")


if __name__ == "__main__":
    main()
