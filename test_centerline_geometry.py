"""
Tests for engine/centerline_geometry.py -- the derived (no typed coordinates) centerline network.

Every assertion is either a plat-printed value or an identity that the geometry must satisfy.
"""

import math

import pytest

from engine.centerline_geometry import FILLET_RADIUS, _dist, solve_network


@pytest.fixture(scope="module")
def net():
    return solve_network()


def test_all_independent_checks_pass(net):
    failed = [(c.name, round(c.residual, 4)) for c in net.checks if not c.ok]
    assert not failed, failed


def test_boundary_caption_closes(net):
    assert net.boundary_closure_ft < 0.05


def test_anchor_is_starfish_mangrove(net):
    assert net.intersections["INT_STARFISH_MANGROVE"].point == pytest.approx((10000.0, 10000.0), abs=1e-9)


def test_beachwood_blvd_is_40ft_inside_east_boundary(net):
    """℄ is parallel to c26 and exactly half the 80' R/W west of it along its whole length."""
    c26 = next(b for b in net.boundary if b["id"] == "c26")
    (n0, e0), (n1, e1) = c26["start"], c26["end"]
    length = math.hypot(n1 - n0, e1 - e0)
    for iid in ("INT_BLVD_NORTH_END", "INT_STARFISH_BEACHWOOD", "INT_KEEL_BEACHWOOD", "INT_BLVD_SOUTH_END"):
        n, e = net.intersections[iid].point
        cross = ((n1 - n0) * (e - e0) - (e1 - e0) * (n - n0)) / length
        assert cross == pytest.approx(-40.0, abs=1e-6), iid  # negative = west (left of northbound c26)


def test_blvd_north_line_reproduces_printed_1626_37(net):
    """Lot frontages + 80' Blvd close the north line printed as 1626.37' (c27)."""
    starfish_n_row = 50.0 + 103.50 + 17 * 75.0 + 113.34  # Block 18 south row from c1
    skew = 150.0 * math.tan(math.radians(1 + 42 / 60 + 50 / 3600))  # Starfish N R/W up to c27, 150'
    north_line = starfish_n_row + skew + 80.0 / math.cos(math.radians(1 + 42 / 60 + 50 / 3600))
    assert north_line == pytest.approx(1626.37, abs=0.02)


def test_every_fillet_is_25ft_and_tangent_to_both_edges(net):
    assert len(net.fillets) == 30
    for f in net.fillets:
        assert f.radius == FILLET_RADIUS
        assert _dist(f.corner, f.pc) == pytest.approx(f.tangent, abs=1e-9)
        assert _dist(f.corner, f.pt) == pytest.approx(f.tangent, abs=1e-9)
        assert _dist(f.rp, f.pc) == pytest.approx(25.0, abs=1e-9)
        assert _dist(f.rp, f.pt) == pytest.approx(25.0, abs=1e-9)
        assert f.tangent == pytest.approx(25.0 * math.tan(math.radians(f.delta_deg / 2)), abs=1e-9)
        assert f.arc_pts[0] == pytest.approx(f.pc, abs=1e-9)
        assert f.arc_pts[-1] == pytest.approx(f.pt, abs=1e-9)


def test_blvd_corner_deltas_are_90_plus_skew(net):
    """Blvd W R/W (N00°41'40"W) meets the E-W streets (N87°35'30"E) 1°42'50" off square: NW 88°17'10", SW 91°42'50"."""
    for f in net.fillets:
        if "BEACHWOOD" in f.id and f.id.endswith("_NW"):
            # block SE corners (e.g. Block 18 Lot 19): interior 91°42'50" -> deflection 88°17'10"
            assert f.delta_deg == pytest.approx(88 + 17 / 60 + 10 / 3600, abs=1e-9)
        elif "BEACHWOOD" in f.id:
            # block NE corners (e.g. Block 17 Lot 17): interior 88°17'10" -> deflection 91°42'50"
            assert f.delta_deg == pytest.approx(91 + 42 / 60 + 50 / 3600, abs=1e-9)
        elif f.id == "F_MARINA_MANGROVE_SE":
            # Marina S R/W (N87°35'30"E) meets Mangrove's south leg (N01°01'40"W): 90° - 1°22'50"
            assert f.delta_deg == pytest.approx(88 + 37 / 60 + 10 / 3600, abs=1e-9)
        else:
            assert f.delta_deg == pytest.approx(90.0, abs=1e-9)


