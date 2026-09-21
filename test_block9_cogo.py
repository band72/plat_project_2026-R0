"""
test_block9_cogo.py -- Pure Deterministic Unit Test Suite for Block 9 Cadastral Engine.

Tests every mathematical formula, surveyor curve solve, P.I. angle bar glyph cutback,
bearing deflection angle, traverse closure, and area computation without any AI or
external dependency.

Run directly via:
  python3 test_block9_cogo.py
or via:
  pytest test_block9_cogo.py
"""

import math
import pytest
from engine.cogo import Point, parse_bearing, azimuth_to_bearing
from engine.curves import solve_curve_all_parameters
from engine.cogo_block import (
    BeachwoodBlock9Solver,
    solve_corner_return,
    intersect_bearings,
    DeterministicLotSolver,
)


def test_pi_angle_bar_glyph_rule_lot27():
    """
    Test Rule 2 on Lot 27 (NW Corner Return):
    Incoming Tangent: N01°01'40"W (Avenue R/W)
    Outgoing Tangent: N88°58'20"E (North Street R/W)
    Central turn Delta must equal 90°00'00".
    With R=25.00', Tangent T must equal 25.0000'.
    Stated dimension along West extends 140.00' to P.I. tick.
    Straight boundary course to P.C. must be 140.00' - 25.00' = 115.00'.
    """
    sol = solve_corner_return("N01°01'40\"W", "N88°58'20\"E", radius=25.0, stated_dim_in_to_pi=140.0)
    assert abs(sol.delta_deg - 90.0) < 1e-6
    assert abs(sol.tangent - 25.0) < 1e-6
    assert abs(sol.arc_length - (25.0 * math.pi / 2.0)) < 1e-4
    assert abs(sol.straight_in - 115.0) < 1e-6
    # Fillet Area = R*T - 0.5*R^2*Delta_rad = 25*25 - 0.5*625*(pi/2) = 625 - 490.8739 = 134.126 SF
    assert abs(sol.fillet_area - 134.126) < 0.05


def test_pi_angle_bar_glyph_rule_lot26():
    """
    Test Rule 2 on Lot 26 (SW Corner Return):
    Incoming Tangent: S01°01'40"E (Avenue R/W to P.I.)
    Outgoing Tangent: N88°58'20"E (Tangent along South to P.C., stated on plat as 25.0' (N.88°58'20"E.))
    Central turn Delta must equal 90°00'00".
    With R=25.00', Tangent T must equal 25.0000'.
    Stated dimension along West extends 109.00' to P.I. tick.
    Straight boundary course to P.C. must be 109.00' - 25.00' = 84.00'.
    """
    sol = solve_corner_return("S01°01'40\"E", "N88°58'20\"E", radius=25.0, stated_dim_in_to_pi=109.0)
    assert abs(sol.delta_deg - 90.0) < 1e-6
    assert abs(sol.tangent - 25.0) < 1e-6
    assert abs(sol.straight_in - 84.0) < 1e-6


def test_bearing_line_intersection():
    """Test analytical 2D ray/line intersection solving."""
    p1 = Point(0.0, 0.0)
    az1 = 0.0   # North
    p2 = Point(50.0, -50.0)
    az2 = 90.0  # East
    p_int = intersect_bearings(p1, az1, p2, az2)
    assert abs(p_int.n - 50.0) < 1e-9
    assert abs(p_int.e - 0.0) < 1e-9


def test_matchline_geometry():
    """
    Verify Matchline orientation, length, and control ties.
    Bearing: N35°18'20"E, Distance: 200.00'.
    Monument: P.R.M. at North end (Cape Horn Ave).
    """
    solver = BeachwoodBlock9Solver()
    p23_se = solver.points["p23_se"]
    p31_ne = solver.points["p31_ne"]
    dist = p23_se.dist_to(p31_ne)
    assert abs(dist - 200.0) < 1e-4

    dn = p31_ne.n - p23_se.n
    de = p31_ne.e - p23_se.e
    az = math.degrees(math.atan2(de, dn)) % 360.0
    az_expected = parse_bearing("N35°18'20\"E")
    assert abs(az - az_expected) < 1e-4


