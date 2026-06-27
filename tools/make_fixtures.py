#!/usr/bin/env python3
"""Generate the SPHERE test-fixture "zoo".

Two tiers:

1. **Committed, deterministic PCM fixtures** — written by hand from a known
   signal via ``sphere_writer`` (no external tools). These are small, stable,
   and checked into ``tests/fixtures/`` so the test suite is self-contained.

2. **Best-effort oracle fixtures** — mu-law / a-law / (eventually) shorten
   variants produced by driving ``sox`` / ``ffmpeg`` / ``shorten`` as
   *black-box binaries* (we run them; we never read their source). Skipped with
   a note if the tool is absent or refuses the format.

Run::

    python tools/make_fixtures.py

The manifest (``tests/fixtures/manifest.json``) records, for each fixture, the
expected header fields and — where known — the canonical little-endian PCM so
tests can assert exact output without re-running any oracle.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

sys.path.insert(0, HERE)
from sphere_writer import pack_pcm, sine_samples, write_sphere_pcm  # noqa: E402

SAMPLE_RATE = 16000
N_FRAMES = 800  # 0.05 s @ 16 kHz — small enough to commit


def _expected_le_pcm(samples, n_bytes):
    """Canonical little-endian PCM bytes the transcoder should emit."""
    return pack_pcm(samples, n_bytes, "01")


def make_pcm_zoo(manifest):
    """Hand-written PCM variants: bit depth x byte order x channels."""
    os.makedirs(FIXTURES, exist_ok=True)

    mono = sine_samples(N_FRAMES, SAMPLE_RATE, channels=1)
    stereo = sine_samples(N_FRAMES, SAMPLE_RATE, channels=2)

    variants = [
        # (name, samples, channels, n_bytes, byte_format)
        ("pcm16le_mono", mono, 1, 2, "01"),
        ("pcm16be_mono", mono, 1, 2, "10"),
        ("pcm16le_stereo", stereo, 2, 2, "01"),
        ("pcm16be_stereo", stereo, 2, 2, "10"),
        ("pcm32le_mono", mono, 1, 4, "01"),
        ("pcm32be_mono", mono, 1, 4, "10"),
    ]

    for name, samples, channels, n_bytes, fmt in variants:
        path = os.path.join(FIXTURES, name + ".sph")
        write_sphere_pcm(
            path,
            samples,
            sample_rate=SAMPLE_RATE,
            channel_count=channels,
            sample_n_bytes=n_bytes,
            sample_byte_format=fmt,
        )
        manifest[name + ".sph"] = {
            "kind": "pcm",
            "sample_rate": SAMPLE_RATE,
            "channel_count": channels,
            "sample_n_bytes": n_bytes,
            "sample_byte_format": fmt,
            "sample_coding": "pcm",
            "expected_pcm_hex": _expected_le_pcm(samples, n_bytes).hex(),
        }
        print(f"  wrote {name}.sph")


def make_unsupported_zoo(manifest):
    """Structurally valid SPHERE files we intentionally reject (fail-loud)."""
    mono = sine_samples(N_FRAMES, SAMPLE_RATE, channels=1)

    # 8-bit PCM — rejected as UnsupportedFormat for now.
    path = os.path.join(FIXTURES, "pcm8_mono.sph")
    samples8 = [max(-128, min(127, s // 256)) for s in mono]
    write_sphere_pcm(
        path, samples8, sample_rate=SAMPLE_RATE, channel_count=1,
        sample_n_bytes=1, sample_byte_format="1",
    )
    manifest["pcm8_mono.sph"] = {"kind": "unsupported_format"}
    print("  wrote pcm8_mono.sph (expected: UnsupportedFormat)")

    # A fake shorten-coded header (body is just PCM) — rejected as
    # UnsupportedCoding because the compression token is unregistered. We only
    # assert the *gate* fires here; real shorten payloads come from corpora.
    from sphere_writer import build_sphere_header

    body = pack_pcm(mono, 2, "01")
    header = build_sphere_header(
        sample_count=N_FRAMES, sample_rate=SAMPLE_RATE, channel_count=1,
        sample_n_bytes=2, sample_byte_format="01",
        sample_coding="pcm,embedded-shorten-v2.00",
    )
    with open(os.path.join(FIXTURES, "shorten_gate.sph"), "wb") as f:
        f.write(header)
        f.write(body)
    manifest["shorten_gate.sph"] = {"kind": "unsupported_coding"}
    print("  wrote shorten_gate.sph (expected: UnsupportedCoding)")


def make_oracle_zoo(manifest):
    """Best-effort: drive external binaries to create harder codings."""
    sox = shutil.which("sox")
    if not sox:
        print("  [skip] sox not found — no mu-law/a-law fixtures generated")
        return

    # Build a small PCM WAV source via sox, then re-encode to SPHERE codings.
    src_wav = os.path.join(FIXTURES, "_src.wav")
    mono = sine_samples(N_FRAMES, SAMPLE_RATE, channels=1)
    _write_wav(src_wav, mono, SAMPLE_RATE, 1, 2)

    for coding, sox_enc in (("ulaw", "u-law"), ("alaw", "a-law")):
        out = os.path.join(FIXTURES, f"{coding}_mono.sph")
        cmd = [sox, src_wav, "-t", "sph", "-e", sox_enc, "-b", "8", out]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"  [skip] sox could not make {coding} SPHERE: {exc}")
            continue
        # Classify by what the file ACTUALLY declares — encoders vary (e.g. some
        # sox builds mislabel a-law as 'pcm'). The manifest must match reality.
        kind = _classify(out)
        manifest[f"{coding}_mono.sph"] = {"kind": kind}
        print(f"  wrote {coding}_mono.sph via sox (declared -> {kind})")

    if os.path.exists(src_wav):
        os.remove(src_wav)


def _classify(sph_path):
    """Return the manifest 'kind' for a SPHERE file by what its header declares.

    Mirrors mercator's capability gate so fixtures stay honest regardless of how
    the external encoder labeled the file.
    """
    from mercator.sphere import SphereHeader

    header, _ = SphereHeader.from_file(sph_path)
    base = header.sample_coding.split(",")[0].strip().lower()
    compressed = "," in header.sample_coding
    if base != "pcm" or compressed:
        return "unsupported_coding"
    if header.sample_n_bytes not in (2, 4):
        return "unsupported_format"
    return "pcm_oracle"  # supported PCM, but payload not asserted (oracle-made)


def _write_wav(path, samples, rate, channels, n_bytes):
    block = channels * n_bytes
    data = pack_pcm(samples, n_bytes, "01")
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + len(data)))
        f.write(b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * block, block, n_bytes * 8))
        f.write(b"data")
        f.write(struct.pack("<I", len(data)))
        f.write(data)


def main():
    manifest = {}
    print(f"Generating fixtures in {FIXTURES}")
    make_pcm_zoo(manifest)
    make_unsupported_zoo(manifest)
    make_oracle_zoo(manifest)
    with open(os.path.join(FIXTURES, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"Wrote manifest with {len(manifest)} entries")


if __name__ == "__main__":
    main()
