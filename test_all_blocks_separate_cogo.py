"""
test_all_blocks_separate_cogo.py -- Pure Deterministic Unit Test Suite for All Subdivision Blocks
Computed Separately in Local Coordinate Space.

Plat: Beachwood Unit Two, Plat Book 30, Pages 82 & 82A, Duval County, FL.
Validates:
- All 10 subdivision blocks (Blocks 9, 10, 11, 12, 13, 14, 15, 16, 17, 18)
- 100% mathematical traverse closure across all 144 lots
- Rule 2 P.I. angle bar glyph corner returns
- Horizontal curves solved via plat_curves integration
- Pure uncoupled translational invariance (independent placement)
"""

import math
import os
import sys

import pytest

from engine.cogo import Point
from engine.cogo_block import (
    BeachwoodBlock9Solver,
    BeachwoodBlock13Solver,
    BeachwoodBlock14Solver,
    BeachwoodBlock15Solver,
    BeachwoodBlock16Solver,
    BeachwoodBlock17Solver,
    BeachwoodBlock18Solver,
    get_all_block_solvers,
)

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_CURVES_PATH = os.path.join(_REPO_ROOT, "plugins", "curves")
if _PLUGIN_CURVES_PATH not in sys.path:
    sys.path.insert(0, _PLUGIN_CURVES_PATH)

try:
    from plat_curves.compound import corner_return, cul_de_sac
    from plat_curves.core import Curve as PlatCurve
    from plat_curves.core import deg_to_dms
    from plat_curves.engine_adapter import (
        get_block_corner_returns,
        get_block_frontage_curves,
    )
    HAS_PLAT_CURVES = True
except ImportError:
    HAS_PLAT_CURVES = False


def test_plat_curves_plugin_integration():
    """Verify that the plat_curves plugin is active and available to the test suite."""
    assert HAS_PLAT_CURVES is True
    c = PlatCurve.from_params(radius=25.0, delta_deg=90.0)
    assert abs(float(c.tangent) - 25.0) < 1e-6
    assert abs(float(c.arc_length) - 39.2699) < 1e-3
    assert deg_to_dms(90.0) == "90°00'00\""
    cr = corner_return((0.0, 0.0), 0.0, 90.0, radius=25.0)
    assert abs(float(cr.curve.tangent) - 25.0) < 1e-6
    cds = cul_de_sac(center=(0.0, 0.0), bulb_radius=50.0, throat_half_width=30.0, fillet_radius=25.0)
    assert "bulb_1" in cds
    assert "reverse_1" in cds
    cr_dict = get_block_corner_returns()
    assert len(cr_dict) == 10
    cr18 = get_block_corner_returns("18")
    assert "CR_BLK18_L19" in cr18
    assert cr18["CR_BLK18_L19"]["tangent"] == 24.2631

    # Verify frontage curves adapter integration
    frontage_dict = get_block_frontage_curves()
    assert len(frontage_dict) >= 6
    fc16 = get_block_frontage_curves("16")
    assert "CURVE_BLK16_MARINA_NORTH_RW" in fc16
    assert fc16["CURVE_BLK16_MARINA_NORTH_RW"]["radius"] == 389.27
    fc15 = get_block_frontage_curves("15")
    assert "CURVE_BLK15_SHELLFISH_L1" in fc15
    assert fc15["CURVE_BLK15_SHELLFISH_L1"]["radius"] == 137.95



def test_get_all_block_solvers_inventory():
    """Verify that all 10 subdivision blocks are instantiated and populated."""
    solvers = get_all_block_solvers()
    expected_blocks = {
        "BLOCK_9", "BLOCK_10", "BLOCK_11", "BLOCK_12", "BLOCK_13",
        "BLOCK_14", "BLOCK_15", "BLOCK_16", "BLOCK_17", "BLOCK_18"
    }
    assert set(solvers.keys()) == expected_blocks

    total_lots = sum(len(s.lots) for s in solvers.values())
    assert total_lots == 144, f"Expected 144 lots across all blocks, got {total_lots}"


