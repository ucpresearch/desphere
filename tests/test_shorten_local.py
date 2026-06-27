"""Real embedded-shorten validation against the local corpus fixtures.

These files are license-restricted, so they live in ``local-fixtures/``
(gitignored, Syncthing-synced) and are NOT committed. The test skips entirely
when they (or ffmpeg) are absent, so CI stays green; locally it verifies
``sph2wav`` output is byte-for-byte identical to ffmpeg's shorten decoder.
"""

from __future__ import annotations

import io
import os
import shutil
import struct
import subprocess
import wave

import pytest

from mercator import read_sphere, transcode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHN_DIR = os.path.join(ROOT, "local-fixtures", "sph2pipe")

PCM_SHORTEN = [
    "123_1pcle_shn.sph",
    "123_1pcbe_shn.sph",
    "123_2pcle_shn.sph",
    "123_2pcbe_shn.sph",
]


def _available(name):
    return os.path.exists(os.path.join(SHN_DIR, name))


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg oracle not installed")
@pytest.mark.parametrize("name", PCM_SHORTEN)
def test_pcm_shorten_matches_ffmpeg(name):
    path = os.path.join(SHN_DIR, name)
    if not _available(name):
        pytest.skip(f"{name} not present in local-fixtures/")

    header, data = read_sphere(path)
    buf = io.BytesIO()
    transcode(header, data, buf)
    with wave.open(io.BytesIO(buf.getvalue()), "rb") as w:
        ours = w.readframes(w.getnframes())

    ref = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "wav", "pipe:1"],
        capture_output=True, check=True,
    ).stdout
    with wave.open(io.BytesIO(ref), "rb") as w:
        theirs = w.readframes(w.getnframes())

    assert ours == theirs, f"{name}: shorten decode differs from ffmpeg"
