"""
test_block10_11_12_cogo.py -- Pure Deterministic Unit Test Suite for Blocks 10, 11
and 12 (the portion of each west of the Beachwood Unit One matchline).

Covers: traverse closure for every certified lot, the 0°20'00" skew mechanism
shared with Block 13 (west/R/W side non-perpendicular to the street grid,
everything else perpendicular), the cross-validation between independently
constructed adjacent lots in Block 12 (Lot 5's computed east side vs Lot 4's
stated west side), and Block 12's flagged-point mechanism for Lots 8-10,
which the plat scan did not yield enough legible data to certify (see
BeachwoodBlock12Solver's docstring and engine/notes_audit.py /
.claude/skills/review-plat-notes).
"""

import math

from engine.cogo_block import (
    BeachwoodBlock10Solver,
    BeachwoodBlock11Solver,
    BeachwoodBlock12Solver,
)


def test_block10_all_lots_close_exactly():
    solver = BeachwoodBlock10Solver()
    assert set(solver.lots.keys()) == {"13", "12", "11", "10", "9"}
    for num, lot in solver.lots.items():
        res = lot.compute_mapcheck()
        assert res.misclose_dist_ft < 1e-6, f"Lot {num} failed to close: {res.misclose_dist_ft}"
        assert res.passed


def test_block10_lot13_skew_matches_stated_rear_dimension():
    """Lot 13 alone uses the non-perpendicular R/W bearing (S01°01'40"E) for
    its west side while every other Block 10 lot uses the standard
    perpendicular divider -- this must reproduce the plat's stated 98.01'
    front / 97.43' rear (a 0.58' taper over 100' depth, same 0°20'00" skew
    documented for Block 13's Lot 11)."""
    solver = BeachwoodBlock10Solver()
    p = solver.points
    front = p["p13_nw"].dist_to(p["p13_ne"])
    rear = p["p13_sw"].dist_to(p["p13_se"])
    assert abs(front - 98.01) < 0.01
    assert abs(rear - 97.43) < 0.01
    assert abs((front - rear) - 100.0 * math.tan(math.radians(20.0 / 60.0))) < 0.01


def test_block10_matchline_length_matches_plat():
    """Lot 9's east side is the matchline: N00°41'40"W, 100.00' per the
    plat's explicit "N.0°41'40"W. 100.0'" label."""
    solver = BeachwoodBlock10Solver()
    p = solver.points
    assert abs(p["p9_se"].dist_to(p["p9_ne"]) - 100.00) < 0.01


def test_block11_all_lots_close_exactly():
    solver = BeachwoodBlock11Solver()
    assert set(solver.lots.keys()) == {"15", "16", "17", "14", "13", "12"}
    for num, lot in solver.lots.items():
        res = lot.compute_mapcheck()
        assert res.misclose_dist_ft < 1e-6, f"Lot {num} failed to close: {res.misclose_dist_ft}"
        assert res.passed


def test_block11_matchline_total_length_matches_plat():
    """The matchline (Lots 17 & 12 east sides) is explicitly labeled
    "N.0°41'40"W. - 200.0'" on the plat -- 100' per row."""
    solver = BeachwoodBlock11Solver()
    p = solver.points
    north_leg = p["p17_se"].dist_to(p["p17_ne"])
    south_leg = p["p12_se"].dist_to(p["p12_ne"])
    assert abs(north_leg - 100.00) < 0.01
    assert abs(south_leg - 100.00) < 0.01
    assert abs((north_leg + south_leg) - 200.00) < 0.01


def test_block11_skew_taper_across_bayou_midline_surfwood():
    """Bayou frontage (243.83') -> mid-dividing-line (243.25') -> Surfwood
    frontage (242.67'), each step down by depth*tan(0°20'00") = 0.58',
    entirely attributable to Lots 15/14's non-perpendicular west side."""
    solver = BeachwoodBlock11Solver()
    p = solver.points
    bayou_total = p["p15_nw"].dist_to(p["p15_ne"]) + p["p16_nw"].dist_to(p["p16_ne"]) + p["p17_nw"].dist_to(p["p17_ne"])
    mid_total = p["p15_sw"].dist_to(p["p15_se"]) + p["p16_sw"].dist_to(p["p16_se"]) + p["p17_sw"].dist_to(p["p17_se"])
    surfwood_total = p["p14_sw"].dist_to(p["p14_se"]) + p["p13_sw"].dist_to(p["p13_se"]) + p["p12_sw"].dist_to(p["p12_se"])
    assert abs(bayou_total - 243.83) < 0.01
    assert abs(mid_total - 243.25) < 0.01
    assert abs(surfwood_total - 242.67) < 0.01
    skew_step = 100.0 * math.tan(math.radians(20.0 / 60.0))
    assert abs((bayou_total - mid_total) - skew_step) < 0.01
    assert abs((mid_total - surfwood_total) - skew_step) < 0.01


def test_block12_all_lots_close_exactly():
    """Lots 4-10 (the part of Block 12 west of the Unit One matchline). Re-read at 400 dpi 2026-09-24:
    the jog courses that used to keep Lots 8-10 flagged are legible, so all seven lots are built."""
    solver = BeachwoodBlock12Solver()
    assert set(solver.lots.keys()) == {"4", "5", "6", "7", "8", "9", "10"}
    for num, lot in solver.lots.items():
        res = lot.compute_mapcheck()
        assert res.misclose_dist_ft < 1e-6, f"Lot {num} failed to close: {res.misclose_dist_ft}"
        assert res.passed
        assert abs(res.area_diff_pct) < 0.05


def test_block12_printed_jog_courses_close():
    """Every printed course that is not used in the construction (the 25.82'/75.04' jog, the 122.45'
    Lot 9/10 line, the 120.0' boundary to the P.R.M., Lot 8's 72.37' and Lot 4's 90.69') is a check."""
    solver = BeachwoodBlock12Solver()
    for key, (calc, printed) in solver.checks.items():
        assert abs(calc - printed) < 0.05, key


def test_block12_lot7_is_a_rectangle_and_lot6_takes_the_extra_20ft():
    """Lot 7 is 100' x 75'. Lot 6's north line is 120.00' = Lot 7's 100' + 20' (the earlier solver
    closed Lot 7 with a 120' south side and a computed 77.62' east side)."""
    solver = BeachwoodBlock12Solver()
    p = solver.points
    assert abs(p["p7_sw"].dist_to(p["p7_se"]) - 100.0) < 1e-6
    assert abs(p["p7_ne"].dist_to(p["p7_se"]) - 75.0) < 1e-6
    assert abs(p["p7_sw"].dist_to(p["p6_ne"]) - 120.0) < 1e-6


def test_block12_matchline_length_matches_plat():
    """Lot 4's east side is the lower matchline segment: N00°41'40"W, 102.20', explicitly labeled on the plat."""
    solver = BeachwoodBlock12Solver()
    p = solver.points
    assert abs(p["p4_se"].dist_to(p["p4_ne"]) - 102.20) < 0.01


def test_block12_no_flagged_points_remain():
    assert BeachwoodBlock12Solver().flagged_points == {}
