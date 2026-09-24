"""Boundary caption (Sheet 1, PB30 Pg82) vs the engine's RAW_BOUNDARY_COURSES table.

The caption was re-read from the 300-dpi scan. Seven courses in the engine table differ from it; the engine
table then "closes" to 1.8 ft (1:4,548) and Bowditch hides the rest, while the caption table closes to 0.04 ft.
A misclosure of that size that collapses when seven transcriptions are corrected is strong independent evidence
that the caption reading is right.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from plat_curves.core import bearing_to_az

DATA = Path(__file__).resolve().parents[1] / "data" / "boundary_caption_pb30_p82.json"
CAPTION = json.loads(DATA.read_text(encoding="utf-8"))["courses"]
CHANGED = {"c2", "c5", "c9", "c11", "c13", "c15", "c24"}


def _closure(courses):
    n = e = perimeter = 0.0
    for c in courses:
        az = math.radians(bearing_to_az(c["bearing"]))
        n += c["distance"] * math.cos(az)
        e += c["distance"] * math.sin(az)
        perimeter += c["distance"]
    return n, e, math.hypot(n, e), perimeter


def test_caption_has_27_courses_in_order():
    assert [c["id"] for c in CAPTION] == [f"c{i}" for i in range(1, 28)]


def test_caption_table_closes_tightly():
    _, _, linear, perimeter = _closure(CAPTION)
    assert linear < 0.10  # 0.042 ft as read
    assert perimeter / linear > 50_000


def test_chord_c22_matches_tangent_deflection():
    """S54°41'40"E tangent (c21) -> chord S57°53'59"E: Delta = 2 * 3°12'19" = 6°24'38" for R=894.08."""
    delta = 2.0 * (bearing_to_az("S54°41'40\"E") - bearing_to_az("S57°53'59\"E"))
    chord = 2.0 * 894.08 * math.sin(math.radians(delta) / 2.0)
    assert chord == pytest.approx(99.98, abs=0.02)


def _engine_rows():
    from engine.cogo_road_centerlines import RAW_BOUNDARY_COURSES

    return {cid: (b, d) for cid, b, d, _ in RAW_BOUNDARY_COURSES}


def test_uncorrected_courses_agree_with_engine():
    """The 20 courses NOT flagged agree with the engine (bearing az within 1e-6 deg, distance exact)."""
    eng = _engine_rows()
    for c in CAPTION:
        if c["id"] in CHANGED:
            continue
        b, d = eng[c["id"]]
        assert bearing_to_az(b) == pytest.approx(bearing_to_az(c["bearing"]), abs=1e-6), c["id"]
        assert d == pytest.approx(c["distance"], abs=1e-9), c["id"]


@pytest.mark.xfail(
    strict=True,
    reason="engine.RAW_BOUNDARY_COURSES has 7 transcription errors vs the Sheet 1 caption "
    "(c2, c5, c9, c11, c13, c15, c24); remove this xfail once the table is fixed",
)
def test_engine_table_matches_caption():
    eng = _engine_rows()
    for c in CAPTION:
        b, d = eng[c["id"]]
        assert bearing_to_az(b) == pytest.approx(bearing_to_az(c["bearing"]), abs=1e-6), c["id"]
        assert d == pytest.approx(c["distance"], abs=1e-9), c["id"]


def test_engine_table_misclosure_is_the_symptom():
    """Records the symptom: the engine's own table only closes to ~1.8 ft, 40x worse than the caption."""
    eng = _engine_rows()
    rows = [{"bearing": eng[c["id"]][0], "distance": eng[c["id"]][1]} for c in CAPTION]
    _, _, linear_engine, _ = _closure(rows)
    _, _, linear_caption, _ = _closure(CAPTION)
    assert linear_engine > 1.0
    assert linear_engine > 20 * linear_caption
