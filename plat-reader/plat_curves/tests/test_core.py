"""plat_curves.core versus the independent brute-force oracle (plat_curves/tests/oracle.py).

The oracle walks arcs numerically and intersects tangent lines; it shares no formula or code with core.py.
"""

from __future__ import annotations

import dataclasses
import functools
import itertools
import math
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # `pytest` (not only `python -m pytest`) from any cwd
    sys.path.insert(0, str(_ROOT))

from plat_curves import core  # noqa: E402
from plat_curves.core import PLAT_TOL_FT, Curve, PlacedCurve  # noqa: E402
from plat_curves.tests import oracle as O  # noqa: E402,N812

# --------------------------------------------------------------------------- grids
RADII = [25.0, 50.0, 269.96, 894.08, 5000.0]
DELTAS = [0.001, 0.5, 5.0, 36.0 + 20.0 / 60.0, 90.0, 135.0, 179.0, 179.9]
DIRECTIONS = ["CW", "CCW"]
BACK_AZS = [0.0, 37.5, 100.0, 190.0, 271.3]  # one per azimuth quadrant, plus due north
PC0 = (12345.678, 23456.789)
FRACS = [0.0, 0.13, 0.5, 0.77, 1.0]

SCALAR_TOL = {"rel": 1e-9, "abs_": 1e-9}


def close(actual, expected, *, rel=1e-9, abs_=1e-9):
    assert actual == pytest.approx(expected, rel=rel, abs=abs_)


def pt_close(actual, expected: complex, scale: float, *, rel=1e-9, abs_=1e-8):
    """Points agree to `rel*scale + abs_` feet (scale = size of the figure, so far-off PIs stay meaningful)."""
    err = abs(O.z(actual) - expected)
    assert err <= rel * max(scale, 1.0) + abs_, f"{actual} vs {O.as_pt(expected)} (err {err:.3e}, scale {scale:.3e})"


def az_close(actual, expected, *, tol=1e-7):
    assert abs(O.ang_diff(actual, expected)) <= tol, f"az {actual} vs {expected}"


# =========================================================================== 1. helpers: dms / bearings / offset
class TestAngleHelpers:
    def test_dms_to_deg_matches_hand_arithmetic(self):
        close(core.dms_to_deg(36, 20, 0), 36 + 20 / 60, abs_=1e-12)
        close(core.dms_to_deg(57, 53, 59), O.dms_to_deg(57, 53, 59), abs_=1e-12)
        close(core.dms_to_deg(0, 0, 1), 1 / 3600, abs_=1e-15)
        close(core.dms_to_deg(12), 12.0, abs_=1e-15)
        close(core.dms_to_deg(89, 59, 59.999), 89 + 59 / 60 + 59.999 / 3600, abs_=1e-12)

    @pytest.mark.parametrize(
        ("deg", "text"),
        [
            (36 + 20 / 60, "36°20'00\""),
            (122.100277778, "122°06'01\""),
            (0.0, "0°00'00\""),
            (5 + 1 / 3600, "5°00'01\""),
            (89.999999, "90°00'00\""),  # rounding carries into degrees
            (12 + 59 / 60 + 59.7 / 3600, "13°00'00\""),  # carry through minutes
        ],
    )
    def test_deg_to_dms(self, deg, text):
        assert core.deg_to_dms(deg) == text

    def test_deg_to_dms_places(self):
        out = core.deg_to_dms(36 + 20 / 60 + 30.5 / 3600, places=1)
        assert out.startswith("36°20'")
        assert float(re.search(r"'([\d.]+)\"", out).group(1)) == pytest.approx(30.5, abs=1e-9)
        out2 = core.deg_to_dms(10.123456 / 3600 + 1, places=3)
        assert float(re.search(r"'([\d.]+)\"", out2).group(1)) == pytest.approx(10.123, abs=1e-9)

    @pytest.mark.parametrize(
        "text",
        [
            "S57°53'59\"E",
            "N 89°18'20\" E",
            "N45°00'00\"W",
            "S12°34'56\"W",
            "N0°00'01\"E",
            "S89°59'59\"W",
            "N 12° 30' 05\" W",
        ],
    )
    def test_bearing_to_az_matches_oracle(self, text):
        close(core.bearing_to_az(text), O.bearing_to_az(text), abs_=1e-9)

    def test_bearing_to_az_known_quadrants(self):
        close(core.bearing_to_az("N45°00'00\"E"), 45.0, abs_=1e-9)
        close(core.bearing_to_az("S45°00'00\"E"), 135.0, abs_=1e-9)
        close(core.bearing_to_az("S45°00'00\"W"), 225.0, abs_=1e-9)
        close(core.bearing_to_az("N45°00'00\"W"), 315.0, abs_=1e-9)
        close(core.bearing_to_az("S57°53'59\"E"), 180.0 - (57 + 53 / 60 + 59 / 3600), abs_=1e-9)

    @pytest.mark.parametrize("bad", ["", "X45°00'00\"E", "N95°00'00\"E", "N45°60'00\"E", "hello"])
    def test_bearing_to_az_rejects_garbage(self, bad):
        with pytest.raises(ValueError):
            core.bearing_to_az(bad)

    @pytest.mark.parametrize(
        "a",
        [
            0.0,
            0.0001,
            12.3456,
            45.0,
            89.99,
            90.5,
            122.100278,
            179.999,
            180.0,
            180.001,
            200.0,
            269.9,
            271.3,
            315.0,
            359.9999,
        ],
    )
    def test_az_to_bearing_round_trips_within_half_second(self, a):
        text = core.az_to_bearing(a)
        assert re.fullmatch(r"[NS]\d{1,2}°\d{2}'\d{2}\"[EW]", O.norm_bearing(text)), text
        assert abs(O.ang_diff(O.bearing_to_az(text), a)) <= 0.5 / 3600 + 1e-9
        assert abs(O.ang_diff(core.bearing_to_az(text), a)) <= 0.5 / 3600 + 1e-9

    @pytest.mark.parametrize("a", [0.0, 90.0, 180.0, 270.0])
    def test_cardinal_azimuths_round_trip(self, a):
        text = core.az_to_bearing(a)
        assert abs(O.ang_diff(core.bearing_to_az(text), a)) <= 1e-9, text
        assert abs(O.ang_diff(O.bearing_to_az(text), a)) <= 1e-9, text

    def test_az_to_bearing_exact_text(self):
        assert O.norm_bearing(core.az_to_bearing(180.0 - (57 + 53 / 60 + 59 / 3600))) == "S57°53'59\"E"
        assert O.norm_bearing(core.az_to_bearing(315.0)) == "N45°00'00\"W"
        assert O.norm_bearing(core.az_to_bearing(225.5)) == "S45°30'00\"W"

    def test_az_to_bearing_wraps_out_of_range(self):
        assert core.az_to_bearing(450.0) == core.az_to_bearing(90.0)
        assert core.az_to_bearing(-45.0) == core.az_to_bearing(315.0)


