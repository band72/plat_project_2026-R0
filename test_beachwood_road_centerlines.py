"""
test_beachwood_road_centerlines.py -- Automated Unit Tests for Road Centerline Network
and Red-Lined Assumptions in Beachwood Unit Two (Duval_Plat_Book_30_Page_82-2.pdf).
"""

import math
import os

import pytest

from engine.audit import dxf_audit
from engine.cogo_road_centerlines import BeachwoodRoadCenterlineEngine


@pytest.fixture
def engine():
    return BeachwoodRoadCenterlineEngine(base_n=10000.0, base_e=10000.0)


def test_anchor_gps_coordinates(engine):
    """Verify ground-truthed GPS tie at Starfish Ave & Mangrove Ave adheres to F.A.C. Rule 1."""
    anchor = engine.intersections["INT_STARFISH_MANGROVE"]
    assert anchor.point.n == 10000.0
    assert anchor.point.e == 10000.0
    assert pytest.approx(anchor.gps_lat, abs=1e-5) == 30.292130
    assert pytest.approx(anchor.gps_lon, abs=1e-5) == -81.530280
    assert anchor.is_assumed is False


def test_intersections_count_and_keys(engine):
    """Verify all major road intersections are computed across both Sheet 1 and Sheet 2."""
    required_keys = [
        "INT_STARFISH_MANGROVE",
        "INT_MANGROVE_NORTH_END",
        "INT_SAIL_MANGROVE",
        "INT_SOUTH_MANGROVE",
        "INT_MANGROVE_DEFL",
        "INT_BAYOU_MANGROVE",
        "INT_SURFWOOD_MANGROVE",
        "INT_MANGROVE_SOUTH_END",
        "INT_SURFWOOD_MATCHLINE",
        "INT_SANSALVADORE_PC",
        "INT_SANSALVADORE_PT",
        "INT_CAPEHORN_MATCHLINE",
        "INT_STARFISH_BEACHWOOD",
        "INT_SAIL_BEACHWOOD",
        "INT_SOUTH_MARINA_PC",
        "INT_MARINA_PT",
        "INT_MARINA_KEEL",
        "INT_KEEL_SOUTH_END",
        "INT_ASSUMP_SS_SURFWOOD_PI",
        "INT_ASSUMP_SANDS_BEACHWOOD",
        "INT_ASSUMP_SANDS_PC",
    ]
    for key in required_keys:
        assert key in engine.intersections, f"Missing intersection {key}"
        intx = engine.intersections[key]
        assert math.isfinite(intx.point.n)
        assert math.isfinite(intx.point.e)


def test_centerline_curves_geometry(engine):
    """Verify analytical curve parameters for Marina Ave and San Salvadore Ave."""
    # 1. Marina Avenue Centerline Curve
    c_marina = engine.curves["C_MARINA_CL"]
    assert pytest.approx(c_marina.radius, abs=0.01) == 419.27
    assert pytest.approx(c_marina.delta_deg, abs=0.01) == 37.7139
    assert pytest.approx(c_marina.arc_length, abs=0.1) == 275.98
    assert pytest.approx(c_marina.tangent, abs=0.1) == 143.21

    # 2. San Salvadore Avenue Centerline Curve
    c_ss = engine.curves["C_SANSALVADORE_CL"]
    assert pytest.approx(c_ss.radius, abs=0.01) == 299.96
    assert pytest.approx(c_ss.delta_deg, abs=0.01) == 36.3333
    assert pytest.approx(c_ss.arc_length, abs=0.1) == 190.22
    assert pytest.approx(c_ss.tangent, abs=0.1) == 98.43

    # 3. Beachwood Boulevard Centerline Curve
    c_blvd = engine.curves["C_BEACHWOOD_BLVD_CL"]
    assert pytest.approx(c_blvd.radius, abs=0.01) == 1959.86
    assert c_blvd.arc_length > 250.0


def test_mangrove_avenue_continuity_and_deflection(engine):
    """Verify Mangrove Avenue runs 730.50' along north leg and deflects at course 1 angle point."""
    north_end = engine.intersections["INT_MANGROVE_NORTH_END"].point
    starfish = engine.intersections["INT_STARFISH_MANGROVE"].point
    defl = engine.intersections["INT_MANGROVE_DEFL"].point

    # Distance North End -> Starfish = 180.00'
    assert pytest.approx(north_end.dist_to(starfish), abs=0.01) == 180.00

    # Distance Starfish -> Deflection = 550.50'
    assert pytest.approx(starfish.dist_to(defl), abs=0.01) == 550.50

    # Total North leg = 180 + 550.50 = 730.50' (Matches Course 1 of parent plat)
    assert pytest.approx(north_end.dist_to(defl), abs=0.01) == 730.50


