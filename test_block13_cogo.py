"""
test_block13_cogo.py -- Pure Deterministic Unit Test Suite for Block 13 Cadastral Engine.

Tests every mathematical formula, surveyor curve solve, Rule 2 P.I. angle bar glyph cutback,
Surfwood Avenue 20' deflection skew, traverse closure, F.A.C. 5J-17 compliance, and area
computation without any AI or external heuristics.

Run directly via:
  python3 test_block13_cogo.py
or via:
  pytest test_block13_cogo.py
"""

import math

from engine.cogo import Point, parse_bearing
from engine.cogo_block import (
    BeachwoodBlock13Solver,
    intersect_bearings,
    solve_corner_return,
    solve_skew_angle,
    solve_skewed_lot_rear_dimension,
)


def test_pi_angle_bar_glyph_rule_lot1():
    """
    Test Rule 2 on Lot 1 (NE Corner Return - Angle Bar '┘'):
    Incoming Tangent: N88°58'20\"E (North 60' Street R/W)
    Outgoing Tangent: S01°01'40\"E (Mangrove Avenue R/W)
    Central turn Delta must equal 90°00'00\".
    With R=25.00', Tangent T must equal 25.0000'.
    Stated dimensions along North and Mangrove extend 100.00' to P.I. tick.
    Straight boundary course to P.T./P.C. must be 100.00' - 25.00' = 75.00'.
    Fillet Area = R*T - 0.5*R^2*Delta_rad = 134.126 SF.
    """
    sol = solve_corner_return(
        "N88°58'20\"E", "S01°01'40\"E",
        radius=25.0, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0
    )
    assert abs(sol.delta_deg - 90.0) < 1e-6
    assert abs(sol.tangent - 25.0) < 1e-6
    assert abs(sol.arc_length - (25.0 * math.pi / 2.0)) < 1e-4
    assert abs(sol.straight_in - 75.0) < 1e-6
    assert abs(sol.straight_out - 75.0) < 1e-6
    assert abs(sol.fillet_area - 134.126) < 0.05


def test_pi_angle_bar_glyph_rule_lot11():
    """
    Test Rule 2 on Lot 11 (SE Corner Return - Angle Bar '└'):
    Incoming Tangent: S01°01'40\"E (Mangrove Avenue R/W to P.I.)
    Outgoing Tangent: S89°18'20\"W (Surfwood Avenue R/W from P.I.)
    Deflection Delta = |269°18'20\" - 178°58'20\"| = 90°20'00\" (90.333333°).
    With R=25.00', Tangent T = R * tan(Delta/2) = 25.0 * tan(45°10'00\") = 25.1459'.
    Stated dimensions along Mangrove and Surfwood extend 100.00' to P.I. tick.
    Straight boundary course to P.C./P.T. must be 100.00' - 25.1459' = 74.8541'.
    Fillet Area = R*T - 0.5*R^2*Delta_rad = 135.95 SF.
    """
    sol = solve_corner_return(
        "S01°01'40\"E", "S89°18'20\"W",
        radius=25.0, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0
    )
    expected_delta = 90.0 + 20.0 / 60.0
    expected_t = 25.0 * math.tan(math.radians(expected_delta / 2.0))

    assert abs(sol.delta_deg - expected_delta) < 1e-6
    assert abs(sol.tangent - expected_t) < 1e-4
    assert abs(sol.tangent - 25.1459) < 0.001
    assert abs(sol.straight_in - (100.0 - expected_t)) < 1e-4
    assert abs(sol.fillet_area - 135.95) < 0.05


def test_surfwood_bearing_skew_and_rear_dimension():
    """
    Verify the 20' deflection skew of Surfwood Avenue (N89°18'20\"E vs N88°58'20\"E):
    Lot depth = 100.00'.
    Skew offset = 100.00' * tan(20') = 100.00' * tan(0.333333°) = 0.5818'.
    Rear Lot 11 dimension = 100.00' - 0.5818' = 99.4182' -> states 99.42' on plat.
    """
    skew_deg = solve_skew_angle("N88°58'20\"E", "N89°18'20\"E")
    assert abs(skew_deg - (20.0 / 60.0)) < 1e-9

    skew_offset = 100.0 * math.tan(math.radians(skew_deg))
    assert abs(skew_offset - 0.5818) < 0.001

    computed_rear = solve_skewed_lot_rear_dimension(100.0, 100.0, skew_deg, "taper")
    assert abs(computed_rear - 99.4182) < 0.001
    assert round(computed_rear, 2) == 99.42


def test_pi_intersection_analytical_geometry():
    """
    Verify that the P.I. for Lot 11 intersects Mangrove Ave tangent and Surfwood Ave tangent
    at exactly 100.00 ft from the north P.R.M. and 100.00 ft from the south rear corner.
    """
    az_mangrove_s = parse_bearing("S01°01'40\"E")
    az_lot_line = parse_bearing("N88°58'20\"E")
    az_surfwood = parse_bearing("N89°18'20\"E")

    p11_nw = Point(0.0, 0.0)
    p11_ne = p11_nw.offset(az_lot_line, 100.0) # P.R.M. on Mangrove Ave
    p11_sw = p11_nw.offset(az_mangrove_s, 99.42)

    p11_pi = intersect_bearings(p11_sw, az_surfwood, p11_ne, az_mangrove_s)

    dist_mangrove_pi = p11_ne.dist_to(p11_pi)
    dist_surfwood_pi = p11_sw.dist_to(p11_pi)

    assert abs(dist_mangrove_pi - 100.0) < 0.005
    assert abs(dist_surfwood_pi - 100.0) < 0.005