@pytest.mark.parametrize("block_name,expected_count", [
    ("BLOCK_18", 19),
    ("BLOCK_17", 34),
    ("BLOCK_16", 14),
    ("BLOCK_15", 18),
    ("BLOCK_14", 24),
    ("BLOCK_13", 11),
    ("BLOCK_12", 4),
    ("BLOCK_11", 6),
    ("BLOCK_10", 5),
    ("BLOCK_9", 9),
])
def test_block_lot_counts_and_traverse_closures(block_name, expected_count):
    """Verify every block has the exact lot count and all lots satisfy traverse closure."""
    solvers = get_all_block_solvers()
    solver = solvers[block_name]
    assert len(solver.lots) == expected_count, f"{block_name} count mismatch"

    for lot_num, lot in solver.lots.items():
        res = lot.compute_mapcheck()
        assert res.passed, f"{block_name} Lot {lot_num} failed mapcheck: misclose={res.misclose_dist_ft:.4f}'"
        assert res.misclose_dist_ft < 0.05, f"{block_name} Lot {lot_num} excessive misclose: {res.misclose_dist_ft:.4f}'"


def test_block18_lateral_convergence():
    """
    Test Block 18 lateral convergence along Beachwood Boulevard.
    Lot 19 West line = 100.00', North rear = 116.33', South front = 113.34', Delta = 2.99'.
    Corner return tangent is computed dynamically via Rule 2:
    Delta = 88°17'10", R = 25.0', T = 25.0 * tan(88°17'10" / 2) = 24.2631'.
    """
    solver = BeachwoodBlock18Solver(Point(1000.0, 500.0))
    p = solver.points
    rear_width = p["B18_L18_NE"].dist_to(p["B18_L19_NE"])
    front_width_pi = p["B18_L18_SE"].dist_to(p["B18_L19_PI_SE"])
    tangent_in = p["B18_L19_PC"].dist_to(p["B18_L19_PI_SE"])
    tangent_out = p["B18_L19_PT"].dist_to(p["B18_L19_PI_SE"])

    assert abs(rear_width - 116.33) < 0.01
    assert abs(front_width_pi - 113.34) < 0.01
    assert abs((rear_width - front_width_pi) - 2.99) < 0.01
    assert abs(tangent_in - solver.sol19.tangent) < 0.01
    assert abs(tangent_out - solver.sol19.tangent) < 0.01
    assert abs(solver.sol19.tangent - 24.2631) < 0.001
    assert solver.sol19.delta_dms == "88°17'10\""


def test_block17_corner_returns_and_convergence():
    """
    Test Block 17 NW and SW corner returns (R=25.0', T=25.0') and East convergence.
    """
    solver = BeachwoodBlock17Solver()
    p = solver.points
    # NW corner return on Lot 1
    t_nw_pc = p["B17_PI_NW"].dist_to(p["B17_L1_PC"])
    t_nw_pt = p["B17_PI_NW"].dist_to(p["B17_L1_PT"])
    assert abs(t_nw_pc - 25.0) < 0.01
    assert abs(t_nw_pt - 25.0) < 0.01

    # SW corner return on Lot 34
    t_sw_pc = p["B17_PI_SW"].dist_to(p["B17_L34_PC"])
    t_sw_pt = p["B17_PI_SW"].dist_to(p["B17_L34_PT"])
    assert abs(t_sw_pc - 25.0) < 0.01
    assert abs(t_sw_pt - 25.0) < 0.01

    # Lateral convergence on Lot 17 & Lot 18: 2.99' difference each
    lot17_front = p["B17_L16_NE"].dist_to(p["B17_L17_NE"])
    lot17_rear = p["B17_L16_SE"].dist_to(p["B17_L17_SE"])
    assert abs(lot17_front - 108.55) < 0.01
    assert abs(lot17_rear - 111.54) < 0.01
    assert abs((lot17_rear - lot17_front) - 2.99) < 0.01


