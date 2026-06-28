# web/ — the client-side sph2wav page

A single static page (`index.html`) that converts NIST SPHERE `.sph` files to
**WAV or FLAC**, **entirely in the browser** via the desphere WASM build. Nothing
is uploaded; no server is involved; nothing is fetched at runtime (all assets are
vendored).

## Features

- **Drop one or many `.sph` files.** One file → direct download. Multiple →
  a single `.zip`. Per-file errors are reported; the good ones still come through.
- **Output WAV or FLAC.** WAV is the desphere decode output directly. FLAC is
  produced in-browser from that WAV (lossless), so it matches desphere's lossless
  ethos — and it's smaller.
- A stray `.wav` input passes straight through (re-encoded if FLAC is selected),
  and malformed input shows desphere's exact fail-loud message.

## Vendored dependencies (`web/vendor/`, committed, no CDN)

- **[libflac.js](https://github.com/mmig/libflac.js)** (`vendor/libflac/`) —
  FLAC encoder; loaded lazily only when FLAC is selected. MIT wrapper around
  Xiph's BSD libFLAC. Works in Chrome, Firefox, and Safari (WASM, no WebCodecs
  needed). The FLAC encode path is oracle-tested: encode a desphere WAV → FLAC →
  decode with ffmpeg → byte-identical PCM (mono & stereo).
- **[fflate](https://github.com/101arrowz/fflate)** (`vendor/fflate.min.js`) —
  the multi-file zip; loaded lazily only when more than one file is dropped. MIT.

## Build / run locally

```bash
# build the WASM into web/pkg (gitignored — regenerated)
wasm-pack build rust --out-dir ../web/pkg --target web --features wasm
# serve (ES modules + .wasm need http, not file://)
python -m http.server -d web 8000   # then open http://localhost:8000
```

## Deploy

`.github/workflows/pages.yml` builds `web/pkg` and publishes `web/` (including
`vendor/`) to GitHub Pages on push to the default branch.