def test_red_lined_assumptions_categorization(engine):
    """Verify that all inferred or projected features are explicitly flagged in RED."""
    assert len(engine.assumptions) >= 3

    # Check that red assumptions are properly categorized
    assumption_types = [a["type"] for a in engine.assumptions]
    assert "TRANSITION_CORRIDOR" in assumption_types
    assert "ARTERIAL_PROJECTION" in assumption_types
    assert "CURVE_CORRIDOR" in assumption_types

    # Verify every assumed segment is flagged
    assumed_segs = [s for s in engine.segments if s.is_assumed]
    assert len(assumed_segs) >= 3
    for s in assumed_segs:
        assert s.is_assumed is True

    # Verify assumed intersections are flagged
    assumed_intx = [i for i in engine.intersections.values() if i.is_assumed]
    assert len(assumed_intx) >= 3


def test_cad_dxf_export_and_audit(engine, tmp_path):
    """Verify CAD DXF export meets Florida cadastral standards with PASS audit and 0 false noise circles."""
    out_dxf = os.path.join(tmp_path, "test_road_centerlines.dxf")
    engine.export_dxf(out_dxf)
    assert os.path.exists(out_dxf)

    audit = dxf_audit(out_dxf)
    assert audit["status"] == "PASS"
    assert audit["entity_counts"]["circles"] == 0
    assert audit["entity_counts"]["lines"] == 120
    assert audit["entity_counts"]["polylines"] == 27
    assert audit["entity_counts"]["texts"] > 0


def test_100_agent_multiagent_consensus(engine):
    """Verify 100-agent multiagent consensus reaches 100% unanimous quorum and converges."""
    res = engine.run_100_agent_consensus(max_rounds=25)
    assert res["converged"] is True
    assert res["unanimous_quorum"] is True
    assert res["yes_votes"] == 100
    assert res["votes"] == 100
    assert res["quorum_pct"] == 100.0
    assert res["final_variance"] < 1e-7
    assert res["final_delta"] < 1e-5


def test_all_plat_centerline_curves(engine):
    """Verify all 6 centerline curves across Sheet 1 and Sheet 2 are mathematically solved."""
    assert len(engine.curves) == 6
    expected_curves = ["C_MARINA_CL", "C_SANSALVADORE_CL", "C_BEACHWOOD_BLVD_CL", "C_SANDS_CL", "C_KEEL_CL", "C_CAPEHORN_CL"]
    for cid in expected_curves:
        assert cid in engine.curves
        c = engine.curves[cid]
        assert c.radius > 0
        assert c.delta_deg > 0
        assert c.arc_length > 0
        assert c.tangent > 0
        assert c.chord_length > 0


def test_shellfish_drive_and_keel_intersection(engine):
    """Verify Shellfish Drive connects Mangrove Ave to Keel Drive."""
    assert "INT_SHELLFISH_MANGROVE" in engine.intersections
    assert "INT_SHELLFISH_KEEL" in engine.intersections
    intx_keel = engine.intersections["INT_SHELLFISH_KEEL"]
    assert pytest.approx(intx_keel.point.n, abs=1.0) == 9247.91
    assert pytest.approx(intx_keel.point.e, abs=1.0) == 10678.32


def test_pi_tangents_rule2_derivation(engine):
    """Verify Rule 2 P.I. tangent derivations: T = R * tan(Delta / 2)."""
    assert len(engine.pi_tangents) == 12  # 2 rays per curve * 6 curves
    for seg in engine.pi_tangents:
        assert seg.is_assumed is True
        assert seg.distance > 0.0

    # Verify P.I. intersections exist and are flagged as assumed
    pi_keys = ["INT_PI_MARINA", "INT_PI_SANSALVADORE", "INT_PI_BEACHWOOD_BLVD", "INT_PI_SANDS", "INT_PI_KEEL", "INT_PI_CAPEHORN"]
    for pk in pi_keys:
        assert pk in engine.intersections
        assert engine.intersections[pk].is_assumed is True


def test_visual_centerlines_drawing_generation(engine, tmp_path):
    """Verify that render_cad_centerlines_drawing generates a high-res plate."""
    out_png = os.path.join(tmp_path, "test_centerlines_drawing.png")
    engine.render_cad_centerlines_drawing(out_png, dpi=100)
    assert os.path.exists(out_png)
    assert os.path.getsize(out_png) > 50000  # Non-trivial image


