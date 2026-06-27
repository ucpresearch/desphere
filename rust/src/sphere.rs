//! NIST SPHERE header parsing — Rust twin of `src/desphere/sphere.py`.
//!
//! Built only from the public NIST format description (ASCII header: `NIST_1A`,
//! a size line, typed `field -TYPE value` lines, then `end_head`).

use crate::error::DecodeError;
use std::collections::HashMap;

const MAGIC: &[u8] = b"NIST_1A";

pub struct SphereHeader {
    pub fields: HashMap<String, String>,
    pub header_size: usize,
}

fn corrupt(msg: impl Into<String>) -> DecodeError {
    DecodeError::Corrupt(msg.into())
}

impl SphereHeader {
    /// Parse a SPHERE header from a blob that contains at least the full header.
    pub fn parse(blob: &[u8]) -> Result<SphereHeader, DecodeError> {
        if !blob.starts_with(MAGIC) {
            return Err(corrupt("not a NIST SPHERE file (missing 'NIST_1A' magic)"));
        }
        let nl1 = blob.iter().position(|&b| b == b'\n').ok_or_else(|| corrupt("truncated SPHERE header"))?;
        let rest = &blob[nl1 + 1..];
        let nl2 = rest.iter().position(|&b| b == b'\n').ok_or_else(|| corrupt("truncated SPHERE header (no size line)"))?;
        let size_line = std::str::from_utf8(&rest[..nl2]).map_err(|_| corrupt("invalid header size line"))?.trim();
        let header_size: usize = size_line.parse().map_err(|_| corrupt(format!("invalid header size line: {size_line:?}")))?;
        if header_size == 0 {
            return Err(corrupt("non-positive header size"));
        }
        if blob.len() < header_size {
            return Err(corrupt(format!("header claims {header_size} bytes but only {} available", blob.len())));
        }
        let text = std::str::from_utf8(&blob[..header_size]).map_err(|_| corrupt("SPHERE header is not valid ASCII"))?;

        let mut lines = text.split('\n');
        lines.next(); // magic
        lines.next(); // size
        let mut fields = HashMap::new();
        let mut saw_end = false;
        for line in lines {
            let s = line.trim();
            if s.is_empty() {
                continue;
            }
            if s == "end_head" {
                saw_end = true;
                break;
            }
            let (name, value) = parse_field_line(s)?;
            fields.insert(name, value);
        }
        if !saw_end {
            return Err(corrupt("SPHERE header missing 'end_head' terminator"));
        }
        let h = SphereHeader { fields, header_size };
        h.validate()?;
        Ok(h)
    }

    /// Split a full-file blob into `(header, audio_data)`.
    pub fn read(blob: &[u8]) -> Result<(SphereHeader, &[u8]), DecodeError> {
        let h = SphereHeader::parse(blob)?;
        let data = &blob[h.header_size..];
        Ok((h, data))
    }

    fn int(&self, name: &str) -> Result<i64, DecodeError> {
        self.fields
            .get(name)
            .ok_or_else(|| corrupt(format!("SPHERE header missing required field: {name}")))?
            .parse()
            .map_err(|_| corrupt(format!("field {name:?} is not an integer")))
    }

    pub fn sample_count(&self) -> Result<i64, DecodeError> { self.int("sample_count") }
    pub fn sample_rate(&self) -> Result<i64, DecodeError> { self.int("sample_rate") }
    pub fn channel_count(&self) -> Result<i64, DecodeError> { self.int("channel_count") }
    pub fn sample_n_bytes(&self) -> Result<i64, DecodeError> { self.int("sample_n_bytes") }

    pub fn sample_byte_format(&self) -> &str {
        self.fields.get("sample_byte_format").map(String::as_str).unwrap_or("1")
    }
    pub fn sample_coding(&self) -> &str {
        self.fields.get("sample_coding").map(String::as_str).unwrap_or("pcm")
    }
    pub fn expected_data_bytes(&self) -> Result<usize, DecodeError> {
        Ok((self.sample_count()? * self.channel_count()? * self.sample_n_bytes()?) as usize)
    }

    fn validate(&self) -> Result<(), DecodeError> {
        for k in ["sample_count", "sample_rate", "channel_count", "sample_n_bytes"] {
            if !self.fields.contains_key(k) {
                return Err(corrupt(format!("SPHERE header missing required field: {k}")));
            }
        }
        if self.channel_count()? < 1 {
            return Err(corrupt(format!("channel_count must be >= 1, got {}", self.channel_count()?)));
        }
        if self.sample_n_bytes()? < 1 {
            return Err(corrupt(format!("sample_n_bytes must be >= 1, got {}", self.sample_n_bytes()?)));
        }
        if self.sample_count()? < 0 {
            return Err(corrupt(format!("sample_count must be >= 0, got {}", self.sample_count()?)));
        }
        if self.sample_rate()? < 1 {
            return Err(corrupt(format!("sample_rate must be >= 1, got {}", self.sample_rate()?)));
        }
        Ok(())
    }
}

/// Parse one `name -TYPE value` line. The value (everything after the type
/// token) may itself contain spaces; an empty value (`-s0`) is allowed.
fn parse_field_line(line: &str) -> Result<(String, String), DecodeError> {
    let mut first = line.splitn(2, char::is_whitespace);
    let name = first.next().unwrap_or("");
    let rest = first.next().map(str::trim_start).unwrap_or("");
    if name.is_empty() || rest.is_empty() {
        return Err(corrupt(format!("malformed SPHERE header line: {line:?}")));
    }
    let mut second = rest.splitn(2, char::is_whitespace);
    let type_tok = second.next().unwrap_or("");
    let value = second.next().map(str::trim).unwrap_or("");
    if !type_tok.starts_with('-') || type_tok.len() < 2 {
        return Err(corrupt(format!("unknown field type in line: {line:?}")));
    }
    // We store the raw value string; typed access (int) parses on demand.
    Ok((name.to_string(), value.to_string()))
}
