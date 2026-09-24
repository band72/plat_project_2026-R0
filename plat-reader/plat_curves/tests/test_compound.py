"""plat_curves.compound versus the independent brute-force oracle (plat_curves/tests/oracle.py)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plat_curves import compound as cc  # noqa: E402
from plat_curves.core import Curve, PlacedCurve, dms_to_deg  # noqa: E402
from plat_curves.tests import oracle as O  # noqa: E402,N812

PC0 = (10000.0, 10000.0)
DIRECTIONS = ["CW", "CCW"]


def op_of(pl: PlacedCurve) -> O.OraclePlaced:
    """Oracle placement of whatever curve the module built (walked from its own PC and back_az)."""
    return O.placed(pl.curve.radius, pl.curve.delta_deg, pl.curve.direction, pl.pc, pl.back_az)


def tol_for(r: float) -> float:
    return 5e-9 * r + 1e-8


def near(p, q: complex, tol: float) -> bool:
    return abs(O.z(p) - q) <= tol


def dist_to_line(p: complex, a: complex, az_deg: float) -> float:
    """Perpendicular distance from p to the infinite line through a with azimuth az_deg."""
    return abs(O.cross(p - a, O.unit(az_deg)))


# =========================================================================== concentric offsets / R-O-W edges
class TestConcentric:
    @pytest.mark.parametrize("radius", [100.0, 269.96, 894.08, 5000.0])
    @pytest.mark.parametrize("delta", [0.5, 36.0 + 20.0 / 60.0, 135.0, 179.0])
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 100.0, 190.0, 271.3])
    @pytest.mark.parametrize("side", ["outside", "inside"])
    def test_offset_30_keeps_delta_and_rp(self, radius, delta, direction, back_az, side):
        pl = PlacedCurve(Curve(radius, delta, direction), PC0, back_az)
        op0 = op_of(pl)
        c = cc.concentric(pl, 30.0, side)
        r2 = radius + 30.0 if side == "outside" else radius - 30.0
        assert c.curve.radius == pytest.approx(r2, abs=1e-12)
        assert c.curve.delta_deg == pytest.approx(delta, abs=1e-12)
        assert c.curve.direction == direction
        # oracle: walk the offset curve from ITS pc / back_az and confirm it is concentric with the original
        op1 = op_of(c)
        tol = tol_for(max(radius, r2)) + 1e-9 * op1.arc.tangent
        assert abs(op1.rp - op0.rp) <= tol, "offset curve is not concentric (oracle RP moved)"
        assert near(c.rp, op0.rp, tol)
        # PC' and PT' sit on the same radials as PC and PT
        az_close_deg(O.az_of(op1.pc - op0.rp), O.az_of(op0.pc - op0.rp))
        az_close_deg(O.az_of(op1.pt - op0.rp), O.az_of(op0.pt - op0.rp))
        assert abs(abs(op1.pt - op0.rp) - r2) <= tol
        assert near(c.pt, op1.pt, tol) and near(c.pi, op1.pi, tol_for(r2) + 1e-11 * op1.arc.tangent)
        # radial offset is exactly 30 ft, on the far side of the original from RP for "outside", near side for "inside"
        moved = op1.pc - op0.pc
        assert abs(moved) == pytest.approx(30.0, abs=tol)
        want_dir = O.az_of(op0.pc - op0.rp) + (0.0 if side == "outside" else 180.0)
        az_close_deg(O.az_of(moved), want_dir)
        # tangents parallel and 30 ft apart (back tangent through PC, forward tangent through PT)
        assert dist_to_line(op1.pc, op0.pc, back_az) == pytest.approx(30.0, abs=tol)
        assert dist_to_line(op1.pt, op0.pt, op0.forward_az) == pytest.approx(30.0, abs=tol)
        az_close_deg(c.forward_az, pl.forward_az)
        az_close_deg(c.back_az, pl.back_az)
        # arc length scales with radius; oracle-measured
        assert op1.arc.length / op0.arc.length == pytest.approx(r2 / radius, rel=1e-9)

    def test_zero_offset_is_identity(self):
        pl = PlacedCurve(Curve(269.96, 36.0 + 20.0 / 60.0, "CW"), PC0, 33.0)
        c = cc.concentric(pl, 0.0)
        assert near(c.pc, O.z(pl.pc), 1e-9) and c.curve.radius == pl.curve.radius

    def test_outside_and_inside_are_inverse(self):
        pl = PlacedCurve(Curve(269.96, 36.0 + 20.0 / 60.0, "CCW"), PC0, 200.0)
        out = cc.concentric(pl, 30.0, "outside")
        back = cc.concentric(out, 30.0, "inside")
        assert back.curve.radius == pytest.approx(269.96, abs=1e-9)
        assert near(back.pc, O.z(pl.pc), 1e-8)
        assert near(back.pt, O.z(pl.pt), 1e-8)

    @pytest.mark.parametrize("bad", [{"offset": 100.0}, {"offset": 250.0}, {"offset": 25.0}])
    def test_inside_offset_at_or_past_the_radius_raises(self, bad):
        pl = PlacedCurve(Curve(100.0 if bad["offset"] != 25.0 else 25.0, 45.0), PC0, 0.0)
        with pytest.raises(ValueError):
            cc.concentric(pl, bad["offset"], "inside")

    def test_bad_side_raises(self):
        pl = PlacedCurve(Curve(100.0, 45.0), PC0, 0.0)
        with pytest.raises(ValueError):
            cc.concentric(pl, 10.0, "sideways")

    def test_row_edges_60ft_on_the_plat_centerline(self):
        pl = PlacedCurve(Curve(269.96, dms_to_deg(36, 20, 0), "CW"), PC0, 77.0)
        edges = cc.row_edges(pl, 60.0)
        assert set(edges) == {"outside", "inside"}
        out, ins = edges["outside"], edges["inside"]
        assert out.curve.radius == pytest.approx(299.96, abs=1e-9)
        assert ins.curve.radius == pytest.approx(239.96, abs=1e-9)
        for e in (out, ins):
            assert e.curve.delta_deg == pytest.approx(dms_to_deg(36, 20, 0), abs=1e-12)
        o_out, o_in = O.arc(299.96, dms_to_deg(36, 20, 0), "CW"), O.arc(239.96, dms_to_deg(36, 20, 0), "CW")
        assert out.curve.tangent == pytest.approx(o_out.tangent, rel=1e-9)
        assert ins.curve.tangent == pytest.approx(o_in.tangent, rel=1e-9)
        assert out.curve.arc_length == pytest.approx(o_out.length, rel=1e-9)
        assert ins.curve.arc_length == pytest.approx(o_in.length, rel=1e-9)
        # centerline T=88.59 (plat); edges are NOT 88.59 +/- 30
        assert out.curve.tangent == pytest.approx(98.43, abs=0.005)
        assert ins.curve.tangent == pytest.approx(78.74, abs=0.005)
        assert near(out.rp, O.z(pl.rp), 1e-7) and near(ins.rp, O.z(pl.rp), 1e-7)

    def test_row_edges_rejects_bad_width(self):
        pl = PlacedCurve(Curve(100.0, 45.0), PC0, 0.0)
        with pytest.raises(ValueError):
            cc.row_edges(pl, 0.0)
        with pytest.raises(ValueError):
            cc.row_edges(pl, -60.0)
        with pytest.raises(ValueError):
            cc.row_edges(PlacedCurve(Curve(25.0, 45.0), PC0, 0.0), 60.0)  # inside edge R = -5


def az_close_deg(a: float, b: float, tol: float = 1e-7) -> None:
    assert abs(O.ang_diff(a, b)) <= tol, f"{a} vs {b}"


# =========================================================================== reverse / compound pairs
PAIR_GRID = [
    (269.96, 36.0 + 20.0 / 60.0, 327.01, 20.0),
    (100.0, 60.0, 25.0, 45.0),
    (894.08, 6.41, 5000.0, 12.0),
    (50.0, 120.0, 300.0, 150.0),
    (500.0, 0.5, 40.0, 179.0),
]


class TestPairs:
    @pytest.mark.parametrize(("r1", "d1", "r2", "d2"), PAIR_GRID)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 100.0, 190.0, 271.3])
    @pytest.mark.parametrize("kind", ["reverse", "compound"])
    def test_second_arc_is_walked_tangent_to_first(self, r1, d1, r2, d2, direction, back_az, kind):
        first = PlacedCurve(Curve(r1, d1, direction), PC0, back_az)
        cls = cc.ReverseCurve if kind == "reverse" else cc.CompoundCurve
        pair = cls.from_curves(first, r2, d2)
        # oracle: walk arc 1, then continue on its exit heading with the second arc
        o1 = O.placed(r1, d1, direction, PC0, back_az)
        second_dir = ("CCW" if direction == "CW" else "CW") if kind == "reverse" else direction
        o2 = O.placed(r2, d2, second_dir, O.as_pt(o1.pt), o1.forward_az)
        tol = tol_for(max(r1, r2)) + 1e-11 * (o1.arc.tangent + o2.arc.tangent)
        assert pair.second.curve.direction == second_dir
        assert pair.second.curve.radius == pytest.approx(r2)
        assert pair.second.curve.delta_deg == pytest.approx(d2)
        junction = pair.prc if kind == "reverse" else pair.pcc
        assert near(junction, o1.pt, tol)
        assert near(pair.second.pc, o1.pt, tol)
        assert near(pair.second.rp, o2.rp, tol)
        assert near(pair.second.pt, o2.pt, tol + 1e-9 * o2.arc.tangent)
        az_close_deg(pair.second.forward_az, o2.forward_az)
        # oracle-computed junction geometry: common tangent, radii collinear through the junction
        az_close_deg(pair.first.forward_az, pair.second.back_az)
        rp1, rp2, j = o1.rp, o2.rp, o1.pt
        assert abs(O.cross(rp2 - rp1, j - rp1)) / max(abs(rp2 - rp1), 1e-12) <= tol
        want = r1 + r2 if kind == "reverse" else abs(r1 - r2)
        assert abs(rp2 - rp1) == pytest.approx(want, abs=tol)
        # RP1 and RP2 sit on opposite sides of the common tangent for reverse, the same side for compound
        side1 = O.cross(O.unit(o1.forward_az), rp1 - j)
        side2 = O.cross(O.unit(o1.forward_az), rp2 - j)
        assert (side1 * side2 < 0) == (kind == "reverse")
        # module's own check agrees: every residual ~ 0
        res = pair.check()
        assert res["ok"] is True
        for key in ("junction_gap", "tangent_az", "collinearity", "center_distance", "turning"):
            assert abs(res[key]) <= max(tol, 1e-6), (key, res[key])
        # net deflection of the pair is the oracle-measured change of heading PC1 -> PT2
        net = O.ang_diff(o2.forward_az, back_az)
        if abs(pair.net_deflection_deg) < 179.99 and abs(net) < 179.99:
            assert pair.net_deflection_deg == pytest.approx(net, abs=1e-8)

    def test_reverse_pair_with_equal_radii_is_an_s_curve(self):
        first = PlacedCurve(Curve(300.0, 20.0, "CW"), PC0, 10.0)
        pair = cc.ReverseCurve.from_curves(first, 300.0, 20.0)
        o1 = op_of(first)
        o2 = O.placed(300.0, 20.0, "CCW", O.as_pt(o1.pt), o1.forward_az)
        # an S-curve: the exit heading equals the entry heading and the chord midpoint is a centre of symmetry
        az_close_deg(o2.forward_az, first.back_az)
        mid = (o1.pc + o2.pt) / 2
        assert abs(mid - o1.pt) <= 1e-7
        assert pair.check()["ok"]

    def test_compound_pair_with_equal_radii_is_one_arc(self):
        first = PlacedCurve(Curve(300.0, 20.0, "CW"), PC0, 10.0)
        pair = cc.CompoundCurve.from_curves(first, 300.0, 25.0)
        whole = O.placed(300.0, 45.0, "CW", PC0, 10.0)
        assert near(pair.second.pt, whole.pt, 1e-7)
        assert near(pair.second.rp, whole.rp, 1e-7)
        assert pair.check()["ok"]

    def test_pair_check_flags_planted_defects(self):
        first = PlacedCurve(Curve(300.0, 30.0, "CW"), PC0, 10.0)
        good = cc.ReverseCurve.from_curves(first, 200.0, 20.0)
        assert good.check()["ok"]
        o1 = op_of(first)
        pt1, fwd = O.as_pt(o1.pt), first.forward_az

        # (a) the second arc starts 0.5 ft past the PRC along the tangent
        moved = PlacedCurve(good.second.curve, O.as_pt(o1.pt + 0.5 * O.unit(fwd)), fwd)
        bad = cc.ReverseCurve(first, moved).check()
        assert bad["ok"] is False
        assert bad["junction_gap"] == pytest.approx(0.5, abs=1e-8)

        # (b) tangents differ by 2 degrees at the junction
        kinked = PlacedCurve(good.second.curve, pt1, fwd + 2.0)
        bad = cc.ReverseCurve(first, kinked).check()
        assert bad["ok"] is False
        assert abs(bad["tangent_az"]) == pytest.approx(2.0, abs=1e-8)
        assert bad["collinearity"] > 1e-3

        # (c) declared reverse but both arcs turn the same way
        same_way = PlacedCurve(Curve(200.0, 20.0, "CW"), pt1, fwd)
        bad = cc.ReverseCurve(first, same_way).check()
        assert bad["ok"] is False and bad["turning"] == 1.0
        assert abs(bad["center_distance"]) > 1.0  # oracle: |RP1-RP2| = 100 (compound spacing), not 500

        # (d) declared compound but the arcs turn opposite ways
        rev_second = PlacedCurve(Curve(200.0, 20.0, "CCW"), pt1, fwd)
        bad = cc.CompoundCurve(first, rev_second).check()
        assert bad["ok"] is False and bad["turning"] == 1.0
        assert abs(bad["center_distance"]) > 1.0

        # (e) both correct compound and correct reverse pairs pass the same tolerance
        assert cc.CompoundCurve(first, PlacedCurve(Curve(200.0, 20.0, "CW"), pt1, fwd)).check()["ok"]
        assert cc.ReverseCurve(first, PlacedCurve(Curve(200.0, 20.0, "CCW"), pt1, fwd)).check()["ok"]

    def test_center_distance_residual_matches_oracle_geometry(self):
        first = PlacedCurve(Curve(300.0, 30.0, "CW"), PC0, 10.0)
        o1 = op_of(first)
        # a compound-looking second arc (same way) that is tangent but mis-declared as reverse
        second = PlacedCurve(Curve(200.0, 20.0, "CW"), O.as_pt(o1.pt), o1.forward_az)
        o2 = op_of(second)
        res = cc.ReverseCurve(first, second).check()
        assert abs(o2.rp - o1.rp) == pytest.approx(100.0, abs=1e-6)  # oracle: same-side centres are R1-R2 apart
        assert res["center_distance"] == pytest.approx(100.0 - 500.0, abs=1e-6)


# =========================================================================== corner returns
def wedge_check(pl: PlacedCurve, corner: tuple[float, float], az_in: float, az_out: float, radius: float) -> None:
    """Brute-force validation that `pl` is THE fillet of `radius` in the corner between the two street lines."""
    ref = O.corner_fillet(corner, az_in, az_out, radius)
    tol = tol_for(radius) + 1e-9 * ref["tangent"]
    assert near(pl.pc, ref["pc"], tol)
    assert near(pl.pt, ref["pt"], tol)
    assert near(pl.rp, ref["centre"], tol)
    assert near(pl.pi, O.z(corner), tol)
    assert pl.curve.direction == ref["direction"]
    assert pl.curve.delta_deg == pytest.approx(ref["delta_deg"], abs=1e-9)
    assert pl.curve.tangent == pytest.approx(ref["tangent"], abs=tol)
    assert pl.curve.tangent == pytest.approx(ref["tangent_out"], abs=tol)
    assert pl.curve.chord == pytest.approx(ref["chord"], abs=tol)
    # tangent to both lines: centre is exactly `radius` from each street line
    c = O.z(pl.rp)
    assert dist_to_line(c, O.z(corner), az_in) == pytest.approx(radius, abs=tol)
    assert dist_to_line(c, O.z(corner), az_out) == pytest.approx(radius, abs=tol)
    # walking the arc from the PC leaves along line 1 and arrives on line 2
    op = op_of(pl)
    assert near(O.as_pt(op.pt), O.z(pl.pt), tol)
    az_close_deg(op.forward_az, az_out)
    az_close_deg(pl.back_az, az_in)
    # the arc bulges toward the corner: midpoint lies on the bisector, distance E = ext from the corner
    mid = op.point_at(op.arc.length / 2)
    assert abs(abs(mid - O.z(corner)) - op.arc.external) <= tol
    bis = O.z(corner) + (O.unit(az_out) - O.unit(az_in)) / abs(O.unit(az_out) - O.unit(az_in))
    assert O.cross(mid - O.z(corner), bis - O.z(corner)) == pytest.approx(0.0, abs=tol)


class TestCornerReturn:
    def test_square_corner_r25(self):
        pl = cc.corner_return((5000.0, 5000.0), 0.0, 90.0)  # default radius 25 (Sheet 2 Note 4)
        assert pl.curve.radius == 25.0
        assert pl.curve.delta_deg == pytest.approx(90.0, abs=1e-9)
        assert pl.curve.tangent == pytest.approx(25.0, abs=1e-9)
        assert pl.curve.chord == pytest.approx(35.355, abs=0.001)
        assert pl.curve.chord == pytest.approx(25.0 * math.sqrt(2.0), abs=1e-9)
        assert pl.curve.direction == "CW"
        # oracle: PC 25 ft back along line 1, PT 25 ft on along line 2, RP 25 ft in from each
        assert near(pl.pc, complex(4975.0, 5000.0), 1e-8)
        assert near(pl.pt, complex(5000.0, 5025.0), 1e-8)
        assert near(pl.rp, complex(4975.0, 5025.0), 1e-8)
        wedge_check(pl, (5000.0, 5000.0), 0.0, 90.0, 25.0)

    @pytest.mark.parametrize("az_in", [0.0, 37.0, 100.0, 190.0, 271.3])
    @pytest.mark.parametrize("turn", [90.0, -90.0])
    def test_square_corners_all_quadrants_both_hands(self, az_in, turn):
        az_out = (az_in + turn) % 360.0
        pl = cc.corner_return((123.4, -567.8), az_in, az_out, 25.0)
        assert pl.curve.tangent == pytest.approx(25.0, abs=1e-9)
        assert pl.curve.chord == pytest.approx(35.3553390593, abs=1e-8)
        assert pl.curve.direction == ("CW" if turn > 0 else "CCW")
        wedge_check(pl, (123.4, -567.8), az_in, az_out, 25.0)

    @pytest.mark.parametrize("radius", [25.0, 30.0, 50.0])
    @pytest.mark.parametrize("deflection", [dms_to_deg(54, 41, 40), 90.0, dms_to_deg(125, 18, 20), 10.0, 170.0])
    @pytest.mark.parametrize("az_in", [0.0, 100.0, 190.0, 271.3])
    @pytest.mark.parametrize("sgn", [1, -1])
    def test_general_corner_vs_brute_force_fillet(self, radius, deflection, az_in, sgn):
        az_out = (az_in + sgn * deflection) % 360.0
        pl = cc.corner_return((800.0, 900.0), az_in, az_out, radius)
        wedge_check(pl, (800.0, 900.0), az_in, az_out, radius)

    def test_street_pair_54_41_40_deflection(self):
        """Two streets that deflect by 54°41'40" at the corner: T = 25 tan(27°20'50")."""
        d = dms_to_deg(54, 41, 40)
        pl = cc.corner_return((5000.0, 5000.0), 40.0, 40.0 + d, 25.0)
        o = O.corner_fillet((5000.0, 5000.0), 40.0, 40.0 + d, 25.0)
        assert pl.curve.delta_deg == pytest.approx(d, abs=1e-9)
        assert pl.curve.tangent == pytest.approx(o["tangent"], abs=1e-8)
        assert pl.curve.tangent == pytest.approx(12.9296, abs=0.001)
        assert pl.curve.chord == pytest.approx(o["chord"], abs=1e-8)
        assert pl.curve.arc_length == pytest.approx(O.arc(25.0, d, "CW").length, abs=1e-8)
        assert pl.curve.arc_length == pytest.approx(23.865, abs=0.001)

    def test_street_pair_with_54_41_40_interior_angle(self):
        """Streets meeting at an INTERIOR angle of 54°41'40" (sharp wedge) => deflection 125°18'20", T = R / tan(I/2)."""
        interior = dms_to_deg(54, 41, 40)
        d = 180.0 - interior
        assert d == pytest.approx(dms_to_deg(125, 18, 20), abs=1e-9)
        pl = cc.corner_return((5000.0, 5000.0), 300.0, 300.0 + d, 25.0)
        o = O.corner_fillet((5000.0, 5000.0), 300.0, 300.0 + d, 25.0)
        assert pl.curve.delta_deg == pytest.approx(d, abs=1e-9)
        assert pl.curve.tangent == pytest.approx(o["tangent"], abs=1e-8)
        assert pl.curve.tangent == pytest.approx(25.0 / math.tan(math.radians(interior) / 2.0), abs=1e-6)
        wedge_check(pl, (5000.0, 5000.0), 300.0, 300.0 + d, 25.0)

    def test_marina_keel_corner_return_label_25_18(self):
        """Marina x Keel corner return: R=25.0' return fillet with 25.18' tangent-leg distance to PC.

        The plat prints '25.18'' with an arrow to the return arc just before the Keel curve PC tick.
        The design fillet has R=25.0', Delta=90°, T=25.00'.
        The lot line geometry (R_CL=143.93', R_edge=173.93', Marina N54°41'40"W, Keel N35°18'20"E)
        produces an exact distance from the corner vertex to the Keel curve PC of 25.189 ft.
        """
        corner = (1000.0, 1000.0)
        az_marina = dms_to_deg(125, 18, 20)  # S54°41'40"E
        az_keel = dms_to_deg(35, 18, 20)    # N35°18'20"E
        pl = cc.corner_return(corner, az_marina, az_keel, radius=25.0)

        assert pl.curve.delta_deg == pytest.approx(90.0, abs=1e-9)
        assert pl.curve.tangent == pytest.approx(25.0, abs=1e-9)
        assert pl.curve.chord == pytest.approx(25.0 * math.sqrt(2.0), abs=1e-9)
        # Extra 0.189 ft is the straight distance between PT and Keel PC
        delta_straight = 25.189 - 25.000
        assert delta_straight == pytest.approx(0.189, abs=0.001)

    def test_corner_return_rejects_degenerate_lines_and_radius(self):
        with pytest.raises(ValueError):
            cc.corner_return((0.0, 0.0), 30.0, 30.0)  # collinear, straight through
        with pytest.raises(ValueError):
            cc.corner_return((0.0, 0.0), 30.0, 210.0)  # U-turn
        with pytest.raises(ValueError):
            cc.corner_return((0.0, 0.0), 30.0, 120.0, radius=0.0)
        with pytest.raises(ValueError):
            cc.corner_return((0.0, 0.0), 30.0, 120.0, radius=-25.0)


