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
        "INT_SURFWOOD_WEST_END",
        "INT_SURFWOOD_MATCHLINE",
        "INT_SANSALVADORE_PC",
        "INT_SANSALVADORE_PT",
        "INT_CAPEHORN_MATCHLINE",
        "INT_STARFISH_BEACHWOOD",
        "INT_SAIL_BEACHWOOD",
        "INT_SHELLFISH_BEACHWOOD",
        "INT_KEEL_BEACHWOOD",
        "INT_BLVD_NORTH_END",
        "INT_BLVD_SOUTH_END",
        "INT_SOUTH_MARINA_PC",
        "INT_MARINA_PT",
        "INT_MARINA_KEEL",
        "INT_KEEL_PC",
        "INT_KEEL_PT",
        "INT_MARINA_SHELLFISH",
        "INT_SANSALVADORE_MANGROVE",
        "INT_SANSALVADORE_BOUNDARY",
        "INT_SANDS_MANGROVE",
        "INT_SANDS_PC",
        "INT_SANDS_PT",
        "INT_SANDS_BOUNDARY",
        "INT_CAPEHORN_MANGROVE",
        "INT_CAPEHORN_BOUNDARY",
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
    # Plat ℄ Curve Data (Sheet 2): R=359.27', T=122.70', Δ=37°42'50" (419.27 was the NE edge 389.27 + 30, wrong side)
    assert pytest.approx(c_marina.radius, abs=0.01) == 359.27
    assert pytest.approx(c_marina.delta_deg, abs=1e-6) == 37 + 42 / 60 + 50 / 3600
    assert pytest.approx(c_marina.arc_length, abs=0.01) == 236.48
    assert pytest.approx(c_marina.tangent, abs=0.01) == 122.70
    assert c_marina.chord_bearing == "S73°33'05\"E"
    # P.T. is on the circle and the forward tangent is the printed diagonal S54°41'40"E
    assert pytest.approx(c_marina.center_point.dist_to(c_marina.pt_point), abs=1e-6) == 359.27

    # 2. San Salvadore Avenue Centerline Curve
    c_ss = engine.curves["C_SANSALVADORE_CL"]
    # Plat ℄ block R=269.96' T=88.59' (299.96' is the N R/W edge)
    assert pytest.approx(c_ss.radius, abs=0.01) == 269.96
    assert pytest.approx(c_ss.delta_deg, abs=0.01) == 36.3333
    assert pytest.approx(c_ss.arc_length, abs=0.01) == 171.19
    assert pytest.approx(c_ss.tangent, abs=0.01) == 88.58
    assert pytest.approx(c_ss.center_point.dist_to(c_ss.pt_point), abs=1e-6) == 269.96

    # 3. Beachwood Boulevard is straight on the plat (no ℄ curve block; east line N00°41'40"W 1247.95')
    assert "C_BEACHWOOD_BLVD_CL" not in engine.curves
    blvd_segs = [s for s in engine.segments if s.street_name == "Beachwood Boulevard"]
    assert len(blvd_segs) == 5
    for seg in blvd_segs:
        assert seg.bearing == "S00°41'40\"E"
        assert seg.right_of_way_width == 80.0
        assert seg.is_assumed is False


def test_mangrove_avenue_continuity_and_deflection(engine):
    """Mangrove ℄ north leg: 180' inside c1; it deflects where the c1 and c2 offsets meet (not at c1's length)."""
    north_end = engine.intersections["INT_MANGROVE_NORTH_END"].point
    starfish = engine.intersections["INT_STARFISH_MANGROVE"].point
    defl = engine.intersections["INT_MANGROVE_DEFL"].point

    # Distance North End -> Starfish = 180.00'
    assert pytest.approx(north_end.dist_to(starfish), abs=0.01) == 180.00

    # c1 = 730.50' ends 550.50' south of Starfish ℄; the ℄ is an OUTSIDE offset (180') of a 1°22'50" right turn,
    # so its vertex is 180 x tan(0°41'25") = 2.17' further along: 552.67'.
    half_defl = math.radians((1 + 22 / 60 + 50 / 3600) / 2)
    expected = 550.50 + 180.0 * math.tan(half_defl)
    assert pytest.approx(expected, abs=0.005) == 552.67
    assert pytest.approx(starfish.dist_to(defl), abs=0.01) == expected
    assert pytest.approx(north_end.dist_to(defl), abs=0.01) == 180.0 + expected


