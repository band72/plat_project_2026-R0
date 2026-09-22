"""
test_plat_pipeline.py -- pytest coverage for engine/plat_pipeline.py, the
generic (non-Beachwood-specific) plat solver (plat-reader/IMPLEMENTATION_PLAN.md).

Deliberately tests the traverse/closure/repair/subdivision LOGIC with
hand-built course lists rather than real scanned images: that logic is the
new code this module adds, and it needs to be verified independent of
OCR/image variance (which is real, documented, and expected to vary --
see IMPLEMENTATION_PLAN.md section 8 -- and is exercised separately via
manual runs against Plat/*.pdf, not asserted on here since success there is
inherently source-material-dependent, not a property of this code).
"""
from __future__ import annotations

import math

from engine.cogo import Course, Point
from engine.plat_pipeline import (
    PipelineDiagnostics,
    Verdict,
    order_courses,
    solve_generic_traverse,
    subdivide_uniform_lot_row,
)

# A "there and back" quadrilateral: course 3 is the exact reverse of course 1
# and course 4 the exact reverse of course 2, so it closes EXACTLY regardless
# of the specific bearings chosen (no orthogonality assumption needed).
CLOSING_COURSES = [
    Course(label="L1", bearing="N01°00'00\"E", distance=300.0),
    Course(label="L2", bearing="S89°00'00\"E", distance=400.0),
    Course(label="L3", bearing="S01°00'00\"W", distance=300.0),
    Course(label="L4", bearing="N89°00'00\"W", distance=400.0),
]


def test_closing_traverse_passes_exactly():
    diag = PipelineDiagnostics()
    result = solve_generic_traverse(Point(0.0, 0.0), CLOSING_COURSES, {}, diag)
    assert result.misclose_dist_ft < 1e-6
    assert result.passed
    assert result.fac_5j17_passed
    assert result.verdict.startswith(Verdict.PASS)
    assert not result.verdict.startswith(Verdict.PASS_REPAIRED)
    assert result.computed_area_sqft > 0


def test_broken_line_course_fails_honestly():
    """A single-digit dropout on a straight course (300.00 -> 30.00) has no
    redundant field to inverse-solve from (unlike a curve's R/L/D/C) --
    the pipeline must report FAILED, not silently force a fake close."""
    broken = list(CLOSING_COURSES)
    broken[2] = Course(label="L3", bearing="S01°00'00\"W", distance=30.0)
    diag = PipelineDiagnostics()
    result = solve_generic_traverse(Point(0.0, 0.0), broken, {}, diag)
    assert not result.passed
    assert result.verdict.startswith(Verdict.FAILED)
    assert result.misclose_dist_ft > 100.0  # the real, undisguised gap


def test_curve_chord_repair_recovers_exact_closure():
    """A corrupted chord (the field that actually affects the walk, unlike
    radius/delta) on an over-determined curve row is recovered via
    engine.repair's existing inverse-solve, and the result is downgraded
    to PASS_REPAIRED (not plain PASS) with the correction disclosed."""
    R, D = 140.0, 20.7053
    length = R * math.radians(D)
    true_chord = 2 * R * math.sin(math.radians(D) / 2)
    curves = {
        "C1": dict(length=round(length, 2), radius=R, delta=D,
                   chord_bearing="N45°00'00\"E", chord=15.32),  # corrupted: true is ~50.32
        "C2": dict(length=round(length, 2), radius=R, delta=D,
                   chord_bearing="S45°00'00\"W", chord=round(true_chord, 2)),
    }
    courses = [Course(label="C1", curve_id="C1"), Course(label="C2", curve_id="C2")]
    diag = PipelineDiagnostics()
    result = solve_generic_traverse(Point(0.0, 0.0), courses, curves, diag)
    assert result.misclose_dist_ft < 0.01
    assert result.verdict.startswith(Verdict.PASS_REPAIRED)
    assert diag.repairs_applied
    assert "chord" in diag.repairs_applied[0]


