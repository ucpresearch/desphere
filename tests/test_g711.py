"""Self-contained G.711 sanity checks (no external tools needed).

The exhaustive table is validated against ffmpeg via the committed
``*_allcodes.sph`` fixtures (see test_fixtures.py). These checks pin a few
anchor values from the ITU-T G.711 standard so the table is sanity-checked even
when fixtures/ffmpeg are unavailable.
"""

from __future__ import annotations

from mercator import g711


def test_table_sizes_and_range():
    assert len(g711.ULAW_TABLE) == 256
    assert len(g711.ALAW_TABLE) == 256
    for t in (g711.ULAW_TABLE, g711.ALAW_TABLE):
        assert all(-32768 <= v <= 32767 for v in t)


def test_ulaw_anchors():
    # 0xFF and 0x7F are the two mu-law "zero" codes (+/- smallest magnitude).
    assert g711.ULAW_TABLE[0xFF] == 0
    assert g711.ULAW_TABLE[0x7F] == 0
    # Full-scale codes (0x00 / 0x80) are the largest magnitudes, opposite signs.
    # Per G.711, code 0x00 is the most-negative sample, 0x80 the most-positive.
    assert g711.ULAW_TABLE[0x00] == -32124
    assert g711.ULAW_TABLE[0x80] == 32124
    assert g711.ULAW_TABLE[0x00] == -g711.ULAW_TABLE[0x80]


def test_alaw_anchors():
    # a-law toggles even bits (xor 0x55); 0x55 -> smallest negative step.
    assert g711.ALAW_TABLE[0x55] == -8
    assert g711.ALAW_TABLE[0xD5] == 8


def test_expand_produces_le_int16():
    out = g711.expand(bytes([0xFF, 0x00]), g711.ULAW_TABLE)
    assert len(out) == 4  # 2 samples x 2 bytes
    import struct

    assert struct.unpack("<2h", out) == (0, g711.ULAW_TABLE[0x00])