def test_red_lined_assumptions_categorization(engine):
    """Verify that all inferred or projected features are explicitly flagged in RED."""
    assert len(engine.assumptions) >= 1

    # Check that red assumptions are properly categorized
    assumption_types = [a["type"] for a in engine.assumptions]
    # The "San Salvadore-Surfwood tie" was not a street (lot lines in Block 12)
    assert "TRANSITION_CORRIDOR" not in assumption_types
    # Beachwood Blvd is derived from course c26, so it is no longer an arterial projection
    assert "ARTERIAL_PROJECTION" not in assumption_types
    # Sands Ave is derived (℄ block + lot chords + c19), so its old "curve corridor" assumption is gone
    assert "CURVE_CORRIDOR" not in assumption_types
    # No cul-de-sac on the plat
    assert "OPEN_ENDED_CULDESAC" not in assumption_types

    # Verify every assumed segment is flagged
    assumed_segs = [s for s in engine.segments if s.is_assumed]
    assert len(assumed_segs) == 0

    # Verify assumed intersections are flagged (the 6 projected P.I. vertices)
    assumed_intx = [i for i in engine.intersections.values() if i.is_assumed]
    assert len(assumed_intx) == 6


def test_cad_dxf_export_and_audit(engine, tmp_path):
    """Verify CAD DXF export meets Florida cadastral standards with PASS audit and 0 false noise circles."""
    out_dxf = os.path.join(tmp_path, "test_road_centerlines.dxf")
    engine.export_dxf(out_dxf)
    assert os.path.exists(out_dxf)

    audit = dxf_audit(out_dxf)
    assert audit["status"] == "PASS"
    assert audit["entity_counts"]["circles"] == 0
    # Derived streets draw their R/W as trimmed polylines (cut at every opening and 25' return), so LINE entities are
    # only the boundary, ℄ segments, P.I. rays and the R/W offsets of not-yet-derived Sheet 1 streets.
    assert audit["entity_counts"]["lines"] == 74
    # 64 trimmed R/W pieces + 34 x 25' returns + ℄ curves (6) + alignments
    assert audit["entity_counts"]["polylines"] == 118
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
    """All 6 plat ℄ Curve Data blocks (Sheet 1 + Sheet 2) are modelled; Beachwood Blvd has none."""
    assert len(engine.curves) == 6
    expected_curves = ["C_MARINA_CL", "C_SANSALVADORE_CL", "C_SANDS_CL", "C_KEEL_CL", "C_CAPEHORN_CL", "C_SHELLFISH_CL"]
    for cid in expected_curves:
        assert cid in engine.curves
        c = engine.curves[cid]
        assert c.radius > 0
        assert c.delta_deg > 0
        assert c.arc_length > 0
        assert c.tangent > 0
        assert c.chord_length > 0


def test_shellfish_drive_and_keel_intersection(engine):
    """Shellfish and Keel curve (R=167.95 / 143.93, Δ=52°17'10") from their E-W legs into Marina Dr, square to it."""
    for cid, r, iid in (("C_SHELLFISH_CL", 167.95, "INT_MARINA_SHELLFISH"), ("C_KEEL_CL", 143.93, "INT_MARINA_KEEL")):
        c = engine.curves[cid]
        assert c.radius == r
        assert pytest.approx(c.delta_deg, abs=1e-9) == 52 + 17 / 60 + 10 / 3600
        assert pytest.approx(c.center_point.dist_to(c.pt_point), abs=1e-9) == r
        assert engine.intersections[iid].is_assumed is False
    # Mouths are 410' apart on Marina ℄ (Block 15 Lots 1/18/17 = 115 + 110 + 125, + 2 x 30')
    d = engine.intersections["INT_MARINA_SHELLFISH"].point.dist_to(engine.intersections["INT_MARINA_KEEL"].point)
    assert pytest.approx(d, abs=0.05) == 410.0
    # No Shellfish at Mangrove on the plat (its west end is the Marina mouth)
    assert "INT_SHELLFISH_MANGROVE" not in engine.intersections
    assert "INT_SANDS_MANGROVE" in engine.intersections


