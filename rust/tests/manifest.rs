//! End-to-end validation of the Rust transcoder against the shared fixture
//! manifest (`../tests/fixtures/manifest.json`) — the same ground truth the
//! Python `test_fixtures.py` uses. PCM/G.711 fixtures must decode to the exact
//! `expected_pcm_hex`; unsupported/malformed ones must fail loud.

use desphere::sphere::SphereHeader;
use desphere::transcode::decode_payload;
use serde_json::Value;
use std::fs;
use std::path::PathBuf;

fn fixdir() -> PathBuf {
    let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    p.push("../tests/fixtures");
    p
}

fn to_hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        s.push_str(&format!("{b:02x}"));
    }
    s
}

#[test]
fn manifest_fixtures_match_expected() {
    if !fixdir().join("manifest.json").exists() {
        eprintln!("fixtures absent; skipping");
        return;
    }
    let text = fs::read_to_string(fixdir().join("manifest.json")).expect("read manifest");
    let manifest: Value = serde_json::from_str(&text).expect("parse manifest");

    let mut checked = 0;
    for (name, spec) in manifest.as_object().unwrap() {
        let kind = spec["kind"].as_str().unwrap();
        let blob = fs::read(fixdir().join(name)).unwrap_or_else(|_| panic!("read {name}"));
        // Every fixture has a well-formed SPHERE header (the body is what varies).
        let (header, data) =
            SphereHeader::read(&blob).unwrap_or_else(|e| panic!("{name}: header parse: {e}"));
        let result = decode_payload(&header, data);

        match kind {
            "pcm" | "g711" => {
                let (_bits, pcm) = result.unwrap_or_else(|e| panic!("{name}: decode: {e}"));
                let want = spec["expected_pcm_hex"].as_str().unwrap();
                assert_eq!(to_hex(&pcm), want, "{name}: PCM differs from manifest");
            }
            "pcm_oracle" => {
                assert!(result.is_ok(), "{name}: expected a clean decode");
            }
            "unsupported_format" | "unsupported_coding" | "malformed_shorten" => {
                assert!(result.is_err(), "{name}: expected fail-loud ({kind})");
            }
            other => panic!("{name}: unknown manifest kind {other:?}"),
        }
        checked += 1;
    }
    assert!(checked >= 8, "manifest looked empty ({checked} fixtures)");
}