class TestPointHelpers:
    @pytest.mark.parametrize("a", [0.0, 30.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0, 359.9, 400.0, -30.0])
    @pytest.mark.parametrize("d", [0.0, 1.0, 100.5, 5000.0])
    def test_offset_matches_complex_rotation(self, a, d):
        start = (1000.0, -2000.0)
        expected = O.z(start) + d * O.unit(a)
        got = core.offset(start, a, d)
        assert got == pytest.approx(O.as_pt(expected), abs=1e-9)

    def test_offset_cardinals(self):
        assert core.offset((0, 0), 0, 10) == pytest.approx((10, 0), abs=1e-12)
        assert core.offset((0, 0), 90, 10) == pytest.approx((0, 10), abs=1e-12)
        assert core.offset((0, 0), 180, 10) == pytest.approx((-10, 0), abs=1e-12)
        assert core.offset((0, 0), 270, 10) == pytest.approx((0, -10), abs=1e-12)

    @pytest.mark.parametrize("a", [0.0, 10.0, 90.0, 135.0, 180.0, 250.0, 359.0])
    def test_dist_and_az_invert_offset(self, a):
        p = (500.0, 700.0)
        q = core.offset(p, a, 321.25)
        close(core.dist(p, q), 321.25, abs_=1e-9)
        az_close(core.az(p, q), a % 360.0, tol=1e-9)
        close(core.dist(q, p), 321.25, abs_=1e-9)
        az_close(core.az(q, p), (a + 180.0) % 360.0, tol=1e-9)

    def test_az_range_and_degenerate(self):
        for a in (0.0, 45.0, 359.999):
            assert 0.0 <= core.az((0, 0), core.offset((0, 0), a, 5)) < 360.0
        with pytest.raises(ValueError):
            core.az((1.0, 1.0), (1.0, 1.0))


