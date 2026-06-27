"""SPHERE header parsing tests."""

from __future__ import annotations

import pytest

from desphere import SphereHeader, read_sphere
from desphere.errors import SphereHeaderError


def test_parses_required_fields(make_sphere):
    path, _ = make_sphere(n_frames=100, sample_rate=8000, channel_count=1)
    header, data = read_sphere(path)
    assert header.sample_rate == 8000
    assert header.channel_count == 1
    assert header.sample_n_bytes == 2
    assert header.sample_count == 100
    assert header.sample_coding == "pcm"
    assert header.expected_data_bytes == 100 * 2
    assert len(data) == 100 * 2


def test_byte_format_default_for_single_byte():
    blob = _header(
        "sample_count -i 1\nsample_rate -i 8000\nchannel_count -i 1\n"
        "sample_n_bytes -i 1\nsample_coding -s3 pcm"
    )
    header = SphereHeader.parse(blob)
    assert header.sample_byte_format == "1"


def test_sample_coding_defaults_to_pcm():
    # Real corpora (classic TIMIT) omit sample_coding entirely; it defaults to
    # pcm and the file must still parse and transcode.
    blob = _header(
        "sample_count -i 4\nsample_rate -i 16000\nchannel_count -i 1\n"
        "sample_n_bytes -i 2\nsample_byte_format -s2 01"
    )
    header = SphereHeader.parse(blob)
    assert header.sample_coding == "pcm"


def test_missing_magic_raises():
    with pytest.raises(SphereHeaderError, match="NIST_1A"):
        SphereHeader.parse(b"RIFF....not a sphere")


def test_missing_end_head_raises():
    blob = b"NIST_1A\n1024\nsample_count -i 1\n" + b" " * 1024
    with pytest.raises(SphereHeaderError, match="end_head"):
        SphereHeader.parse(blob[:1024])


def test_missing_required_field_raises():
    with pytest.raises(SphereHeaderError, match="missing required field"):
        SphereHeader.parse(_header("sample_rate -i 8000"))


def test_bad_integer_field_raises():
    with pytest.raises(SphereHeaderError, match="integer"):
        SphereHeader.parse(
            _header(
                "sample_count -i notanumber\nsample_rate -i 8000\n"
                "channel_count -i 1\nsample_n_bytes -i 2\nsample_coding -s3 pcm"
            )
        )


def test_repr_is_informative(make_sphere):
    path, _ = make_sphere()
    header, _ = read_sphere(path)
    text = repr(header)
    assert "sample_rate=16000" in text
    assert "pcm" in text


def _header(body: str, header_size: int = 1024) -> bytes:
    """Build a padded SPHERE header blob from a field body string."""
    text = f"NIST_1A\n{header_size}\n{body}\nend_head\n"
    raw = text.encode("ascii")
    return raw + b" " * (header_size - len(raw))