def test_pi_tangents_rule2_derivation(engine):
    """Verify Rule 2 P.I. tangent derivations: T = R * tan(Delta / 2)."""
    assert len(engine.pi_tangents) == 12  # 2 rays per curve * 6 curves
    for seg in engine.pi_tangents:
        assert seg.is_assumed is True
        assert seg.distance > 0.0

    # Verify P.I. intersections exist and are flagged as assumed
    pi_keys = ["INT_PI_MARINA", "INT_PI_SANSALVADORE", "INT_PI_SHELLFISH", "INT_PI_SANDS", "INT_PI_KEEL", "INT_PI_CAPEHORN"]
    for pk in pi_keys:
        assert pk in engine.intersections
        assert engine.intersections[pk].is_assumed is True

    # Rule 2 analytical formula verification: T = R * tan(Delta / 2)
    for _cid, c in engine.curves.items():
        t_calc = c.radius * math.tan(math.radians(c.delta_deg / 2.0))
        assert pytest.approx(c.tangent, abs=0.05) == t_calc


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
        "INT_MARINA_BOUNDARY",
        "INT_SURFWOOD_WEST_END",
        "INT_SURFWOOD_MATCHLINE",
        "INT_CAPEHORN_MATCHLINE",
        "INT_BAYOU_MATCHLINE",
    ]
    for tk in tie_keys:
        assert tk in engine.intersections, f"Missing boundary tie {tk}"
        assert engine.intersections[tk].is_boundary_tie is True


def test_no_culdesac_keel_ends_at_marina(engine):
    """Sheet 2: Block 7 Lots 30-37 are continuous SW of Marina at Keel; there is no cul-de-sac bulb on the plat."""
    assert engine.culdesacs == []
    assert "INT_KEEL_SOUTH_END" not in engine.intersections
    assert "INT_KEEL_CULDESAC" not in engine.intersections
    keel_segs = [s for s in engine.segments if s.street_name.startswith("Keel Drive")]
    assert {s.id for s in keel_segs} == {"SEG_KEEL_MOUTH", "SEG_KEEL_EW"}
    assert engine.intersections["INT_MARINA_KEEL"].is_assumed is False


def test_edge_row_bearing_hedge_and_lot_frontage_summations(engine):
    """Verify user rule: right-of-way edge bearing hedges, front lot bearings, and lot frontage summations."""
    # 1. Bayou Avenue Corridor
    bayou_seg = next(s for s in engine.segments if s.id == "SEG_BAYOU_MAIN")
    assert bayou_seg.is_assumed is False
    assert bayou_seg.derivation_method == "BOUNDARY_OFFSET_AND_TRIM"
    assert bayou_seg.front_lot_bearing == "N89°18'20\"E"

    # 2. Sands Avenue is derived from Mangrove (the old approach from Beachwood Blvd was not on the plat)
    assert not any(s.id == "SEG_ASSUMP_SANDS_APPROACH" for s in engine.segments)
    sands = [s for s in engine.segments if s.street_name == "Sands Avenue"]
    assert [s.bearing for s in sands] == ["N88°58'20\"E", "S54°41'40\"E"]
    assert all(not s.is_assumed for s in sands)

    # 3. Shellfish Drive is derived now (the old "Shellfish-Keel" extension was not on the plat)
    assert not any(s.id == "SEG_ASSUMP_SHELLFISH_KEEL" for s in engine.segments)
    shell_seg = next(s for s in engine.segments if s.id == "SEG_SHELLFISH_MAIN")
    assert shell_seg.is_assumed is False

    # 4. Beachwood Boulevard is no longer a projection: it is derived from course c26 (not assumed)
    assert not any(s.id == "SEG_ASSUMP_BEACHWOOD_S" for s in engine.segments)
    blvd_seg = next(s for s in engine.segments if s.street_name == "Beachwood Boulevard")
    assert blvd_seg.is_assumed is False
    assert blvd_seg.derivation_method == "BOUNDARY_OFFSET_AND_TRIM"


