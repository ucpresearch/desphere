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
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

sys.path.insert(0, HERE)
from sphere_writer import (  # noqa: E402
    pack_pcm,
    sine_samples,
    write_sphere_pcm,
    write_sphere_raw,
)

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
    manifest["shorten_gate.sph"] = {"kind": "malformed_shorten"}
    print("  wrote shorten_gate.sph (expected: MercatorError — no 'ajkg' magic)")


def make_g711_zoo(manifest):
    """Exhaustive G.711 fixtures: all 256 codes, with ffmpeg-decoded truth.

    The payload is every possible companded byte (0..255), so the fixture pins
    the *entire* expansion table. Ground truth is ffmpeg's pcm_mulaw/pcm_alaw
    decoder run as a black-box binary on the raw codes — its output PCM is baked
    into the manifest, so the test stays self-contained (no ffmpeg at test time).
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("  [skip] ffmpeg not found — no G.711 (mu-law/a-law) fixtures")
        return

    all_codes = bytes(range(256))
    for coding, ff_fmt in (("ulaw", "mulaw"), ("alaw", "alaw")):
        try:
            proc = subprocess.run(
                [ffmpeg, "-v", "error", "-f", ff_fmt, "-ar", str(SAMPLE_RATE),
                 "-ac", "1", "-i", "pipe:0", "-f", "s16le", "-ac", "1",
                 "-ar", str(SAMPLE_RATE), "pipe:1"],
                input=all_codes, capture_output=True, check=True,
            )
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"  [skip] ffmpeg could not decode {coding}: {exc}")
            continue

        expected = proc.stdout  # little-endian s16, 256 samples -> 512 bytes
        name = f"{coding}_allcodes.sph"
        write_sphere_raw(
            os.path.join(FIXTURES, name),
            all_codes,
            sample_count=len(all_codes),
            sample_rate=SAMPLE_RATE,
            channel_count=1,
            sample_n_bytes=1,
            sample_byte_format="1",
            sample_coding=coding,
        )
        manifest[name] = {"kind": "g711", "expected_pcm_hex": expected.hex()}
        print(f"  wrote {name} (256 codes, ffmpeg truth = {len(expected)} bytes)")


def main():
    manifest = {}
    print(f"Generating fixtures in {FIXTURES}")
    make_pcm_zoo(manifest)
    make_unsupported_zoo(manifest)
    make_g711_zoo(manifest)
    with open(os.path.join(FIXTURES, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"Wrote manifest with {len(manifest)} entries")


if __name__ == "__main__":
    main()