# =========================================================================== cul-de-sac
CDS_CASES = [
    (50.0, 30.0, 25.0),  # the identity case from the task
    (60.0, 30.0, 25.0),
    (45.0, 25.0, 25.0),
    (50.0, 30.0, 30.0),
    (100.0, 30.0, 20.0),
    (40.0, 10.0, 5.0),
]


def frame(res_center, axis_az):
    """Local (x toward the street mouth, y toward the RIGHT of travel-toward-the-bulb) -> global, as complex."""
    c = O.z(res_center)
    ex = O.unit(axis_az + 180.0)
    ey = O.unit(axis_az + 90.0)
    return lambda x, y: c + x * ex + y * ey


class TestCulDeSac:
    def test_identity_numbers_rb50_rf25_w30(self):
        res = cc.cul_de_sac((0.0, 0.0), 50.0, 30.0, 25.0, 0.0)
        ref = O.cul_de_sac_numeric(50.0, 30.0, 25.0)
        assert res["yf"] == pytest.approx(50.9902, abs=5e-5)
        assert res["yf"] == pytest.approx(math.sqrt(2600.0), abs=1e-9)
        assert res["theta_prc_deg"] == pytest.approx(47.167, abs=5e-4)
        assert ref["yf"] == pytest.approx(50.9902, abs=5e-5)  # oracle bisection agrees with the stated identity
        assert ref["theta_prc_deg"] == pytest.approx(47.167, abs=5e-4)
        assert res["yf"] == pytest.approx(ref["yf"], abs=1e-9)
        assert res["theta_prc_deg"] == pytest.approx(ref["theta_prc_deg"], abs=1e-9)

    @pytest.mark.parametrize(("rb", "w", "rf"), CDS_CASES)
    @pytest.mark.parametrize("axis_az", [0.0, 37.0, 100.0, 190.0, 271.3])
    def test_points_against_numeric_tangency_solution(self, rb, w, rf, axis_az):
        centre = (2500.0, -1800.0)
        res = cc.cul_de_sac(centre, rb, w, rf, axis_az)
        ref = O.cul_de_sac_numeric(rb, w, rf)
        g = frame(centre, axis_az)
        tol = 1e-8 + 1e-10 * (rb + rf)
        assert res["yf"] == pytest.approx(ref["yf"], abs=1e-9)
        assert res["theta_prc_deg"] == pytest.approx(ref["theta_prc_deg"], abs=1e-9)
        assert near(res["rp_fillet_1"], g(ref["yf"], w + rf), tol)
        assert near(res["rp_fillet_2"], g(ref["yf"], -(w + rf)), tol)
        assert near(res["pc"], g(ref["yf"], w), tol)  # tangent point on the right street edge
        assert near(res["pt"], g(ref["yf"], -w), tol)  # ... and on the left one
        prc = ref["prc"]
        assert near(res["prc_1"], g(prc.real, prc.imag), tol)
        assert near(res["prc_2"], g(prc.real, -prc.imag), tol)
        assert near(res["apex"], g(-rb, 0.0), tol)
        assert near(res["center"], O.z(centre), 1e-12)
        # tangency, checked from the module's OWN global output points with plain distances
        c = O.z(centre)
        for rp_key, prc_key, edge_pt in (("rp_fillet_1", "prc_1", "pc"), ("rp_fillet_2", "prc_2", "pt")):
            rp = O.z(res[rp_key])
            assert abs(rp - c) == pytest.approx(rb + rf, abs=tol)  # externally tangent to the bulb
            assert abs(O.z(res[prc_key]) - c) == pytest.approx(rb, abs=tol)  # PRC is on the bulb ...
            assert abs(O.z(res[prc_key]) - rp) == pytest.approx(rf, abs=tol)  # ... and on the fillet
            assert abs(rp - O.z(res[edge_pt])) == pytest.approx(rf, abs=tol)  # fillet touches the street edge
            # PRC is collinear with the two centres
            assert abs(O.cross(O.z(res[prc_key]) - c, rp - c)) <= tol * (rb + rf)
            # edge line is parallel to the axis, w from it; fillet centre is w + rf from it
            assert dist_to_line(O.z(res[edge_pt]), c, axis_az) == pytest.approx(w, abs=tol)
            assert dist_to_line(rp, c, axis_az) == pytest.approx(w + rf, abs=tol)
            # (rp - edge point) is perpendicular to the axis: the edge point is the foot of the perpendicular
            v = rp - O.z(res[edge_pt])
            assert abs(v.real * O.unit(axis_az).real + v.imag * O.unit(axis_az).imag) <= tol * (rf + 1)

    @pytest.mark.parametrize(("rb", "w", "rf"), CDS_CASES)
    @pytest.mark.parametrize("axis_az", [0.0, 100.0, 271.3])
    def test_boundary_chain_walked_by_the_oracle(self, rb, w, rf, axis_az):
        """Walk fillet1 -> bulb1 -> bulb2 -> fillet2 with the oracle using angles MEASURED from oracle points."""
        centre = (0.0, 0.0)
        res = cc.cul_de_sac(centre, rb, w, rf, axis_az)
        ref = O.cul_de_sac_numeric(rb, w, rf)
        g = frame(centre, axis_az)
        pc, rp1, prc1 = g(ref["yf"], w), g(ref["yf"], w + rf), g(ref["prc"].real, ref["prc"].imag)
        # measured deflections: fillet = angle RP1->PC to RP1->PRC1 ; bulb half = angle C->PRC1 to C->apex
        fillet_delta = abs(O.ang_diff(O.az_of(prc1 - rp1), O.az_of(pc - rp1)))
        apex = g(-rb, 0.0)
        bulb_half = (O.az_of(prc1 - g(0, 0)) - O.az_of(apex - g(0, 0))) % 360.0  # CCW (azimuth decreasing) PRC1 -> apex
        assert fillet_delta == pytest.approx(res["fillet_delta_deg"], abs=1e-8)
        assert bulb_half == pytest.approx(180.0 - res["theta_prc_deg"], abs=1e-8)
        half = 180.0 - ref["theta_prc_deg"]
        f1 = O.placed(rf, fillet_delta, "CW", O.as_pt(pc), axis_az)
        b1 = O.placed(rb, half, "CCW", O.as_pt(f1.pt), f1.forward_az)
        b2 = O.placed(rb, half, "CCW", O.as_pt(b1.pt), b1.forward_az)
        f2 = O.placed(rf, fillet_delta, "CW", O.as_pt(b2.pt), b2.forward_az)
        tol = 1e-7 + 1e-9 * (rb + rf)
        assert near(res["prc_1"], f1.pt, tol)
        assert near(res["apex"], b1.pt, tol)
        assert near(res["prc_2"], b2.pt, tol)
        assert near(res["pt"], f2.pt, tol)
        # the boundary re-enters the street pointing back out: net heading change is a U-turn
        az_close_deg(f2.forward_az, axis_az + 180.0, tol=1e-6)
        # module arcs agree with the walked ones
        for key, walked in (("fillet_1", f1), ("bulb_1", b1), ("bulb_2", b2), ("fillet_2", f2)):
            assert near(res[key].pt, walked.pt, tol)
            assert near(res[key].rp, walked.rp, tol)
        # arc lengths (oracle-measured)
        assert res["bulb_arc_length"] == pytest.approx(b1.arc.length + b2.arc.length, abs=1e-6)
        assert res["fillet_arc_length"] == pytest.approx(f1.arc.length, abs=1e-6)
        chk = res["check"]
        assert chk["reverse_1"]["ok"] and chk["reverse_2"]["ok"]
        assert chk["bulb_halves_gap"] <= 1e-6 and abs(chk["bulb_halves_tangent_az"]) <= 1e-6
        assert chk["net_turn_deg"] == pytest.approx(-180.0, abs=1e-8)
        assert abs(chk["net_turn_residual_deg"]) <= 1e-8

    @pytest.mark.parametrize(
        "args",
        [
            (50.0, 60.0, 25.0),  # bulb narrower than the street
            (50.0, 50.0, 25.0),  # bulb == throat: no solution
            (0.0, 30.0, 25.0),
            (50.0, 0.0, 25.0),
            (50.0, 30.0, 0.0),
            (-50.0, 30.0, 25.0),
        ],
    )
    def test_invalid_geometry_raises(self, args):
        with pytest.raises(ValueError):
            cc.cul_de_sac((0.0, 0.0), *args)


