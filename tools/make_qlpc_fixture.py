#!/usr/bin/env python3
"""Generate a self-contained QLPC shorten test fixture from a SYNTHETIC signal.

A resonant AR(2) process is the kind of signal shorten compresses with its
optional LPC predictor, so encoding it (``shorten -p N``) yields real FN_QLPC
blocks. The signal is fully synthetic (deterministic LCG excitation), so the
resulting fixture carries no corpus license and can be committed.

This needs the black-box ``shorten`` encoder (oracles/shorten; built via
oracles/build_shorten.sh). It writes:
    tests/fixtures/qlpc_ar2.wav   ground-truth PCM (the encoder's input)
    tests/fixtures/qlpc_ar2.shn   shorten stream containing QLPC blocks

The test (tests/test_qlpc.py) decodes the .shn and asserts it equals the .wav,
so it is self-contained at test time (no encoder/oracle needed).
"""
from __future__ import annotations
import math
import os
import struct
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHORTEN = os.path.join(ROOT, "oracles", "shorten")
OUT_DIR = os.path.join(ROOT, "tests", "fixtures")


def ar2_signal(n=4096, a1=1.7, a2=-0.72, drive=300.0, seed=12345):
    """Deterministic resonant AR(2) signal, clipped to int16."""
    x = seed
    s = [0.0, 0.0]
    out = []
    for _ in range(n):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        e = ((x / 0x7FFFFFFF) * 2 - 1) * drive
        nxt = a1 * s[-1] + a2 * s[-2] + e
        s.append(nxt)
        out.append(max(-30000, min(30000, int(round(nxt)))))
    return out


def multisine_signal(n=4096, comps=((0.05, 8000.0), (0.13, 6000.0),
                                    (0.21, 4000.0), (0.31, 3000.0))):
    """Deterministic multi-resonance signal. Its broadband spectral structure
    drives shorten to pick HIGH per-block LPC orders (>3), exercising the
    nwrap=maxnlpc larger-history path that the AR(2) signal (orders 2-3) never
    reaches."""
    out = []
    for i in range(n):
        v = sum(a * math.sin(2 * math.pi * f * i) for f, a in comps)
        out.append(max(-30000, min(30000, int(round(v)))))
    return out


def _write(name, channels, order=3):
    """channels: list of per-channel int16 lists (all same length). Writes a WAV
    + a shorten -p <order> (QLPC) stream; returns (wav, shn)."""
    wav = os.path.join(OUT_DIR, name + ".wav")
    shn = os.path.join(OUT_DIR, name + ".shn")
    n = len(channels[0])
    inter = [s for i in range(n) for s in (c[i] for c in channels)]
    with wave.open(wav, "wb") as w:
        w.setnchannels(len(channels)); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(struct.pack("<%dh" % len(inter), *inter))
    # -p <order> sets the LPC search ceiling; -v2 is the SPHERE shorten version.
    subprocess.run([SHORTEN, "-p", str(order), "-v2", wav, shn], check=True)
    print("wrote", wav, "and", shn, f"({os.path.getsize(shn)} bytes)")


def main():
    if not os.path.exists(SHORTEN):
        sys.exit("need oracles/shorten (build via oracles/build_shorten.sh)")
    os.makedirs(OUT_DIR, exist_ok=True)
    _write("qlpc_ar2", [ar2_signal()])
    # stereo: two distinct AR(2) channels -> exercises alternating-channel QLPC.
    _write("qlpc_ar2_stereo",
           [ar2_signal(seed=12345), ar2_signal(a1=1.4, a2=-0.6, seed=999)])
    # high order: maxnlpc=12 with blocks of order >3 -> exercises the
    # nwrap=maxnlpc larger-history branch (AR(2) above never gets past order 3).
    _write("qlpc_hi", [multisine_signal()], order=12)


if __name__ == "__main__":
    main()
