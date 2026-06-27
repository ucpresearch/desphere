"""Fail-loud tests: unsupported / malformed inputs must raise, never guess."""

from __future__ import annotations

import io
import os

import pytest

from desphere import read_sphere, transcode
from desphere.errors import (
    SphereHeaderError,
    UnsupportedCoding,
    UnsupportedFormat,
)
from desphere.sphere import SphereHeader


def _transcode(path):
    header, data = read_sphere(path)
    transcode(header, data, io.BytesIO())


def test_8bit_pcm_rejected(make_sphere):
    path, _ = make_sphere(sample_n_bytes=1, sample_byte_format="1")
    with pytest.raises(UnsupportedFormat, match="8-bit"):
        _transcode(path)


def test_malformed_shorten_rejected(make_sphere):
    # PCM-embedded-shorten is supported, but a shorten tag over a non-shorten
    # body (no 'ajkg' magic) must fail loudly, not emit garbage.
    from desphere.errors import DesphereError

    path, _ = make_sphere(sample_coding="pcm,embedded-shorten-v2.00")
    with pytest.raises(DesphereError, match="ajkg"):
        _transcode(path)


def test_ulaw_wrong_width_rejected(make_sphere):
    # u-law is supported, but only as 8-bit; a 2-byte u-law header is invalid.
    path, _ = make_sphere(sample_coding="ulaw", sample_n_bytes=2)
    with pytest.raises(UnsupportedFormat, match="ulaw expects 1-byte"):
        _transcode(path)


def test_unknown_byte_format_rejected():
    blob = _header(
        "sample_count -i 1\nsample_rate -i 8000\nchannel_count -i 1\n"
        "sample_n_bytes -i 2\nsample_byte_format -s2 99\nsample_coding -s3 pcm"
    )
    header = SphereHeader.parse(blob)
    from desphere.codecs import resolve_codec

    codec = resolve_codec(header)
    with pytest.raises(UnsupportedFormat, match="sample_byte_format"):
        codec.decode(header, b"\x00\x00")


def test_truncated_payload_rejected(make_sphere):
    path, _ = make_sphere(n_frames=100, sample_n_bytes=2)
    # Chop the payload in half.
    with open(path, "rb") as f:
        blob = f.read()
    truncated = blob[: 1024 + 100]  # header + 50 of 200 payload bytes
    with open(path, "wb") as f:
        f.write(truncated)
    with pytest.raises(SphereHeaderError, match="truncated"):
        _transcode(path)


def test_not_a_sphere_file(tmp_path):
    p = tmp_path / "x.sph"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    with pytest.raises(SphereHeaderError, match="NIST_1A"):
        read_sphere(str(p))


def _header(body: str, header_size: int = 1024) -> bytes:
    text = f"NIST_1A\n{header_size}\n{body}\nend_head\n"
    raw = text.encode("ascii")
    return raw + b" " * (header_size - len(raw))