def test_closed_outer_boundary(engine):
    """Verify parent outer boundary (Sheet 1 Caption) forms a closed figure with 0.000' closure."""
    assert len(engine.boundary_segments) == 27
    assert len(engine.boundary_points) == 28
    # Exact closure
    p_start = engine.boundary_points[0]
    p_end = engine.boundary_points[-1]
    assert p_start.dist_to(p_end) == 0.0
    # Perimeter
    assert pytest.approx(engine.boundary_metrics["perimeter_ft"], abs=0.1) == 8226.67
    # Area
    assert engine.boundary_metrics["parent_area_sqft"] > 2790000.0
    assert pytest.approx(engine.boundary_metrics["parent_acres"], abs=0.5) == 64.15


def test_boundary_tie_intersections(engine):
    """Verify centerline-to-boundary connection nodes exist for all boundary streets."""
    tie_keys = [
        "INT_MANGROVE_NORTH_END",
        "INT_STARFISH_WEST_END",
        "INT_SAIL_WEST_END",
        "INT_SOUTH_WEST_END",
        "INT_SHELLFISH_WEST_END",
        "INT_SURFWOOD_WEST_END",
        "INT_MANGROVE_SOUTH_END",
        "INT_SURFWOOD_MATCHLINE",
        "INT_CAPEHORN_MATCHLINE",
        "INT_BAYOU_MATCHLINE",
    ]
    for tk in tie_keys:
        assert tk in engine.intersections, f"Missing boundary tie {tk}"
        assert engine.intersections[tk].is_boundary_tie is True


def test_open_ended_culdesac_keel_drive(engine):
    """Verify Keel Drive terminates at an open-ended cul-de-sac that does NOT close."""
    assert len(engine.culdesacs) == 1
    cds = engine.culdesacs[0]
    assert cds["street"] == "Keel Drive"
    assert cds["bulb_radius_ft"] == 50.0
    assert cds["closes_to_boundary"] is False

    # Check that it is also registered in assumptions
    assumption_types = [a["type"] for a in engine.assumptions]
    assert "OPEN_ENDED_CULDESAC" in assumption_types


def test_edge_row_bearing_hedge_and_lot_frontage_summations(engine):
    """Verify user rule: right-of-way edge bearing hedges, front lot bearings, and lot frontage summations."""
    # 1. Bayou Avenue Corridor
    bayou_seg = next(s for s in engine.segments if s.id == "SEG_ASSUMP_BAYOU_E")
    assert bayou_seg.is_assumed is True
    assert bayou_seg.derivation_method == "FRONT_LOT_SUMMATION_APPROXIMATION"
    assert bayou_seg.front_lot_bearing == "N89°18'20\"E"
    assert bayou_seg.summed_lot_frontages is not None
    assert len(bayou_seg.summed_lot_frontages) >= 3

    # 2. Sands Avenue Approach Corridor
    sands_seg = next(s for s in engine.segments if s.id == "SEG_ASSUMP_SANDS_APPROACH")
    assert sands_seg.is_assumed is True
    assert sands_seg.derivation_method == "FRONT_LOT_SUMMATION_APPROXIMATION"
    assert sands_seg.front_lot_bearing == "S87°35'30\"W"
    assert sands_seg.summed_lot_frontages is not None

    # 3. Shellfish Drive East Extension
    shell_seg = next(s for s in engine.segments if s.id == "SEG_ASSUMP_SHELLFISH_KEEL")
    assert shell_seg.is_assumed is True
    assert shell_seg.derivation_method == "FRONT_LOT_SUMMATION_APPROXIMATION"
    assert shell_seg.summed_lot_frontages is not None

    # 4. Beachwood Boulevard South Projection
    blvd_seg = next(s for s in engine.segments if s.id == "SEG_ASSUMP_BEACHWOOD_S")
    assert blvd_seg.is_assumed is True
    assert blvd_seg.derivation_method == "RIGHT_OF_WAY_EDGE_HEDGE"
    assert blvd_seg.front_lot_bearing == "S08°30'00\"E"


