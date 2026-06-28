# Releasing desphere

desphere ships as **two** PyPI projects from this one repo:

| Project            | Built by   | Contents                                   | Install                  |
| ------------------ | ---------- | ------------------------------------------ | ------------------------ |
| `desphere`         | hatchling  | pure-Python package + universal wheel      | `pip install desphere`   |
| `desphere-native`  | maturin    | optional Rust accelerator, abi3 wheels     | `pip install desphere[fast]` |

`desphere` works on its own. `desphere[fast]` pulls in `desphere-native`; when
present, desphere transparently routes the slow kernels (shorten, G.711) through
it and produces **byte-identical** output, falling back to pure Python otherwise.

Publishing uses **PyPI Trusted Publishing (OIDC)** via
`.github/workflows/release.yml` — no API tokens are stored anywhere.

---

## One-time setup (your action, on PyPI)

Both projects must exist on PyPI and trust this repo's release workflow before
the first automated publish. Trusted Publishing can be configured **before** the
project exists ("pending publisher"), so you don't have to upload manually first.

For **each** project (`desphere` and `desphere-native`):

1. Sign in at <https://pypi.org> → *Your projects* → *Publishing* (or
   *Account settings → Publishing* for a pending publisher).
2. Add a **GitHub Actions** trusted publisher:
   - **Owner:** `ucpresearch`
   - **Repository:** `desphere`
   - **Workflow name:** `release.yml`
   - **Environment:** the per-project environment below.

   | PyPI project       | Environment name        |
   | ------------------ | ----------------------- |
   | `desphere`         | `pypi-desphere`         |
   | `desphere-native`  | `pypi-desphere-native`  |

3. In GitHub → repo **Settings → Environments**, create both environments
   (`pypi-desphere`, `pypi-desphere-native`). Optionally add a required reviewer
   so a publish needs a manual click.

(Optional but recommended: do a first run against **TestPyPI** by temporarily
pointing the publish steps at `repository-url: https://test.pypi.org/legacy/` and
registering the same trusted publishers there.)

---

## Cutting a release

1. Bump the version in **all four** places (keep them in lockstep):
   - `pyproject.toml` → `[project] version`
   - `rust/Cargo.toml` → `[package] version`
   - `rust/pyproject.toml` → `[project] version`
   - `src/desphere/__init__.py` → `__version__`
2. Update `CHANGELOG.md` (move *Unreleased* into a dated version section).
3. Commit, then tag and push:
   ```bash
   git commit -am "release: v0.1.0"
   git tag v0.1.0
   git push && git push --tags
   ```
4. The `Release` workflow builds the pure sdist+wheel and the native abi3 wheels
   (linux x86_64/aarch64, macOS universal2, Windows x64), then publishes each
   project from its environment. `desphere-native` is **wheels-only** (no sdist —
   the optional accelerator degrades to pure Python where no wheel matches; the
   pure `desphere` provides the source-installable path). Both publish steps use
   `skip-existing: true`, so re-running after a partial upload only fills the gaps.
   Watch it under **Actions**; if you set required reviewers, approve each
   environment.

### Dry run (no publish)

Trigger the workflow manually (**Actions → Release → Run workflow**). The build
jobs run and upload artifacts; the publish jobs are skipped because they require
a `refs/tags/v*` push. Download the artifacts to inspect the wheels.

---

## Local sanity checks before tagging

```bash
# Pure package: lean sdist (only src/desphere + tests + docs) and a universal wheel
python -m build --outdir /tmp/desphere_dist
tar -tzf /tmp/desphere_dist/*.tar.gz | sed 's#desphere-0.1.0/##' | sort   # no rust/ web/ oracles/
python -m twine check /tmp/desphere_dist/*

# Native accelerator: builds, installs, and stays byte-identical to pure Python
cd rust && VIRTUAL_ENV=$HOME/local/scr/venvs/desphere maturin develop --release --features python && cd ..
python -m pytest -q           # the parity test (test_native_matches_pure) runs only when native is importable
```

A version mismatch between `desphere` and `desphere-native` is harmless (the
accelerator is resolved by name, not pinned), but releasing them together keeps
things tidy.
