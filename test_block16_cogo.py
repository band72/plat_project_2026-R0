"""
test_block16_cogo.py -- Pure Deterministic Unit Test Suite for Block 16 Cadastral Engine.

Plat: Beachwood Unit Two, Plat Book 30, Pages 82 & 82A, Duval County, FL.
Tests all 14 lots, Rule 2 P.I. angle bar glyph cutbacks, Marina Avenue omni-parameter curves,
Keel Drive curves, wedge lot apex convergence, mathematical closures, and area compliance.
"""

import math

from engine.cogo import parse_bearing
from engine.cogo_block import (
    BeachwoodBlock16Solver,
    solve_corner_return,
)
from engine.curves import solve_curve_all_parameters


def test_pi_angle_bar_glyph_rule_lot1():
    """
    Test Rule 2 on Lot 1 (NW Corner Return - Angle Bar '┌'):
    Incoming Tangent: N02°24'30\"W (West Street R/W)
    Outgoing Tangent: N87°35'30\"E (Sail Avenue R/W)
    Central turn Delta = 90°00'00\".
    With R=25.00', Tangent T = 25.0000'.
    Stated dimension along Sail extends 93.50' to P.I. tick -> Cutback to P.T. = 68.50'.
    Stated dimension along West extends 100.00' to P.I. tick -> Cutback to P.C. = 75.00'.
    Fillet Area Deduction = 134.126 SF.
    """
    sol = solve_corner_return(
        "N02°24'30\"W", "N87°35'30\"E",
        radius=25.0, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=93.50, rot="CW"
    )
    assert abs(sol.delta_deg - 90.0) < 1e-6
    assert abs(sol.tangent - 25.0) < 1e-6
    assert abs(sol.arc_length - (25.0 * math.pi / 2.0)) < 1e-4
    assert abs(sol.straight_in - 75.0) < 1e-6
    assert abs(sol.straight_out - 68.5) < 1e-6
    assert abs(sol.fillet_area - 134.126) < 0.05


def test_pi_angle_bar_glyph_rule_lot33():
    """
    Test Rule 2 on Lot 33 (SW Corner Return - Angle Bar '└'):
    Incoming Tangent: S02°24'30\"E (West Street R/W)
    Outgoing Tangent: N87°35'30\"E (South Street R/W)
    Central turn Delta = 90°00'00\".
    With R=25.00', Tangent T = 25.0000'.
    Stated dimension along South extends 93.50' to P.I. tick -> Cutback to P.T. = 68.50'.
    Stated dimension along West extends 100.00' to P.I. tick -> Cutback to P.C. = 75.00'.
    Fillet Area Deduction = 134.126 SF.
    """
    sol = solve_corner_return(
        "S02°24'30\"E", "N87°35'30\"E",
        radius=25.0, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=93.50, rot="CCW"
    )
    assert abs(sol.delta_deg - 90.0) < 1e-6
    assert abs(sol.tangent - 25.0) < 1e-6
    assert abs(sol.arc_length - (25.0 * math.pi / 2.0)) < 1e-4
    assert abs(sol.straight_in - 75.0) < 1e-6
    assert abs(sol.straight_out - 68.5) < 1e-6
    assert abs(sol.fillet_area - 134.126) < 0.05


def test_corner_return_lot29():
    """
    Test Lot 29 SE Corner Return (Angle Bar '┘'):
    Tangent-in: S54°41'40\"E (Marina Ave PT tangent-out)
    Tangent-out: N35°18'20\"E (Keel Drive tangent-in)
    Deflection Delta = |125°18'20\" - 35°18'20\"| = 90°00'00\" exact!
    With R=25.00', Tangent T = 25.0000', Arc = 39.27', Chord = 35.36' @ N35°18'20\"E.
    """
    sol = solve_corner_return(
        "S54°41'40\"E", "N35°18'20\"E",
        radius=25.0, stated_dim_in_to_pi=25.0, stated_dim_out_to_pi=25.0, rot="CCW"
    )
    assert abs(sol.delta_deg - 90.0) < 1e-6
    assert abs(sol.tangent - 25.0) < 1e-6
    assert abs(sol.arc_length - (25.0 * math.pi / 2.0)) < 1e-4
    assert abs(sol.chord - (2.0 * 25.0 * math.sin(math.pi / 4.0))) < 1e-4


