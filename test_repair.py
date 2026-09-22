"""
Does inverse-solving actually recover the corrupted OCR fields?

Tested against the real failing rows from benchmark_cells.py, scored against
the hand-transcribed ground truth in data/trail_ridge_estates.py.

This was previously a print-only script (no assertions), so a regression in
engine.repair could silently drop the recovery rate to zero and the "test"
would still report success. These are real pytest assertions instead.
"""
from __future__ import annotations

import data.trail_ridge_estates as trd
from engine.ocr import validate_curve
from engine.repair import apply_corrections, digit_edit_ok, inverse_solve_curve, radius_consensus

# Actual OCR output rows that failed (verbatim from the benchmark run)
OCR_ROWS = {
    "C3":  dict(length=172.69, radius=119.0, delta=89.9517, chord_bearing="N44°25'14\"E", chord=155.50),
    "C45": dict(length=13.06,  radius=20.0,  delta=14.9672, chord_bearing="N87°55'49\"W", chord=13.02),
    "C46": dict(length=44.76,  radius=29.0,  delta=102.58,  chord_bearing="N51°17'24\"W", chord=39.02),
    "C21": dict(length=74.22,  radius=140.0, delta=3.3767,  chord_bearing="N66°47'15\"E", chord=73.36),
    "C15": dict(length=0.59,   radius=140.0, delta=2.7053,  chord_bearing="N08°15'04\"W", chord=90.32),
    "C28": dict(length=30.27,  radius=26.0,  delta=9.0,     chord_bearing="S44°23'47\"W", chord=35.36),
    "C49": dict(length=168.28, radius=274.0, delta=68.1672, chord_bearing="S68°10'02\"E", chord=165.65),
    "C35": dict(length=15.86,  radius=274.0, delta=77.83,   chord_bearing="S77°49'48\"E", chord=76.62),
    "C6":  dict(length=26.34,  radius=82.0,  delta=8.2483,  chord_bearing="S08°14'54\"W", chord=20.24),
    "C25": dict(length=19.95,  radius=1148.0, delta=12.5572, chord_bearing="N12°33'26\"W", chord=19.93),
    "C37": dict(length=20.38,  radius=1000.0, delta=87.5533, chord_bearing="S87°33'12\"E", chord=20.88),
}

# Rows the current tiered pipeline (intra-row inverse + radius consensus)
# recovers to an EXACT match against ground truth. Locks in the measured
# 4/11 (36%) recovery rate as a regression floor: if this set shrinks, the
# repair pipeline got worse.
EXPECTED_EXACT = {"C3", "C21", "C45", "C46"}

GROUND_TRUTH = {k: v for k, v in trd.CURVE_TABLE.items() if isinstance(v, dict) and "radius" in v}


def _matches_ground_truth(rec: dict, gt: dict, tol=0.02) -> bool:
    return (abs(rec["radius"] - gt["radius"]) < tol
            and abs(rec["length"] - gt["length"]) < tol
            and abs(rec["chord"] - gt["chord"]) < tol
            and abs(rec["delta"] - gt["delta"]) < 0.01)


def _run_pipeline():
    """Tier 1 (intra-row inverse) + Tier 2 (radius consensus), applied and
    re-verified -- mirrors the manual repair workflow in scripts/benchmark_cells.py."""
    corrections = {}
    for cid, rec in OCR_ROWS.items():
        cands = inverse_solve_curve(rec)
        if cands:
            corrections[cid] = cands[0]

    for cid, c in radius_consensus(dict(OCR_ROWS)).items():
        corrections.setdefault(cid, c)

    return apply_corrections(OCR_ROWS, corrections)


def test_all_ground_truth_rows_present():
    """Sanity check on the fixture data itself: every OCR row under test has
    a matching hand-transcribed ground-truth row to score against."""
    missing = set(OCR_ROWS) - set(GROUND_TRUTH)
    assert not missing, f"no ground truth for: {sorted(missing)}"


def test_exact_recovery_rate_does_not_regress():
    fixed, _applied, _review = _run_pipeline()
    exact = {cid for cid, rec in fixed.items() if _matches_ground_truth(rec, GROUND_TRUTH[cid])}
    assert exact >= EXPECTED_EXACT, (
        f"lost previously-recovered rows: {EXPECTED_EXACT - exact}. "
        f"Currently exact: {sorted(exact)}"
    )


def test_recovered_rows_are_individually_correct():
    fixed, _applied, _review = _run_pipeline()
    for cid in EXPECTED_EXACT:
        gt = GROUND_TRUTH[cid]
        rec = fixed[cid]
        assert _matches_ground_truth(rec, gt), f"{cid}: got {rec}, expected {gt}"
        ok, _ = validate_curve(rec)
        assert ok, f"{cid}: corrected row does not pass geometric validation: {rec}"


def test_auto_applied_corrections_are_all_high_confidence():
    """Only single-digit-edit-plausible corrections may be applied
    automatically; redundancy-only ("column leak") corrections must be
    flagged for human review, never written in silently."""
    _fixed, applied, review = _run_pipeline()
    assert applied, "expected at least one auto-applied correction"
    for entry in applied:
        assert entry["action"] == "auto-applied"
    for entry in review:
        assert entry["action"] == "FLAGGED for review (not auto-applied)"
    # C49 and C25 are only corroborated by redundancy (no plausible
    # single-digit edit) -- they must be flagged, not auto-applied.
    review_ids = {e["curve"] for e in review}
    assert {"C49", "C25"} <= review_ids


def test_unrecovered_rows_stay_flagged_not_silently_wrong():
    """Rows the pipeline can't confidently fix must not be marked exact --
    guards against a false-positive "fix" being worse than no fix."""
    fixed, _applied, _review = _run_pipeline()
    still_bad = set(OCR_ROWS) - EXPECTED_EXACT
    for cid in still_bad:
        assert not _matches_ground_truth(fixed[cid], GROUND_TRUTH[cid]), (
            f"{cid} now matches ground truth -- update EXPECTED_EXACT if the "
            "repair pipeline genuinely improved"
        )


# --- lower-level unit coverage for the OCR digit-confusion matcher ---

def test_digit_edit_ok_detects_substitution():
    # '5' and '6' are in each other's OCR confusion set (CONFUSE).
    ok, why = digit_edit_ok(5.0, 6.0, decimals=0)
    assert ok
    assert "substitution" in why


def test_digit_edit_ok_rejects_multi_digit_difference():
    ok, _why = digit_edit_ok(12.5572, 99.9999, decimals=4)
    assert not ok
