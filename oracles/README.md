# Oracle binaries (gitignored, Syncthing-synced)

Black-box decode oracles for validating mercator. **We run these; we never read
their source** (clean-room rule). Not committed (license + binary); they travel
across machines via Syncthing.

| binary | role | notes |
|--------|------|-------|
| `sph2pipe` | decode everything, incl. type-8 + bitshift (CALLHOME) | the robust one — prefer it |
| `w_decode` | decode shorten incl. type-8 on SMALL files | heap-corrupts on large real-speech files |
| `shorten` | **encoder** (also decodes via `-x`) | build via `build_shorten.sh`; used to synthesize QLPC + high-bitshift test files (no corpus file uses them) |

## Usage

```bash
# PCM ground truth (any coding):
./oracles/sph2pipe -p -f wav  input.sph  out.wav
# raw mu-law byte stream (for type-8 reverse-engineering):
./oracles/sph2pipe -u -f raw  input.sph  out.ulaw
# w_decode (strip the 1024-byte SPHERE header from its output):
./oracles/w_decode -f -o pcm_01 input.sph out.sph
```

## Rebuilding

- `sph2pipe`: copied from
  `~/local/decfiles/private/Research/Dev/Collaborations/JieRen/sph2pipe_v2.5/sph2pipe`.
- `w_decode`: `sh build_w_decode.sh ~/local/scr/sphere $PWD/w_decode`
  (patches the link for modern glibc; compiles, never reads the source).
- `shorten`: `sh build_shorten.sh` (downloads drtonyr/shorten to
  `~/local/scr/shorten-src`, compiles with a modern-stdarg `exit_shim.c`; compiles,
  never reads the source). shorten's license is non-FOSS → strictly black-box.

ffmpeg (system) is also an oracle for PCM-shorten and plain PCM/G.711, but
cannot decode type-8 ulaw-shorten.
