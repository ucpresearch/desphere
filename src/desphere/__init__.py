"""desphere — a clean-room NIST SPHERE -> RIFF/WAV transcoder.

Flatten a "sphere" (NIST SPHERE audio) into a flat WAV. MIT-licensed,
zero-dependency, built only from public format documentation and black-box
testing — never from GPL/LGPL source.

Public API::

    from desphere import read_sphere, transcode, sph_to_wav, SphereHeader

    header, data = read_sphere("utt.sph")
    with open("utt.wav", "wb") as f:
        transcode(header, data, f)
"""

from __future__ import annotations

from .errors import (
    DesphereError,
    SphereHeaderError,
    UnsupportedCoding,
    UnsupportedFormat,
)
from .sphere import SphereHeader
from .transcode import read_sphere, sph_to_wav, transcode
from .wav import write_wav

__version__ = "0.0.1"

__all__ = [
    "__version__",
    "SphereHeader",
    "read_sphere",
    "transcode",
    "sph_to_wav",
    "write_wav",
    "DesphereError",
    "SphereHeaderError",
    "UnsupportedCoding",
    "UnsupportedFormat",
]