def test_all_11_lots_closed_and_precise():
    """
    Certified MapCheck Traverses for all 11 lots in Block 13:
    Every lot must close with linear misclose <= 0.0001 ft,
    precision EXACT (0.000 ft), and pass F.A.C. 5J-17 standards.
    """
    solver = BeachwoodBlock13Solver()
    results = solver.solve_all()
    assert len(results) == 11

    for lot_num, res in results.items():
        assert res.passed, f"Lot {lot_num} failed traverse closure"
        assert res.misclose_dist_ft < 1e-4, f"Lot {lot_num} misclose {res.misclose_dist_ft} > 0.0001 ft"
        assert res.fac_5j17_passed, f"Lot {lot_num} failed Florida 5J-17 standard"
        assert res.precision_str == "EXACT (0.000 ft)", f"Lot {lot_num} precision not EXACT"


def test_all_lot_areas_within_plat_spec():
    """
    Verify computed net parcel areas match target specifications:
    - Lot 1: 9,865.9 SF (10,000 - 134.13 fillet)
    - Lots 2-9: 7,725.0 SF each (77.25' x 100.00')
    - Lot 10: 7,692.0 SF (76.92' x 100.00')
    - Lot 11: 9,835.1 SF (9,971.09 - 135.95 fillet)
    """
    solver = BeachwoodBlock13Solver()
    results = solver.solve_all()

    expected_areas = {
        "1": 9865.87,
        "2": 7725.00,
        "3": 7725.00,
        "4": 7725.00,
        "5": 7725.00,
        "6": 7725.00,
        "7": 7725.00,
        "8": 7725.00,
        "9": 7725.00,
        "10": 7692.00,
        "11": 9835.14,
    }

    for lot_num, exp_a in expected_areas.items():
        comp_a = results[lot_num].computed_area_sqft
        diff = abs(comp_a - exp_a)
        assert diff < 0.5, f"Lot {lot_num} computed {comp_a:.1f} SF vs expected {exp_a:.1f} SF (diff: {diff:.2f} SF)"


def test_block13_total_boundary_sum():
    """
    Verify total frontage and rear boundary sums:
    Frontage to P.I.s: 100' + 8*77.25' + 76.92' + 100' = 894.92'
    Rear on Drainage R/W: 100' + 8*77.25' + 76.92' + 99.42' = 894.34'
    Difference is exactly the 0.58' skew cutback.
    Total Net Block Area: 89,193.0 SF (2.0476 Acres).
    """
    front_sum = 100.0 + 8 * 77.25 + 76.92 + 100.0
    rear_sum = 100.0 + 8 * 77.25 + 76.92 + 99.42

    assert abs(front_sum - 894.92) < 1e-9
    assert abs(rear_sum - 894.34) < 1e-9
    assert abs((front_sum - rear_sum) - 0.58) < 0.005

    solver = BeachwoodBlock13Solver()
    results = solver.solve_all()
    tot_area = sum(r.computed_area_sqft for r in results.values())
    assert abs(tot_area - 89193.0) < 1.0


def test_curve_and_line_tables_populated():
    """Verify Curve Table and Line Table data integrity."""
    solver = BeachwoodBlock13Solver()
    c_table = solver.get_curve_table_data()
    l_table = solver.get_line_table_data()

    assert len(c_table) == 2
    assert c_table[0]["tag"] == "C1" and c_table[0]["radius"] == 25.0
    assert c_table[1]["tag"] == "C2" and c_table[1]["radius"] == 25.0

    assert len(l_table) >= 30
    assert l_table[0]["tag"] == "L1"


def test_corner_return_curve_table_bearings_match_the_solve():
    """The published curve table's chord_bearing for each corner return
    must come from that corner's own solve_corner_return() result, not a
    separately hand-typed string -- found C1 diverging from sol1's actual
    chord_bearing by both hemisphere and angle (S43°58'20"W typed vs
    S46°01'40"E solved) because it had been typed by hand instead of read
    from self.sol1.chord_bearing."""
    solver = BeachwoodBlock13Solver()
    c_table = {row["tag"]: row for row in solver.get_curve_table_data()}
    for tag, sol in (("C1", solver.sol1), ("C2", solver.sol11)):
        published = parse_bearing(c_table[tag]["chord_bearing"])
        solved = parse_bearing(sol.chord_bearing)
        assert abs(published - solved) < 0.01, (
            f"{tag}: table says {c_table[tag]['chord_bearing']}, "
            f"solver computed {sol.chord_bearing}"
        )


if __name__ == "__main__":
    print("=" * 80)
    print("  RUNNING DETERMINISTIC COGO UNIT TESTS: BLOCK 13")
    print("=" * 80)
    test_pi_angle_bar_glyph_rule_lot1()
    print("  [PASS] test_pi_angle_bar_glyph_rule_lot1")
    test_pi_angle_bar_glyph_rule_lot11()
    print("  [PASS] test_pi_angle_bar_glyph_rule_lot11")
    test_surfwood_bearing_skew_and_rear_dimension()
    print("  [PASS] test_surfwood_bearing_skew_and_rear_dimension")
    test_pi_intersection_analytical_geometry()
    print("  [PASS] test_pi_intersection_analytical_geometry")
    test_all_11_lots_closed_and_precise()
    print("  [PASS] test_all_11_lots_closed_and_precise (11/11 Lots Closed EXACT)")
    test_all_lot_areas_within_plat_spec()
    print("  [PASS] test_all_lot_areas_within_plat_spec (All 11 Areas Verified)")
    test_block13_total_boundary_sum()
    print("  [PASS] test_block13_total_boundary_sum")
    test_curve_and_line_tables_populated()
    print("  [PASS] test_curve_and_line_tables_populated")
    print("=" * 80)
    print("  ALL 8 TESTS PASSED (100% Deterministic Mathematical Precision)")
    print("=" * 80)
