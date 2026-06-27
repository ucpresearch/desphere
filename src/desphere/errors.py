"""Exception hierarchy for desphere.

Everything that goes wrong raises a subclass of :class:`DesphereError`, so a
caller (or the ``sph2wav`` CLI) can catch one type and always get an actionable
message instead of a stack trace or, worse, a plausible-but-wrong WAV.
"""

from __future__ import annotations


class DesphereError(Exception):
    """Base class for all desphere errors."""


class SphereHeaderError(DesphereError):
    """The NIST SPHERE header is missing, malformed, or internally inconsistent.

    Also raised when the audio payload is shorter than the header claims.
    """


class UnsupportedCoding(DesphereError):
    """The ``sample_coding`` is structurally valid but not implemented.

    Examples: a base coding desphere does not recognize, or a compression token
    other than ``embedded-shorten-v2.00``. We fail loudly rather than guess.
    """


class UnsupportedFormat(DesphereError):
    """A structurally valid field describes a layout we have not validated.

    Examples: 8-bit or 24-bit PCM, or an unrecognized ``sample_byte_format``.
    """