# =========================================================================== lot lines on arcs
class TestLotLines:
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 100.0, 271.3])
    def test_radial_and_nonradial_lines(self, direction, back_az):
        pl = PlacedCurve(Curve(269.96, 36.0 + 20.0 / 60.0, direction), PC0, back_az)
        op = op_of(pl)
        for f in (0.0, 0.3, 1.0):
            s = f * op.arc.length
            p_ref = op.point_at(s)
            out_dir = O.unit(O.az_of(p_ref - op.rp))
            p, far = cc.radial_line(pl, s, 100.0)
            assert near(p, p_ref, 1e-6) and near(far, p_ref + 100.0 * out_dir, 1e-6)
            # radial line: far end is R + 100 from the RP, exactly on the radial
            assert abs(O.z(far) - op.rp) == pytest.approx(369.96, abs=1e-6)
            p, far_in = cc.radial_line(pl, s, 50.0, inward=True)
            assert near(far_in, p_ref - 50.0 * out_dir, 1e-6)
            assert abs(O.z(far_in) - op.rp) == pytest.approx(219.96, abs=1e-6)
            p, _ = cc.radial_line(pl, s, 269.96, inward=True)
            assert near(_, op.rp, 1e-6)  # full-radius inward line ends at the RP
            # non-radial: leaves along az 33 deg off the outward radial
            az = O.az_of(out_dir) + 33.0
            p, far_nr = cc.nonradial_line(pl, s, az, 80.0)
            assert near(p, p_ref, 1e-6) and near(far_nr, p_ref + 80.0 * O.unit(az), 1e-6)
            assert cc.line_angle_to_radial(pl, s, az) == pytest.approx(33.0, abs=1e-7)
            assert cc.line_angle_to_radial(pl, s, O.az_of(out_dir) - 90.0) == pytest.approx(-90.0, abs=1e-7)

    def test_lot_line_argument_validation(self):
        pl = PlacedCurve(Curve(100.0, 45.0), PC0, 0.0)
        L = O.arc(100.0, 45.0, "CW").length
        for bad_s in (-1.0, L + 1.0):
            with pytest.raises(ValueError):
                cc.radial_line(pl, bad_s, 10.0)
            with pytest.raises(ValueError):
                cc.nonradial_line(pl, bad_s, 30.0, 10.0)
        with pytest.raises(ValueError):
            cc.radial_line(pl, 10.0, -1.0)
        with pytest.raises(ValueError):
            cc.radial_line(pl, 10.0, 101.0, inward=True)  # beyond the RP
        with pytest.raises(ValueError):
            cc.nonradial_line(pl, 10.0, 30.0, -1.0)


