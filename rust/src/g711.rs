//! ITU-T G.711 mu-law / a-law expansion to 16-bit linear PCM.
//!
//! Ported from the Python `g711` module (built from the ITU-T G.711 public
//! standard; no GPL source). Fixed 256-entry tables.

const BIAS: i32 = 0x84; // 132

pub fn ulaw_to_linear(u_val: u8) -> i16 {
    let u = !u_val;
    let mut t: i32 = (((u & 0x0F) as i32) << 3) + BIAS;
    t <<= (u & 0x70) >> 4;
    (if u & 0x80 != 0 { BIAS - t } else { t - BIAS }) as i16
}

pub fn alaw_to_linear(a_val: u8) -> i16 {
    let a = a_val ^ 0x55;
    let mantissa = (a & 0x0F) as i32;
    let segment = ((a & 0x70) >> 4) as i32;
    let t = if segment == 0 {
        (mantissa << 4) + 8
    } else {
        ((mantissa << 4) + 0x108) << (segment - 1)
    };
    (if a & 0x80 != 0 { t } else { -t }) as i16
}

/// Precomputed code (0..=255) -> signed 16-bit sample.
pub fn ulaw_table() -> [i16; 256] {
    let mut t = [0i16; 256];
    let mut i = 0usize;
    while i < 256 {
        t[i] = ulaw_to_linear(i as u8);
        i += 1;
    }
    t
}

pub fn alaw_table() -> [i16; 256] {
    let mut t = [0i16; 256];
    let mut i = 0usize;
    while i < 256 {
        t[i] = alaw_to_linear(i as u8);
        i += 1;
    }
    t
}
