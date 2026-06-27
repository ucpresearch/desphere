"""Validate the committed fixture zoo against its manifest.

The manifest (built by ``tools/make_fixtures.py``) records, per fixture, the
expected coding and — for PCM — the exact little-endian payload the transcoder
should emit. PCM fixtures must transcode to that payload byte-for-byte;
unsupported fixtures must raise the documented error type.
"""

from __future__ import annotations

import io
import json
import os
import struct
import wave

import pytest

from desphere import read_sphere, transcode
from desphere.errors import DesphereError, UnsupportedCoding, UnsupportedFormat

MANIFEST = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "manifest.json"
)


def _load_manifest():
    if not os.path.exists(MANIFEST):
        pytest.skip("fixture manifest not generated (run tools/make_fixtures.py)")
    with open(MANIFEST) as f:
        return json.load(f)


def _cases():
    manifest = _load_manifest() if os.path.exists(MANIFEST) else {}
    return sorted(manifest.items())


@pytest.mark.parametrize("name,spec", _cases())
def test_fixture(name, spec):
    path = os.path.join(os.path.dirname(MANIFEST), name)
    kind = spec["kind"]

    if kind in ("pcm", "g711"):
        header, data = read_sphere(path)
        buf = io.BytesIO()
        transcode(header, data, buf)
        with wave.open(io.BytesIO(buf.getvalue()), "rb") as w:
            payload = w.readframes(w.getnframes())
        assert payload.hex() == spec["expected_pcm_hex"]
    elif kind == "pcm_oracle":
        # Supported PCM produced by an external encoder: must transcode to a
        # readable WAV (no hand-known payload to compare against).
        header, data = read_sphere(path)
        buf = io.BytesIO()
        transcode(header, data, buf)
        with wave.open(io.BytesIO(buf.getvalue()), "rb") as w:
            assert w.getnframes() == header.sample_count
    elif kind == "unsupported_format":
        header, data = read_sphere(path)
        with pytest.raises(UnsupportedFormat):
            transcode(header, data, io.BytesIO())
    elif kind == "unsupported_coding":
        header, data = read_sphere(path)
        with pytest.raises(UnsupportedCoding):
            transcode(header, data, io.BytesIO())
    elif kind == "malformed_shorten":
        # A shorten coding tag over a body that isn't a valid shorten stream
        # must fail loudly (no 'ajkg' magic), never emit garbage.
        header, data = read_sphere(path)
        with pytest.raises(DesphereError):
            transcode(header, data, io.BytesIO())
    else:
        pytest.fail(f"unknown fixture kind {kind!r} for {name}")
