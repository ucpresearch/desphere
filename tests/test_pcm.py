"""End-to-end PCM transcode tests: SPHERE -> WAV, read back, compare exactly."""

from __future__ import annotations

import io
import struct
import wave

import pytest

from desphere import read_sphere, transcode


def _transcode_to_bytes(path) -> bytes:
    header, data = read_sphere(path)
    buf = io.BytesIO()
    transcode(header, data, buf)
    return buf.getvalue()


def _read_wav(blob: bytes):
    with wave.open(io.BytesIO(blob), "rb") as w:
        return {
            "channels": w.getnchannels(),
            "sampwidth": w.getsampwidth(),
            "rate": w.getframerate(),
            "frames": w.getnframes(),
            "data": w.readframes(w.getnframes()),
        }


@pytest.mark.parametrize("byte_format", ["01", "10"])
def test_16bit_mono_roundtrip(make_sphere, byte_format):
    path, samples = make_sphere(
        n_frames=300, channel_count=1, sample_n_bytes=2,
        sample_byte_format=byte_format,
    )
    wav = _read_wav(_transcode_to_bytes(path))
    assert wav["channels"] == 1
    assert wav["sampwidth"] == 2
    assert wav["rate"] == 16000
    assert wav["frames"] == 300

    got = list(struct.unpack(f"<{len(samples)}h", wav["data"]))
    assert got == samples


@pytest.mark.parametrize("byte_format", ["01", "10"])
def test_16bit_stereo_roundtrip(make_sphere, byte_format):
    path, samples = make_sphere(
        n_frames=200, channel_count=2, sample_n_bytes=2,
        sample_byte_format=byte_format,
    )
    wav = _read_wav(_transcode_to_bytes(path))
    assert wav["channels"] == 2
    assert wav["frames"] == 200
    got = list(struct.unpack(f"<{len(samples)}h", wav["data"]))
    assert got == samples  # interleaving preserved


@pytest.mark.parametrize("byte_format", ["01", "10"])
def test_32bit_mono_roundtrip(make_sphere, byte_format):
    path, samples = make_sphere(
        n_frames=150, channel_count=1, sample_n_bytes=4,
        sample_byte_format=byte_format,
    )
    wav = _read_wav(_transcode_to_bytes(path))
    assert wav["sampwidth"] == 4
    got = list(struct.unpack(f"<{len(samples)}i", wav["data"]))
    assert got == samples


def test_trailing_padding_is_ignored(make_sphere, tmp_path):
    path, samples = make_sphere(n_frames=100, channel_count=1, sample_n_bytes=2)
    # Append junk after the declared payload; output must be unchanged.
    with open(path, "ab") as f:
        f.write(b"\xde\xad\xbe\xef" * 8)
    wav = _read_wav(_transcode_to_bytes(path))
    got = list(struct.unpack(f"<{len(samples)}h", wav["data"]))
    assert got == samples
