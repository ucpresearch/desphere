"""Embedded-shorten (v2) decoding for NIST SPHERE.

Clean-room implementation from Tony Robinson (1994), *SHORTEN: Simple lossless
and near-lossless waveform compression* (CUED/F-INFENG/TR.156), plus black-box
validation against decoder/encoder output (ffmpeg, sph2pipe, and the `shorten`
encoder, all run as binaries; their source was never read). Verified byte-exact:
16-bit PCM vs ffmpeg (sph2pipe corpus, mono & stereo); lossless mu-law (type 8,
including the non-linear BITSHIFT remap) vs sph2pipe on real CALLHOME; and QLPC
(LPC) blocks vs the shorten encoder + ffmpeg (orders 1..20, mono & stereo).

Bitstream summary (MSB-first):
  - magic ``ajkg`` + 1-byte version, then a bit-packed stream.
  - ``uvar(k)``: unary high part (count of 0-bits to a terminating 1) then k low
    bits; value = (high << k) | low.  ``ulong``: k = uvar(2), then uvar(k).
    ``var(k)``: uvar(k) then zig-zag to signed.
  - header: ftype, nchan, blocksize, maxnlpc, nmean, nskip (each ulong),
    then nskip skip bytes.
  - per block: command uvar(2). DIFF0..3 read energy=uvar(3); residuals use Rice
    parameter k = energy+1; reconstruct by polynomial integration (DIFF0 adds a
    running-mean offset). QLPC reads order=uvar(2) + var(6) coefficients and
    predicts from mean-removed history (see _ulaw_value_to_byte / the QLPC
    branch). ZERO = a silent block. VERBATIM/BLOCKSIZE/BITSHIFT as documented.
    QUIT ends the stream.
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
# monotonic "sorted-code" domain and map back to mu-law bytes (see
# _ulaw_value_to_byte).
_TYPE_S16HL = 3
_TYPE_S16LH = 5
_TYPE_ULAW = 8
_SUPPORTED_FTYPES = (_TYPE_S16HL, _TYPE_S16LH, _TYPE_ULAW)


def _shift_code(C: int, s: int) -> int:
    """Left-shift a mu-law *magnitude code* ``C`` (0..127) by ``s`` in code space.

    Type-8 bitshift is NOT a linear-amplitude shift; against the sph2pipe oracle
    it is a piecewise-linear remap of the companded code: the output grows at
    slope ``2**s`` inside mu-law segment 0 and the slope halves at every 16-code
    segment boundary until it reaches 1. Geometry (segment boundaries at 16, 32,
    48, ...) forces the closed form ``C_out = min_j(2**(s-j)*C + a_j)`` with
    intercepts ``a_j = 8*j + a_{j-1}//2`` = 0, 8, 20, 34, 49, ...  (a_1=8 and
    a_2=20 are exactly what the oracle shows; see docs/SHORTEN.md).
    """
    best = C << s
    a = 0
    for j in range(1, s + 1):
        a = 8 * j + (a >> 1)
        cand = (C << (s - j)) + a
        if cand < best:
            best = cand
    return best


def _ulaw_value_to_byte(v: int, bitshift: int) -> int:
    """Map a type-8 reconstructed value + active bitshift to a mu-law byte.

    ``v`` is the reconstructed value in shorten's sorted-code (rank) domain;
    ``v in [-128,127]`` maps bijectively onto mu-law [0,255] and is exactly the
    G.711 sort order (verified byte-exact vs w_decode/sph2pipe). With a nonzero
    bitshift the shift is applied in mu-law *magnitude-code* space (see
    :func:`_shift_code`); history/prediction stay in the pre-shift rank domain.
    """
    if bitshift == 0:
        if not -128 <= v <= 127:
            raise UnsupportedFormat(
                f"shorten type-8 reconstructed value {v} is outside the "
                "8-bit mu-law domain — an unvalidated code path"
            )
        return (255 - v) if v >= 0 else (128 + v) & 0xFF

    # split into sign + magnitude code: rank r>=0 -> C=r; r<0 -> C=|r|-1
    if v >= 0:
        sign, C = 0, v
    else:
        sign, C = 1, -v - 1
    C = _shift_code(C, bitshift)
    if C > 127:
        C = 127  # saturate to the loudest magnitude code
    rank = C if sign == 0 else -(C + 1)
    return (255 - rank) if rank >= 0 else (rank + 128) & 0xFF

_MAGIC = b"ajkg"
_NWRAP = 3  # history samples needed for DIFF3 (QLPC needs maxnlpc; see decode)

# QLPC (LPC-predicted) block parameters, reverse-engineered byte-exact against
# the `shorten` encoder + ffmpeg (orders 1..20, v2): per block the order is
# uvar(2); each quantized coefficient is var(6); the residual Rice parameter is
# energy+1 (as for DIFF); and the predictor is
#     pred = (Σ coef[j]·(hist[t-1-j] - offset) + (1 << _LPC_QUANT)) >> _LPC_QUANT
# with `offset` the same running-mean used by DIFF0.  _LPC_QUANT is the
# coefficient fixed-point precision (prediction right-shift); coefficients are
# coded with one extra bit (var(_LPC_QUANT + 1)).
_LPCQSIZE = 2
_LPC_QUANT = 5


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
        try:
            byte = self.data[self.pos]
        except IndexError:
            # Running past the end means a truncated/corrupt stream. Raise the
            # project's error type (a no-op try in CPython when not triggered, so
            # this does not slow the hot path) instead of a bare IndexError.
            raise MercatorError(
                "truncated or corrupt shorten stream: ran past end of bitstream"
            ) from None
        b = (byte >> (7 - self.bit)) & 1
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
    if len(data) < 5:
        raise MercatorError("truncated shorten stream: missing version byte")
    br = _BitReader(data, 4)
    version = br.data[br.pos]
    br.pos += 1
    # Only embedded-shorten v2 is validated; v0/v1 use different defaults and
    # would silently mis-decode under v2 semantics, so fail loud rather than
    # emit a plausible-but-wrong WAV.
    if version != 2:
        raise UnsupportedFormat(
            f"shorten version {version} not supported (only v2 is validated)"
        )

    ftype = br.ulong()
    nchan = br.ulong()
    blocksize = br.ulong()
    maxnlpc = br.ulong()
    nmean = br.ulong()
    nskip = br.ulong()
    for _ in range(nskip):
        br.uvar(_NSKIPSIZE)

    # Structural sanity: a zero/negative channel count or blocksize is corrupt
    # and would otherwise crash later (modulo-by-zero, empty channel lists).
    if nchan < 1:
        raise MercatorError(f"invalid shorten channel count {nchan}")
    if blocksize < 1:
        raise MercatorError(f"invalid shorten blocksize {blocksize}")

    if ftype not in _SUPPORTED_FTYPES:
        raise UnsupportedFormat(
            f"shorten sample type {ftype} not supported yet "
            f"(supported: {_SUPPORTED_FTYPES} = 16-bit PCM and lossless mu-law)"
        )

    # QLPC needs `maxnlpc` samples of history; DIFF needs 3. Keep the larger.
    nwrap = maxnlpc if maxnlpc > _NWRAP else _NWRAP
    chan_out: List[List[int]] = [[] for _ in range(nchan)]
    chan_hist = [[0] * nwrap for _ in range(nchan)]
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
            if blocksize < 1:
                raise MercatorError(f"invalid shorten blocksize {blocksize}")
            continue
        if fn == _FN_BITSHIFT:
            bitshift = br.uvar(_BITSHIFTSIZE)
            # uvar's unary part is unbounded, so a corrupt stream could encode an
            # astronomically large shift; a real bitshift only strips trailing
            # zero bits (<=16 for 16-bit PCM, <=12 for mu-law). Cap it so a huge
            # value cannot turn every sample into an O(shift) loop in _shift_code
            # or a multi-million-bit `v << bitshift`. Fail loud (project policy).
            if bitshift > 32:
                raise UnsupportedFormat(
                    f"shorten bitshift {bitshift} is implausibly large "
                    "(corrupt or unsupported stream)"
                )
            continue
        if fn == _FN_VERBATIM:
            n = br.uvar(_VERBATIM_CKSIZE)
            for _ in range(n):
                br.uvar(_VERBATIM_BYTE)
            continue

        hist = chan_hist[ch]
        if fn == _FN_ZERO:
            blk = [0] * blocksize
        elif fn == _FN_QLPC:
            k = br.uvar(_ENERGYSIZE) + 1
            order = br.uvar(_LPCQSIZE)
            # A valid block's order never exceeds maxnlpc (the history we keep);
            # a larger value is corrupt and would index past the history buffer.
            if order > maxnlpc:
                raise MercatorError(
                    f"shorten QLPC order {order} exceeds maxnlpc {maxnlpc} "
                    "(corrupt stream)"
                )
            coef = [br.var(_LPC_QUANT + 1) for _ in range(order)]
            off = coffset(ch)
            buf = list(hist)
            blk = []
            for _ in range(blocksize):
                r = br.var(k)
                if order:
                    dot = 0
                    for j in range(order):
                        dot += coef[j] * (buf[-1 - j] - off)
                    v = r + ((dot + (1 << _LPC_QUANT)) >> _LPC_QUANT) + off
                else:
                    # order 0 = predict the mean only (no LPC term); avoids the
                    # +1 the rounding term would add to an empty dot product.
                    v = r + off
                blk.append(v)
                buf.append(v)
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

        # Prediction history and the running mean stay in the *pre-shift*
        # reconstructed domain (the residuals were coded there); bitshift is a
        # purely cosmetic output transform.  This matters for type-8: the shift
        # is non-linear in code space, so shifting history would desync DIFF.
        chan_hist[ch] = (hist + blk)[-nwrap:]
        if nmean:
            means[ch].append(_cdiv(sum(blk) + blocksize // 2, blocksize))

        if ftype == _TYPE_ULAW:
            chan_out[ch].extend(_ulaw_value_to_byte(v, bitshift) for v in blk)
        elif bitshift:
            chan_out[ch].extend(v << bitshift for v in blk)
        else:
            chan_out[ch].extend(blk)
        ch = (ch + 1) % nchan

    n = min(len(c) for c in chan_out) if chan_out else 0
    interleaved: List[int] = []
    for i in range(n):
        for c in chan_out:
            interleaved.append(c[i])

    # For ULAW, chan_out already holds mu-law bytes (0..255); for PCM types it
    # holds signed 16-bit samples.
    return interleaved, ("ulaw" if ftype == _TYPE_ULAW else "pcm16"), nchan
