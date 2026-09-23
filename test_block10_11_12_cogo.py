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


def test_block12_lots_4_through_7_close_exactly():
    solver = BeachwoodBlock12Solver()
    assert set(solver.lots.keys()) == {"7", "6", "5", "4"}
    for num, lot in solver.lots.items():
        res = lot.compute_mapcheck()
        assert res.misclose_dist_ft < 1e-6, f"Lot {num} failed to close: {res.misclose_dist_ft}"
        assert res.passed


def test_block12_lot6_computed_east_side_matches_west_side():
    """Lot 6 is built from exactly 3 stated sides (west 71.27', north
    120.00', south 120.52'); the 4th (east) side is computed by closure,
    not read off the plat. It should come out very close to the west side's
    own length (71.27') -- the near-parallelogram shape this lot actually
    has, and a strong self-consistency check on the reading."""
    solver = BeachwoodBlock12Solver()
    p = solver.points
    west = p["p6_nw"].dist_to(p["p6_sw"])
    east = p["p6_ne"].dist_to(p["p6_se"])
    assert abs(west - 71.27) < 0.01
    assert abs(east - west) < 0.05


def test_block12_lot5_computed_east_side_matches_lot4_stated_west_side():
    """Lot 5's east side (computed by closure from its 3 stated sides) and
    Lot 4's west side (independently read as 90.69' off the plat) describe
    the SAME physical boundary. They should agree to within plat-drafting
    rounding (this reading gets them within 0.01') -- the key
    cross-validation that confirms both lots were transcribed correctly."""
    solver = BeachwoodBlock12Solver()
    p = solver.points
    lot5_east = p["p5_ne"].dist_to(p["p5_se"])
    lot4_west = p["p4_sw"].dist_to(p["p4_nw"])
    assert abs(lot4_west - 90.69) < 0.01
    assert abs(lot5_east - lot4_west) < 0.02


def test_block12_matchline_length_matches_plat():
    """Lot 4's east side is the lower matchline segment: N00°41'40"W,
    102.20', explicitly labeled on the plat."""
    solver = BeachwoodBlock12Solver()
    p = solver.points
    assert abs(p["p4_se"].dist_to(p["p4_ne"]) - 102.20) < 0.01


def test_block12_lots_8_9_10_are_not_certified():
    """Lots 8, 9, 10 front the San Salvadore Ave curve transition through
    several short jog courses this reading could not certify -- they must
    NOT appear in self.lots (never silently certify a lot from a guess)."""
    solver = BeachwoodBlock12Solver()
    assert "8" not in solver.lots
    assert "9" not in solver.lots
    assert "10" not in solver.lots


def test_block12_flagged_point_is_computed_by_intersection_not_guessed():
    """The one Lot 8 corner this reading offers (NE, approximate) must come
    from intersect_bearings() against two real, plat-stated lines (the
    Lot 7/8 divider and the matchline) -- not an arbitrary coordinate."""
    solver = BeachwoodBlock12Solver()
    assert "Lot8_NE_approx" in solver.flagged_points
    info = solver.flagged_points["Lot8_NE_approx"]
    assert "intersect_bearings" in info["method"]
    p = info["point"]
    # Sanity: the flagged point must lie on the known Lot 7/8 divider line
    # (N88°58'20"E) extended from the certified Lot 7 NE corner.
    p7_ne = solver.points["p7_ne"]
    az = math.degrees(math.atan2(p.e - p7_ne.e, p.n - p7_ne.n)) % 360.0
    assert abs(az - solver.az_div) < 0.5 or abs(az - solver.az_div) > 359.5
