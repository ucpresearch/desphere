"""Real embedded-shorten validation against the local corpus + oracle.

License-restricted corpus files live in ``local-fixtures/`` and the black-box
oracle binaries in ``oracles/`` (both gitignored, Syncthing-synced, NOT
committed). The test skips when they're absent so CI stays green; locally it
verifies ``sph2wav`` output is byte-for-byte identical to ``sph2pipe`` (the
robust oracle that also handles μ-law-shorten, which ffmpeg cannot).
"""

from __future__ import annotations

import io
import os
import subprocess
import wave

import pytest

from mercator import read_sphere, transcode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHN_DIR = os.path.join(ROOT, "local-fixtures", "sph2pipe")
SPH2PIPE = os.path.join(ROOT, "oracles", "sph2pipe")

# All sph2pipe shorten test files: PCM (LE/BE) and μ-law, mono and stereo.
SHORTEN_FILES = [
    "123_1pcle_shn.sph",
    "123_1pcbe_shn.sph",
    "123_2pcle_shn.sph",
    "123_2pcbe_shn.sph",
    "123_1ulaw_shn.sph",
    "123_2ulaw_shn.sph",
]


def _our_pcm(path):
    header, data = read_sphere(path)
    buf = io.BytesIO()
    transcode(header, data, buf)
    with wave.open(io.BytesIO(buf.getvalue()), "rb") as w:
        return w.readframes(w.getnframes())


def _oracle_pcm(path):
    out = subprocess.run(
        [SPH2PIPE, "-p", "-f", "wav", path, "/dev/stdout"],
        capture_output=True, check=True,
    ).stdout
    with wave.open(io.BytesIO(out), "rb") as w:
        return w.readframes(w.getnframes())


@pytest.mark.skipif(not os.path.exists(SPH2PIPE), reason="sph2pipe oracle absent")
@pytest.mark.parametrize("name", SHORTEN_FILES)
def test_shorten_matches_sph2pipe(name):
    path = os.path.join(SHN_DIR, name)
    if not os.path.exists(path):
        pytest.skip(f"{name} not present in local-fixtures/")
    assert _our_pcm(path) == _oracle_pcm(path), f"{name}: decode differs from sph2pipe"
