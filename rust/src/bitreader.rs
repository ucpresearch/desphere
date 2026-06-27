//! MSB-first bit reader over a byte slice — the Rust twin of the Python
//! `_BitReader`. EOF returns `Err` (never a panic — important for WASM), and
//! field widths / unary run lengths are capped so corrupt input fails loud
//! instead of overflowing or spinning (see ../../docs/RUST_PORT.md).

use crate::error::DecodeError;

// Caps: no valid shorten field needs anywhere near these. They bound the unary
// run, the literal width `k`, and keep `high << k` inside u64.
const MAX_UNARY: u64 = 1 << 26;
const MAX_WIDTH: u32 = 32;

pub struct BitReader<'a> {
    data: &'a [u8],
    pos: usize,
    bit: u8,
}

impl<'a> BitReader<'a> {
    pub fn new(data: &'a [u8], start: usize) -> Self {
        BitReader { data, pos: start, bit: 0 }
    }

    #[inline]
    pub fn get_bit(&mut self) -> Result<u32, DecodeError> {
        let byte = *self.data.get(self.pos).ok_or(DecodeError::Corrupt(
            "truncated or corrupt shorten stream: ran past end of bitstream".into(),
        ))?;
        let b = ((byte >> (7 - self.bit)) & 1) as u32;
        self.bit += 1;
        if self.bit == 8 {
            self.bit = 0;
            self.pos += 1;
        }
        Ok(b)
    }

    pub fn get_bits(&mut self, n: u32) -> Result<u64, DecodeError> {
        if n > MAX_WIDTH {
            return Err(DecodeError::Corrupt(format!("oversized bit field width {n}")));
        }
        let mut v: u64 = 0;
        for _ in 0..n {
            v = (v << 1) | self.get_bit()? as u64;
        }
        Ok(v)
    }

    /// `uvar(k)`: unary high part (0-bits to a terminating 1), then `k` literal
    /// low bits. value = (high << k) | low.
    pub fn uvar(&mut self, k: u32) -> Result<u64, DecodeError> {
        if k > MAX_WIDTH {
            return Err(DecodeError::Corrupt(format!("oversized uvar width {k}")));
        }
        let mut high: u64 = 0;
        while self.get_bit()? == 0 {
            high += 1;
            if high > MAX_UNARY {
                return Err(DecodeError::Corrupt("runaway unary code".into()));
            }
        }
        let low = if k > 0 { self.get_bits(k)? } else { 0 };
        Ok((high << k) | low)
    }

    /// `ulong`: k = uvar(2), then uvar(k).
    pub fn ulong(&mut self) -> Result<u64, DecodeError> {
        let k = self.uvar(2)? as u32;
        self.uvar(k)
    }

    /// `var(k)`: uvar(k) then zig-zag to signed (0→0, 1→-1, 2→1, 3→-2, …).
    pub fn var(&mut self, k: u32) -> Result<i64, DecodeError> {
        let u = self.uvar(k)?;
        Ok(if u & 1 == 0 {
            (u >> 1) as i64
        } else {
            // Python ~(u>>1) == -(u>>1) - 1
            -((u >> 1) as i64) - 1
        })
    }
}
