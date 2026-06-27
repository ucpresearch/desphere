"""Exception hierarchy for mercator.

Everything that goes wrong raises a subclass of :class:`MercatorError`, so a
caller (or the ``sph2wav`` CLI) can catch one type and always get an actionable
message instead of a stack trace or, worse, a plausible-but-wrong WAV.
"""

from __future__ import annotations


class MercatorError(Exception):
    """Base class for all mercator errors."""


class SphereHeaderError(MercatorError):
    """The NIST SPHERE header is missing, malformed, or internally inconsistent.

    Also raised when the audio payload is shorter than the header claims.
    """


class UnsupportedCoding(MercatorError):
    """The ``sample_coding`` is valid but not implemented yet.

    Examples: ``ulaw``/``alaw`` (G.711) or any compressed coding such as
    ``pcm,embedded-shorten-v2.00``. We fail loudly rather than guess.
    """


class UnsupportedFormat(MercatorError):
    """A structurally valid field describes a layout we have not validated.

    Examples: 8-bit or 24-bit PCM, or an unrecognized ``sample_byte_format``.
    """
