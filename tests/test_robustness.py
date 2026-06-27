"""Fail-loud robustness: corrupt/adversarial input must raise a precise
DesphereError, never hang, crash with a bare traceback, or emit a wrong WAV.

These pin the guards added after the Phase-C review (truncation, version,
structural fields, an unbounded bitshift DoS, the WAV size ceiling, and the
compressed-detection / length-cross-check gaps).
"""

from __future__ import annotations

import io
import os

import pytest

from desphere import shorten, transcode
from desphere.errors import DesphereError, SphereHeaderError, UnsupportedFormat
from desphere.wav import write_wav

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


# --- a minimal shorten bit-writer, just enough to craft malformed headers -----
class _BW:
    def __init__(self):
        self.buf = bytearray(); self.cur = 0; self.n = 0

    def bit(self, b):
        self.cur = (self.cur << 1) | (b & 1); self.n += 1
        if self.n == 8:
            self.buf.append(self.cur); self.cur = 0; self.n = 0

    def bits(self, v, k):
        for i in range(k - 1, -1, -1):
            self.bit((v >> i) & 1)

    def uvar(self, v, k):
        for _ in range(v >> k):
            self.bit(0)
        self.bit(1)
        if k:
            self.bits(v & ((1 << k) - 1), k)

    def ulong(self, v):
        k = v.bit_length()
        self.uvar(k, 2)
        self.uvar(v, k)

    def flush(self):
        while self.n:
            self.bit(0)
        return bytes(self.buf)


def _stream(ftype=3, nchan=1, blocksize=256, maxnlpc=0, nmean=0, nskip=0, body=b""):
    w = _BW()
    for v in (ftype, nchan, blocksize, maxnlpc, nmean, nskip):
        w.ulong(v)
    return b"ajkg\x02" + w.flush() + body


def _qlpc_ar2():
    with open(os.path.join(FIX, "qlpc_ar2.shn"), "rb") as f:
        return f.read()


def test_truncated_stream_raises_desphere_error():
    data = _qlpc_ar2()
    with pytest.raises(DesphereError):
        shorten.decode(data[: len(data) // 2])


def test_missing_magic_and_version():
    with pytest.raises(DesphereError):
        shorten.decode(b"nope" + b"\x00" * 8)
    with pytest.raises(DesphereError):
        shorten.decode(b"ajkg")  # magic but no version byte


def test_unsupported_version_fails_loud():
    data = bytearray(_qlpc_ar2())
    data[4] = 1  # version byte -> 1 (v2-only decoder must reject, not mis-decode)
    with pytest.raises(UnsupportedFormat):
        shorten.decode(bytes(data))


def test_zero_channels_and_blocksize():
    with pytest.raises(DesphereError):
        shorten.decode(_stream(nchan=0))
    with pytest.raises(DesphereError):
        shorten.decode(_stream(blocksize=0))


def test_implausible_bitshift_does_not_hang():
    # FN_BITSHIFT (code 6) then a huge shift value; must fail fast, not loop.
    w = _BW()
    w.uvar(6, 2)        # FN_BITSHIFT
    w.uvar(100000, 2)   # absurd shift
    body = w.flush()
    with pytest.raises(UnsupportedFormat):
        shorten.decode(_stream(ftype=8, body=body))


def test_wav_over_4gb_raises_clean_error():
    class _FakeHuge:
        def __len__(self):
            return 0x100000000  # 4 GiB, no allocation
    with pytest.raises(DesphereError):
        write_wav(io.BytesIO(), channels=1, sample_rate=16000,
                  bits_per_sample=16, data=_FakeHuge())


def test_trailing_comma_coding_still_length_validates():
    # "pcm," must be treated as plain PCM (length-checked), not as a compressed
    # coding that skips the truncation guard.
    from desphere.sphere import SphereHeader
    hdr = SphereHeader(
        fields={
            "sample_count": "100", "channel_count": "1", "sample_n_bytes": "2",
            "sample_rate": "16000", "sample_byte_format": "01",
            "sample_coding": "pcm,",
        },
        header_size=1024,
    )
    with pytest.raises(SphereHeaderError):
        transcode(hdr, b"\x00" * 10, io.BytesIO())  # 10 << 200 expected bytes