# =========================================================================== 2. Curve scalars vs oracle
class TestCurveScalars:
    @pytest.mark.parametrize("r", RADII)
    @pytest.mark.parametrize("delta", DELTAS)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    def test_all_scalars_match_oracle(self, r, delta, direction):
        c = Curve(r, delta, direction)
        o = O.arc(r, delta, direction)
        close(c.arc_length, o.length, **SCALAR_TOL)
        close(c.tangent, o.tangent, **SCALAR_TOL)
        close(c.tangent, o.tangent_fwd, **SCALAR_TOL)  # oracle sanity: symmetric tangents
        close(c.chord, o.chord, **SCALAR_TOL)
        close(c.middle_ordinate, o.middle_ordinate, **SCALAR_TOL)
        close(c.external, o.external, **SCALAR_TOL)
        close(c.sector_area, o.sector_area, **SCALAR_TOL)
        close(c.segment_area, o.segment_area, **SCALAR_TOL)
        close(c.fillet_area, o.fillet_area, **SCALAR_TOL)

    @pytest.mark.parametrize("r", RADII)
    def test_degree_of_curve_arc_definition_measured(self, r):
        c = Curve(r, 30.0)
        close(c.degree_arc, O.degree_arc(r), rel=1e-7, abs_=1e-6)
        close(c.degree_arc, 5729.5779513 / r, rel=1e-9)  # SPEC constant

    @pytest.mark.parametrize("r", [60.0, 269.96, 894.08, 5000.0])
    def test_degree_of_curve_chord_definition_measured(self, r):
        close(Curve(r, 30.0).degree_chord, O.degree_chord(r), rel=1e-9, abs_=1e-8)

    def test_degree_chord_at_exactly_50ft_is_a_half_turn(self):
        # a 100 ft chord is a diameter when R = 50 (oracle bisection is flat there, so this one is closed-form)
        close(Curve(50.0, 30.0).degree_chord, 180.0, abs_=1e-9)

    def test_degree_chord_below_50ft_is_not_a_number_or_error(self):
        # sin(Dc/2) = 50/R has no solution for R < 50: the module documents nan; accept nan or ValueError, never a number
        try:
            v = Curve(25.0, 30.0).degree_chord
        except ValueError:
            return
        assert math.isnan(v)

    def test_oracle_walks_the_spec_check(self):
        """SPEC: CW, back_az=0 => RP due east of PC, RP->PC = 270 deg, sweeping toward 360."""
        p = O.placed(100.0, 30.0, "CW", (0.0, 0.0), 0.0)
        pt_close(O.as_pt(p.rp), 0 + 100j, 100.0)
        az_close(O.az_of(p.pc - p.rp), 270.0)
        az_close(O.az_of(p.point_at(10.0) - p.rp), 270.0 + math.degrees(10.0 / 100.0))

    def test_oracle_matches_closed_forms_independently(self):
        """The oracle itself agrees with textbook closed forms (guards against an oracle bug hiding a module bug)."""
        r, d = 269.96, 36.0 + 20.0 / 60.0
        o = O.arc(r, d, "CW")
        h = math.radians(d) / 2
        close(o.tangent, r * math.tan(h), rel=1e-12)
        close(o.length, r * 2 * h, rel=1e-12)
        close(o.chord, 2 * r * math.sin(h), rel=1e-12)
        close(o.middle_ordinate, r * (1 - math.cos(h)), rel=1e-9)
        close(o.external, r * (1 / math.cos(h) - 1), rel=1e-9)
        close(o.sector_area, r * r * h, rel=1e-11)
        close(o.segment_area, r * r * (2 * h - math.sin(2 * h)) / 2, rel=1e-10)

    def test_curve_is_frozen_and_direction_normalised(self):
        c = Curve(100.0, 30.0)
        assert c.direction == "CW"
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.radius = 5.0  # type: ignore[misc]
        assert Curve(100.0, 30.0, "ccw").direction == "CCW"

    def test_curve_rejects_bad_direction(self):
        with pytest.raises(ValueError):
            Curve(100.0, 30.0, "LEFT")


