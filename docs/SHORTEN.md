# Embedded-shorten (v2) — clean-room algorithm reference

This documents the shorten v2 bitstream as **we reverse-engineered it** from
Tony Robinson (1994) *SHORTEN* (CUED/F-INFENG/TR.156) plus black-box validation
against decoder *output* (ffmpeg, NIST `w_decode`, `sph2pipe` — run as binaries;
their source was never read). Implementation: `src/mercator/shorten.py`.

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
| 7 | QLPC | LPC-predicted block — **OPEN, not implemented** |
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

### BITSHIFT

For PCM types, the reconstructed value is `<< bitshift` at output (history keeps
the pre-shift value). **Untested** — the validated PCM files use `bitshift = 0`.

## Type 8 — lossless mu-law

The reconstructed value `v` is a **sorted-code index**, not a sample. Map it to a
mu-law byte, then G.711-expand to PCM for WAV:

```
ulaw_byte = (255 - v) if v >= 0 else (128 + v)      # v in [-128,127] ↔ [0,255]
```

Verified byte-exact (vs `w_decode` and `sph2pipe`) on the small sph2pipe
ulaw-shorten files (which have `bitshift = 0` and small `|v|`).

### OPEN PROBLEM: type 8 + BITSHIFT

Loud real speech (CALLHOME, e.g. `LDC96S34`) emits `FN_BITSHIFT` (values 0/1
alternating) on the 8-bit mu-law domain, and our reconstruction diverges in loud
regions. Evidence (vs `sph2pipe` oracle): first divergence at frame 7682, ch0,
`bitshift=1`, DIFF1 — the **true index is −3 (odd)**, but `v << bitshift` is
always even. So:
1. BITSHIFT does **not** simply mean `index = v << bitshift` here, and
2. the full-range `v → mu-law` table may differ from the linear formula above
   (only validated for `v ∈ [-70,66]`).

These two unknowns are entangled. Resolve with the `sph2pipe` oracle (it decodes
CALLHOME fine): `sph2pipe -u -f raw file.sph` gives the true mu-law byte stream;
`-p -f wav` gives PCM. Convert true mu-law → true index and compare to the
reconstructed `v` (accounting for bitshift) to disentangle the table from the
shift semantics. Until solved, `shorten.py` **fails loud** on type-8 +
nonzero-bitshift and on out-of-range type-8 values — never emits guessed audio.

## Validation oracles (black-box only — never read their source)

- **`sph2pipe`** (most robust; decodes everything incl. CALLHOME):
  `~/local/decfiles/private/Research/Dev/Collaborations/JieRen/sph2pipe_v2.5/sph2pipe`.
  `sph2pipe -p -f wav in.sph out.wav` (→PCM), `sph2pipe -u -f raw in.sph out` (→mu-law).
- **ffmpeg**: decodes PCM-embedded-shorten and plain PCM/G.711; **cannot** decode
  type-8 ulaw-shorten.
- **NIST `w_decode`**: decodes type-8 on small files but heap-corrupts on large
  ones. Build via `scratch/build_w_decode.sh` (compiling ≠ reading source).
