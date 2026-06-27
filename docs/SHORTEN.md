# Embedded-shorten (v2) — clean-room algorithm reference

This documents the shorten v2 bitstream as **we reverse-engineered it** from
Tony Robinson (1994) *SHORTEN* (CUED/F-INFENG/TR.156) plus black-box validation
against decoder *output* (ffmpeg, NIST `w_decode`, `sph2pipe` — run as binaries;
their source was never read). Implementation: `src/desphere/shorten.py`.

Everything here is verified **byte-exact against an oracle** unless explicitly
marked OPEN/unvalidated.

## Stream layout

A `pcm,embedded-shorten-v2.00` or `ulaw,embedded-shorten-v2.00` SPHERE file has
the normal 1024-byte ASCII header, then the shorten stream starting at byte 1024:

```
"ajkg"            4 bytes, magic
<version>         1 byte (2 for v2)
<bitstream...>    MSB-first bit-packed
```

## Bit primitives (MSB-first)

- `get_bit()` — next bit, most-significant-first within each byte.
- `uvar(k)` — **unary** high part (count 0-bits up to a terminating 1-bit) then
  `k` literal low bits: `value = (high << k) | low`.
- `ulong()` — `k = uvar(2)`, then `uvar(k)`. (Self-describing; used for header
  fields.)
- `var(k)` — `u = uvar(k)`, then zig-zag to signed: `(u>>1)` if `u` even else
  `~(u>>1)`. So `u=0→0, 1→-1, 2→1, 3→-2, …`.

Constants: `ULONGSIZE=2`, `NSKIPSIZE=1`, `ENERGYSIZE=3`, `BITSHIFTSIZE=2`,
`FNSIZE=2`, `VERBATIM_CKSIZE=5`, `VERBATIM_BYTE=8`.

## Header (each an `ulong()`)

`ftype, nchan, blocksize, maxnlpc, nmean, nskip` — then `nskip` skip bytes
(`uvar(NSKIPSIZE)` each, discarded). Typical: `blocksize=256`.

`ftype` (sample type): `3 = S16HL` (16-bit, stored big-endian), `5 = S16LH`
(16-bit, little-endian) — both reconstruct the **same integer samples**, emitted
as little-endian WAV. `8 = ULAW` (lossless mu-law, see below).

## Block loop

Read `cmd = uvar(FNSIZE)` repeatedly until `QUIT`:

| code | name | action |
|------|------|--------|
| 0–3 | DIFF0..DIFF3 | polynomial-predicted block (below) |
| 4 | QUIT | end of stream |
| 5 | BLOCKSIZE | `blocksize = ulong()` |
| 6 | BITSHIFT | `bitshift = uvar(BITSHIFTSIZE)` |
| 7 | QLPC | LPC-predicted block (below) |
| 8 | ZERO | a block of `blocksize` zeros |
| 9 | VERBATIM | `n = uvar(5)`; then `n` bytes of `uvar(8)` (discarded for audio) |

For `nchan > 1`, blocks **alternate channels** (block 0 → ch0, block 1 → ch1, …);
each channel keeps its own history and mean state. Output is interleaved.

### DIFF blocks

```
k = uvar(ENERGYSIZE) + 1          # residual Rice parameter is energy+1 (!)
for each of blocksize samples:
    r = var(k)
    DIFF0: v = r + offset         # offset = running mean (below)
    DIFF1: v = r + p1
    DIFF2: v = r + 2*p1 - p2
    DIFF3: v = r + 3*p1 - 3*p2 + p3
    # p1,p2,p3 = previous 3 reconstructed samples, carried ACROSS blocks
```

The `+1` on the energy → Rice parameter is the single least-obvious detail.

### Running-mean offset (DIFF0 only)

All divisions are **C-style, truncate toward zero**. Per decoded block store
`mean = (sum_of_block + blocksize/2) / blocksize`. The DIFF0 offset is
`(Σ last nmean means + nmean/2) / nmean` (missing history padded with 0).

The `+blocksize/2` per-block rounding bias is essential: without it, channels
with negative DC drift by exactly 1 (only caught because stereo ch1 ≈ −ch0, so
ch0 passed and ch1 failed). When `nmean == 0`, offset is 0.

### QLPC blocks (LPC prediction)

Reverse-engineered byte-exact against the `shorten` encoder + ffmpeg (orders
1..20, v2). Layout after the `FN_QLPC` command:

```
energy = uvar(ENERGYSIZE)          # residual Rice parameter k = energy+1 (as DIFF)
order  = uvar(LPCQSIZE)            # LPCQSIZE = 2; per-block LPC order
coef   = [ var(LPCQUANT+1) for _ in range(order) ]   # LPCQUANT = 5 -> coeffs are var(6)
offset = running mean              # same coffset() as DIFF0
for each of blocksize samples:
    r   = var(k)
    dot = Σ_j coef[j] * (hist[t-1-j] - offset)        # hist carried across blocks
    v   = r + ((dot + (1 << LPCQUANT)) >> LPCQUANT) + offset
```

