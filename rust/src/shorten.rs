//! Embedded-shorten (v2) decoder — Rust twin of `src/desphere/shorten.py`.
//!
//! CLEAN-ROOM: translated solely from desphere's own MIT Python (itself built
//! from the public Robinson 1994 TR.156 algorithm description + black-box oracle
//! testing). No GPL/LGPL decoder source — FFmpeg, the original `shorten` C
//! sources, or `sph2pipe` — was ever read. See ../../PROVENANCE.md.
//!
//! This must reproduce the Python reference bit-for-bit; it is validated against
//! the same committed fixtures (`tests/fixtures/*.shn`). Integer-width and shift
//! semantics follow ../../docs/RUST_PORT.md: i32 for per-sample state, **i64 for
//! every accumulator**, Rust signed `>>` for the arithmetic-floor roundings, and
//! Rust `/` for the truncate-toward-zero mean (`_cdiv`).

use crate::bitreader::BitReader;
use crate::error::DecodeError;

// Bitstream field widths (TR.156).
const NSKIPSIZE: u32 = 1;
const ENERGYSIZE: u32 = 3;
const BITSHIFTSIZE: u32 = 2;
const FNSIZE: u32 = 2;
const VERBATIM_CKSIZE: u32 = 5;
const VERBATIM_BYTE: u32 = 8;
const LPCQSIZE: u32 = 2;
const LPC_QUANT: u32 = 5; // coeff fixed-point precision; coeffs are var(LPC_QUANT+1)

// Function codes.
const FN_QUIT: u64 = 4;
const FN_BLOCKSIZE: u64 = 5;
const FN_BITSHIFT: u64 = 6;
const FN_QLPC: u64 = 7;
const FN_ZERO: u64 = 8;
const FN_VERBATIM: u64 = 9;

// Sample types we support.
const TYPE_S16HL: u64 = 3;
const TYPE_S16LH: u64 = 5;
const TYPE_ULAW: u64 = 8;

const NWRAP_MIN: usize = 3;

// Sanity caps for corrupt input (valid streams are far below these). They bound
// allocations and the per-field widths; they do NOT bound the *reconstructed*
// DIFF/QLPC values (a third-order integrator or the QLPC dot product can exceed
// i64 on crafted input), so the accumulators below use checked arithmetic and
// surface DecodeError::Corrupt rather than panicking (a WASM trap) or wrapping.
const MAX_NCHAN: u64 = 256;
const MAX_BLOCKSIZE: u64 = 1 << 24;
const MAX_MAXNLPC: u64 = 1024;
const MAX_NMEAN: u64 = 1 << 16;
const MAX_NSKIP: u64 = 1 << 20;
const MAX_BITSHIFT: u64 = 32;
// Cap total decoded samples so a few crafted bytes can't drive an unbounded
// allocation (OOM/abort in WASM). ~1.5 G samples is far beyond any real file.
const MAX_TOTAL_SAMPLES: usize = 1 << 30;

#[inline]
fn overflow() -> DecodeError {
    DecodeError::Corrupt("shorten reconstruction overflowed i64 (corrupt stream)".into())
}

/// Left shift that saturates to i64 bounds on value overflow, reproducing the
/// Python spec's bignum `v << s` followed by the downstream i16/127 clamp
/// (history/running-mean use the pre-shift value, so saturating only the output
/// is exact). Plain i64 `<<` silently wraps and would diverge from Python.
#[inline]
fn shl_sat(v: i64, s: u32) -> i64 {
    let r = (v as i128) << s; // s <= MAX_BITSHIFT (32), so this fits i128
    r.clamp(i64::MIN as i128, i64::MAX as i128) as i64
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    /// Values are signed 16-bit PCM samples (clamp to i16 at output).
    Pcm16,
    /// Values are mu-law bytes 0..=255 (expand via G.711 for PCM).
    Ulaw,
}

/// C-style integer division (truncate toward zero). `b` is always > 0 here, and
/// Rust's `/` already truncates toward zero, so this is just `a / b`.
#[inline]
fn cdiv(a: i64, b: i64) -> i64 {
    debug_assert!(b > 0);
    a / b
}