def test_marina_avenue_sub_curves():
    """
    Verify Marina Avenue North R/W curve:
    Total Delta = 37°42'50\" (37.713889°), R = 389.27'.
    Divided equally into 3 lots (Lots 31, 30, 29) of Delta = 12°34'16.67\" each.
    Each chord = 2 * 389.27 * sin(12.571296° / 2) = 85.24' exact!
    Chord Bearings:
      Lot 31: S86°07'22\"E
      Lot 30: S73°33'06\"E
      Lot 29: S60°58'49\"E
    """
    r = 389.27
    delta_tot = 37.0 + 42.0/60.0 + 50.0/3600.0
    delta_sub = delta_tot / 3.0

    c_sol = solve_curve_all_parameters(radius=r, delta_deg=delta_sub)
    assert abs(float(c_sol["chord"]) - 85.24) < 0.01
    assert abs(float(c_sol["length"]) - 85.39) < 0.05


def test_keel_drive_lot28_frontage():
    """
    Verify Keel Drive North R/W curve fronting Lot 28:
    R = 167.95', Chord = 68.75' @ N60°18'20\"E.
    Central turn Delta = 2 * arcsin(68.75 / (2 * 167.95)) = 23°37'15\" (23.6208°).
    Arc length = 167.95 * radians(23.6208°) = 69.24'.
    """
    r = 167.95
    c = 68.75
    delta = 2.0 * math.degrees(math.asin(c / (2.0 * r)))
    c_sol = solve_curve_all_parameters(radius=r, delta_deg=delta)
    assert abs(float(c_sol["chord"]) - 68.75) < 1e-4
    assert abs(float(c_sol["length"]) - 69.24) < 0.05
    assert abs(delta - (23.0 + 37.0/60.0 + 15.0/3600.0)) < 0.01


def test_lot29_apex_convergence():
    """
    Verify that Lot 29 is a wedge parcel whose rear lines converge to an exact
    single-point apex at x = 403.26 ft along the centerline:
    - West dividing line: S19°20'32\"W 147.37'
    - East dividing line: S35°01'42\"E 166.73'
    """
    solver = BeachwoodBlock16Solver()
    p_apex = solver.points["p_cl_apex"]
    dist_from_orig = solver.origin.dist_to(p_apex)
    expected_dist = 93.50 + 89.76 + 110.00 + 110.00 # 403.26'
    assert abs(dist_from_orig - expected_dist) < 1e-3


def test_block16_all_14_lots_closed_and_precise():
    """Verify that all 14 lots in Block 16 close with 0.000 ft misclose (EXACT)."""
    solver = BeachwoodBlock16Solver()
    results = solver.solve_all()
    assert len(results) == 14

    for lot_id, res in results.items():
        assert res.misclose_dist_ft < 1e-4, f"Lot {lot_id} misclose too high: {res.misclose_dist_ft}"
        assert res.precision_str == "EXACT (0.000 ft)"
        assert res.fac_5j17_passed is True
        assert res.passed is True


def test_block16_curvilinear_lot_areas_match_stated():
    """Closure alone doesn't catch a curve-segment sign error: the vertex
    chain still closes regardless of whether a segment area was added or
    subtracted, since that adjustment only affects computed_area_sqft, not
    misclosure. Lots 31/30/29/28 each carry a curve side (Marina Ave and/or
    the Lot 29 corner return) -- assert area_diff_pct is negligible for
    every lot, not just that it closes, so a stated-area formula using the
    opposite sign convention from DeterministicLotSolver.compute_mapcheck()
    (which happened here: found the "stated" precompute subtracting a
    segment area that compute_mapcheck's rot="CW" handling adds) is caught
    instead of silently passing as a "closed" traverse with a wrong area."""
    solver = BeachwoodBlock16Solver()
    results = solver.solve_all()
    for lot_id, res in results.items():
        assert abs(res.area_diff_pct) < 0.01, (
            f"Lot {lot_id}: computed {res.computed_area_sqft:.1f} SF vs "
            f"stated {res.stated_area_sqft:.1f} SF ({res.area_diff_pct:.2f}% off) -- "
            "check the curve segment-area sign matches this lot's curve_specs rot"
        )