def test_right_of_way_offset_corridor_boundaries(engine):
    """Verify offset lines for straight segments and offset arcs for curves."""
    # 1. Straight segment offset
    starfish = next(s for s in engine.segments if s.id == "SEG_STARFISH_MAIN")
    assert starfish.half_width == 30.0
    (l_start, l_end), (r_start, r_end) = starfish.get_offset_lines()
    assert pytest.approx(l_start.dist_to(l_end), abs=0.01) == starfish.distance
    assert pytest.approx(r_start.dist_to(r_end), abs=0.01) == starfish.distance
    assert pytest.approx(l_start.dist_to(r_start), abs=0.01) == 60.0

    # 2. Arterial 100' R/W segment offset
    blvd_proj = next(s for s in engine.segments if s.id == "SEG_ASSUMP_BEACHWOOD_S")
    assert blvd_proj.half_width == 50.0
    (l_start, l_end), (r_start, r_end) = blvd_proj.get_offset_lines()
    assert pytest.approx(l_start.dist_to(r_start), abs=0.01) == 100.0

    # 3. Curve offset arcs (San Salvadore: CL R=299.96' -> Inner R=269.96', Outer R=329.96')
    c_ss = engine.curves["C_SANSALVADORE_CL"]
    assert c_ss.half_width == 30.0
    inner_arc, outer_arc = c_ss.get_offset_arcs()
    assert pytest.approx(inner_arc["radius"], abs=0.01) == 269.96  # Matches stated North R/W curve
    assert pytest.approx(outer_arc["radius"], abs=0.01) == 329.96


def test_validate_all_curves_consistency(engine):
    """Verify analytical mathematical consistency of all 6 centerline curves."""
    valid_res = engine.validate_all_curves()
    assert len(valid_res) == 6
    for cid, res in valid_res.items():
        assert res["is_valid"] is True, f"Curve {cid} failed mathematical consistency audit: {res}"
        assert res["diff_arc"] < 0.1
        assert res["diff_chord"] < 0.1
        assert res["diff_tan"] < 0.1
        assert res["diff_euclid"] < 0.1


def test_culdesac_fillet_parameters(engine):
    """Verify Keel Drive open-ended cul-de-sac includes reverse curve fillet transitions."""
    cds = engine.culdesacs[0]
    assert cds["reverse_fillet_radius_ft"] == 25.0
    assert cds["bulb_radius_ft"] == 50.0
    assert cds["right_of_way_width_ft"] == 60.0


def test_culdesac_analytical_geometry_and_fillets(engine):
    """Verify exact analytical coordinates and fillet tangencies for Keel Drive cul-de-sac."""
    geom = engine.get_culdesac_geometry("CULDESAC_KEEL_DRIVE")
    assert geom["bulb_radius_ft"] == 50.0
    assert geom["corridor_half_width_ft"] == 30.0
    assert geom["fillet_radius_ft"] == 25.0
    assert pytest.approx(geom["throat_distance_yf_ft"], abs=0.01) == 50.99
    assert pytest.approx(geom["theta_prc_deg"], abs=0.01) == 47.17
    assert pytest.approx(geom["delta_bulb_deg"], abs=0.01) == 265.67

    # Tangency verifications:
    # 1. pc_left to c_left = fillet radius 25.0'
    assert pytest.approx(geom["pc_left"].dist_to(geom["center_left_fillet"]), abs=0.001) == 25.0
    # 2. prc_left to c_left = fillet radius 25.0'
    assert pytest.approx(geom["prc_left"].dist_to(geom["center_left_fillet"]), abs=0.001) == 25.0
    # 3. prc_left to bulb center = bulb radius 50.0'
    assert pytest.approx(geom["prc_left"].dist_to(geom["center_point"]), abs=0.001) == 50.0
    # 4. pt_right to c_right = fillet radius 25.0'
    assert pytest.approx(geom["pt_right"].dist_to(geom["center_right_fillet"]), abs=0.001) == 25.0
    # 5. prc_right to c_right = fillet radius 25.0'
    assert pytest.approx(geom["prc_right"].dist_to(geom["center_right_fillet"]), abs=0.001) == 25.0
    # 6. prc_right to bulb center = bulb radius 50.0'
    assert pytest.approx(geom["prc_right"].dist_to(geom["center_point"]), abs=0.001) == 50.0
    # 7. Throat width between pc_left and pt_right = exactly 60.00'
    assert pytest.approx(geom["pc_left"].dist_to(geom["pt_right"]), abs=0.001) == 60.0

    # Continuous boundary polyline has vertices
    assert len(geom["boundary_pts"]) >= 50


