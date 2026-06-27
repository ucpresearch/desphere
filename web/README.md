# web/ — the client-side sph2wav page

A single static page (`index.html`) that converts a NIST SPHERE `.sph` to `.wav`
**entirely in the browser** via the desphere WASM build. Nothing is uploaded; no
server is involved.

## Build / run locally

```bash
# build the WASM into web/pkg (gitignored — regenerated)
wasm-pack build rust --out-dir ../web/pkg --target web --features wasm
# serve (ES modules + .wasm need http, not file://)
python -m http.server -d web 8000   # then open http://localhost:8000
```

## Deploy

`.github/workflows/pages.yml` builds `web/pkg` and publishes `web/` to GitHub
Pages on push to the default branch.

The page also passes a stray `.wav` straight back (with a note), and shows the
exact fail-loud message on malformed input.