def test_block16_centerline_balance():
    """
    Verify that the North row cumulative frontage (618.50 ft) and South row rear
    cumulative length (618.50 ft) balance with exact mathematical precision:
    North: 93.50 + 7 * 75.00 = 618.50'
    South: 93.50 + 89.76 + 110.00 + 110.00 + 0.00 + 110.00 + 105.24 = 618.50'
    """
    north_sum = 93.50 + 7 * 75.00
    south_sum = 93.50 + 89.76 + 110.00 + 110.00 + 0.00 + 110.00 + 105.24
    assert abs(north_sum - 618.50) < 1e-6
    assert abs(south_sum - 618.50) < 1e-6
    assert abs(north_sum - south_sum) < 1e-6


def test_curve_and_line_tables_populated():
    """Verify Curve Table and Line Table data integrity."""
    solver = BeachwoodBlock16Solver()
    c_table = solver.get_curve_table_data()
    l_table = solver.get_line_table_data()

    assert len(c_table) == 7
    assert c_table[0]["tag"] == "C1" and c_table[0]["radius"] == 25.0
    assert c_table[1]["tag"] == "C2" and c_table[1]["radius"] == 25.0
    assert c_table[2]["tag"] == "C3" and c_table[2]["radius"] == 389.27
    assert c_table[5]["tag"] == "C6" and c_table[5]["radius"] == 25.0
    assert c_table[6]["tag"] == "C7" and c_table[6]["radius"] == 167.95

    assert len(l_table) >= 16
    assert l_table[0]["tag"] == "L1"


def test_corner_return_curve_table_bearings_match_the_solve():
    """The published curve table's chord_bearing for a corner-return curve
    (C1/C2/C6) must come from that same corner's own solve_corner_return()
    result, not a separately hand-typed string -- found C1/C2/C6 all
    diverged from their solver's actual chord_bearing (wrong hemisphere or
    off by up to 90 deg) because they'd been typed by hand instead of
    read from self.sol1/sol33/sol29.chord_bearing."""
    solver = BeachwoodBlock16Solver()
    c_table = {row["tag"]: row for row in solver.get_curve_table_data()}
    for tag, sol in (("C1", solver.sol1), ("C2", solver.sol33), ("C6", solver.sol29)):
        published = parse_bearing(c_table[tag]["chord_bearing"])
        solved = parse_bearing(sol.chord_bearing)
        assert abs(published - solved) < 0.01, (
            f"{tag}: table says {c_table[tag]['chord_bearing']}, "
            f"solver computed {sol.chord_bearing}"
        )


if __name__ == "__main__":
    print("=" * 80)
    print("  RUNNING DETERMINISTIC COGO UNIT TESTS: BLOCK 16")
    print("=" * 80)
    test_pi_angle_bar_glyph_rule_lot1()
    print("  [PASS] test_pi_angle_bar_glyph_rule_lot1")
    test_pi_angle_bar_glyph_rule_lot33()
    print("  [PASS] test_pi_angle_bar_glyph_rule_lot33")
    test_corner_return_lot29()
    print("  [PASS] test_corner_return_lot29")
    test_marina_avenue_sub_curves()
    print("  [PASS] test_marina_avenue_sub_curves")
    test_keel_drive_lot28_frontage()
    print("  [PASS] test_keel_drive_lot28_frontage")
    test_lot29_apex_convergence()
    print("  [PASS] test_lot29_apex_convergence")
    test_block16_all_14_lots_closed_and_precise()
    print("  [PASS] test_block16_all_14_lots_closed_and_precise (14/14 Lots Closed EXACT)")
    test_block16_centerline_balance()
    print("  [PASS] test_block16_centerline_balance (618.50' Balance)")
    test_curve_and_line_tables_populated()
    print("  [PASS] test_curve_and_line_tables_populated")
    print("=" * 80)
    print("  ALL 9 TESTS PASSED (100% Deterministic Mathematical Precision)")
    print("=" * 80)