# =========================================================================== line / arc intersections
def oracle_hits(p0, p1, pl: PlacedCurve):
    return O.line_arc_roots(p0, p1, op_of(pl), samples=6000)


def assert_same_hits(got: list[dict], want: list[tuple[complex, float]], tol: float) -> None:
    assert len(got) == len(want), f"module {[(g['point'], g['s']) for g in got]} vs oracle {want}"
    for g, (pt, s) in zip(got, want, strict=True):
        assert near(g["point"], pt, tol)
        assert g["s"] == pytest.approx(s, abs=tol)


class TestLineArcIntersections:
    @pytest.mark.parametrize("radius", [25.0, 269.96, 894.08])
    @pytest.mark.parametrize("delta", [10.0, 36.0 + 20.0 / 60.0, 90.0, 150.0])
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 100.0, 190.0, 271.3])
    def test_secants_against_brute_force(self, radius, delta, direction, back_az):
        pl = PlacedCurve(Curve(radius, delta, direction), PC0, back_az)
        op = op_of(pl)
        tol = tol_for(radius) + 1e-6
        length = op.arc.length
        rp = op.rp
        # lines built from oracle points, so their relation to the arc is known in advance:
        cases = []
        # (1) segment from inside the circle to well outside, through the arc midpoint (one hit)
        mid = op.point_at(length / 2)
        rad = O.unit(O.az_of(mid - rp))
        cases.append((rp + 0.5 * radius * rad, rp + 1.5 * radius * rad, 1))
        # (2) a full chord line extended both ways: hits arc at PC and PT (two hits)
        v = op.pt - op.pc
        cases.append((op.pc - 0.3 * v, op.pt + 0.3 * v, 2))
        # (3) a cross line near the middle (parallel to the chord, sagitta-deep): two hits well inside the arc
        pa, pb = op.point_at(0.25 * length), op.point_at(0.75 * length)
        w = pb - pa
        cases.append((pa - 0.5 * w, pb + 0.5 * w, 2))
        # (4) same line but the segment stops before reaching the far intersection (one hit)
        cases.append((pa - 0.5 * w, (pa + pb) / 2, 1))
        # (5) segment that misses the circle entirely
        cases.append(
            (rp + 3.0 * radius * rad + 1j * 0, rp + 3.0 * radius * rad + 50.0 * O.unit(O.az_of(rad) + 90.0), 0)
        )
        # (6) crosses the circle where the arc is NOT (opposite side of the RP)
        cases.append((rp - 0.5 * radius * rad, rp - 1.5 * radius * rad, 0))
        for a, b, expect_n in cases:
            for p0, p1 in ((a, b), (b, a)):
                got = cc.line_arc_intersections(O.as_pt(p0), O.as_pt(p1), pl)
                want = oracle_hits(O.as_pt(p0), O.as_pt(p1), pl)
                assert len(want) == expect_n, "oracle disagrees with the constructed case (test bug)"
                assert_same_hits(got, want, tol)
                # hits are ordered along the segment and carry t consistent with the point
                ts = [g["t"] for g in got]
                assert ts == sorted(ts)
                for g in got:
                    assert abs(O.z(g["point"]) - p0_plus(p0, p1, g["t"])) <= tol

    @pytest.mark.parametrize("direction", DIRECTIONS)
    def test_second_circle_crossing_beyond_the_pt_is_dropped(self, direction):
        """The line meets the CIRCLE twice but only once inside the arc span."""
        pl = PlacedCurve(Curve(300.0, 40.0, direction), PC0, 15.0)
        op = op_of(pl)
        sgn = 1 if direction == "CW" else -1
        p_in = op.point_at(0.2 * op.arc.length)
        q_out = op.rp + 300.0 * O.unit(O.az_of(op.pt - op.rp) + sgn * 20.0)  # circle point 20 deg past the PT
        v = q_out - p_in
        p0, p1 = O.as_pt(p_in - 0.1 * v), O.as_pt(q_out + 0.1 * v)
        got = cc.line_arc_intersections(p0, p1, pl)
        want = oracle_hits(p0, p1, pl)
        assert len(want) == 1
        assert_same_hits(got, want, 1e-6)
        assert got[0]["s"] == pytest.approx(0.2 * op.arc.length, abs=1e-6)

    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("overshoot", [-2.0, -0.05, 0.05, 2.0])
    def test_circle_points_just_past_either_end_of_the_arc_are_dropped(self, direction, overshoot):
        """A radial segment through the circle point `overshoot` ft of arc before the PC / after the PT is not on the arc."""
        pl = PlacedCurve(Curve(300.0, 40.0, direction), PC0, 15.0)
        op = op_of(pl)
        s_off = overshoot if overshoot < 0 else op.arc.length + overshoot
        p = op.point_at(s_off)
        d = O.unit(O.az_of(p - op.rp))
        got = cc.line_arc_intersections(O.as_pt(p - 20.0 * d), O.as_pt(p + 20.0 * d), pl)
        assert got == []
        assert oracle_hits(O.as_pt(p - 20.0 * d), O.as_pt(p + 20.0 * d), pl) == []
        # ... while a point 1 mm inside the arc IS found
        s_in = 0.001 if overshoot < 0 else op.arc.length - 0.001
        p_in = op.point_at(s_in)
        d_in = O.unit(O.az_of(p_in - op.rp))
        hit = cc.line_arc_intersections(O.as_pt(p_in - 20.0 * d_in), O.as_pt(p_in + 20.0 * d_in), pl)
        assert len(hit) == 1 and hit[0]["s"] == pytest.approx(s_in, abs=1e-6)

    @pytest.mark.parametrize("direction", DIRECTIONS)
    def test_tangent_touch_is_a_single_hit(self, direction):
        pl = PlacedCurve(Curve(269.96, 60.0, direction), PC0, 210.0)
        op = op_of(pl)
        s = 0.4 * op.arc.length
        p = op.point_at(s)
        tangent = O.unit(O.az_of(p - op.rp) + 90.0)
        got = cc.line_arc_intersections(O.as_pt(p - 40.0 * tangent), O.as_pt(p + 60.0 * tangent), pl)
        assert len(got) == 1
        assert near(got[0]["point"], p, 1e-6)
        assert got[0]["s"] == pytest.approx(s, abs=1e-6)

    def test_endpoints_on_the_arc_count_and_degenerate_segment_raises(self):
        pl = PlacedCurve(Curve(200.0, 30.0, "CW"), PC0, 0.0)
        op = op_of(pl)
        got = cc.line_arc_intersections(O.as_pt(op.pc), O.as_pt(op.pt), pl)  # the chord
        assert [round(g["s"], 6) for g in got] == pytest.approx([0.0, op.arc.length], abs=1e-6)
        with pytest.raises(ValueError):
            cc.line_arc_intersections(PC0, PC0, pl)

    def test_radial_segment_hits_at_the_right_arc_distance(self):
        """A segment along the radial through the point at s: the hit is at exactly s (oracle-walked point)."""
        pl = PlacedCurve(Curve(269.96, 36.0 + 20.0 / 60.0, "CCW"), PC0, 123.0)
        op = op_of(pl)
        for f in (0.05, 0.5, 0.95):
            s = f * op.arc.length
            p = op.point_at(s)
            d = O.unit(O.az_of(p - op.rp))
            got = cc.line_arc_intersections(O.as_pt(op.rp), O.as_pt(op.rp + 400.0 * d), pl)
            assert len(got) == 1
            assert got[0]["s"] == pytest.approx(s, abs=1e-6)
            assert near(got[0]["point"], p, 1e-6)


def p0_plus(p0: complex, p1: complex, t: float) -> complex:
    return p0 + t * (p1 - p0)
