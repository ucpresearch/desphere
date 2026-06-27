"""``sph2wav`` command-line interface.

Usage::

    sph2wav INPUT.sph [OUTPUT.wav]
    sph2wav --info INPUT.sph
    sph2wav INPUT.sph -        # write WAV to stdout

Mirrors the name of the tool people migrate away from, so it is easy to find.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile

from . import __version__
from .errors import DesphereError
from .sphere import SphereHeader
from .transcode import read_sphere, transcode


def _default_output(in_path: str) -> str:
    root, _ = os.path.splitext(in_path)
    return root + ".wav"


def _print_info(header: SphereHeader, in_path: str, data_len: int) -> None:
    duration = (
        header.sample_count / header.sample_rate if header.sample_rate else 0.0
    )
    print(f"{in_path}")
    print(f"  sample_coding      : {header.sample_coding}")
    print(f"  sample_rate        : {header.sample_rate} Hz")
    print(f"  channel_count      : {header.channel_count}")
    print(f"  sample_n_bytes     : {header.sample_n_bytes} ({header.sample_n_bytes * 8}-bit)")
    print(f"  sample_byte_format : {header.sample_byte_format}")
    print(f"  sample_sig_bits    : {header.sample_sig_bits}")
    print(f"  sample_count       : {header.sample_count} ({duration:.3f} s)")
    print(f"  header_size        : {header.header_size} bytes")
    tokens = [t.strip().lower() for t in header.sample_coding.split(",")]
    if len(tokens) > 1 and tokens[1]:
        # Compressed: the payload is a bitstream, so expected_data_bytes is the
        # UNCOMPRESSED size, not a target to match.
        print(
            f"  payload bytes      : {data_len} "
            f"(compressed; uncompressed ~{header.expected_data_bytes})"
        )
    else:
        print(f"  payload bytes      : {data_len} (expected {header.expected_data_bytes})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sph2wav",
        description="Transcode a NIST SPHERE file to RIFF/WAV (desphere).",
    )
    p.add_argument("input", help="input .sph file")
    p.add_argument(
        "output",
        nargs="?",
        help="output .wav file (default: input with .wav extension; '-' for stdout)",
    )
    p.add_argument("--info", action="store_true", help="print header and exit")
    p.add_argument(
        "-f", "--force", action="store_true", help="overwrite output if it exists"
    )
    p.add_argument("--version", action="version", version=f"desphere {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        header, data = read_sphere(args.input)
    except DesphereError as exc:
        print(f"sph2wav: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"sph2wav: cannot read {args.input}: {exc}", file=sys.stderr)
        return 2

    if args.info:
        _print_info(header, args.input, len(data))
        return 0

    out_path = args.output or _default_output(args.input)
    to_stdout = out_path == "-"

    if not to_stdout:
        if os.path.abspath(out_path) == os.path.abspath(args.input):
            print(
                "sph2wav: refusing to overwrite the input file; "
                "specify a different output path",
                file=sys.stderr,
            )
            return 2
        if os.path.exists(out_path) and not args.force:
            print(
                f"sph2wav: {out_path} exists (use -f/--force to overwrite)",
                file=sys.stderr,
            )
            return 2

    try:
        if to_stdout:
            transcode(header, data, sys.stdout.buffer)
        else:
            # Write to a temp file and atomically rename on success, so a failed
            # decode never leaves a partial or 0-byte .wav behind.
            out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
            fd, tmp = tempfile.mkstemp(suffix=".wav.tmp", dir=out_dir)
            try:
                with os.fdopen(fd, "wb") as f:
                    transcode(header, data, f)
                os.replace(tmp, out_path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
    except DesphereError as exc:
        print(f"sph2wav: {exc}", file=sys.stderr)
        return 2

    if not to_stdout:
        print(f"sph2wav: wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