/// Running-mean offset: `(Σ last nmean means + nmean/2) / nmean`, truncating.
/// Missing history is padded with zeros, which do not change the sum.
fn coffset(means_c: &[i64], nmean: usize) -> Result<i64, DecodeError> {
    if nmean == 0 {
        return Ok(0);
    }
    let start = means_c.len().saturating_sub(nmean);
    let mut sum: i64 = 0;
    for &m in &means_c[start..] {
        sum = sum.checked_add(m).ok_or_else(overflow)?;
    }
    sum = sum.checked_add((nmean as i64) / 2).ok_or_else(overflow)?;
    Ok(cdiv(sum, nmean as i64))
}

/// Type-8 BITSHIFT in mu-law magnitude-code space: slope 2^s in segment 0,
/// halving at each 16-code boundary. `C_out = min_j((C << (s-j)) + a_j)`,
/// `a_j = 8j + a_{j-1}/2`. Computed in i128 so an adversarially large `c` cannot
/// wrap before the caller's `> 127` saturation (matches the Python bignum).
fn shift_code(c: i64, s: u32) -> i64 {
    let c = c as i128;
    let mut best = c << s;
    let mut a: i128 = 0;
    for j in 1..=s {
        a = 8 * (j as i128) + (a >> 1);
        let cand = (c << (s - j)) + a;
        if cand < best {
            best = cand;
        }
    }
    best.clamp(i64::MIN as i128, i64::MAX as i128) as i64
}

/// Map a type-8 reconstructed value + active bitshift to a mu-law byte.
fn ulaw_value_to_byte(v: i64, bitshift: u32) -> Result<u8, DecodeError> {
    if bitshift == 0 {
        if !(-128..=127).contains(&v) {
            return Err(DecodeError::Unsupported(format!(
                "shorten type-8 reconstructed value {v} is outside the 8-bit mu-law domain"
            )));
        }
        return Ok(if v >= 0 {
            (255 - v) as u8
        } else {
            ((128 + v) & 0xFF) as u8
        });
    }
    let (sign, c) = if v >= 0 { (0i64, v) } else { (1i64, -v - 1) };
    let mut c = shift_code(c, bitshift);
    if c > 127 {
        c = 127; // saturate to the loudest magnitude code
    }
    let rank = if sign == 0 { c } else { -(c + 1) };
    Ok(if rank >= 0 {
        (255 - rank) as u8
    } else {
        ((rank + 128) & 0xFF) as u8
    })
}