def test_block15_curvilinear_courses():
    """
    Block 15 west end is over-determined by the plat: the Shellfish S R/W curve
    (R=137.95', chord 121.56'), Marina 115'/110'/125' between P.I.s and the Keel
    N R/W curve (R=173.93') must reproduce the printed 79.20', 126.84', 167.98'
    and 116.28' lot lines and land the Keel curve on Lot 14's SW corner.
    """
    solver = BeachwoodBlock15Solver()
    p = solver.points
    # Lot 1 Shellfish Drive arc chord (plat: 121.56' N61°26'55"E)
    assert abs(p["B15_L1_SH_PC"].dist_to(p["B15_L1_SH_PT"]) - 121.56) < 0.01

    # Independent printed lines close to within 0.02'
    for key in ["Lot 1/18 line 79.20'", "Lot 18/17 line 126.84'", "Lot 16 W line 167.98'",
                "Lot 15 W line 116.28'", "Lot 15 Keel chord 75.29'", "Keel curve end on Lot 14 SW (0')"]:
        calc, printed = solver.checks[key]
        assert abs(calc - printed) < 0.02, key

    # Lots 9 & 10 east lines are straight along Beachwood Blvd (100.04' = 100' / cos 1°42'50")
    assert abs(p["B15_L9_PI_NE"].dist_to(p["B15_L9_SE"]) - 100.04) < 0.01

    # R=25' corner returns at all four block corners
    for sol in (solver.sol1, solver.sol9, solver.sol10, solver.sol17):
        assert sol.radius == 25.0

    # Lots 15 and 16 outer R/W radius = 173.93' (CL 143.93' + 30' half-width)
    assert solver.lots["15"].curve_specs["side_3"]["radius"] == 173.93
    assert solver.lots["16"].curve_specs["side_3"]["radius"] == 173.93

    # Every lot closes and matches its record area
    for num, res in solver.solve_all().items():
        assert res.passed, num
        assert abs(res.area_diff_sqft) < 1.0, num


def test_block14_turnaround_bulb():
    """
    Test Block 14 West cul-de-sac turnaround bulb geometry.
    North and South rows span 200.00' total block depth.
    Verifies plat_curves cul_de_sac reverse fillet solution.
    """
    solver = BeachwoodBlock14Solver()
    p = solver.points
    total_depth = p["B14_NW"].dist_to(p["B14_SW"])
    assert abs(total_depth - 200.00) < 0.01

    if hasattr(solver, "turnaround"):
        ta = solver.turnaround
        assert ta["bulb_radius"] == 50.0
        assert ta["throat_half_width"] == 30.0
        assert ta["fillet_radius"] == 25.0
        assert abs(ta["check"]["net_turn_deg"] - (-180.0)) < 1e-4
        assert "B14_BULB_CENTER" in p
        assert "B14_BULB_APEX" in p
        assert "B14_BULB_PRC1" in p
        assert "B14_BULB_PRC2" in p
        assert abs(p["B14_BULB_CENTER"].dist_to(p["B14_BULB_APEX"]) - 50.0) < 1e-4
        assert abs(p["B14_BULB_CENTER"].dist_to(p["B14_BULB_PRC1"]) - 50.0) < 1e-4
        assert abs(p["B14_BULB_CENTER"].dist_to(p["B14_BULB_PRC2"]) - 50.0) < 1e-4