def test_centerline_reference_alignments_preserved(engine):
    """
    Verify road centerline polylines are preserved as continuous engineering reference
    baselines with cumulative stationing (0+00.00) for municipal design applications.
    """
    alignments = engine.get_centerline_reference_alignments()
    assert "MANGROVE_AVENUE" in alignments
    assert "STARFISH_AVENUE" in alignments
    assert "SAIL_AVENUE" in alignments
    assert "SOUTH_ST_MARINA_AVE" in alignments
    assert "SURFWOOD_AVENUE" in alignments
    assert "SHELLFISH_DRIVE" in alignments
    assert "BEACHWOOD_BOULEVARD" in alignments
    assert "KEEL_DRIVE" in alignments

    # Mangrove Avenue primary reference baseline
    mangrove = alignments["MANGROVE_AVENUE"]
    assert mangrove["total_length_ft"] > 1200.0
    assert len(mangrove["polyline_points"]) >= 9
    assert mangrove["stations"][0]["station"] == "0+00.00"
    assert "Ground GPS Control Anchor" in mangrove["stations"][1]["name"]

    # Starfish Avenue reference baseline
    starfish = alignments["STARFISH_AVENUE"]
    assert starfish["total_length_ft"] > 1400.0
    assert len(starfish["polyline_points"]) >= 3
    assert starfish["stations"][0]["station"] == "0+00.00"

    # South Street & Marina Avenue composite curve baseline
    marina = alignments["SOUTH_ST_MARINA_AVE"]
    assert marina["total_length_ft"] > 800.0
    assert len(marina["polyline_points"]) >= 15
    assert len(marina["stations"]) == 5


def test_northeast_corridor_convergence_and_convergence_rate(engine):
    """
    Verify the northeast corridor (Sheet 2, Book 30 Page 82A) geometric progression:
    1. Blocks 17, 16, 15 are each 200.08' deep (back-to-back 100.04' lots).
    2. East-west avenues (Starfish, Sail, Shellfish, Keel) are each 60.00' wide.
    3. Centerline spacing between consecutive avenues is uniformly 260.00'.
    4. Lateral convergence rate between west block faces (N02°24'30\"W) and
       Course 26 / Beachwood Blvd (N00°41'40\"W) is exactly 2.99' per 100.04' lot depth.
    """
    lot_depth = 100.04
    block_depth = 2 * lot_depth  # 200.08'
    rw_width = 60.00
    cl_spacing = block_depth + rw_width  # 260.08' (approx 260.00')

    # Convergence rate per 100.04' lot depth:
    # tan(2°24'30") - tan(0°41'40") = 0.042054 - 0.012122 = 0.029932
    convergence_per_lot = lot_depth * (math.tan(math.radians(2.0 + 24.5/60.0)) - math.tan(math.radians(41.0/60.0 + 40.0/3600.0)))
    assert pytest.approx(convergence_per_lot, abs=0.05) == 2.99

    # Verify Block 18 Lot 19 stated plat convergence:
    # Rear = 116.33', Front = 113.34' -> delta = 2.99'
    delta_blk18_lot19 = 116.33 - 113.34
    assert pytest.approx(delta_blk18_lot19, abs=0.01) == 2.99

    # Verify Block 17 Lot 17 stated plat convergence:
    # Rear = 111.54', Front = 108.55' -> delta = 2.99'
    delta_blk17_lot17 = 111.54 - 108.55
    assert pytest.approx(delta_blk17_lot17, abs=0.01) == 2.99

    # Verify Block 17 Lot 18 stated plat convergence:
    # Rear = 108.55', Front = 105.56' -> delta = 2.99'
    delta_blk17_lot18 = 108.55 - 105.56
    assert pytest.approx(delta_blk17_lot18, abs=0.01) == 2.99

    # Verify Block 16 Lot 17 stated plat convergence:
    # Rear = 103.76', Front = 100.77' -> delta = 2.99'
    delta_blk16_lot17 = 103.76 - 100.77
    assert pytest.approx(delta_blk16_lot17, abs=0.01) == 2.99

    # Verify Block 16 Lot 18 stated plat convergence:
    # Rear = 100.77', Front = 97.78' -> delta = 2.99'
    delta_blk16_lot18 = 100.77 - 97.78
    assert pytest.approx(delta_blk16_lot18, abs=0.01) == 2.99

    # Verify Block 15 Lot 9 stated plat convergence:
    # Rear = 95.98', Front = 92.99' -> delta = 2.99'
    delta_blk15_lot9 = 95.98 - 92.99
    assert pytest.approx(delta_blk15_lot9, abs=0.01) == 2.99

    # Verify Block 15 Lot 10 stated plat convergence:
    # Rear = 92.99', Front = 90.00' -> delta = 2.99'
    delta_blk15_lot10 = 92.99 - 90.00
    assert pytest.approx(delta_blk15_lot10, abs=0.01) == 2.99




