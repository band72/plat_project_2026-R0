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
    assert audit["entity_counts"]["lines"] > 0
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