def test_cl_curve_data_tangents(net):
    for c in net.curve_data:
        delta_rad = c["arc_length"] / c["radius"]
        assert c["tangent"] == pytest.approx(c["radius"] * math.tan(delta_rad / 2), abs=1e-9)
        assert c["chord"] == pytest.approx(2 * c["radius"] * math.sin(delta_rad / 2), abs=1e-9)


def test_engine_uses_derived_blvd(net):
    from engine.cogo_road_centerlines import BeachwoodRoadCenterlineEngine
    eng = BeachwoodRoadCenterlineEngine()
    for iid in ("INT_STARFISH_BEACHWOOD", "INT_SAIL_BEACHWOOD", "INT_SHELLFISH_BEACHWOOD", "INT_KEEL_BEACHWOOD"):
        p = eng.intersections[iid].point
        assert (p.n, p.e) == pytest.approx(net.intersections[iid].point, abs=1e-9)
    assert "C_BEACHWOOD_BLVD_CL" not in eng.curves
    assert len(eng.corner_fillets) == 30


def test_mangrove_south_leg_is_180ft_inside_c2(net):
    """The south leg ℄ is placed from the Block 14 lot dimensions; it must sit 180' inside c2 (drainage + lot + half)."""
    c2 = next(b for b in net.boundary if b["id"] == "c2")
    (n0, e0), (n1, e1) = c2["start"], c2["end"]
    length = math.hypot(n1 - n0, e1 - e0)
    for iid in ("INT_MANGROVE_DEFL", "INT_SANDS_MANGROVE", "INT_CAPEHORN_MANGROVE"):
        n, e = net.intersections[iid].point
        cross = ((n1 - n0) * (e - e0) - (e1 - e0) * (n - n0)) / length
        assert cross == pytest.approx(-180.0, abs=1e-6), iid  # negative = left of travel = east of southbound c2


def test_mangrove_crossings_two_sided_agreement(net):
    """Cape Horn and the 40' drainage R/W placed from the east-side lots land on the west-side lot sums."""
    by_name = {c.name: c for c in net.checks}
    for key in ("Cape Horn N R/W", "40' drainage R/W N line"):
        chk = next(c for n, c in by_name.items() if n.startswith(key))
        assert abs(chk.residual) < 0.01, chk


def test_marina_curve_matches_both_sides_and_boundary(net):
    """Marina ℄ P.C. from the NE lots equals the SW lots; c20 ends on the NE R/W; edge chords check to 3"."""
    names = [c for c in net.checks if c.name.startswith("Marina")]
    assert len(names) >= 10
    assert all(c.ok for c in names), [(c.name, c.residual) for c in names if not c.ok]
    mc = net.placed_curves["C_MARINA_CL"]
    assert mc.curve.radius == 359.27
    assert _dist(mc.pi, mc.pc) == pytest.approx(122.70, abs=0.01)
    assert _dist(mc.pi, mc.pt) == pytest.approx(122.70, abs=0.01)
    assert _dist(mc.rp, mc.pt) == pytest.approx(359.27, abs=1e-9)


def test_shellfish_and_keel_mouths(net):
    """Printed tangent legs 25.0' (Shellfish) / 25.18' (Keel) and the 410' mouth spacing reproduce from the east rows."""
    legs = [c for c in net.checks if "edge: Marina NE R/W corner to edge P.C." in c.name]
    assert len(legs) == 4 and all(c.ok for c in legs)
    spacing = next(c for c in net.checks if c.name.startswith("Shellfish-to-Keel mouth spacing"))
    assert abs(spacing.residual) < 0.02
    for fid in ("F_MARINA_SHELLFISH_N", "F_MARINA_SHELLFISH_S", "F_MARINA_KEEL_N", "F_MARINA_KEEL_S"):
        f = next(x for x in net.fillets if x.id == fid)
        assert f.radius == 25.0 and f.delta_deg == pytest.approx(90.0, abs=1e-9)


def test_san_salvadore_matches_sheet1(net):
    """℄ R=269.96 (not 299.96): N edge 299.96 / S edge 239.96 chords, c13 midpoint, 260' from Cape Horn ℄."""
    ss = [c for c in net.checks if c.name.startswith("San Salvadore")]
    assert len(ss) >= 9 and all(c.ok for c in ss), [(c.name, c.residual) for c in ss if not c.ok]
    assert net.placed_curves["C_SANSALVADORE_CL"].curve.radius == 269.96
