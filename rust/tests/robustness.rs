//! Adversarial/robustness regressions for the Rust port: crafted streams that
//! used to panic (WASM trap, debug overflow) or silently wrap/diverge from the
//! Python spec must now return a clean `Err` (or, for the saturating shift, an
//! `Ok` that matches the spec) — never panic. `cargo test` runs the debug
//! profile with overflow-checks on, so a panic here would fail the test.

use desphere::shorten::decode;

/// Minimal MSB-first bit writer mirroring src/bitreader.rs, just enough to craft
/// shorten streams for these tests.
struct BitWriter {
    buf: Vec<u8>,
    cur: u8,
    n: u8,
}
impl BitWriter {
    fn new() -> Self {
        BitWriter {
            buf: Vec::new(),
            cur: 0,
            n: 0,
        }
    }
    fn bit(&mut self, b: u32) {
        self.cur = (self.cur << 1) | (b as u8 & 1);
        self.n += 1;
        if self.n == 8 {
            self.buf.push(self.cur);
            self.cur = 0;
            self.n = 0;
        }
    }
    fn bits(&mut self, v: u64, k: u32) {
        for i in (0..k).rev() {
            self.bit(((v >> i) & 1) as u32);
        }
    }
    fn uvar(&mut self, v: u64, k: u32) {
        for _ in 0..(v >> k) {
            self.bit(0);
        }
        self.bit(1);
        if k > 0 {
            self.bits(v & ((1u64 << k) - 1), k);
        }
    }
    fn ulong(&mut self, v: u64) {
        let k = 64 - v.leading_zeros().min(63); // bit_length (>=1 handled by uvar)
        let k = if v == 0 { 0 } else { k };
        self.uvar(k as u64, 2);
        self.uvar(v, k);
    }
    fn var(&mut self, s: i64, k: u32) {
        let u = if s >= 0 {
            (s as u64) << 1
        } else {
            (((-s) as u64) << 1) - 1
        };
        self.uvar(u, k);
    }
    fn finish(mut self) -> Vec<u8> {
        while self.n != 0 {
            self.bit(0);
        }
        let mut out = b"ajkg\x02".to_vec();
        out.append(&mut self.buf);
        out
    }
}

const FN_QUIT: u64 = 4;
const FN_DIFF3: u64 = 3;

/// A DIFF3 block (third-order integrator) with large residuals overflows the i64
/// reconstruction accumulator partway through the block. Must fail loud, not
/// panic (debug/WASM) or wrap (release).
#[test]
fn diff3_overflow_fails_loud_not_panic() {
    let mut w = BitWriter::new();
    // header: ftype=3 (S16HL), nchan=1, blocksize=2000, maxnlpc=0, nmean=0, nskip=0
    for v in [3u64, 1, 2000, 0, 0, 0] {
        w.ulong(v);
    }
    w.uvar(FN_DIFF3, 2); // command
    w.uvar(31, 3); // energy -> k = 32
    for _ in 0..2000 {
        w.var(1i64 << 35, 32); // huge residuals -> v grows ~ r*n^3/6 past i64
    }
    w.uvar(FN_QUIT, 2);
    let data = w.finish();
    let r = decode(&data);
    assert!(
        r.is_err(),
        "expected fail-loud on DIFF3 overflow, got {r:?}"
    );
}

/// `v << bitshift` used to wrap i64 (Rust) while Python computes the bignum then
/// clamps. With the saturating shift, decode succeeds without panic; this pins
/// the no-panic guarantee on the reviewer's exact 17-byte reproducer.
#[test]
fn bitshift_overflow_does_not_panic() {
    let data: [u8; 17] = [
        97, 106, 107, 103, 2, 222, 247, 153, 150, 0, 148, 122, 0, 0, 0, 0, 128,
    ];
    // Must not panic; returns Ok (saturated, matching Python's clamp) or a clean Err.
    let _ = decode(&data);
}
