//! Byte-exact validation of the Rust shorten decoder against the same committed
//! fixtures the Python reference uses (`../tests/fixtures`). No oracle needed at
//! test time — the ground truth is the synthetic WAV/raw that was encoded.

use desphere::shorten::{decode, Kind};
use std::fs;
use std::path::PathBuf;

fn fixture(name: &str) -> PathBuf {
    let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    p.push("../tests/fixtures");
    p.push(name);
    p
}

/// The fixtures live in the repo (shared with the Python tests), not inside the
/// crate, so a packaged/published crate won't have them — skip gracefully there.
fn fixtures_present() -> bool {
    fixture("qlpc_ar2.shn").exists()
}

fn pcm_le(values: &[i64]) -> Vec<u8> {
    let mut out = Vec::with_capacity(values.len() * 2);
    for &v in values {
        let c = v.clamp(-32768, 32767) as i16;
        out.extend_from_slice(&c.to_le_bytes());
    }
    out
}

fn check_pcm(stem: &str) {
    if !fixtures_present() {
        eprintln!("fixtures absent; skipping");
        return;
    }
    let shn = fs::read(fixture(&format!("{stem}.shn"))).unwrap();
    let (vals, kind, _n) = decode(&shn).expect("decode failed");
    assert_eq!(kind, Kind::Pcm16);
    let got = pcm_le(&vals);
    // Our committed .wav is a canonical 44-byte header + LE PCM data chunk.
    let wav = fs::read(fixture(&format!("{stem}.wav"))).unwrap();
    let truth = &wav[44..44 + got.len()];
    assert_eq!(got, truth, "{stem}: PCM differs from ground truth");
}

#[test]
fn qlpc_mono_byte_exact() {
    check_pcm("qlpc_ar2");
}

#[test]
fn qlpc_stereo_byte_exact() {
    check_pcm("qlpc_ar2_stereo");
}

#[test]
fn qlpc_high_order_byte_exact() {
    check_pcm("qlpc_hi");
}

#[test]
fn ulaw_bitshift_byte_exact() {
    if !fixtures_present() {
        eprintln!("fixtures absent; skipping");
        return;
    }
    let shn = fs::read(fixture("ulaw_bitshift.shn")).unwrap();
    let (vals, kind, _n) = decode(&shn).expect("decode failed");
    assert_eq!(kind, Kind::Ulaw);
    let got: Vec<u8> = vals.iter().map(|&v| v as u8).collect();
    let truth = fs::read(fixture("ulaw_bitshift.ulaw")).unwrap();
    assert_eq!(
        got, truth,
        "ulaw_bitshift: mu-law bytes differ from ground truth"
    );
}

#[test]
fn rejects_corrupt_input() {
    if !fixtures_present() {
        eprintln!("fixtures absent; skipping");
        return;
    }
    // bad magic, truncation, and unsupported version must Err (never panic).
    assert!(decode(b"nope").is_err());
    assert!(decode(b"ajkg").is_err()); // magic but no version
    let mut v = fs::read(fixture("qlpc_ar2.shn")).unwrap();
    assert!(decode(&v[..v.len() / 2]).is_err()); // truncated
    v[4] = 1; // version 1
    assert!(decode(&v).is_err());
}