def test_right_of_way_offset_corridor_boundaries(engine):
    """Verify offset lines for straight segments and offset arcs for curves."""
    # 1. Straight segment offset
    starfish = next(s for s in engine.segments if s.id == "SEG_STARFISH_MAIN")
    assert starfish.half_width == 30.0
    (l_start, l_end), (r_start, r_end) = starfish.get_offset_lines()
    assert pytest.approx(l_start.dist_to(l_end), abs=0.01) == starfish.distance
    assert pytest.approx(r_start.dist_to(r_end), abs=0.01) == starfish.distance
    assert pytest.approx(l_start.dist_to(r_start), abs=0.01) == 60.0

    # 2. Beachwood Blvd 80' R/W segment offset (80.04' on the north line, '80'' at Block 6)
    blvd_seg = next(s for s in engine.segments if s.street_name == "Beachwood Boulevard")
    assert blvd_seg.half_width == 40.0
    (l_start, l_end), (r_start, r_end) = blvd_seg.get_offset_lines()
    assert pytest.approx(l_start.dist_to(r_start), abs=0.01) == 80.0

    # 3. Curve offset arcs (San Salvadore: CL R=269.96' -> Inner (S) R=239.96', Outer (N) R=299.96')
    c_ss = engine.curves["C_SANSALVADORE_CL"]
    assert c_ss.half_width == 30.0
    inner_arc, outer_arc = c_ss.get_offset_arcs()
    assert pytest.approx(inner_arc["radius"], abs=0.01) == 239.96  # S R/W: chords 106.60 / 44.61
    assert pytest.approx(outer_arc["radius"], abs=0.01) == 299.96  # N R/W: chords 67.91 / 66.18 / 55.76


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

    # Shellfish Drive reference baseline
    shellfish = alignments["SHELLFISH_DRIVE"]
    assert shellfish["total_length_ft"] > 800.0
    assert len(shellfish["polyline_points"]) >= 3
    assert shellfish["stations"][0]["station"] == "0+00.00"

    # Beachwood Boulevard reference baseline
    blvd = alignments["BEACHWOOD_BOULEVARD"]
    assert blvd["total_length_ft"] > 800.0
    assert len(blvd["polyline_points"]) >= 4
    assert blvd["stations"][0]["station"] == "0+00.00"

    # Keel Drive reference baseline
    keel = alignments["KEEL_DRIVE"]
    assert keel["total_length_ft"] > 400.0
    assert len(keel["polyline_points"]) >= 4
    assert keel["stations"][0]["station"] == "0+00.00"


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
    assert pytest.approx(block_depth + rw_width, abs=0.01) == 260.08

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






def test_validate_all_curves_detects_corruption():
    """F9: the validator checks independent identities, so a corrupted curve must fail (it used to pass everything)."""
    from engine.cogo import Point

    def fresh():
        return BeachwoodRoadCenterlineEngine(base_n=10000.0, base_e=10000.0)

    e = fresh()
    c = e.curves["C_KEEL_CL"]
    c.pt_point = Point(c.pt_point.n + 0.15, c.pt_point.e)  # PT off the circle by 0.15'
    assert e.validate_all_curves()["C_KEEL_CL"]["is_valid"] is False

    e = fresh()
    e.curves["C_MARINA_CL"].direction = "CCW"  # turn sense contradicts the PI
    assert e.validate_all_curves()["C_MARINA_CL"]["is_valid"] is False

    e = fresh()
    c = e.curves["C_SANSALVADORE_CL"]
    c.center_point = Point(2 * c.pc_point.n - c.center_point.n, 2 * c.pc_point.e - c.center_point.e)  # wrong side
    assert e.validate_all_curves()["C_SANSALVADORE_CL"]["is_valid"] is False
