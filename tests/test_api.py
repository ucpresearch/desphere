"""The high-level byte API + optional native accelerator.

`transcode_bytes` must give the same result as the pure-Python reference whether
or not the Rust accelerator (desphere-native) is installed, and fail loud on
non-SPHERE input.
"""

from __future__ import annotations

import io
import os
import struct

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


def test_native_matches_pure(monkeypatch):
    """When the accelerator is installed, every decode kernel must equal the
    pure-Python reference byte-for-byte: the streaming transcode (PCM + G.711)
    and the shorten codec."""
    if not desphere.native_available():
        pytest.skip("native accelerator not installed")
    import desphere.codecs as codecs
    import desphere_native as native
    from desphere import g711, shorten

    # Streaming transcode: PCM (always pure) + G.711 (native vs pure).
    sph = ["pcm16be_stereo.sph", "ulaw_allcodes.sph", "alaw_allcodes.sph"]
    with_native = {n: _pure_wav(os.path.join(FIX, n)) for n in sph}
    monkeypatch.setattr(codecs, "_native", None)  # force pure for this test
    for n in sph:
        assert with_native[n] == _pure_wav(os.path.join(FIX, n)), f"{n}: native != pure"

    # Shorten kernel: native shorten_to_pcm vs the pure decode + expand/clamp.
    def pure_shorten_pcm(stream):
        values, kind, _nchan = shorten.decode(stream)
        if kind == "ulaw":
            return g711.expand(bytes(values), g711.ULAW_TABLE)
        clipped = [max(-32768, min(32767, v)) for v in values]
        return struct.pack("<%dh" % len(clipped), *clipped)

    for stem in ["qlpc_ar2", "qlpc_ar2_stereo", "qlpc_hi", "ulaw_bitshift"]:
        with open(os.path.join(FIX, stem + ".shn"), "rb") as f:
            stream = f.read()
        _nchan, _is_ulaw, pcm = native.shorten_to_pcm(stream)
        assert bytes(pcm) == pure_shorten_pcm(stream), f"{stem}: shorten native != pure"
