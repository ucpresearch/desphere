"""Embedded-shorten (v2) decoding for NIST SPHERE.

Clean-room implementation from Tony Robinson (1994), *SHORTEN: Simple lossless
and near-lossless waveform compression* (CUED/F-INFENG/TR.156), plus black-box
validation against ffmpeg's decoder output (run as a binary; its source was
never read). Verified byte-exact vs ffmpeg on the sph2pipe test files
(123_1/2 pcbe/pcle, mono and stereo).

Bitstream summary (MSB-first):
  - magic ``ajkg`` + 1-byte version, then a bit-packed stream.
  - ``uvar(k)``: unary high part (count of 0-bits to a terminating 1) then k low
    bits; value = (high << k) | low.  ``ulong``: k = uvar(2), then uvar(k).
    ``var(k)``: uvar(k) then zig-zag to signed.
  - header: ftype, nchan, blocksize, maxnlpc, nmean, nskip (each ulong),
    then nskip skip bytes.
  - per block: command uvar(2). DIFF0..3 read energy=uvar(3); residuals use Rice
    parameter k = energy+1; reconstruct by polynomial integration (DIFF0 adds a
    running-mean offset). ZERO = a silent block. VERBATIM/BLOCKSIZE/BITSHIFT as
    documented. QUIT ends the stream.
  - running-mean offset (DIFF0): per block store mean = (sum + blocksize/2) /
    blocksize; offset = (Σ last nmean means + nmean/2) / nmean.  All divisions
    truncate toward zero (C semantics).
"""

from __future__ import annotations

from typing import List, Tuple

from .errors import MercatorError, UnsupportedFormat

# Bitstream constants (TR.156)
_ULONGSIZE = 2
_NSKIPSIZE = 1
_ENERGYSIZE = 3
_BITSHIFTSIZE = 2
_FNSIZE = 2
_VERBATIM_CKSIZE = 5
_VERBATIM_BYTE = 8

# Function codes
_FN_DIFF0, _FN_DIFF1, _FN_DIFF2, _FN_DIFF3 = 0, 1, 2, 3
_FN_QUIT, _FN_BLOCKSIZE, _FN_BITSHIFT = 4, 5, 6
_FN_QLPC, _FN_ZERO, _FN_VERBATIM = 7, 8, 9

# Sample types. 16-bit PCM: HL = stored big-endian, LH = little-endian — both
# decode to the same integer samples, emitted as little-endian WAV. ULAW
# (type 8) is shorten's lossless mu-law mode: the reconstructed values live in a
# monotonic "sorted-code" domain and map back to mu-law bytes (see _val_to_ulaw).
_TYPE_S16HL = 3
_TYPE_S16LH = 5
_TYPE_ULAW = 8
_SUPPORTED_FTYPES = (_TYPE_S16HL, _TYPE_S16LH, _TYPE_ULAW)


def _val_to_ulaw(v: int) -> int:
    """Map a shorten type-8 reconstructed value to its mu-law byte (0..255).

    Derived by black-box comparison against NIST ``w_decode`` output:
    v in [-128,127] maps bijectively onto mu-law [0,255].
    """
    return (255 - v) if v >= 0 else (128 + v) & 0xFF

_MAGIC = b"ajkg"
_NWRAP = 3  # history samples needed for DIFF3