def test_uncoupled_translational_invariance():
    """
    Confirm that translating a block to arbitrary local coordinates
    leaves lot dimensions, angles, misclose, and areas 100% unchanged.
    """
    origin_a = Point(0.0, 0.0)
    origin_b = Point(87654.321, -12345.678)

    solver_a = BeachwoodBlock16Solver(origin_a)
    solver_b = BeachwoodBlock16Solver(origin_b)

    for lot_num in solver_a.lots:
        res_a = solver_a.lots[lot_num].compute_mapcheck()
        res_b = solver_b.lots[lot_num].compute_mapcheck()

        assert abs(res_a.misclose_dist_ft - res_b.misclose_dist_ft) < 1e-6
        assert abs(res_a.computed_area_sqft - res_b.computed_area_sqft) < 1e-4
        assert res_a.passed == res_b.passed


def test_block13_corner_returns_and_skew():
    """
    Test Block 13 Lot 1 NE corner return (R=25.0', Delta=90°00'00", T=25.0000')
    and Lot 11 SE corner return (R=25.0', Delta=90°20'00", T=25.1459').
    Verifies 20' deflection skew derivation on Surfwood Avenue.
    """
    solver = BeachwoodBlock13Solver()
    assert len(solver.points) > 0
    assert solver.sol1.delta_dms == "90°00'00\""
    assert abs(solver.sol1.tangent - 25.0) < 1e-4

    # Lot 11 SE corner return
    assert solver.sol11.delta_dms == "90°20'00\""
    assert abs(solver.sol11.tangent - 25.1459) < 1e-3

    # Rear skew calculation: 100' depth * tan(20') = 0.58' taper
    assert abs((100.0 - solver.lot11_rear_calc) - 0.58) < 0.02


def test_block9_corner_returns():
    """
    Test Block 9 Lot 27 NW corner return (R=25.0', Delta=90°00'00", T=25.0000')
    and Lot 26 SW corner return (R=25.0', Delta=83°30'00", T=22.3134').
    """
    solver = BeachwoodBlock9Solver()
    assert solver.sol27.delta_dms == "90°00'00\""
    assert abs(solver.sol27.tangent - 25.0) < 1e-4
    assert solver.sol26.delta_dms == "83°30'00\""
    assert abs(solver.sol26.tangent - 22.3134) < 1e-3


