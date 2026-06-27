# Porting desphere to Rust (for a Rust client / WASM)

The Python decoder in `src/desphere/` is the **reference spec**: it is validated
byte-exact against ffmpeg / sph2pipe / the `shorten` encoder on real and
synthetic streams. A Rust port must reproduce its output **bit-for-bit**, so the
subtle integer semantics below are not optional. This is the same Python-first →
Rust path as `praatfan-core-clean`.

The single most important fact: **Python integers are arbitrary precision**, so
the reference never overflows or wraps. Rust must pick widths that cannot
overflow on valid input, and must **never `wrapping_*`** (that would diverge from
the spec) and **never panic/abort** (fatal in WASM) — return a `DecodeError`
instead.

## Integer widths (validated empirically + bounded theoretically)

Measured peaks across all fixtures incl. the 14.4M-sample CALLHOME file and
stereo QLPC up to order 16, with the theoretical bound that actually governs the
type:

| Quantity | Observed peak | Width | Why |
|----------|---------------|-------|-----|
| samples / history / residuals / coeffs / means / offsets | \|v\|≈13 k | **i32** | comfortably in i16 on real data, but reconstruction is **not clamped** mid-stream (see below), so use i32 |
| QLPC dot product + per-term `coef*(buf-off)` | ~2^20 | **i64** | order≤maxnlpc (unbounded in stream), coeff `var(6)` unbounded, `(buf-off)` up to ~2^17 → product can exceed 2^31 |
| block sum (`sum(blk)`) | ~2^18 | **i64** | = O(blocksize × max\|sample\|); blocksize is a `ulong`, unbounded |
| running-mean sum (`sum(recent)`) | ~2^11 | **i64** | = O(nmean × 32768); nmean is a `ulong` |

So: **i32 for the per-sample state, i64 for every accumulator.** Combined with
the header caps below, i64 cannot overflow even on adversarial input; for
defense-in-depth use `checked_add`/`checked_mul` on the accumulators and surface
a `DecodeError`.

## Reconstruction is NOT clamped — clamp only at output

`v_diff`/`v_qlpc` and the polynomial terms (`2*p1-p2`, `3*p1-3*p2+p3`) can sit
slightly outside i16 for near-full-scale data, and history (`chan_hist`, the QLPC
`buf`) carries those unclamped values into the next prediction. Only the final
PCM emit clamps (`codecs.ShortenCodec`: `lo if v<lo else hi if v>hi else v`). A
naive port that stored samples as i16 would wrap/saturate inside the prediction
loop and **desync**. Keep all state i32; clamp with `v.clamp(-32768, 32767) as i16`
only at emit.

## Shift vs division semantics (do not conflate — they differ on negatives)

Two roundings live side by side:

- **QLPC prediction** `(dot + (1 << LPC_QUANT)) >> LPC_QUANT` (LPC_QUANT=5) and
  the type-8 `_shift_code` left-shifts, and PCM `v << bitshift`: Python `>>`/`<<`
  on ints are **arithmetic / floor toward −∞**. Rust `>>`/`<<` on **signed**
  integers are also arithmetic — so they map directly **provided the operand is a
  signed type (i64)**. On an unsigned type Rust `>>` is logical → wrong for
  negative `dot`. Verified: Python `(-1+32)>>5 == 0`, `(-33+32)>>5 == -1`.
- **mean / offset** use `_cdiv` = **truncate toward zero** (C semantics). Rust's
  integer `/` already truncates toward zero, so `_cdiv(a,b)` is just `a / b` on
  i64 (drop the helper; `debug_assert!(b > 0)`). These DIFFER from floor for
  negatives: `_cdiv(-5,256)==0` but `-5//256==-1`; `_cdiv(-257,256)==-1` but
  `-257//256==-2`. **Do not** use `/` for the QLPC rounding or `>>` for the mean.

(`blocksize//2` and `nmean//2` operands are always positive → plain `/2`.)

## Bit reader & EOF

`get_bit` indexes the byte buffer; on a truncated/zero-padded stream the `uvar`
unary loop walks off the end. Python raises (now `DesphereError`); Rust slice
indexing **panics** (aborts WASM). Make the reader return `Result` on EOF and
propagate. The unary loop and `get_bits(k)` must also tolerate a large `k`
(corrupt energy) without `<<` overflow — read against the EOF guard and cap `k`.

## Validate header / per-block fields up front (caps)

The reference now fails loud on these; the port should too (and the caps keep the
i64 accumulators provably safe):

- `magic == "ajkg"`, `len >= 5`, **`version == 2`** (v0/v1 silently mis-decode).
- `nchan >= 1`, `blocksize >= 1` (also re-check on the `BLOCKSIZE` command).
- `bitshift <= 32` (a `uvar` shift is unbounded → O(shift) loop / huge shl = DoS).
- QLPC `order <= maxnlpc`; treat `order == 0` as predict-the-mean (`v = r + off`).
- After decode, cross-check decoded sample count == `sample_count * nchan`
  (truncate excess, error on short) — mirrors the PCM path.
- For WASM/DoS hardening also cap `nchan`, `blocksize`, `maxnlpc`, `nmean`, and
  the VERBATIM count to sane maxima before allocating.

## Output

- PCM: clamp then `i16::to_le_bytes` (host-independent — no `sys.byteorder`
  byteswap branch that `g711.expand` needs in Python).
- Big-endian SPHERE PCM (`sample_byte_format == "10"`): port `_to_little_endian`
  as `chunks_exact_mut(n_bytes).for_each(|c| c.reverse())`; identity for `01`/`1`.
- RIFF/WAV size fields are u32 → error (don't `struct`-panic) if `riff_size`
  exceeds `0xFFFF_FFFF`, before writing any bytes.

## Validation strategy

Reuse the committed byte-exact fixtures as the Rust test corpus — they need no
oracle at test time:

- `tests/fixtures/qlpc_ar2{,_stereo,_hi}.{shn,wav}` — QLPC mono/stereo, orders
  2–12 (qlpc_hi exercises the `maxnlpc>3` larger-history path and negative-dot
  rounding).
- `tests/fixtures/ulaw_bitshift.{shn,ulaw}` — type-8 + bitshift 0–4 (pins the
  `a_4` intercept and the arithmetic-shift rounding).
- The PCM/G.711 fixtures + manifest under `tests/fixtures/`.

Decode each in Rust and assert equality with the committed ground-truth WAV/raw.
For broader coverage, run the same black-box oracle comparison the Python side
uses (`oracles/sph2pipe`, `ffmpeg`, `oracles/shorten -x`) on the gitignored
`local-fixtures/` corpus.
