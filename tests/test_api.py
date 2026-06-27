"""The high-level byte API + optional native accelerator.

`transcode_bytes` must give the same result as the pure-Python reference whether
or not the Rust accelerator (desphere-native) is installed, and fail loud on
non-SPHERE input.
"""

from __future__ import annotations

import io
import os

import pytest

import desphere
from desphere import read_sphere, transcode, transcode_bytes
from desphere.errors import DesphereError

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _pure_wav(path):
    header, data = read_sphere(path)
    buf = io.BytesIO()
    transcode(header, data, buf)
    return buf.getvalue()


@pytest.mark.parametrize(
    "name", ["pcm16le_mono.sph", "pcm16be_stereo.sph", "ulaw_allcodes.sph"]
)
def test_transcode_bytes_matches_reference(name):
    path = os.path.join(FIX, name)
    with open(path, "rb") as f:
        raw = f.read()
    # Identical to the pure-Python path, whether or not the native accel is used.
    assert transcode_bytes(raw) == _pure_wav(path)


def test_transcode_bytes_fails_loud_on_non_sphere():
    with pytest.raises(DesphereError):
        transcode_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")  # a WAV, not SPHERE
    with pytest.raises(DesphereError):
        transcode_bytes(b"not audio at all")


def test_native_available_is_bool():
    assert isinstance(desphere.native_available(), bool)
