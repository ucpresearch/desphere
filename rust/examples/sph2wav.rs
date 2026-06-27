//! Minimal CLI demo: transcode a NIST SPHERE file to WAV.
//!
//!     cargo run --example sph2wav -- input.sph output.wav
//!
//! The library is the product; this mirrors the Python `sph2wav` for parity
//! checks and as a usage example.

use std::process::ExitCode;

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: sph2wav <input.sph> <output.wav>");
        return ExitCode::from(2);
    }
    let sph = match std::fs::read(&args[1]) {
        Ok(b) => b,
        Err(e) => {
            eprintln!("sph2wav: cannot read {}: {e}", args[1]);
            return ExitCode::from(2);
        }
    };
    match desphere::transcode(&sph) {
        Ok(wav) => {
            if let Err(e) = std::fs::write(&args[2], wav) {
                eprintln!("sph2wav: cannot write {}: {e}", args[2]);
                return ExitCode::from(2);
            }
            ExitCode::SUCCESS
        }
        Err(e) => {
            eprintln!("sph2wav: {e}");
            ExitCode::from(2)
        }
    }
}