def test_order_courses_merges_lines_and_curves_by_numeric_id():
    lines = {"L1": dict(bearing="N01°00'00\"E", length=100.0),
             "L3": dict(bearing="S01°00'00\"W", length=100.0)}
    curves = {"C2": dict(radius=50.0, length=10.0, delta=11.46,
                         chord_bearing="N45°00'00\"E", chord=10.0)}
    diag = PipelineDiagnostics()
    courses, curves_by_id = order_courses(curves, lines, diag)
    assert [c.label for c in courses] == ["L1", "C2", "L3"]
    assert diag.ordering_is_heuristic
    assert "C2" in curves_by_id


def test_order_courses_keeps_rows_with_unreadable_id_label():
    """A row whose ID label failed to OCR (engine.ocr's '_lrowN'/'_rowN'
    convention) must still be walked, not silently dropped -- losing a row
    entirely because one label smudged throws away otherwise-good geometry."""
    lines = {"L1": dict(bearing="N01°00'00\"E", length=100.0),
             "_lrow1": dict(bearing="S01°00'00\"W", length=100.0, id_missing=True)}
    diag = PipelineDiagnostics()
    courses, _curves = order_courses({}, lines, diag)
    assert len(courses) == 2
    assert diag.ordering_is_heuristic
    assert any("unreadable ID label" in w for w in diag.warnings)


def test_no_courses_extracted_is_reported_not_crashed():
    diag = PipelineDiagnostics()
    result = solve_generic_traverse(Point(0.0, 0.0), [], {}, diag)
    assert not result.passed
    assert result.verdict.startswith(Verdict.FAILED)
    assert result.courses == []


def test_uniform_lot_subdivision_areas_sum_to_boundary():
    diag = PipelineDiagnostics()
    boundary = solve_generic_traverse(Point(0.0, 0.0), CLOSING_COURSES, {}, diag)
    lots = subdivide_uniform_lot_row(boundary, 4, diag)
    assert len(lots) == 4
    assert all(lot.passed for lot in lots)
    total = sum(lot.computed_area_sqft for lot in lots)
    assert abs(total - boundary.computed_area_sqft) < 1.0
    # uniform widths: each lot should be (front distance / 4) wide, so the
    # four lot areas should be equal to each other.
    areas = [lot.computed_area_sqft for lot in lots]
    assert max(areas) - min(areas) < 0.01


def test_lot_subdivision_skips_when_next_course_is_not_orthogonal():
    """A frontage whose next course isn't ~90 deg away isn't a simple
    rectangular row -- must be skipped with a clear reason, not forced."""
    non_rect = [
        Course(label="L1", bearing="N01°00'00\"E", distance=300.0),
        Course(label="L2", bearing="S45°00'00\"E", distance=400.0),  # not ~90 deg from L1
        Course(label="L3", bearing="S01°00'00\"W", distance=300.0),
        Course(label="L4", bearing="N45°00'00\"W", distance=400.0),
    ]
    diag = PipelineDiagnostics()
    boundary = solve_generic_traverse(Point(0.0, 0.0), non_rect, {}, diag)
    lots = subdivide_uniform_lot_row(boundary, 4, diag)
    assert lots == []
    assert any("not ~90 deg apart" in w for w in diag.warnings)


def test_lot_flags_populated_and_surfaced():
    diag = PipelineDiagnostics()
    diag.warnings.append("test diagnostic warning")
    diag.repairs_applied.append("C1 chord corrected")
    boundary = solve_generic_traverse(Point(0.0, 0.0), CLOSING_COURSES, {}, diag)
    assert hasattr(boundary, "flags")
    assert "test diagnostic warning" in boundary.flags
    assert any("C1 chord corrected" in f for f in boundary.flags)

    lots = subdivide_uniform_lot_row(boundary, 2, diag)
    assert len(lots) == 2
    assert all(hasattr(lot, "flags") and len(lot.flags) > 0 for lot in lots)


def test_extract_call_table_borderless_fallback():
    import numpy as np

    from engine.plat_pipeline import extract_call_table
    # Blank/borderless 400x400 image has no table borders
    blank = np.ones((400, 400), dtype=np.uint8) * 255
    curves, lines, diag = extract_call_table(blank)
    assert curves == {}
    assert lines == {}
    assert any("falling back to full image table scan" in w for w in diag.warnings)
