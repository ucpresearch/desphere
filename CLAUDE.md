# CLAUDE.md — mercator

## Project overview

**mercator** flattens a "sphere": it transcodes **NIST SPHERE** audio (`.sph`,
used by TIMIT, WSJ, Switchboard, …) — with or without **shorten** compression —
into plain **RIFF/WAV**. MIT-licensed, zero runtime dependencies, pure Python.
CLI entry point: `sph2wav`. It is a standalone sibling of `praatfan-core-clean`,
the same author's low-level acoustic stack.

---

## ⚠️ CRITICAL: clean-room policy (absolute)

mercator must remain permissively licensable (MIT). Therefore:

### NEVER read (L)GPL source code — *ever*.

This is a hard rule with no exceptions. It explicitly forbids reading:
- FFmpeg's NIST/shorten decoder (LGPL)
- the original `shorten` sources and `sph2pipe` sources
- any GPL/LGPL codebase, including praatfan's GPL siblings

### Permitted sources only

- **NIST SPHERE format** — public NIST documentation (ASCII header, typed
  object fields).
- **ITU-T G.711** — for μ-law / a-law companding tables (public telecom standard).
- **Shorten** — Tony Robinson (1994), *SHORTEN: Simple lossless and near-lossless
  waveform compression*, CUED/F-INFENG/TR.156 (published academic report).
- **Black-box oracle testing** — run `ffmpeg` / `sox` / `sph2pipe` as **binaries**
  and compare only their **output**. Running a binary is not reading its source.
  (`ffmpeg` is the trustworthy oracle here; `sox` misreads hand-written SPHERE
  headers — fine as a *writer*, unreliable as a *reader*.)

### On third-party prose writeups

Copyright protects source code, not file formats, facts, or algorithms (the
idea/expression dichotomy). Consulting **prose/tabular** descriptions of a format
— even third-party ones — is acceptable and is *not* "reading GPL source." The
one guardrail: **never use a writeup that embeds verbatim GPL source code.**
Treat prose writeups as a cross-check; the authoritative primary sources are the
TR, ITU specs, and NIST docs.

---

## 🧠 Memory & plans — save LOCALLY in this repo

`~/.claude/` is **not** Syncthing-synced, but this repo **is**. So persist
working state inside the repo instead of under `~/.claude`:

- **Memories** → `memories/` (this directory, not `~/.claude/.../memory/`).
- **Plans** → `plans/` (this directory, not `~/.claude/plans/`).

Both are **gitignored but Syncthing-synced** — they travel across machines
without polluting git history (mirrors the `praatfan-core-clean` convention).

### Memory format

Each memory is one file in `memories/` with frontmatter:

```markdown
---
name: <short-kebab-case-slug>
description: <one-line summary used for relevance during recall>
metadata:
  type: user | feedback | project | reference
---

<the fact; link related memories with [[their-name]].>
```

Keep `memories/MEMORY.md` as a one-line-per-memory index. Before saving, check
for an existing file that already covers the fact and update it instead of
duplicating. When in plan mode, write the plan into the harness-provided plan
file *and* save a copy to `plans/` so it survives in the synced tree.

---

## 🏗️ Architecture

```
src/mercator/
├── sphere.py      # NIST SPHERE header parser -> (SphereHeader, raw bytes)
├── codecs.py      # capability gate (resolve_codec) + PCM / G.711 decoders
├── g711.py        # ITU-T G.711 mu-law / a-law expansion tables
├── wav.py         # minimal canonical RIFF/PCM writer
├── transcode.py   # orchestration + payload-length validation
└── cli.py         # sph2wav
```

The **capability gate** (`codecs.resolve_codec`) is the single extension point
and the enforcer of the project's guiding principle:

> **Support the obvious, clearly-documented, lossless path first; fail loudly on
> anything not yet validated.** Never emit a plausible-but-wrong WAV.

Adding a coding = registering a decoder. Until then the gate raises a precise
`UnsupportedCoding` / `UnsupportedFormat`.

### Supported matrix

| Coding | Status |
|--------|--------|
| `pcm` 16/32-bit, byte order `01`/`10` | ✅ supported (Phase A) |
| `pcm` multi-channel (interleaved) | ✅ supported |
| `pcm` 8-bit / 24-bit | ⛔ `UnsupportedFormat` (conventions unvalidated) |
| `ulaw` / `alaw` (G.711, 8-bit) | ✅ supported (Phase B) |
| `pcm,embedded-shorten-v2.00` (16-bit) | ✅ supported (Phase C) — byte-exact vs ffmpeg, mono & stereo |
| `ulaw,embedded-shorten` (shorten type 8) / QLPC | ⛔ `UnsupportedFormat` — future work |

---

## 🧪 Fixtures & verification

We do **not** depend on real corpus files for the supported codings. The "zoo"
is *generated*: `python tools/make_fixtures.py` writes SPHERE variants from a
known signal (PCM, by hand) and from exhaustive G.711 codes (all 256, with
**ffmpeg-decoded ground truth baked into `tests/fixtures/manifest.json`** so
tests stay self-contained). `tools/sphere_writer.py` is the SPHERE-writing
helper (tooling only — mercator itself never *writes* SPHERE).

Verification ladder:
1. `pytest` — round-trips, fail-loud assertions, manifest checks (ffmpeg truth).
2. Black-box oracle: `ffmpeg -i x.sph out.wav` vs `sph2wav x.sph` — compare PCM
   payloads byte-for-byte. Confirmed exact on hand-written *and* sox-authored
   PCM, and on all 256 G.711 codes.

Real corpus `.sph` files are needed for **Phase C (shorten)** only — ffmpeg can
decode shorten (oracle) but cannot encode it, so we can't synthesize those.

---

## 🔧 Development environment

The virtualenv lives **outside** the synced repo, symlinked in (venvs are
platform-specific and must not sync):

```bash
uv venv ~/local/scr/venvs/mercator --python 3.12
ln -s ~/local/scr/venvs/mercator .venv          # .venv is gitignored
VIRTUAL_ENV=$HOME/local/scr/venvs/mercator uv pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Use `uv pip`, never bare `pip`.

---

## 🗺️ Roadmap

- **Phase A** ✅ — SPHERE header + 16/32-bit PCM, lossless.
- **Phase B** ✅ — μ-law / a-law (ITU-T G.711).
- **Phase C** ✅ — embedded-shorten (16-bit PCM) from TR.156 + ffmpeg oracle,
  byte-exact on real sph2pipe corpus files (mono & stereo). `src/mercator/shorten.py`.
  Remaining: shorten lossless-μ-law (type 8) + QLPC blocks.

### Shorten decode notes (hard-won, validated vs ffmpeg)

- Bit order MSB-first. `uvar(k)` = unary(0s→1) high part + k low bits.
  `ulong` = `uvar(uvar(2))`. `var(k)` = `uvar(k)` then zig-zag to signed.
- Per DIFF block: `energy = uvar(3)`; **residual Rice parameter `k = energy+1`**.
- DIFF0 adds a running-mean offset; DIFF1/2/3 use polynomial history (carried
  across blocks). The exact mean (all divisions **C-truncate toward zero**):
  per-block `mean = (sum + blocksize/2) / blocksize`;
  `offset = (Σ last nmean means + nmean/2) / nmean`. The per-block `+blocksize/2`
  rounding bias is essential — without it, channels with negative DC drift by 1.
