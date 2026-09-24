"""Test suite for engine_adapter.py in plat_curves."""

import math

import pytest

from plat_curves.core import dist
from plat_curves.engine_adapter import (
    STATED_PLAT_CURVES,
    build_placed_curve_from_plat,
    compute_concentric_row_edges,
    compute_corner_return,
    compute_open_cul_de_sac,
    placed_to_engine_curve_dict,
)


def test_stated_plat_curves_consistency():
    """Verify that all stated plat curve definitions are internally consistent with Curve formulas."""
    for _cid, spec in STATED_PLAT_CURVES.items():
        assert spec["radius"] > 0
        assert spec["delta_deg"] > 0
        assert spec["tangent"] > 0
        r = spec["radius"]
        d = spec["delta_deg"]
        t_calc = r * math.tan(math.radians(d / 2.0))
        # Stated T should agree within 0.1 ft (Shellfish has 0.084 ft discrepancy noted on plat)
        assert abs(t_calc - spec["tangent"]) < 0.10


def test_build_placed_curve_from_plat():
    """Verify building a placed curve from stated plat data."""
    pc = (1000.0, 2000.0)
    back_az = 90.0  # Due East
    pl = build_placed_curve_from_plat("C_MARINA_CL", pc=pc, back_az=back_az)
    assert pl.curve.radius == 359.27
    assert pl.pc == pc
    assert pl.back_az == 90.0
    assert abs(dist(pl.rp, pl.pt) - 359.27) < 1e-6
    assert abs(dist(pl.pc, pl.pi) - pl.curve.tangent) < 1e-6
    assert abs(dist(pl.pi, pl.pt) - pl.curve.tangent) < 1e-6


def test_placed_to_engine_curve_dict():
    """Verify dictionary conversion compatible with CenterlineCurve."""
    pc = (500.0, 500.0)
    back_az = 125.3056
    pl = build_placed_curve_from_plat("C_SANSALVADORE_CL", pc=pc, back_az=back_az)
    d = placed_to_engine_curve_dict(pl, "C_SANSALVADORE_CL", "San Salvadore Avenue")
    assert d["id"] == "C_SANSALVADORE_CL"
    assert d["radius"] == 269.96
    assert d["tangent"] == pytest.approx(pl.curve.tangent, abs=1e-4)
    assert d["chord_length"] == pytest.approx(pl.curve.chord, abs=1e-4)
    assert d["direction"] == "CW"


def test_compute_concentric_row_edges():
    """Verify concentric edge calculation at +/- 30' half-width."""
    pc = (0.0, 0.0)
    pl = build_placed_curve_from_plat("C_SANSALVADORE_CL", pc=pc, back_az=0.0)
    edges = compute_concentric_row_edges(pl, row_width=60.0)
    assert "outside" in edges
    assert "inside" in edges
    assert edges["outside"].curve.radius == pytest.approx(299.96, abs=1e-4)
    assert edges["inside"].curve.radius == pytest.approx(239.96, abs=1e-4)


def test_compute_corner_return():
    """Verify corner return fillet calculation."""
    corner = (100.0, 100.0)
    # Travel East into corner, then travel North out of corner
    fillet = compute_corner_return(corner=corner, az_in=90.0, az_out=0.0, radius=25.0)
    assert fillet.curve.radius == 25.0
    assert fillet.curve.delta_deg == pytest.approx(90.0, abs=1e-4)
    assert fillet.curve.tangent == pytest.approx(25.0, abs=1e-4)


def test_compute_open_cul_de_sac():
    """Verify cul-de-sac turnaround computation."""
    res = compute_open_cul_de_sac(
        center=(0.0, 0.0),
        bulb_radius=50.0,
        throat_half_width=30.0,
        fillet_radius=25.0,
        axis_az=215.3056,  # S35°18'20"W
    )
    assert res["throat_distance_yf_ft"] == pytest.approx(50.990195, abs=1e-4)
    assert res["theta_prc_deg"] == pytest.approx(47.1670, abs=1e-3)


def test_stated_block_corner_returns():
    """Verify registry of stated subdivision block corner returns."""
    from plat_curves.engine_adapter import (
        STATED_BLOCK_CORNER_RETURNS,
        get_block_corner_returns,
    )
    all_cr = get_block_corner_returns()
    assert len(all_cr) == 10
    assert len(STATED_BLOCK_CORNER_RETURNS) == 10
    # Test specific block queries
    cr18 = get_block_corner_returns("18")
    assert len(cr18) == 1
    assert cr18["CR_BLK18_L19"]["radius"] == 25.0
    assert cr18["CR_BLK18_L19"]["tangent"] == 24.2631

    cr17 = get_block_corner_returns("17")
    assert len(cr17) == 2
    assert "CR_BLK17_L1" in cr17
    assert "CR_BLK17_L34" in cr17

    cr9 = get_block_corner_returns("9")
    assert len(cr9) == 2
    assert cr9["CR_BLK9_L26"]["tangent"] == 22.3134


def test_stated_block_frontage_curves():
    """Verify registry of stated subdivision block frontage and interior curves."""
    from plat_curves.engine_adapter import (
        STATED_BLOCK_FRONTAGE_CURVES,
        get_block_frontage_curves,
    )
    all_fc = get_block_frontage_curves()
    assert len(all_fc) >= 6
    assert len(STATED_BLOCK_FRONTAGE_CURVES) >= 6

    fc16 = get_block_frontage_curves("16")
    assert "CURVE_BLK16_MARINA_NORTH_RW" in fc16
    assert fc16["CURVE_BLK16_MARINA_NORTH_RW"]["radius"] == 389.27
    assert "CURVE_BLK16_KEEL_L28" in fc16
    assert fc16["CURVE_BLK16_KEEL_L28"]["radius"] == 167.95

    fc15 = get_block_frontage_curves("15")
    assert "CURVE_BLK15_SHELLFISH_L1" in fc15
    assert fc15["CURVE_BLK15_SHELLFISH_L1"]["radius"] == 137.95
    assert "CURVE_BLK15_KEEL_L15" in fc15
    assert fc15["CURVE_BLK15_KEEL_L15"]["radius"] == 173.93
    assert "CURVE_BLK15_EAST_BOUNDARY" in fc15
    assert fc15["CURVE_BLK15_EAST_BOUNDARY"]["radius"] == 1959.86

