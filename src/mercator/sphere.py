"""NIST SPHERE header parsing.

The NIST SPHERE format is a fixed ASCII header followed by raw audio bytes.
This module is built purely from the *public* NIST format description; no
GPL/LGPL source (sph2pipe, the original ``shorten``, FFmpeg, ...) was consulted.

Header structure::

    NIST_1A\n              <- 7-byte magic + newline
    <header-size>\n        <- total header length in bytes (ASCII int, usually 1024)
    field -TYPE value\n    <- zero or more typed object fields
    ...
    end_head\n             <- marks the end of the field list
    <whitespace padding>   <- spaces up to <header-size>
    <audio data>           <- begins at byte offset <header-size>

Field types:
    -i        integer
    -r        real (float)
    -s<N>     string of length N
"""

from __future__ import annotations

from typing import Dict

from .errors import SphereHeaderError

MAGIC = b"NIST_1A"
_DEFAULT_HEADER_SIZE = 1024

# Fields we require to interpret the audio payload. Note: sample_coding is NOT
# required — real corpora (e.g. classic TIMIT) omit it, and it defaults to
# "pcm" per the NIST convention (see SphereHeader.sample_coding).
_REQUIRED = (
    "sample_count",
    "sample_rate",
    "channel_count",
    "sample_n_bytes",
)


class SphereHeader:
    """Parsed NIST SPHERE header.

    Use :meth:`from_file` to read a file, or :meth:`parse` for an in-memory
    header. Typed field values are available both via attribute-style
    properties (the common fields) and via :meth:`get` for anything else.
    """

    def __init__(self, fields: Dict[str, object], header_size: int) -> None:
        self.fields = fields
        self.header_size = header_size
        self._validate()

    # ------------------------------------------------------------------ parse

    @classmethod
    def parse(cls, blob: bytes) -> "SphereHeader":
        """Parse a SPHERE header from bytes (must contain the full header)."""
        if not blob.startswith(MAGIC):
            raise SphereHeaderError(
                "not a NIST SPHERE file (missing 'NIST_1A' magic)"
            )

        # The header size lives on line 2; read it before trusting the rest.
        first_lines = blob.split(b"\n", 2)
        if len(first_lines) < 2:
            raise SphereHeaderError("truncated SPHERE header (no size line)")
        try:
            header_size = int(first_lines[1].strip())
        except ValueError as exc:
            raise SphereHeaderError(
                f"invalid header size line: {first_lines[1]!r}"
            ) from exc
        if header_size <= 0:
            raise SphereHeaderError(f"non-positive header size: {header_size}")
        if len(blob) < header_size:
            raise SphereHeaderError(
                f"header claims {header_size} bytes but only {len(blob)} available"
            )

        try:
            text = blob[:header_size].decode("ascii")
        except UnicodeDecodeError as exc:
            raise SphereHeaderError("SPHERE header is not valid ASCII") from exc

        lines = text.split("\n")
        # lines[0] == magic, lines[1] == size; fields start at index 2.
        fields: Dict[str, object] = {}
        saw_end = False
        for line in lines[2:]:
            stripped = line.strip()
            if stripped == "":
                continue
            if stripped == "end_head":
                saw_end = True
                break
            name, value = _parse_field_line(stripped)
            fields[name] = value

        if not saw_end:
            raise SphereHeaderError("SPHERE header missing 'end_head' terminator")

        return cls(fields, header_size)

    @classmethod
    def from_file(cls, path) -> "tuple[SphereHeader, bytes]":
        """Read ``path`` and return ``(header, audio_data_bytes)``."""
        with open(path, "rb") as f:
            head = f.read(_DEFAULT_HEADER_SIZE)
            if not head.startswith(MAGIC):
                raise SphereHeaderError(
                    f"{path}: not a NIST SPHERE file (missing 'NIST_1A' magic)"
                )
            parts = head.split(b"\n", 2)
            if len(parts) < 2:
                raise SphereHeaderError(f"{path}: truncated SPHERE header")
            try:
                header_size = int(parts[1].strip())
            except ValueError as exc:
                raise SphereHeaderError(
                    f"{path}: invalid header size line: {parts[1]!r}"
                ) from exc
            if header_size > len(head):
                head += f.read(header_size - len(head))
            header = cls.parse(head)
            f.seek(header.header_size)
            data = f.read()
        return header, data

    # -------------------------------------------------------------- accessors

    def get(self, name: str, default=None):
        return self.fields.get(name, default)

    @property
    def sample_count(self) -> int:
        return int(self.fields["sample_count"])

    @property
    def sample_rate(self) -> int:
        return int(self.fields["sample_rate"])

    @property
    def channel_count(self) -> int:
        return int(self.fields["channel_count"])

    @property
    def sample_n_bytes(self) -> int:
        return int(self.fields["sample_n_bytes"])

    @property
    def sample_byte_format(self) -> str:
        # Single-byte audio has no byte order; default to "1".
        return str(self.fields.get("sample_byte_format", "1"))

    @property
    def sample_sig_bits(self) -> int:
        return int(self.fields.get("sample_sig_bits", self.sample_n_bytes * 8))

    @property
    def sample_coding(self) -> str:
        return str(self.fields.get("sample_coding", "pcm"))

    @property
    def expected_data_bytes(self) -> int:
        return self.sample_count * self.channel_count * self.sample_n_bytes

    # --------------------------------------------------------------- internal

    def _validate(self) -> None:
        missing = [k for k in _REQUIRED if k not in self.fields]
        if missing:
            raise SphereHeaderError(
                "SPHERE header missing required field(s): " + ", ".join(missing)
            )
        if self.channel_count < 1:
            raise SphereHeaderError(
                f"channel_count must be >= 1, got {self.channel_count}"
            )
        if self.sample_n_bytes < 1:
            raise SphereHeaderError(
                f"sample_n_bytes must be >= 1, got {self.sample_n_bytes}"
            )

    def __repr__(self) -> str:
        return (
            f"SphereHeader(sample_count={self.sample_count}, "
            f"sample_rate={self.sample_rate}, channel_count={self.channel_count}, "
            f"sample_n_bytes={self.sample_n_bytes}, "
            f"sample_byte_format={self.sample_byte_format!r}, "
            f"sample_coding={self.sample_coding!r})"
        )


def _parse_field_line(line: str) -> "tuple[str, object]":
    """Parse one ``name -TYPE value`` header line into ``(name, typed_value)``."""
    parts = line.split(None, 2)
    if len(parts) < 3:
        # A type with an empty string value (-s0) is the only legitimate
        # 2-token case; everything else is malformed.
        if len(parts) == 2 and parts[1].startswith("-s"):
            name, type_tok = parts
            return name, ""
        raise SphereHeaderError(f"malformed SPHERE header line: {line!r}")

    name, type_tok, raw = parts
    if not type_tok.startswith("-") or len(type_tok) < 2:
        raise SphereHeaderError(f"unknown field type in line: {line!r}")

    kind = type_tok[1]
    value = raw.strip()
    if kind == "i":
        try:
            return name, int(value)
        except ValueError as exc:
            raise SphereHeaderError(
                f"field {name!r} declared integer but value is {value!r}"
            ) from exc
    if kind == "r":
        try:
            return name, float(value)
        except ValueError as exc:
            raise SphereHeaderError(
                f"field {name!r} declared real but value is {value!r}"
            ) from exc
    if kind == "s":
        return name, value
    raise SphereHeaderError(f"unknown field type {type_tok!r} in line: {line!r}")