def test_all_blocks_arc_endpoint_continuity():
    """
    Rigorously audit all curved boundary courses across all 10 blocks (144 lots).
    Ensures that for every arc:
    - Arc points exist and have >= 2 segments.
    - Arc starting point matches course start_pt to < 0.001 ft.
    - Arc ending point matches course end_pt to < 0.001 ft.
    - Curve metadata contains valid radius and non-empty delta_dms.
    """
    solvers = get_all_block_solvers()
    curve_count = 0
    for bname, s in solvers.items():
        res = s.solve_all()
        for lnum, lr in res.items():
            for c in lr.courses:
                if c.is_curve:
                    curve_count += 1
                    assert len(c.arc_points) >= 2, f"{bname} Lot {lnum} insufficient arc points"
                    assert c.arc_points[0].dist_to(c.start_pt) < 1e-3
                    assert c.arc_points[-1].dist_to(c.end_pt) < 1e-3
                    assert abs(c.start_pt.dist_to(c.end_pt) - c.curve_data["chord"]) < 1e-3
                    assert c.curve_data["radius"] > 0
                    assert c.curve_data["delta_dms"] != ""
                    # Mid-ordinate displacement verification M = R * (1 - cos(Delta / 2))
                    mid_c_n = 0.5 * (c.start_pt.n + c.end_pt.n)
                    mid_c_e = 0.5 * (c.start_pt.e + c.end_pt.e)
                    arc_mid = c.arc_points[len(c.arc_points) // 2]
                    disp = math.hypot(arc_mid.n - mid_c_n, arc_mid.e - mid_c_e)
                    r = c.curve_data["radius"]
                    d = c.curve_data["delta_deg"]
                    expected_m = r * (1.0 - math.cos(math.radians(d / 2.0)))
                    assert abs(disp - expected_m) < 0.01, f"{bname} Lot {lnum} mid-ordinate displacement mismatch"

    assert curve_count == 21, f"Expected 21 curved courses across all blocks, found {curve_count}"


def test_master_area_and_total_lot_count():
    """
    Verify complete master cadastral synthesis:
    - 144 total lots across all 10 blocks.
    - 100% traverse closure (< 0.0001 ft misclose per lot).
    - Total subdivision net area converges to 1,181,021.9 SF (27.11 Acres).
    """
    solvers = get_all_block_solvers()
    total_lots = 0
    total_area = 0.0
    for bname, s in solvers.items():
        res = s.solve_all()
        total_lots += len(res)
        for lnum, r in res.items():
            assert r.passed, f"{bname} Lot {lnum} failed mapcheck"
            assert r.misclose_dist_ft < 1e-4, f"{bname} Lot {lnum} misclose={r.misclose_dist_ft}"
            total_area += r.computed_area_sqft

    assert total_lots == 144
    assert abs(total_area - 1182760.4) < 1.0  # Block 15 west end re-read from scan 2026-09-24


def test_all_corner_returns_are_25ft_fillets():
    """
    Sheet 2 Note 4: "All block corners are rounded with 25' radii fillets unless otherwise noted."
    Verify that every corner return curve in the subdivision is a true 25 ft fillet (R = 25.0'):
    - Radius is exactly 25.0 ft across all blocks.
    - Tangent is strictly T = R * tan(Delta / 2) = 25.0 * tan(Delta / 2).
    - Stated corner return fillet area is strictly positive.
    - Cul-de-sac throat reverse fillets on Block 14 are also 25.0 ft fillets.
    """
    import math
    cr_dict = get_block_corner_returns()
    assert len(cr_dict) == 10
    for key, spec in cr_dict.items():
        assert spec["radius"] == 25.0, f"{key} radius must be 25.0 ft"
        d_deg = spec["delta_deg"]
        expected_t = 25.0 * math.tan(math.radians(d_deg / 2.0))
        assert abs(spec["tangent"] - expected_t) < 0.01, f"{key} tangent mismatch"

    # Verify Block solvers instantiate 25.0' fillets
    b9 = BeachwoodBlock9Solver()
    assert b9.sol27.radius == 25.0 and b9.sol26.radius == 25.0

    b13 = BeachwoodBlock13Solver()
    assert b13.sol1.radius == 25.0 and b13.sol11.radius == 25.0

    b16 = BeachwoodBlock16Solver()
    assert b16.sol1.radius == 25.0 and b16.sol33.radius == 25.0 and b16.sol29.radius == 25.0

    b17 = BeachwoodBlock17Solver()
    assert b17.sol1.radius == 25.0 and b17.sol34.radius == 25.0

    b18 = BeachwoodBlock18Solver()
    assert b18.sol19.radius == 25.0

    b14 = BeachwoodBlock14Solver()
    assert b14.turnaround["fillet_radius"] == 25.0


def test_verify_codebase_uses_refinements():
    """
    Rigorously verify that the codebase is actively using all developed refinements:
    1. engine.cogo_block._HAS_PLAT_CURVES is active (True) and aliases PlatCurve/PlacedCurve.
    2. All 10 block corner returns derive parameters directly from get_block_corner_returns().
    3. All block frontage curves derive parameters directly from get_block_frontage_curves().
    4. Tangent cutbacks strictly follow T = 25.0 * tan(Delta / 2).
    5. Every arc course generates arc points via PlacedCurve with exact chord equality.
    """
    import math

    import engine.cogo_block as c_blk

    # 1. Plugin integration active in engine
    assert c_blk._HAS_PLAT_CURVES is True
    assert c_blk.PlatCurve is PlatCurve

    # 2. Corner return adapter queries
    cr_all = get_block_corner_returns()
    assert len(cr_all) == 10

    # Block 9
    b9 = BeachwoodBlock9Solver()
    cr9 = get_block_corner_returns("9")
    assert b9.sol27.radius == cr9["CR_BLK9_L27"]["radius"] == 25.0
    assert b9.sol26.radius == cr9["CR_BLK9_L26"]["radius"] == 25.0
    assert b9.lots["27"].curve_specs["side_2"]["radius"] == b9.sol27.radius
    assert b9.lots["26"].curve_specs["side_5"]["radius"] == b9.sol26.radius

    # Block 13
    b13 = BeachwoodBlock13Solver()
    cr13 = get_block_corner_returns("13")
    assert b13.sol1.radius == cr13["CR_BLK13_L1"]["radius"] == 25.0
    assert b13.sol11.radius == cr13["CR_BLK13_L11"]["radius"] == 25.0
    assert b13.lots["1"].curve_specs["side_3"]["radius"] == b13.sol1.radius
    assert b13.lots["11"].curve_specs["side_4"]["radius"] == b13.sol11.radius

    # Block 16
    b16 = BeachwoodBlock16Solver()
    cr16 = get_block_corner_returns("16")
    fc16 = get_block_frontage_curves("16")
    assert b16.sol1.radius == cr16["CR_BLK16_L1"]["radius"] == 25.0
    assert b16.sol33.radius == cr16["CR_BLK16_L33"]["radius"] == 25.0
    assert b16.sol29.radius == cr16["CR_BLK16_L29"]["radius"] == 25.0
    assert b16.r_marina == fc16["CURVE_BLK16_MARINA_NORTH_RW"]["radius"] == 389.27
    assert b16.r_keel == fc16["CURVE_BLK16_KEEL_L28"]["radius"] == 167.95
    assert b16.lots["1"].curve_specs["side_2"]["radius"] == b16.sol1.radius
    assert b16.lots["33"].curve_specs["side_4"]["radius"] == b16.sol33.radius
    assert b16.lots["29"].curve_specs["side_2"]["radius"] == b16.sol29.radius

    # Block 17
    b17 = BeachwoodBlock17Solver()
    cr17 = get_block_corner_returns("17")
    assert b17.sol1.radius == cr17["CR_BLK17_L1"]["radius"] == 25.0
    assert b17.sol34.radius == cr17["CR_BLK17_L34"]["radius"] == 25.0
    assert b17.lots["1"].curve_specs["side_1"]["radius"] == b17.sol1.radius
    assert b17.lots["34"].curve_specs["side_4"]["radius"] == b17.sol34.radius

    # Block 18
    b18 = BeachwoodBlock18Solver()
    cr18 = get_block_corner_returns("18")
    assert b18.sol19.radius == cr18["CR_BLK18_L19"]["radius"] == 25.0
    assert b18.lots["19"].curve_specs["side_3"]["radius"] == b18.sol19.radius

    # Block 15
    fc15 = get_block_frontage_curves("15")
    assert fc15["CURVE_BLK15_SHELLFISH_L1"]["radius"] == 137.95
    assert fc15["CURVE_BLK15_EAST_BOUNDARY"]["radius"] == 1959.86

    # Block 14
    b14 = BeachwoodBlock14Solver()
    fc14 = get_block_frontage_curves("14")
    assert b14.turnaround["bulb_radius"] == fc14["CURVE_BLK14_CULDESAC_BULB"]["bulb_radius"] == 50.0
    assert b14.turnaround["fillet_radius"] == fc14["CURVE_BLK14_CULDESAC_BULB"]["fillet_radius"] == 25.0

    # 4. Tangent cutback verification: T = 25 * tan(Delta / 2)
    for _solver, sol_obj in [
        (b9, b9.sol27), (b9, b9.sol26),
        (b13, b13.sol1), (b13, b13.sol11),
        (b16, b16.sol1), (b16, b16.sol33), (b16, b16.sol29),
        (b17, b17.sol1), (b17, b17.sol34),
        (b18, b18.sol19),
    ]:
        delta_rad = math.radians(sol_obj.delta_deg)
        calc_t = 25.0 * math.tan(delta_rad / 2.0)
        assert abs(sol_obj.tangent - calc_t) < 0.001

    # 5. Exact chord verification: C = 2 * R * sin(Delta / 2)
    solvers = get_all_block_solvers()
    for bname, s in solvers.items():
        res = s.solve_all()
        for lnum, lr in res.items():
            for c in lr.courses:
                if c.is_curve:
                    r = c.curve_data["radius"]
                    d = c.curve_data["delta_deg"]
                    expected_chord = 2.0 * r * math.sin(math.radians(d / 2.0))
                    actual_chord = c.curve_data["chord"]
                    assert abs(actual_chord - expected_chord) < 0.005, f"{bname} Lot {lnum} chord mismatch"


def test_all_corner_returns_bow_outward_to_pi():
    """
    Rigorously verify that EVERY corner return curve across all blocks
    bows OUTWARD toward the street intersection P.I. (rounding the corner),
    and NEVER bows inward into the lot:
    dist(arc_midpoint, P.I.) MUST BE strictly less than dist(chord_midpoint, P.I.).
    """
    import math

    corner_tests = [
        ("Block 9 Lot 27 (NW)", BeachwoodBlock9Solver(), "27", 1, "p27_pi"),
        ("Block 9 Lot 26 (SW)", BeachwoodBlock9Solver(), "26", 4, "p26_pi"),
        ("Block 13 Lot 1 (NE)", BeachwoodBlock13Solver(), "1", 2, "p1_pi_ne"),
        ("Block 13 Lot 11 (SE)", BeachwoodBlock13Solver(), "11", 3, "p11_pi_se"),
        ("Block 16 Lot 1 (NW)", BeachwoodBlock16Solver(), "1", 1, "p1_nw_pi"),
        ("Block 16 Lot 33 (SW)", BeachwoodBlock16Solver(), "33", 3, "p33_sw_pi"),
        ("Block 16 Lot 29 (SE)", BeachwoodBlock16Solver(), "29", 1, "p29_ret_pi"),
        ("Block 17 Lot 1 (NW)", BeachwoodBlock17Solver(), "1", 0, "B17_PI_NW"),
        ("Block 17 Lot 34 (SW)", BeachwoodBlock17Solver(), "34", 3, "B17_PI_SW"),
        ("Block 18 Lot 19 (SE)", BeachwoodBlock18Solver(), "19", 2, "B18_L19_PI_SE"),
    ]

    for desc, solver, lot_num, course_idx, pi_key in corner_tests:
        res = solver.solve_all()
        c = res[lot_num].courses[course_idx]
        assert c.is_curve, f"{desc} course {course_idx} is not marked as curve"
        chord_mid_n = 0.5 * (c.start_pt.n + c.end_pt.n)
        chord_mid_e = 0.5 * (c.start_pt.e + c.end_pt.e)
        arc_mid = c.arc_points[len(c.arc_points) // 2]
        pi = solver.points[pi_key]

        dist_chord = math.hypot(chord_mid_n - pi.n, chord_mid_e - pi.e)
        dist_arc = math.hypot(arc_mid.n - pi.n, arc_mid.e - pi.e)

        # The arc must bow TOWARD the P.I. (rounding off the corner)
        assert dist_arc < dist_chord, (
            f"{desc} arc bows INWARD into lot! dist(arc, PI)={dist_arc:.3f} >= dist(chord, PI)={dist_chord:.3f}"
        )
        # For 25' fillet at 90 deg, dist_chord ~ 17.68', dist_arc ~ 10.36'
        assert abs(dist_arc - (math.sqrt(2.0) - 1.0) * 25.0) < 1.0, (
            f"{desc} unexpected arc distance to PI: {dist_arc}"
        )