# =========================================================================== 3. PlacedCurve vs oracle
class TestPlacedCurveVsOracle:
    @pytest.mark.parametrize("r", RADII)
    @pytest.mark.parametrize("delta", DELTAS)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", BACK_AZS)
    def test_key_points_and_azimuths(self, r, delta, direction, back_az):
        pl = PlacedCurve(Curve(r, delta, direction), PC0, back_az)
        op = O.placed(r, delta, direction, PC0, back_az)
        scale = max(r, op.arc.tangent)
        pt_close(pl.pc, op.pc, r)
        pt_close(pl.rp, op.rp, r)
        pt_close(pl.pi, op.pi, scale, rel=1e-11)
        pt_close(pl.pt, op.pt, r)
        az_close(pl.forward_az, op.forward_az)
        az_close(pl.chord_az, op.chord_az, tol=1e-6 if delta < 0.01 else 1e-8)
        # RP is on the correct side: RP is 90 deg right (CW) / left (CCW) of the back tangent
        sgn = 1 if direction == "CW" else -1
        az_close(O.az_of(op.rp - op.pc), back_az + sgn * 90.0)
        # every stated point lies on the oracle circle
        assert abs(abs(O.z(pl.pt) - O.z(pl.rp)) - r) <= 1e-9 * r + 1e-8
        assert abs(abs(O.z(pl.pc) - O.z(pl.rp)) - r) <= 1e-9 * r + 1e-9

    @pytest.mark.parametrize("r", RADII)
    @pytest.mark.parametrize("delta", DELTAS)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 100.0, 271.3])
    def test_bearing_strings_within_rounding(self, r, delta, direction, back_az):
        pl = PlacedCurve(Curve(r, delta, direction), PC0, back_az)
        op = O.placed(r, delta, direction, PC0, back_az)
        half_sec = 0.5 / 3600 + 1e-9
        for text, want in (
            (pl.back_bearing, back_az),
            (pl.forward_bearing, op.forward_az),
            (pl.chord_bearing, op.chord_az),
        ):
            assert abs(O.ang_diff(O.bearing_to_az(text), want)) <= half_sec, (text, want)

    @pytest.mark.parametrize("r", RADII)
    @pytest.mark.parametrize("delta", DELTAS)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 37.5, 190.0, 271.3])
    def test_point_at_azimuth_at_radial_az_at(self, r, delta, direction, back_az):
        pl = PlacedCurve(Curve(r, delta, direction), PC0, back_az)
        op = O.placed(r, delta, direction, PC0, back_az)
        length = op.arc.length
        tol = 5e-9 * r + 1e-9
        sgn = 1 if direction == "CW" else -1
        for f in FRACS:
            s = f * length
            want = op.point_at(s)
            got = pl.point_at(s)
            assert abs(O.z(got) - want) <= tol, (f, got, O.as_pt(want))
            # outward radial from the RP; the oracle RP is an independent construction
            az_close(pl.radial_az_at(s), O.az_of(want - op.rp), tol=1e-7 if delta > 0.01 else 1e-6)
            # radial and travel direction are 90 deg apart, sense set by direction
            az_close(pl.azimuth_at(s), pl.radial_az_at(s) + sgn * 90.0, tol=1e-9)
            if 0.0 < f < 1.0:
                az_close(pl.azimuth_at(s), op.back_az + O.az_of(_local_dir(op, s)), tol=1e-7 if delta > 0.01 else 1e-5)
        pt_close(pl.point_at(0.0), op.pc, r)
        pt_close(pl.point_at(length), op.pt, r)
        az_close(pl.azimuth_at(0.0), back_az, tol=1e-9)
        az_close(pl.azimuth_at(length), op.forward_az, tol=1e-8)

    @pytest.mark.parametrize("r", [25.0, 269.96, 5000.0])
    @pytest.mark.parametrize("delta", [0.5, 36.0 + 20.0 / 60.0, 179.9])
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("n", [1, 7, 24])
    def test_arc_points(self, r, delta, direction, n):
        pl = PlacedCurve(Curve(r, delta, direction), PC0, 123.0)
        op = O.placed(r, delta, direction, PC0, 123.0)
        pts = pl.arc_points(n)
        assert len(pts) == n + 1
        pt_close(pts[0], op.pc, r)
        pt_close(pts[-1], op.pt, r)
        tol = 5e-9 * r + 1e-9
        for k, p in enumerate(pts):
            assert abs(O.z(p) - op.point_at(op.arc.length * k / n)) <= tol
            assert abs(abs(O.z(p) - op.rp) - r) <= tol  # every vertex is on the circle
        # equal arc spacing => equal chords between consecutive vertices
        chords = [abs(O.z(pts[k + 1]) - O.z(pts[k])) for k in range(n)]
        assert max(chords) - min(chords) <= 1e-9 * max(chords) + 1e-9

    def test_arc_points_default_is_24_segments_and_validates(self):
        pl = PlacedCurve(Curve(100.0, 45.0), (0.0, 0.0), 0.0)
        assert len(pl.arc_points()) == 25
        with pytest.raises(ValueError):
            pl.arc_points(0)

    def test_placed_curve_is_frozen(self):
        pl = PlacedCurve(Curve(100.0, 45.0), (0.0, 0.0), 10.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            pl.back_az = 3.0  # type: ignore[misc]


def _local_dir(op: O.OraclePlaced, s: float) -> complex:
    """Oracle tangent direction at arc distance s in the local (back_az = 0) frame."""
    eps = min(0.01, 0.01 * op.arc.length)
    return O.walk_local_point(op.arc.radius, s + eps, op.arc.direction) - O.walk_local_point(
        op.arc.radius, s - eps, op.arc.direction
    )


# =========================================================================== 4. constructors
FACTORY_R = [25.0, 269.96, 5000.0]
FACTORY_DELTAS = [0.001, 0.5, 36.0 + 20.0 / 60.0, 135.0, 179.0]


class TestFactories:
    @pytest.mark.parametrize("r", FACTORY_R)
    @pytest.mark.parametrize("delta", FACTORY_DELTAS)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 100.0, 190.0, 271.3])
    def test_from_pi_recovers_curve(self, r, delta, direction, back_az):
        op = O.placed(r, delta, direction, PC0, back_az)
        pl = PlacedCurve.from_pi(O.as_pt(op.pi), back_az, op.forward_az, r)
        scale = max(r, op.arc.tangent)
        assert pl.direction == direction
        close(pl.curve.delta_deg, delta, rel=1e-9, abs_=1e-9)
        close(pl.curve.radius, r, rel=1e-12)
        pt_close(pl.pc, op.pc, scale, rel=1e-10)
        pt_close(pl.pt, op.pt, scale, rel=1e-10)
        pt_close(pl.rp, op.rp, scale, rel=1e-10)
        az_close(pl.back_az, back_az, tol=1e-9)

    def test_from_pi_rejects_degenerate_tangents(self):
        with pytest.raises(ValueError):
            PlacedCurve.from_pi((0.0, 0.0), 45.0, 45.0, 100.0)  # collinear: no curve
        with pytest.raises(ValueError):
            PlacedCurve.from_pi((0.0, 0.0), 45.0, 225.0, 100.0)  # reversal: Delta = 180
        with pytest.raises(ValueError):
            PlacedCurve.from_pi((0.0, 0.0), 45.0, 90.0, -5.0)
        with pytest.raises(ValueError):
            PlacedCurve.from_pi((0.0, 0.0), 45.0, 90.0, 0.0)

    def test_from_pi_wraps_across_north(self):
        """350 -> 20 is a 30 deg RIGHT turn (CW); 20 -> 350 is a 30 deg LEFT turn (CCW)."""
        cw = PlacedCurve.from_pi((0.0, 0.0), 350.0, 20.0, 100.0)
        ccw = PlacedCurve.from_pi((0.0, 0.0), 20.0, 350.0, 100.0)
        assert (cw.direction, ccw.direction) == ("CW", "CCW")
        close(cw.curve.delta_deg, 30.0, abs_=1e-9)
        close(ccw.curve.delta_deg, 30.0, abs_=1e-9)
        o = O.arc(100.0, 30.0, "CW")
        close(cw.curve.tangent, o.tangent, **SCALAR_TOL)

    @pytest.mark.parametrize("r", FACTORY_R)
    @pytest.mark.parametrize("delta", FACTORY_DELTAS)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 37.5, 190.0, 271.3])
    def test_from_pc_pt_recovers_curve(self, r, delta, direction, back_az):
        op = O.placed(r, delta, direction, PC0, back_az)
        scale = max(r, op.arc.tangent)
        pl = PlacedCurve.from_pc_pt(PC0, O.as_pt(op.pt), r, direction)
        close(pl.curve.delta_deg, delta, rel=1e-8, abs_=1e-9)
        az_close(pl.back_az, back_az, tol=1e-6 if delta < 0.01 else 1e-7)
        pt_close(pl.pt, op.pt, scale, rel=1e-9)
        # tiny-delta chords (4e-4 ft) are ill-conditioned: 1e-12 ft coordinate noise -> ~1e-8 rad of back_az
        pt_close(pl.rp, op.rp, scale, rel=1e-9, abs_=1e-6 if delta < 0.01 else 1e-8)
        # explicit back_az is honoured and cross-checked
        pl2 = PlacedCurve.from_pc_pt(PC0, O.as_pt(op.pt), r, direction, back_az=back_az)
        pt_close(pl2.pt, op.pt, scale, rel=1e-9)

    def test_from_pc_pt_rejects_impossible_geometry(self):
        with pytest.raises(ValueError):
            PlacedCurve.from_pc_pt((0.0, 0.0), (0.0, 200.0), 100.0, "CW")  # chord == diameter: Delta = 180
        with pytest.raises(ValueError):
            PlacedCurve.from_pc_pt((0.0, 0.0), (0.0, 250.0), 100.0, "CW")  # chord > diameter
        with pytest.raises(ValueError):
            PlacedCurve.from_pc_pt((0.0, 0.0), (0.0, 0.0), 100.0, "CW")  # coincident
        with pytest.raises(ValueError):
            PlacedCurve.from_pc_pt((0.0, 0.0), (0.0, 50.0), 100.0, "CW", back_az=200.0)  # wrong tangent for that chord

    @pytest.mark.parametrize("r", FACTORY_R)
    @pytest.mark.parametrize("delta", FACTORY_DELTAS)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 100.0, 271.3])
    def test_from_rp_recovers_curve(self, r, delta, direction, back_az):
        op = O.placed(r, delta, direction, PC0, back_az)
        start_az = O.az_of(op.pc - op.rp)  # oracle: azimuth RP -> PC
        pl = PlacedCurve.from_rp(O.as_pt(op.rp), r, start_az, delta, direction)
        scale = max(r, op.arc.tangent)
        az_close(pl.back_az, back_az, tol=1e-7)
        pt_close(pl.pc, op.pc, r, rel=1e-9)
        pt_close(pl.pt, op.pt, scale, rel=1e-9)
        pt_close(pl.rp, op.rp, r, rel=1e-9)

    @pytest.mark.parametrize("r", FACTORY_R)
    @pytest.mark.parametrize("delta", FACTORY_DELTAS)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    @pytest.mark.parametrize("back_az", [0.0, 100.0, 190.0, 271.3])
    def test_from_pt_places_backwards(self, r, delta, direction, back_az):
        op = O.placed(r, delta, direction, PC0, back_az)
        pl = PlacedCurve.from_pt(O.as_pt(op.pt), op.forward_az, Curve(r, delta, direction))
        scale = max(r, op.arc.tangent)
        az_close(pl.back_az, back_az, tol=1e-9)
        pt_close(pl.pc, op.pc, scale, rel=1e-10)
        pt_close(pl.pt, op.pt, scale, rel=1e-10)
        pt_close(pl.rp, op.rp, scale, rel=1e-10)