/// Decode an embedded-shorten stream (`data` starts at the `ajkg` magic).
/// Returns `(interleaved_values, kind, channel_count)` — for `Pcm16` the values
/// are signed samples (clamp to i16 to emit); for `Ulaw` they are mu-law bytes.
pub fn decode(data: &[u8]) -> Result<(Vec<i64>, Kind, usize), DecodeError> {
    if data.len() < 4 || &data[0..4] != b"ajkg" {
        return Err(DecodeError::Corrupt(
            "not a shorten stream (missing 'ajkg' magic)".into(),
        ));
    }
    if data.len() < 5 {
        return Err(DecodeError::Corrupt(
            "truncated shorten stream: missing version byte".into(),
        ));
    }
    let version = data[4];
    if version != 2 {
        return Err(DecodeError::Unsupported(format!(
            "shorten version {version} not supported (only v2 is validated)"
        )));
    }
    let mut br = BitReader::new(data, 5);

    let ftype = br.ulong()?;
    let nchan = br.ulong()?;
    let blocksize0 = br.ulong()?;
    let maxnlpc = br.ulong()?;
    let nmean = br.ulong()?;
    let nskip = br.ulong()?;
    if nskip > MAX_NSKIP {
        return Err(DecodeError::Corrupt(format!("implausible nskip {nskip}")));
    }
    for _ in 0..nskip {
        br.uvar(NSKIPSIZE)?;
    }

    if ftype != TYPE_S16HL && ftype != TYPE_S16LH && ftype != TYPE_ULAW {
        return Err(DecodeError::Unsupported(format!(
            "shorten sample type {ftype} not supported (16-bit PCM and mu-law only)"
        )));
    }
    if !(1..=MAX_NCHAN).contains(&nchan) {
        return Err(DecodeError::Corrupt(format!(
            "invalid shorten channel count {nchan}"
        )));
    }
    if !(1..=MAX_BLOCKSIZE).contains(&blocksize0) {
        return Err(DecodeError::Corrupt(format!(
            "invalid shorten blocksize {blocksize0}"
        )));
    }
    if maxnlpc > MAX_MAXNLPC {
        return Err(DecodeError::Unsupported(format!(
            "implausible maxnlpc {maxnlpc}"
        )));
    }
    if nmean > MAX_NMEAN {
        return Err(DecodeError::Unsupported(format!(
            "implausible nmean {nmean}"
        )));
    }

    let nchan = nchan as usize;
    let mut blocksize = blocksize0 as usize;
    let nmean = nmean as usize;
    let is_ulaw = ftype == TYPE_ULAW;
    let nwrap = (maxnlpc as usize).max(NWRAP_MIN);

    let mut chan_out: Vec<Vec<i64>> = vec![Vec::new(); nchan];
    let mut chan_hist: Vec<Vec<i64>> = vec![vec![0i64; nwrap]; nchan];
    let mut means: Vec<Vec<i64>> = vec![Vec::new(); nchan];
    let mut bitshift: u32 = 0;
    let mut ch = 0usize;
    let mut total: usize = 0; // cumulative decoded samples (OOM guard)

    loop {
        let fnc = br.uvar(FNSIZE)?;
        if fnc == FN_QUIT {
            break;
        }
        if fnc == FN_BLOCKSIZE {
            let b = br.ulong()?;
            if !(1..=MAX_BLOCKSIZE).contains(&b) {
                return Err(DecodeError::Corrupt(format!(
                    "invalid shorten blocksize {b}"
                )));
            }
            blocksize = b as usize;
            continue;
        }
        if fnc == FN_BITSHIFT {
            let bs = br.uvar(BITSHIFTSIZE)?;
            if bs > MAX_BITSHIFT {
                return Err(DecodeError::Unsupported(format!(
                    "shorten bitshift {bs} is implausibly large (corrupt or unsupported)"
                )));
            }
            bitshift = bs as u32;
            continue;
        }
        if fnc == FN_VERBATIM {
            let n = br.uvar(VERBATIM_CKSIZE)?;
            for _ in 0..n {
                br.uvar(VERBATIM_BYTE)?;
            }
            continue;
        }

        // --- data block: build `blk` (pre-shift reconstructed values) ---
        let blk: Vec<i64> = if fnc == FN_ZERO {
            vec![0i64; blocksize]
        } else if fnc == FN_QLPC {
            let k = br.uvar(ENERGYSIZE)? as u32 + 1;
            let order = br.uvar(LPCQSIZE)? as usize;
            if order as u64 > maxnlpc {
                return Err(DecodeError::Corrupt(format!(
                    "shorten QLPC order {order} exceeds maxnlpc {maxnlpc}"
                )));
            }
            let mut coef = Vec::with_capacity(order);
            for _ in 0..order {
                coef.push(br.var(LPC_QUANT + 1)?);
            }
            let off = coffset(&means[ch], nmean)?;
            let mut buf: Vec<i64> = chan_hist[ch].clone();
            let mut blk = Vec::with_capacity(blocksize);
            for _ in 0..blocksize {
                let r = br.var(k)?;
                let v = if order > 0 {
                    // Checked i64 accumulator: valid data peaks far inside i16, so
                    // this only fires on corrupt/adversarial input (RUST_PORT.md).
                    let mut dot: i64 = 0;
                    let n = buf.len();
                    for (j, &c) in coef.iter().enumerate() {
                        let d = buf[n - 1 - j].checked_sub(off).ok_or_else(overflow)?;
                        let term = c.checked_mul(d).ok_or_else(overflow)?;
                        dot = dot.checked_add(term).ok_or_else(overflow)?;
                    }
                    let pred =
                        dot.checked_add(1i64 << LPC_QUANT).ok_or_else(overflow)? >> LPC_QUANT;
                    r.checked_add(pred)
                        .and_then(|x| x.checked_add(off))
                        .ok_or_else(overflow)?
                } else {
                    r.checked_add(off).ok_or_else(overflow)?
                };
                blk.push(v);
                buf.push(v);
            }
            blk
        } else if fnc <= 3 {
            // DIFF0..3
            let k = br.uvar(ENERGYSIZE)? as u32 + 1;
            let off = if fnc == 0 {
                coffset(&means[ch], nmean)?
            } else {
                0
            };
            let hist = &chan_hist[ch];
            let (mut p1, mut p2, mut p3) = (
                hist[hist.len() - 1],
                hist[hist.len() - 2],
                hist[hist.len() - 3],
            );
            let mut blk = Vec::with_capacity(blocksize);
            for _ in 0..blocksize {
                let r = br.var(k)?;
                // Checked: a DIFF3 third-order integrator can exceed i64 on
                // crafted input; valid audio stays tiny.
                let v = match fnc {
                    0 => r.checked_add(off),
                    1 => r.checked_add(p1),
                    2 => 2i64
                        .checked_mul(p1)
                        .and_then(|t| r.checked_add(t))
                        .and_then(|x| x.checked_sub(p2)),
                    _ => 3i64
                        .checked_mul(p1)
                        .and_then(|t1| r.checked_add(t1))
                        .and_then(|x| 3i64.checked_mul(p2).and_then(|t2| x.checked_sub(t2)))
                        .and_then(|x| x.checked_add(p3)),
                }
                .ok_or_else(overflow)?;
                blk.push(v);
                p3 = p2;
                p2 = p1;
                p1 = v;
            }
            blk
        } else {
            return Err(DecodeError::Corrupt(format!(
                "unknown shorten function code {fnc}"
            )));
        };

        // History & running mean stay in the pre-shift domain.
        {
            let hist = &chan_hist[ch];
            let new_hist: Vec<i64> = if blk.len() >= nwrap {
                blk[blk.len() - nwrap..].to_vec()
            } else {
                let keep = nwrap - blk.len();
                let mut nh = hist[hist.len() - keep..].to_vec();
                nh.extend_from_slice(&blk);
                nh
            };
            chan_hist[ch] = new_hist;
        }
        if nmean > 0 {
            let mut s: i64 = 0; // checked i64 accumulator
            for &x in &blk {
                s = s.checked_add(x).ok_or_else(overflow)?;
            }
            s = s.checked_add((blocksize as i64) / 2).ok_or_else(overflow)?;
            means[ch].push(cdiv(s, blocksize as i64));
        }

        // Bound total output so a non-terminating stream can't OOM (WASM abort).
        total = total
            .checked_add(blk.len())
            .filter(|&t| t <= MAX_TOTAL_SAMPLES)
            .ok_or_else(|| {
                DecodeError::Corrupt("shorten stream exceeds the maximum decoded length".into())
            })?;

        // Emit, applying bitshift per sample type.
        if is_ulaw {
            for &v in &blk {
                chan_out[ch].push(ulaw_value_to_byte(v, bitshift)? as i64);
            }
        } else if bitshift > 0 {
            for &v in &blk {
                chan_out[ch].push(shl_sat(v, bitshift));
            }
        } else {
            chan_out[ch].extend_from_slice(&blk);
        }
        ch = (ch + 1) % nchan;
    }

    let n = chan_out.iter().map(|c| c.len()).min().unwrap_or(0);
    let mut interleaved = Vec::with_capacity(n * nchan);
    for i in 0..n {
        for c in &chan_out {
            interleaved.push(c[i]);
        }
    }
    let kind = if is_ulaw { Kind::Ulaw } else { Kind::Pcm16 };
    Ok((interleaved, kind, nchan))
}