Notes (each was a non-obvious, oracle-pinned detail): coefficients are coded with
**one extra bit** beyond the fixed-point precision (`var(LPCQUANT+1)`); the
residual `k` is `energy+1` exactly as DIFF; the predictor works on the
**mean-removed** history and adds the mean back; and the rounding term is
`1 << LPCQUANT` (a +1 after the shift), *not* the usual `1 << (LPCQUANT-1)`.
QLPC needs `maxnlpc` samples of history (vs 3 for DIFF). Note: **no NIST/SPHERE
corpus file uses QLPC** — the encoders default to polynomial DIFF — so the
fixture is synthetic (`tools/make_qlpc_fixture.py`).

### BITSHIFT

Prediction and the running mean stay in the **pre-shift** reconstructed domain
(the residuals were coded there); bitshift is applied only as an output
transform, and the per-channel history keeps the pre-shift values. For PCM types
output is `v << bitshift` (untested — the validated PCM files use `bitshift = 0`).
For type-8 mu-law the shift is **not** linear; see below.

## Type 8 — lossless mu-law

The reconstructed value `v` is a **sorted-code index**, not a sample. With
`bitshift = 0`, map it directly to a mu-law byte, then G.711-expand to PCM:

```
ulaw_byte = (255 - v) if v >= 0 else (128 + v)      # v in [-128,127] ↔ [0,255]
```

This is exactly the G.711 sort order — **verified byte-exact for all 256 codes**
(the rank of each mu-law byte sorted by its expanded linear value equals this
formula), and byte-exact vs `w_decode`/`sph2pipe` on the sph2pipe ulaw files.

### Type 8 + BITSHIFT — SOLVED (byte-exact vs sph2pipe)

Loud real speech (CALLHOME, e.g. `LDC96S34`) emits `FN_BITSHIFT` on the mu-law
stream. The old suspicion that the `v → mu-law` table was wrong is **disproven**
(it's the exact G.711 sort order, above). The actual subtlety: **bitshift on
type-8 is not a linear-amplitude shift** (`v << bitshift` is always even, but
true indices can be odd) — it is a remap in mu-law **magnitude-code** space.

Write the reconstructed `v` as sign + magnitude code `C`: `C = v` for `v ≥ 0`,
`C = |v| − 1` for `v < 0` (so `C ≥ 0`). The shift sends `C → C_out` where the
output grows at slope `2^bitshift` inside mu-law segment 0 and the slope
**halves at every 16-code segment boundary** (`C_out = 16, 32, 48, …`) until it
reaches 1. Segment geometry forces the closed form:

```
C_out = min over j in [0, bitshift] of ( (C << (bitshift - j)) + a_j )
a_j   = 8*j + a_{j-1} // 2            # a = 0, 8, 20, 34, 49, ...
```

e.g. `bitshift=1 → C_out = min(2C, C+8)`; `bitshift=2 → min(4C, 2C+8, C+20)`.
Then re-attach the sign (`rank = C_out` if `v ≥ 0` else `-(C_out + 1)`) and map
the rank to a mu-law byte as above. History/mean use the **pre-shift** `v`.

Validated **byte-exact vs `sph2pipe`** on `LDC96S34-ma_0671.sph` (both channels,
14.4M samples; bitshift 0/1/2 on audio, 12 on silence) and **byte-exact vs the
`shorten` encoder + ffmpeg** on synthetic mu-law crafted to force higher shifts
(bitshift 3 and 12 on nonzero codes — `tools/make_ulaw_bitshift_fixture.py`).
The `a_1=8`/`a_2=20` intercepts the oracle shows are exactly what segment
boundaries 16/32 predict, and `a_3=34` checks out too — the geometric model *is*
the mechanism. Implemented in `shorten.py` (`_shift_code` / `_ulaw_value_to_byte`);
the closed form is used for all shifts (output code saturates at 127).

Oracle recipe (for re-deriving): `sph2pipe -u -f raw -c N file.sph` gives the
true mu-law byte stream per channel; convert byte → rank and compare to the
reconstructed `v` per `bitshift` to read off `C_out = f(C, bitshift)`.

## Validation oracles (black-box only — never read their source)

- **`sph2pipe`** (most robust; decodes everything incl. CALLHOME):
  `~/local/decfiles/private/Research/Dev/Collaborations/JieRen/sph2pipe_v2.5/sph2pipe`.
  `sph2pipe -p -f wav in.sph out.wav` (→PCM), `sph2pipe -u -f raw in.sph out` (→mu-law).
- **ffmpeg**: decodes PCM-embedded-shorten and plain PCM/G.711; **cannot** decode
  type-8 ulaw-shorten.
- **NIST `w_decode`**: decodes type-8 on small files but heap-corrupts on large
  ones. Build via `scratch/build_w_decode.sh` (compiling ≠ reading source).