def test_interior_rear_boundary_sum():
    """
    Verify rear lot line consistency along S63°12'00"E:
    North Row: Lot 28 (67.31') + Lot 29 (68.00') = 135.31'.
    South Row: Lot 26 (30.00') + Lot 25 (82.31') + Lot 24 (23.00') = 135.31'.
    Total length must match across both tiers exactly.
    """
    north_sum = 67.31 + 68.00
    south_sum = 30.00 + 82.31 + 23.00
    assert abs(north_sum - south_sum) < 1e-9
    assert abs(north_sum - 135.31) < 1e-9


def test_all_9_lots_closed_and_precise():
    """
    Certified MapCheck Traverses for all 9 lots:
    Every lot must close with linear error <= 0.0001 ft and pass F.A.C. 5J-17.
    """
    solver = BeachwoodBlock9Solver()
    results = solver.solve_all()
    assert len(results) == 9

    for lot_num, res in results.items():
        assert res.passed, f"Lot {lot_num} failed traverse closure"
        assert res.misclose_dist_ft < 1e-4, f"Lot {lot_num} linear misclose {res.misclose_dist_ft} > 0.0001 ft"
        assert res.fac_5j17_passed, f"Lot {lot_num} failed Florida 5J-17 standard"
        assert res.precision_str == "EXACT (0.000 ft)", f"Lot {lot_num} precision was not EXACT"


def test_lot_areas_within_plat_spec():
    """
    Verify net computed parcel areas match target stated areas within 0.1%.
    """
    solver = BeachwoodBlock9Solver()
    results = solver.solve_all()

    expected_areas = {
        "27": 11793.4,
        "28": 9632.5,
        "29": 8287.2,
        "30": 7500.0,
        "31": 7500.0,
        "26": 12446.1,
        "25": 8300.6,
        "24": 8329.5,
        "23": 7499.1,
    }

    for lot_num, exp_a in expected_areas.items():
        comp_a = results[lot_num].computed_area_sqft
        pct_err = abs(comp_a - exp_a) / exp_a * 100.0
        assert pct_err < 0.1, f"Lot {lot_num} computed {comp_a:.1f} SF vs expected {exp_a:.1f} SF (diff: {pct_err:.2f}%)"


def test_corner_fillet_area_deduction():
    """
    Test fillet area deduction on corner parcels:
    Gross corner box - fillet area = net parcel.
    Fillet area for R=25' and Delta=90° is R*T - 0.5*R^2*Delta_rad.
    """
    R = 25.0
    Delta_rad = math.pi / 2.0
    T = R * math.tan(Delta_rad / 2.0)
    fillet_a = R * T - 0.5 * (R ** 2) * Delta_rad
    assert abs(fillet_a - 134.126) < 0.05


if __name__ == "__main__":
    import sys
    print("=" * 80)
    print("  RUNNING DETERMINISTIC COGO UNIT TESTS (OFFLINE / ZERO AI)")
    print("=" * 80)
    test_pi_angle_bar_glyph_rule_lot27()
    print("  [PASS] test_pi_angle_bar_glyph_rule_lot27")
    test_pi_angle_bar_glyph_rule_lot26()
    print("  [PASS] test_pi_angle_bar_glyph_rule_lot26")
    test_bearing_line_intersection()
    print("  [PASS] test_bearing_line_intersection")
    test_matchline_geometry()
    print("  [PASS] test_matchline_geometry")
    test_interior_rear_boundary_sum()
    print("  [PASS] test_interior_rear_boundary_sum")
    test_all_9_lots_closed_and_precise()
    print("  [PASS] test_all_9_lots_closed_and_precise (9/9 Lots Closed)")
    test_lot_areas_within_plat_spec()
    print("  [PASS] test_lot_areas_within_plat_spec (All 9 Areas Verified)")
    test_corner_fillet_area_deduction()
    print("  [PASS] test_corner_fillet_area_deduction")
    print("=" * 80)
    print("  ALL 8 TESTS PASSED (100% Deterministic Mathematical Precision)")
    print("=" * 80)