def _cdiv(a: int, b: int) -> int:
    """C-style integer division (truncate toward zero)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


class _BitReader:
    """MSB-first bit reader over a byte string."""

    __slots__ = ("data", "pos", "bit")

    def __init__(self, data: bytes, start: int = 0) -> None:
        self.data = data
        self.pos = start
        self.bit = 0

    def get_bit(self) -> int:
        b = (self.data[self.pos] >> (7 - self.bit)) & 1
        self.bit += 1
        if self.bit == 8:
            self.bit = 0
            self.pos += 1
        return b

    def get_bits(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | self.get_bit()
        return v

    def uvar(self, k: int) -> int:
        high = 0
        while self.get_bit() == 0:
            high += 1
        return (high << k) | (self.get_bits(k) if k else 0)

    def ulong(self) -> int:
        return self.uvar(self.uvar(_ULONGSIZE))

    def var(self, k: int) -> int:
        u = self.uvar(k)
        return (u >> 1) if (u & 1) == 0 else ~(u >> 1)


def decode(data: bytes) -> Tuple[List[int], str, int]:
    """Decode an embedded-shorten stream.

    ``data`` is the bytes following the SPHERE header. Returns
    ``(interleaved_values, kind, channel_count)`` where ``kind`` is ``"pcm16"``
    (values are signed 16-bit samples) or ``"ulaw"`` (values are mu-law bytes
    0..255, to be expanded via G.711).
    """
    if data[:4] != _MAGIC:
        raise MercatorError("not a shorten stream (missing 'ajkg' magic)")
    br = _BitReader(data, 4)
    version = br.data[br.pos]
    br.pos += 1
    if version > 2:
        raise UnsupportedFormat(f"shorten version {version} not supported (need <= 2)")

    ftype = br.ulong()
    nchan = br.ulong()
    blocksize = br.ulong()
    maxnlpc = br.ulong()
    nmean = br.ulong()
    nskip = br.ulong()
    for _ in range(nskip):
        br.uvar(_NSKIPSIZE)

    if ftype not in _SUPPORTED_FTYPES:
        raise UnsupportedFormat(
            f"shorten sample type {ftype} not supported yet "
            f"(supported: {_SUPPORTED_FTYPES} = 16-bit PCM and lossless mu-law)"
        )

    chan_out: List[List[int]] = [[] for _ in range(nchan)]
    chan_hist = [[0] * _NWRAP for _ in range(nchan)]
    means: List[List[int]] = [[] for _ in range(nchan)]
    bitshift = 0
    ch = 0

    def coffset(c: int) -> int:
        if nmean == 0:
            return 0
        recent = means[c][-nmean:]
        recent = [0] * (nmean - len(recent)) + recent
        return _cdiv(sum(recent) + nmean // 2, nmean)

    while True:
        fn = br.uvar(_FNSIZE)
        if fn == _FN_QUIT:
            break
        if fn == _FN_BLOCKSIZE:
            blocksize = br.ulong()
            continue
        if fn == _FN_BITSHIFT:
            bitshift = br.uvar(_BITSHIFTSIZE)
            if bitshift and ftype == _TYPE_ULAW:
                # bitshift interacting with the 8-bit mu-law domain is a code
                # path we cannot validate: the only oracle (NIST w_decode)
                # corrupts memory on the large real-speech files that use it.
                raise UnsupportedFormat(
                    "shorten lossless mu-law (type 8) with bitshift is not yet "
                    "validated (no working decode oracle for this case)"
                )
            continue
        if fn == _FN_VERBATIM:
            n = br.uvar(_VERBATIM_CKSIZE)
            for _ in range(n):
                br.uvar(_VERBATIM_BYTE)
            continue
        if fn == _FN_QLPC:
            raise UnsupportedFormat(
                "shorten QLPC (LPC-predicted) blocks not supported yet"
            )

        hist = chan_hist[ch]
        if fn == _FN_ZERO:
            blk = [0] * blocksize
        elif fn in (_FN_DIFF0, _FN_DIFF1, _FN_DIFF2, _FN_DIFF3):
            k = br.uvar(_ENERGYSIZE) + 1
            off = coffset(ch) if fn == _FN_DIFF0 else 0
            p1, p2, p3 = hist[-1], hist[-2], hist[-3]
            blk = []
            for _ in range(blocksize):
                r = br.var(k)
                if fn == _FN_DIFF0:
                    v = r + off
                elif fn == _FN_DIFF1:
                    v = r + p1
                elif fn == _FN_DIFF2:
                    v = r + 2 * p1 - p2
                else:
                    v = r + 3 * p1 - 3 * p2 + p3
                blk.append(v)
                p3, p2, p1 = p2, p1, v
        else:
            raise UnsupportedFormat(f"unknown shorten function code {fn}")

        if bitshift:
            blk = [v << bitshift for v in blk]

        chan_out[ch].extend(blk)
        chan_hist[ch] = (hist + blk)[-_NWRAP:]
        if nmean:
            means[ch].append(_cdiv(sum(blk) + blocksize // 2, blocksize))
        ch = (ch + 1) % nchan

    n = min(len(c) for c in chan_out) if chan_out else 0
    interleaved: List[int] = []
    for i in range(n):
        for c in chan_out:
            interleaved.append(c[i])

    if ftype == _TYPE_ULAW:
        out = []
        for v in interleaved:
            if not -128 <= v <= 127:
                raise UnsupportedFormat(
                    f"shorten type-8 reconstructed value {v} is outside the "
                    "8-bit mu-law domain — an unvalidated code path"
                )
            out.append(_val_to_ulaw(v))
        return out, "ulaw", nchan
    return interleaved, "pcm16", nchan