# =========================================================================== 5. station table
class TestStationTable:
    def test_rows_and_deflections_against_oracle(self):
        r, delta, back_az = 894.08, 36.0 + 20.0 / 60.0, 33.0
        pl = PlacedCurve(Curve(r, delta, "CW"), PC0, back_az)
        op = O.placed(r, delta, "CW", PC0, back_az)
        rows = pl.station_table(pc_station=1234.56, spacing=100.0)
        length = op.arc.length
        assert rows[0]["label"] == "PC" and rows[-1]["label"] == "PT"
        close(rows[0]["station"], 1234.56, abs_=1e-9)
        close(rows[-1]["station"], 1234.56 + length, **SCALAR_TOL)
        # full stations between: 1300, 1400, ... strictly inside (1234.56, 1234.56+L)
        want = [k * 100.0 for k in range(13, int((1234.56 + length) // 100) + 1) if k * 100.0 < 1234.56 + length]
        got = [row["station"] for row in rows[1:-1]]
        assert got == pytest.approx(want, abs=1e-6)
        for row in rows:
            s = row["station"] - 1234.56
            close(row["s"], s, abs_=1e-6)
            want_pt = op.point_at(row["s"])
            assert abs(O.z(row["point"]) - want_pt) <= 5e-9 * r + 1e-9
            # deflection from the tangent at the PC to the chord PC->point: measured, not formula
            if row["s"] > 0.0:
                chord_az = O.az_of(want_pt - op.pc)
                measured = abs(O.ang_diff(chord_az, back_az))
                close(row["deflection_deg"], measured, rel=1e-9, abs_=1e-8)
                close(row["chord"], abs(want_pt - op.pc), rel=1e-9, abs_=1e-8)
            else:
                close(row["deflection_deg"], 0.0, abs_=1e-12)
                close(row["chord"], 0.0, abs_=1e-9)
        # final deflection is half the central angle
        close(rows[-1]["deflection_deg"], delta / 2.0, abs_=1e-9)
        close(rows[-1]["chord"], op.arc.chord, **SCALAR_TOL)

    def test_station_landing_exactly_on_pc_and_pt(self):
        """PC on a full station is listed once (as PC); a PT landing on a full station is listed once (as PT)."""
        r = 500.0
        delta = math.degrees(300.0 / r)  # L = 300.00 ft (definition of the radian)
        pl = PlacedCurve(Curve(r, delta, "CW"), (0.0, 0.0), 0.0)
        assert O.arc(r, delta, "CW").length == pytest.approx(300.0, abs=1e-9)
        rows = pl.station_table(pc_station=100.0, spacing=100.0)
        assert [(row["label"], round(row["station"], 6)) for row in rows] == [
            ("PC", 100.0), ("STA", 200.0), ("STA", 300.0), ("PT", 400.0),
        ]  # fmt: skip

    def test_station_text_and_short_curve(self):
        pl = PlacedCurve(Curve(100.0, 30.0, "CCW"), (0.0, 0.0), 0.0)  # L = 52.36
        rows = pl.station_table(pc_station=0.0)
        assert [r_["label"] for r_ in rows] == ["PC", "PT"]  # shorter than one full station
        assert rows[0]["station_text"] == "0+00.00"
        assert rows[1]["station_text"] == "0+52.36"

    def test_station_table_default_spacing(self):
        pl = PlacedCurve(Curve(500.0, 60.0), (0.0, 0.0), 0.0)  # L = 523.6
        rows = pl.station_table()
        assert [round(row["station"]) for row in rows[1:-1]] == [100, 200, 300, 400, 500]
        with pytest.raises(ValueError):
            pl.station_table(spacing=0.0)


# =========================================================================== 6. Curve.from_params: all 28 pairs
PARAMS = ["radius", "delta_deg", "arc_length", "chord", "tangent", "middle_ordinate", "external", "degree_arc"]
PAIRS = list(itertools.combinations(PARAMS, 2))
REF_CURVES = [(269.96, 36.0 + 20.0 / 60.0), (25.0, 90.0), (5000.0, 12.5), (894.08, 6.41), (100.0, 150.0)]


@functools.cache
def _oracle_values(r: float, delta: float) -> tuple:
    o = O.arc(r, delta, "CW")
    return (r, delta, o.length, o.chord, o.tangent, o.middle_ordinate, o.external, O.degree_arc(r))


def oracle_values(r: float, delta: float) -> dict[str, float]:
    return dict(zip(PARAMS, _oracle_values(r, delta), strict=True))


class TestFromParams:
    def test_there_are_28_pairs(self):
        assert len(PAIRS) == 28

    @pytest.mark.parametrize(("r", "delta"), REF_CURVES)
    @pytest.mark.parametrize(("k1", "k2"), PAIRS)
    @pytest.mark.parametrize("direction", DIRECTIONS)
    def test_every_pair_reproduces_the_curve(self, r, delta, k1, k2, direction):
        vals = oracle_values(r, delta)
        if {k1, k2} == {"radius", "degree_arc"}:
            with pytest.raises(ValueError):  # Da *is* R: two names, one piece of information
                Curve.from_params(direction, **{k1: vals[k1], k2: vals[k2]})
            return
        if {k1, k2} == {"tangent", "middle_ordinate"}:
            # T/M = tan h / (1 - cos h) is genuinely two-valued (minimum near Delta = 103.6 deg); the oracle confirms
            sols = Curve.solutions(direction, tangent=vals["tangent"], middle_ordinate=vals["middle_ordinate"])
            assert any(abs(c.radius - r) < 1e-6 * r and abs(c.delta_deg - delta) < 1e-6 for c in sols), sols
            for c in sols:
                o = O.arc(c.radius, c.delta_deg, "CW")
                close(o.tangent, vals["tangent"], rel=1e-7, abs_=1e-7)
                close(o.middle_ordinate, vals["middle_ordinate"], rel=1e-7, abs_=1e-7)
            got = Curve.from_params(direction, tangent=vals["tangent"], middle_ordinate=vals["middle_ordinate"])
            assert got.delta_deg == min(c.delta_deg for c in sols)
            if delta < 100.0:
                close(got.radius, r, rel=1e-7)
                close(got.delta_deg, delta, rel=1e-7)
            return
        c = Curve.from_params(direction, **{k1: vals[k1], k2: vals[k2]})
        close(c.radius, r, rel=1e-7)
        close(c.delta_deg, delta, rel=1e-7, abs_=1e-8)
        assert c.direction == direction

    @pytest.mark.parametrize(("r", "delta"), REF_CURVES)
    def test_full_parameter_set_cross_checks(self, r, delta):
        vals = oracle_values(r, delta)
        c = Curve.from_params("CW", **vals)
        close(c.radius, r, rel=1e-7)
        close(c.delta_deg, delta, rel=1e-7, abs_=1e-8)

    def test_plat_rounded_values_are_consistent(self):
        """Values as printed on the plat (2-decimal ft, whole seconds) must not trip the cross-check."""
        c = Curve.from_params(
            "CW",
            radius=269.96,
            delta_deg=core.dms_to_deg(36, 20, 0),
            tangent=88.59,
            arc_length=171.19,
            chord=168.34,
            middle_ordinate=13.46,
            external=14.16,
        )
        close(c.radius, 269.96, rel=1e-12)

    @pytest.mark.parametrize("bad", ["tangent", "arc_length", "chord", "middle_ordinate", "external"])
    @pytest.mark.parametrize("shift", [0.5, -0.5, 3.0])
    def test_inconsistent_extra_raises(self, bad, shift):
        vals = oracle_values(269.96, 36.0 + 20.0 / 60.0)
        kw = {"radius": vals["radius"], "delta_deg": vals["delta_deg"], bad: vals[bad] + shift}
        with pytest.raises(ValueError):
            Curve.from_params("CW", **kw)

    def test_inconsistent_extra_within_plat_tolerance_is_accepted(self):
        vals = oracle_values(269.96, 36.0 + 20.0 / 60.0)
        for name in ("tangent", "arc_length", "chord"):
            for shift in (0.005, -0.005, 0.015):
                assert shift < PLAT_TOL_FT
                Curve.from_params(
                    "CW", radius=vals["radius"], delta_deg=vals["delta_deg"], **{name: vals[name] + shift}
                )

    def test_inconsistent_delta_extra_raises(self):
        vals = oracle_values(269.96, 36.0 + 20.0 / 60.0)
        with pytest.raises(ValueError):
            Curve.from_params(
                "CW", radius=269.96, tangent=vals["tangent"], delta_deg=vals["delta_deg"] + 0.05
            )  # 0.24 ft
        with pytest.raises(ValueError):
            Curve.from_params("CW", radius=269.96, tangent=vals["tangent"], degree_arc=O.degree_arc(300.0))

    def test_tolerance_argument_is_honoured(self):
        vals = oracle_values(269.96, 36.0 + 20.0 / 60.0)
        kw = {"radius": 269.96, "delta_deg": vals["delta_deg"], "tangent": vals["tangent"] + 0.1}
        with pytest.raises(ValueError):
            Curve.from_params("CW", **kw)
        Curve.from_params("CW", tol=0.5, **kw)

    def test_none_values_are_ignored(self):
        vals = oracle_values(269.96, 36.0 + 20.0 / 60.0)
        c = Curve.from_params("CCW", radius=269.96, delta_deg=None, tangent=vals["tangent"], chord=None)
        close(c.delta_deg, 36.0 + 20.0 / 60.0, rel=1e-9)
        assert c.direction == "CCW"

    @pytest.mark.parametrize("kw", [{}, {"radius": 100.0}, {"tangent": 50.0}, {"delta_deg": 30.0}, {"degree_arc": 5.0}])
    def test_underdetermined_raises(self, kw):
        with pytest.raises(ValueError):
            Curve.from_params("CW", **kw)

    def test_unknown_parameter_name_raises(self):
        with pytest.raises((TypeError, ValueError)):
            Curve.from_params("CW", radius=100.0, delta_deg=30.0, sagitta=2.0)

    def test_degree_arc_pair_uses_measured_definition(self):
        """(Da, Delta): the oracle-measured degree of curve gives back R."""
        c = Curve.from_params("CW", degree_arc=O.degree_arc(400.0), delta_deg=25.0)
        close(c.radius, 400.0, rel=1e-8)


# =========================================================================== 7. validation
class TestValidation:
    @pytest.mark.parametrize("delta", [0.0, -1e-9, -5.0, -180.0, 180.0, 180.0000001, 200.0, 360.0, math.inf, math.nan])
    def test_curve_rejects_bad_delta(self, delta):
        with pytest.raises(ValueError):
            Curve(100.0, delta)

    @pytest.mark.parametrize("radius", [0.0, -1e-9, -25.0, math.inf, math.nan])
    def test_curve_rejects_bad_radius(self, radius):
        with pytest.raises(ValueError):
            Curve(radius, 30.0)

    @pytest.mark.parametrize("delta", [0.0, -5.0, 180.0, 181.0, 359.0])
    def test_from_params_rejects_bad_delta(self, delta):
        with pytest.raises(ValueError):
            Curve.from_params("CW", radius=100.0, delta_deg=delta)

    @pytest.mark.parametrize("radius", [0.0, -100.0])
    def test_from_params_rejects_bad_radius(self, radius):
        with pytest.raises(ValueError):
            Curve.from_params("CW", radius=radius, delta_deg=30.0)

    @pytest.mark.parametrize(
        "kw",
        [
            {"radius": 100.0, "chord": 200.0},  # chord = diameter => Delta = 180
            {"radius": 100.0, "chord": 250.0},
            {"radius": 100.0, "arc_length": 314.2},  # arc > half circle
            {"radius": 100.0, "middle_ordinate": 100.0},
            {"radius": 100.0, "tangent": -5.0},
            {"arc_length": 100.0, "chord": 101.0},  # chord can never exceed the arc
            {"middle_ordinate": 10.0, "external": 5.0},  # M < E always
            {"chord": 50.0, "tangent": 20.0},  # T >= C/2 always
        ],
    )
    def test_unrealisable_pairs_rejected(self, kw):
        with pytest.raises(ValueError):
            Curve.from_params("CW", **kw)

    def test_extremes_that_are_legal(self):
        Curve(1e-3, 1e-6)
        Curve(1e6, 179.9999999)
        c = Curve.from_params("CW", radius=100.0, chord=199.99)
        assert 0.0 < c.delta_deg < 180.0


# =========================================================================== 8. plat-real fixtures
class TestPlatFixtures:
    DELTA = core.dms_to_deg(36, 20, 0)

    @pytest.mark.parametrize(
        ("radius", "tangent", "tol"),
        [(269.96, 88.59, 0.01), (327.01, 107.31, 0.01), (459.36, 150.73, 0.01)],
    )
    def test_delta_36_20_tangents(self, radius, tangent, tol):
        c = Curve(radius, self.DELTA)
        o = O.arc(radius, self.DELTA, "CW")
        assert c.tangent == pytest.approx(tangent, abs=tol)
        assert o.tangent == pytest.approx(tangent, abs=tol)  # oracle agrees with the plat
        assert c.tangent == pytest.approx(o.tangent, rel=1e-9)

    def test_r269_96_length(self):
        c = Curve(269.96, self.DELTA)
        assert c.tangent == pytest.approx(88.59, abs=0.01)
        assert c.arc_length == pytest.approx(171.19, abs=0.01)
        assert O.arc(269.96, self.DELTA, "CCW").length == pytest.approx(171.19, abs=0.01)

    @pytest.mark.parametrize("radius", [269.96, 327.01, 459.36])
    def test_plat_values_reproduce_from_any_two(self, radius):
        o = O.arc(radius, self.DELTA, "CW")
        for a, b in itertools.combinations(("tangent", "arc_length", "chord", "middle_ordinate", "external"), 2):
            if {a, b} == {"tangent", "middle_ordinate"}:
                continue  # two-valued pair, covered elsewhere
            c = Curve.from_params(
                "CW",
                **{
                    a: getattr(o, "length" if a == "arc_length" else a),
                    b: getattr(o, "length" if b == "arc_length" else b),
                },
            )
            close(c.radius, radius, rel=1e-7)
            close(c.delta_deg, self.DELTA, rel=1e-7)

    def test_r894_08_chord_99_98_legal_description(self):
        """Legal description: curve left, R=894.08, chord bearing S57°53'59"E, chord 99.98 (no arc length is printed).

        NOTE: 100.16 ft is NOT an arc length. It is course c21 (S54°41'40"E 100.16'), the tangent run BEFORE this
        curve. The 100.16 arc below is therefore a deliberately planted inconsistency, used only to check that
        Curve.from_params rejects an over-determined triple that disagrees beyond PLAT_TOL_FT.

        Plat-derived check (independent of R): the chord leaves the S54°41'40"E tangent at Delta/2, so
        Delta = 2*(57°53'59" - 54°41'40") = 6°24'38", which matches R + chord (6°24'37.x") to about a second.
        R + chord give L = 100.032 ft.
        """
        r = 894.08
        delta_c = O.delta_from_radius_and_chord(r, 99.98)
        delta_l = O.delta_from_radius_and_arc(r, 100.16)
        delta_bearings = 2.0 * (core.bearing_to_az("S54°41'40\"E") - core.bearing_to_az("S57°53'59\"E"))
        assert delta_bearings == pytest.approx(O.dms_to_deg(6, 24, 38), abs=1e-6)
        assert delta_bearings == pytest.approx(delta_c, abs=2.0 / 3600)
        assert O.dms_to_deg(6, 24, 37) == pytest.approx(delta_c, abs=0.5 / 3600)  # 6°24'37.5"
        assert delta_c == pytest.approx(6.410411735, abs=1e-6)
        assert delta_l == pytest.approx(6.418603789, abs=1e-6)
        # module agrees with the oracle on the chord-derived curve
        c = Curve.from_params("CW", radius=r, chord=99.98)
        close(c.delta_deg, delta_c, rel=1e-7, abs_=1e-8)
        assert c.arc_length == pytest.approx(100.032, abs=0.002)
        assert core.deg_to_dms(c.delta_deg) == "6°24'37\""
        # ... and a planted arc of 100.16 is inconsistent with R + chord (module and oracle both say so)
        assert abs(c.arc_length - 100.16) > 0.10 > PLAT_TOL_FT
        with pytest.raises(ValueError):
            Curve.from_params("CW", radius=r, chord=99.98, arc_length=100.16)
        with pytest.raises(ValueError):
            Curve.from_params("CW", radius=r, arc_length=100.16, chord=99.98)
        # the radius that WOULD reconcile the planted L=100.16 with C=99.98 (oracle bisection) is nowhere near 894.08
        r_implied = O.solve_bisect(
            lambda rr: O.chord_walk(rr, math.degrees(100.16 / rr)) - 99.98, 300.0, 700.0, iters=60
        )
        assert r_implied == pytest.approx(482.0, abs=2.0)
        c2 = Curve.from_params("CW", arc_length=100.16, chord=99.98)
        close(c2.radius, r_implied, rel=1e-6)

    @pytest.mark.parametrize("direction", DIRECTIONS)
    def test_r894_08_chord_bearing_places_curve(self, direction):
        """Chord S57°53'59"E, 99.98 ft: from_pc_pt recovers Delta and the chord bearing round-trips."""
        chord_az = core.bearing_to_az("S57°53'59\"E")
        pc = (5000.0, 5000.0)
        pt = core.offset(pc, chord_az, 99.98)
        pl = PlacedCurve.from_pc_pt(pc, pt, 894.08, direction)
        close(pl.curve.delta_deg, O.delta_from_radius_and_chord(894.08, 99.98), rel=1e-7, abs_=1e-8)
        assert O.norm_bearing(pl.chord_bearing) == "S57°53'59\"E"
        op = O.placed(894.08, pl.curve.delta_deg, direction, pc, pl.back_az)
        pt_close(O.as_pt(op.pt), O.z(pt), 100.0, abs_=1e-6)
        az_close(op.chord_az, chord_az, tol=1e-7)
