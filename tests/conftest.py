"""Shared test fixtures.

Adds ``tools/`` to the import path so tests can synthesize SPHERE files with
the same writer the fixture generator uses.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

sys.path.insert(0, TOOLS)

from sphere_writer import sine_samples, write_sphere_pcm  # noqa: E402


@pytest.fixture
def make_sphere(tmp_path):
    """Factory: write a PCM SPHERE file and return (path, samples)."""

    def _make(
        *,
        n_frames=400,
        sample_rate=16000,
        channel_count=1,
        sample_n_bytes=2,
        sample_byte_format="01",
        sample_coding="pcm",
        name="t.sph",
    ):
        # Keep amplitude within the signed range of the sample width so the
        # writer never overflows (8-bit fixtures exist only to test rejection).
        amplitude = 100 if sample_n_bytes == 1 else 10000
        samples = sine_samples(
            n_frames, sample_rate, channels=channel_count, amplitude=amplitude
        )
        path = tmp_path / name
        write_sphere_pcm(
            path,
            samples,
            sample_rate=sample_rate,
            channel_count=channel_count,
            sample_n_bytes=sample_n_bytes,
            sample_byte_format=sample_byte_format,
            sample_coding=sample_coding,
        )
        return str(path), samples

    return _make


@pytest.fixture
def fixtures_dir():
    return FIXTURES
