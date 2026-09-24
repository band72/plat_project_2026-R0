"""plat_curves.plat_notation (parse / audit / offset diagnosis) versus the independent oracle."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plat_curves import plat_notation as pn  # noqa: E402
from plat_curves.core import PLAT_TOL_FT, dms_to_deg  # noqa: E402
from plat_curves.plat_notation import PlatCurveReading, audit_reading, diagnose_offset, parse_curve_data  # noqa: E402
from plat_curves.tests import oracle as O  # noqa: E402,N812

DELTA_36_20 = dms_to_deg(36, 20, 0)


def rounded_plat_values(radius: float, delta_true_deg: float) -> dict[str, float]:
    """What a plat would print for a design curve: R/T/L/C to 0.01 ft, delta to whole arc-seconds.

    T/L/C come from the oracle (walked geometry) using the TRUE design delta; delta is then rounded to 1", exactly the
    situation that makes recomputation from the printed R + delta drift by up to R * 0.5".
    """
    o = O.arc(radius, delta_true_deg, "CW")
    return {
        "radius": round(radius, 2),
        "delta_deg": round(delta_true_deg * 3600.0) / 3600.0,
        "tangent": round(o.tangent, 2),
        "arc_length": round(o.length, 2),
        "chord": round(o.chord, 2),
    }


def plat_reading(**over) -> PlatCurveReading:
    """The Beachwood centerline curve as printed: R 269.96, Delta 36°20'00", T 88.59, L 171.19 (C from oracle, 168.34)."""
    kw = {
        "id": "test-1",
        "sheet": 2,
        "street": "Test Street",
        "kind": "centerline",
        "radius": 269.96,
        "delta_deg": DELTA_36_20,
        "tangent": 88.59,
        "arc_length": 171.19,
        "chord": 168.34,
    }
    kw.update(over)
    return PlatCurveReading(**kw)


# =========================================================================== parse_curve_data
BASE = "Δ=36°20'00\" R.=269.96' T.=88.59'"
VARIANTS = [
    BASE,
    "∆=36°20'00\" R.=269.96' T.=88.59'",  # U+2206 INCREMENT instead of Greek Delta
    "△=36°20'00\" R=269.96' T=88.59'",  # triangle glyph, no dots after the letters
    "Δ = 36° 20′ 00″   R. = 269.96′   T. = 88.59′",  # prime / double-prime marks, spaced out
    "A=36°20'00\" R.=269.96' T.=88.59'",  # Greek Delta OCR'd as Latin A
    "Delta=36°20'00'' R.=269.96 T.=88.59",  # spelled out, '' for seconds, no foot marks
    "Δ 36°20'00\" R. 269.96' T. 88.59'",  # no equals signs at all
    "Δ=36º20’00” R:269.96’ T:88.59’",  # masculine ordinal as degree, curly quotes, colons
    "T.=88.59' R.=269.96' Δ=36°20'00\"",  # different field order
    "Δ=36°20' R.=269.96' T.=88.59'",  # seconds omitted (00")
    "Δ=36°20'00\"\nR.=269.96'\nT.=88.59'",  # newlines, as OCR line breaks
    "Δ=36°20'00\" R.=269.96' T.=88.59'",  # non-breaking spaces
    "Δ=36°20′00″ R.=269.96′ T.=88.59′",  # explicit U+2032 / U+2033
    "Δ=36°20’00’’ R.=269.96’ T.=88.59’",  # two right-quotes for the seconds mark
    "  Δ=36°20'00\", R.=269.96', T.=88.59'  ",  # padding and commas between fields
    "Δ=36°20'00\"; R.=269.96'; T.=88.59'",  # semicolons
    "Δ=36°20'00\" Rad.=269.96' Tan.=88.59'",  # long labels
]


class TestParse:
    @pytest.mark.parametrize("text", VARIANTS)
    def test_typographic_variants_parse_identically(self, text):
        got = parse_curve_data(text)
        assert set(got) == {"delta_deg", "radius", "tangent"}, got
        assert got["delta_deg"] == pytest.approx(DELTA_36_20, abs=1e-9)
        assert got["radius"] == pytest.approx(269.96, abs=1e-12)
        assert got["tangent"] == pytest.approx(88.59, abs=1e-12)
        assert all(isinstance(v, float) for v in got.values())

    def test_delta_seconds_are_read_not_dropped(self):
        assert parse_curve_data("Δ=36°20'45\" R.=269.96'")["delta_deg"] == pytest.approx(
            dms_to_deg(36, 20, 45), abs=1e-9
        )
        assert parse_curve_data("Δ=0°05'07\" R.=5000.00'")["delta_deg"] == pytest.approx(dms_to_deg(0, 5, 7), abs=1e-9)
        assert parse_curve_data("Δ=89°59'59\" R.=25.00'")["delta_deg"] == pytest.approx(
            dms_to_deg(89, 59, 59), abs=1e-9
        )

    def test_arc_chord_and_bearing_fields(self):
        got = parse_curve_data("Δ=6°24'37\" R.=894.08' L.=100.16' C.=99.98' Ch. Brg. S57°53'59\"E")
        assert got["radius"] == pytest.approx(894.08)
        assert got["arc_length"] == pytest.approx(100.16)
        assert got["chord"] == pytest.approx(99.98)
        assert got["delta_deg"] == pytest.approx(dms_to_deg(6, 24, 37), abs=1e-9)
        assert O.norm_bearing(got["chord_bearing"]) == "S57°53'59\"E"
        assert O.bearing_to_az(got["chord_bearing"]) == pytest.approx(180.0 - dms_to_deg(57, 53, 59), abs=1e-9)

    @pytest.mark.parametrize(
        ("text", "want_az"),
        [
            ("Ch.Brg. N.78°11'40\"W. C=50.00'", 360.0 - dms_to_deg(78, 11, 40)),
            ("S 57°53'59\" E  R=100.00'", 180.0 - dms_to_deg(57, 53, 59)),
            ("N 89°18'20\" E R=100.00'", dms_to_deg(89, 18, 20)),
            ("S12°34'56\"W R=100.00'", 180.0 + dms_to_deg(12, 34, 56)),
            ("N45°00'00\"W R=100.00'", 315.0),
        ],
    )
    def test_chord_bearing_variants_all_four_quadrants(self, text, want_az):
        got = parse_curve_data(text)
        assert got.get("radius", got.get("chord")) in (pytest.approx(100.0), pytest.approx(50.0))
        assert O.bearing_to_az(got["chord_bearing"]) == pytest.approx(want_az, abs=1e-6)

    def test_bearing_letters_are_not_mistaken_for_labels(self):
        # N/S/E/W and 'C' in "Ch." must not become radius / external / chord values
        got = parse_curve_data("S57°53'59\"E Ch. R.=894.08'")
        assert set(got) == {"chord_bearing", "radius"}

    def test_thousands_separator_and_comma_decimal(self):
        assert parse_curve_data("R.=1,234.56' Δ=10°00'00\"")["radius"] == pytest.approx(1234.56)
        assert parse_curve_data("R=269,96 Δ=36°20'00\"")["radius"] == pytest.approx(269.96)

    @pytest.mark.parametrize(
        ("text", "want"),
        [
            ("R.=100.00'", {"radius": 100.0}),
            ("T.=50.5'", {"tangent": 50.5}),
            ("L=12.34", {"arc_length": 12.34}),
            ("C.=7'", {"chord": 7.0}),
        ],
    )
    def test_only_keys_actually_found_are_returned(self, text, want):
        assert parse_curve_data(text) == pytest.approx(want)

    @pytest.mark.parametrize("text", ["", "   ", "no curve data here", "LOT 12 BLOCK 7", "PB 30 PG 82"])
    def test_no_curve_data_gives_empty_dict(self, text):
        assert parse_curve_data(text) == {}

    def test_reading_from_text_round_trip(self):
        r = PlatCurveReading.from_text(BASE, id="r1", sheet=2, street="X", kind="centerline")
        assert (r.radius, r.tangent) == (pytest.approx(269.96), pytest.approx(88.59))
        assert r.delta_deg == pytest.approx(DELTA_36_20, abs=1e-9)
        assert audit_reading(r)["verdict"] == "consistent"


# =========================================================================== PlatCurveReading
class TestReadingRecord:
    def test_spec_fields_exist_and_none_means_unreadable(self):
        r = PlatCurveReading(
            id="a1",
            sheet=1,
            street="Sands Ave",
            kind="row_edge",
            radius=100.0,
            delta_deg=None,
            tangent=None,
            arc_length=None,
            chord=None,
            chord_bearing=None,
            confidence=0.4,
            notes="blurry",
        )
        for name in (
            "id", "sheet", "street", "kind", "radius", "delta_deg", "tangent", "arc_length", "chord",
            "chord_bearing", "confidence", "notes",
        ):  # fmt: skip
            assert hasattr(r, name)
        assert r.delta_deg is None and r.tangent is None
        assert audit_reading(r)["verdict"] == "underdetermined"

    def test_from_dict_matches_json_rows(self):
        row = {
            "id": "s1-01", "sheet": 1, "street": "San Salvadore", "kind": "centerline", "radius": 269.96,
            "delta_deg": DELTA_36_20, "tangent": 88.59, "arc_length": 171.19, "chord": None, "chord_bearing": None,
            "confidence": 0.9, "crop": "x.png", "evidence": "R.=269.96'", "ambiguities": [],
        }  # fmt: skip
        r = PlatCurveReading.from_dict(row)
        assert r.radius == 269.96 and r.chord is None
        assert audit_reading(r)["verdict"] == "consistent"


# =========================================================================== audit_reading
class TestAudit:
    def test_plat_curve_is_consistent(self):
        out = audit_reading(plat_reading())
        assert out["verdict"] == "consistent"
        assert out["n_checks"] == 3
        # residual = stated - recomputed, from the oracle, each within plat rounding
        o = O.arc(269.96, DELTA_36_20, "CW")
        assert out["residuals"]["tangent"] == pytest.approx(88.59 - o.tangent, abs=1e-6)
        assert out["residuals"]["arc_length"] == pytest.approx(171.19 - o.length, abs=1e-6)
        assert out["residuals"]["chord"] == pytest.approx(168.34 - o.chord, abs=1e-6)
        assert all(abs(v) < PLAT_TOL_FT for v in out["residuals"].values())
        assert all(out["within"].values())

    def test_recomputed_values_match_the_oracle(self):
        out = audit_reading(plat_reading())
        o = O.arc(269.96, DELTA_36_20, "CW")
        rec = out["recomputed"]
        assert rec["tangent"] == pytest.approx(o.tangent, rel=1e-9)
        assert rec["arc_length"] == pytest.approx(o.length, rel=1e-9)
        assert rec["chord"] == pytest.approx(o.chord, rel=1e-9)
        assert rec["middle_ordinate"] == pytest.approx(o.middle_ordinate, rel=1e-9)
        assert rec["external"] == pytest.approx(o.external, rel=1e-9)

    @pytest.mark.parametrize(("radius", "t_printed"), [(269.96, 88.59), (327.01, 107.31), (459.36, 150.73)])
    def test_plat_fixtures_are_consistent(self, radius, t_printed):
        o = O.arc(radius, DELTA_36_20, "CW")
        r = PlatCurveReading(
            radius=radius,
            delta_deg=DELTA_36_20,
            tangent=t_printed,
            arc_length=round(o.length, 2),
            chord=round(o.chord, 2),
        )
        out = audit_reading(r)
        assert out["verdict"] == "consistent", out["reason"]
        assert abs(out["residuals"]["tangent"]) <= 0.01

    @pytest.mark.parametrize("radius", [25.0, 100.0, 269.96, 894.08, 5000.0])
    @pytest.mark.parametrize("delta_dms", [(0, 30, 0.4), (5, 0, 29.6), (36, 20, 0.49), (90, 0, 0.5), (150, 10, 30.45)])
    def test_correctly_rounded_plat_values_never_false_alarm(self, radius, delta_dms):
        """T/L/C from the true design delta, delta printed to 1": the audit must still say consistent."""
        delta_true = dms_to_deg(*delta_dms)
        printed = rounded_plat_values(radius, delta_true)
        out = audit_reading(PlatCurveReading(**printed))
        assert out["verdict"] == "consistent", (printed, out["reason"])

    def test_large_radius_needs_the_widened_tolerance(self):
        """R = 15000: half an arc-second of delta is 0.036 ft of arc, more than the flat 0.02 ft plat tolerance."""
        delta_true = dms_to_deg(60, 0, 0.49)
        printed = rounded_plat_values(15000.0, delta_true)
        out = audit_reading(PlatCurveReading(**printed))
        assert out["verdict"] == "consistent", (printed, out["reason"])
        assert abs(out["residuals"]["arc_length"]) > 0.005  # nonzero residual: rounding really did matter

    @pytest.mark.parametrize("name", ["tangent", "arc_length", "chord"])
    @pytest.mark.parametrize("shift", [0.5, -0.5, 5.0, -5.0])
    def test_planted_error_is_inconsistent_and_located(self, name, shift):
        good = plat_reading()
        r = plat_reading(**{name: getattr(good, name) + shift})
        out = audit_reading(r)
        assert out["verdict"] == "inconsistent"
        assert out["basis"] == ("radius", "delta_deg")
        assert out["within"][name] is False
        assert all(ok for k, ok in out["within"].items() if k != name)
        o = O.arc(269.96, DELTA_36_20, "CW")
        oracle_value = {"tangent": o.tangent, "arc_length": o.length, "chord": o.chord}[name]
        assert out["residuals"][name] == pytest.approx(getattr(good, name) + shift - oracle_value, abs=1e-6)
        assert (out["residuals"][name] > 0) == (shift > 0)

    def test_wrong_delta_is_inconsistent(self):
        out = audit_reading(plat_reading(delta_deg=dms_to_deg(36, 21, 0)))  # one minute off = 4.7 ft of arc
        assert out["verdict"] == "inconsistent"

    def test_planted_error_among_four_values_is_named_as_suspect(self):
        r = plat_reading(chord=168.34 + 0.5)
        out = audit_reading(r)
        assert out["verdict"] == "inconsistent"
        assert "chord" in out["suspects"]

    def test_tolerance_argument(self):
        r = plat_reading(tangent=88.59 + 0.03)
        assert audit_reading(r)["verdict"] == "inconsistent"  # 0.03 - 0.0057 > 0.02 + rounding allowance
        assert audit_reading(r, tol=0.05)["verdict"] == "consistent"
        assert audit_reading(plat_reading(tangent=88.59 + 0.5), tol=1.0)["verdict"] == "consistent"

    def test_r894_08_chord_99_98_and_arc_100_16_are_inconsistent(self):
        """Oracle: R + chord => L = 100.03; R + L=100.16 => chord 100.11.  The printed triple cannot be one curve."""
        r = PlatCurveReading(radius=894.08, chord=99.98, arc_length=100.16, kind="boundary")
        out = audit_reading(r)
        assert out["verdict"] == "inconsistent"
        assert out["basis"] == ("radius", "arc_length")
        d_arc = math.degrees(100.16 / 894.08)
        assert out["residuals"]["chord"] == pytest.approx(99.98 - O.chord_walk(894.08, d_arc), abs=1e-6)
        assert out["residuals"]["chord"] == pytest.approx(-0.1276, abs=5e-4)
        # from R + chord instead, the arc is what disagrees (oracle: 100.032)
        d_chord = O.delta_from_radius_and_chord(894.08, 99.98)
        scan = {tuple(s["pair"]): s for s in out["pair_scan"]}
        rc = scan[("radius", "chord")]
        assert rc["residuals"]["arc_length"] == pytest.approx(100.16 - O.length_walk(894.08, d_chord), abs=1e-5)
        # the (L, C) pair alone implies R ~ 482 ft (oracle bisection) -- nowhere near 894.08
        r_lc = O.solve_bisect(lambda rr: O.chord_walk(rr, math.degrees(100.16 / rr)) - 99.98, 300.0, 700.0, iters=60)
        assert scan[("arc_length", "chord")]["recomputed"]["radius"] == pytest.approx(r_lc, rel=1e-6)
        assert abs(r_lc - 894.08) > 300.0

    def test_exactly_determined_pair_is_consistent_and_solved_like_the_oracle(self):
        out = audit_reading(PlatCurveReading(radius=269.96, arc_length=171.19))
        assert out["verdict"] == "consistent" and out["n_checks"] == 0
        d = math.degrees(171.19 / 269.96)
        o = O.arc(269.96, d, "CW")
        assert out["recomputed"]["delta_deg"] == pytest.approx(d, abs=1e-9)
        assert out["recomputed"]["tangent"] == pytest.approx(o.tangent, rel=1e-9)
        assert out["recomputed"]["chord"] == pytest.approx(o.chord, rel=1e-9)

    def test_delta_is_recovered_from_radius_and_tangent(self):
        out = audit_reading(PlatCurveReading(radius=269.96, tangent=88.59))
        assert out["verdict"] == "consistent"
        # oracle: the delta whose walked tangent-line intersection is 88.59 ft from the PC on R=269.96
        d_oracle = O.solve_bisect(lambda deg: O.arc(269.96, deg, "CW").tangent - 88.59, 1.0, 120.0, iters=50)
        assert out["recomputed"]["delta_deg"] == pytest.approx(d_oracle, abs=1e-7)
        # T printed to 0.01 ft: dT = 0.0057 ft moves delta by ~8"; still the plat's 36°20' to well under a minute
        assert abs(out["recomputed"]["delta_deg"] - DELTA_36_20) < 0.003

    @pytest.mark.parametrize(
        "kw",
        [{}, {"radius": 269.96}, {"delta_deg": DELTA_36_20}, {"tangent": 88.59}, {"chord_bearing": "N45°00'00\"E"}],
    )
    def test_fewer_than_two_parameters_is_underdetermined(self, kw):
        assert audit_reading(PlatCurveReading(**kw))["verdict"] == "underdetermined"

    @pytest.mark.parametrize(
        "kw",
        [
            {"radius": -5.0, "tangent": 10.0},
            {"radius": 100.0, "delta_deg": 200.0},
            {"radius": 100.0, "delta_deg": 0.0},
            {"radius": 100.0, "chord": 250.0},  # chord longer than the diameter
            {"arc_length": 100.0, "chord": 101.0},  # chord longer than its arc
        ],
    )
    def test_impossible_readings_are_flagged_not_crashed(self, kw):
        assert audit_reading(PlatCurveReading(**kw))["verdict"] in ("inconsistent", "underdetermined")

    def test_verdict_vocabulary_and_no_mutation(self):
        r = plat_reading()
        before = r.to_dict()
        for rr in (r, plat_reading(tangent=99.0), PlatCurveReading(radius=1.0)):
            assert audit_reading(rr)["verdict"] in ("consistent", "inconsistent", "underdetermined")
        assert r.to_dict() == before

    def test_accepts_plain_dict_rows(self):
        out = audit_reading({"radius": 269.96, "delta_deg": DELTA_36_20, "tangent": 88.59})
        assert out["verdict"] == "consistent"


# =========================================================================== diagnose_offset
def oracle_radius_from_tangent(delta_deg: float, tangent: float) -> float:
    """Radius whose walked tangent-line intersection is `tangent` ft from the PC (bisection on the oracle)."""
    return O.solve_bisect(lambda rr: O.arc(rr, delta_deg, "CW").tangent - tangent, 1.0, 5000.0, iters=60)


class TestDiagnoseOffset:
    def test_stated_r_is_the_outside_edge_planted_plus_30(self):
        """R printed as 299.96 (= centerline 269.96 + 30) beside the centerline's T=88.59."""
        out = diagnose_offset(plat_reading(radius=299.96, chord=None))
        assert out["hypothesis"] == "stated R is a R/W edge, not centerline"
        assert out["implied_centerline_R"] == pytest.approx(269.96, abs=PLAT_TOL_FT)
        assert out["which_edge"] == "outside"
        # independent confirmation from the oracle: T = 88.59 at Delta 36°20' needs R ~ 269.96, not 299.96
        assert oracle_radius_from_tangent(DELTA_36_20, 88.59) == pytest.approx(269.96, abs=0.02)
        assert abs(oracle_radius_from_tangent(DELTA_36_20, 88.59) - 299.96) > 29.9

    def test_stated_r_is_the_inside_edge_planted_minus_30(self):
        out = diagnose_offset(plat_reading(radius=239.96, chord=None))
        assert out["hypothesis"] == "stated R is a R/W edge, not centerline"
        assert out["implied_centerline_R"] == pytest.approx(269.96, abs=PLAT_TOL_FT)
        assert out["which_edge"] == "inside"

    def test_all_of_t_l_c_and_delta_present(self):
        out = diagnose_offset(plat_reading(radius=299.96))
        assert out["implied_centerline_R"] == pytest.approx(269.96, abs=PLAT_TOL_FT)
        assert out["which_edge"] == "outside"

    def test_delta_not_stated_is_solved_from_t_and_l(self):
        out = diagnose_offset(plat_reading(radius=299.96, delta_deg=None, chord=None))
        assert out["hypothesis"] == "stated R is a R/W edge, not centerline"
        assert out["implied_centerline_R"] == pytest.approx(269.96, abs=0.05)
        assert out["which_edge"] == "outside"

    @pytest.mark.parametrize("radius", [269.96, 327.01, 459.36])
    def test_edge_confusion_on_every_plat_fixture(self, radius):
        o = O.arc(radius, DELTA_36_20, "CW")
        for shift, edge in ((+30.0, "outside"), (-30.0, "inside")):
            r = PlatCurveReading(
                radius=radius + shift, delta_deg=DELTA_36_20, tangent=round(o.tangent, 2), arc_length=round(o.length, 2)
            )
            out = diagnose_offset(r, row_width=60.0)
            assert out["hypothesis"] == "stated R is a R/W edge, not centerline", (radius, shift)
            assert out["implied_centerline_R"] == pytest.approx(radius, abs=PLAT_TOL_FT)
            assert out["which_edge"] == edge

    def test_row_width_argument_is_honoured(self):
        # 40 ft right-of-way: edges are +-20 ft
        out = diagnose_offset(plat_reading(radius=289.96, chord=None), row_width=40.0)
        assert out["hypothesis"] == "stated R is a R/W edge, not centerline"
        assert out["implied_centerline_R"] == pytest.approx(269.96, abs=PLAT_TOL_FT)
        assert out["which_edge"] == "outside"
        # ... and the same reading is NOT explained by a 60 ft right-of-way
        out60 = diagnose_offset(plat_reading(radius=289.96, chord=None), row_width=60.0)
        assert out60["implied_centerline_R"] is None or out60["implied_centerline_R"] != pytest.approx(
            269.96, abs=PLAT_TOL_FT
        )

    def test_stated_r_and_tlc_on_opposite_edges(self):
        """R = 329.96 (outside edge of a 299.96 centerline) but T/L/C belong to R = 269.96 (its inside edge)."""
        out = diagnose_offset(plat_reading(radius=329.96, chord=None))
        assert "opposite" in out["hypothesis"]
        assert out["implied_centerline_R"] == pytest.approx(299.96, abs=PLAT_TOL_FT)
        assert out["which_edge"] == "outside"

    def test_consistent_reading_reports_no_offset(self):
        out = diagnose_offset(plat_reading())
        assert out["which_edge"] is None
        assert "edge" not in out["hypothesis"] or "no offset" in out["hypothesis"]
        assert out["implied_centerline_R"] == pytest.approx(269.96, abs=PLAT_TOL_FT)

    def test_unexplained_disagreement_is_not_blamed_on_the_offset(self):
        out = diagnose_offset(plat_reading(radius=310.0, chord=None))  # 40.04 ft off: not 0, +-30, +-60
        assert out["which_edge"] is None
        assert out["implied_centerline_R"] is None
        assert out["implied_radius_shift"] == pytest.approx(269.96 - 310.0, abs=0.05)

    def test_implied_radii_match_oracle(self):
        out = diagnose_offset(plat_reading(radius=299.96, chord=None))
        assert out["implied_radii"]["tangent"] == pytest.approx(
            oracle_radius_from_tangent(DELTA_36_20, 88.59), abs=1e-6
        )
        assert out["implied_radii"]["arc_length"] == pytest.approx(
            171.19 / math.radians(DELTA_36_20), abs=1e-9
        )  # L = R * delta

    def test_nothing_to_compare_is_handled(self):
        assert diagnose_offset(PlatCurveReading(radius=300.0))["implied_centerline_R"] is None
        assert diagnose_offset(PlatCurveReading(tangent=88.59, delta_deg=DELTA_36_20))["implied_centerline_R"] is None
        assert diagnose_offset(PlatCurveReading())["implied_centerline_R"] is None


# =========================================================================== stated readings on disk survive the pipeline
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _data_rows():
    rows = []
    for f in sorted(DATA_DIR.glob("readings_*.json")):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue  # another agent may be mid-write
        rows += [(f.name, row) for row in (data if isinstance(data, list) else data.get("readings", []))]
    return rows


@pytest.mark.parametrize(
    ("fname", "row"), _data_rows() or [pytest.param("none", {}, marks=pytest.mark.skip("no data yet"))]
)
def test_transcribed_readings_flow_through_audit_and_diagnosis(fname, row):
    """No transcribed row may crash the audit / diagnosis (the verdict itself is the auditor's business)."""
    reading = PlatCurveReading.from_dict(row)
    out = audit_reading(reading)
    assert out["verdict"] in ("consistent", "inconsistent", "underdetermined")
    d = diagnose_offset(reading)
    assert "hypothesis" in d
    assert pn.PLAT_TOL_FT == PLAT_TOL_FT


class TestLostDegreeSignWarns:
    """S1: a delta whose degree sign was OCR'd away must be refused WITH a warning, never guessed and never silent."""

    @pytest.mark.parametrize("text", ["Δ=36'20'00\" R.=269.96' T.=88.59'", "Δ=36 20 00 R=269.96 T=88.59"])
    def test_unparseable_delta_warns_and_is_not_set(self, text):
        from plat_curves.plat_notation import parse_curve_data_ex

        out, warnings = parse_curve_data_ex(text)
        assert "delta_deg" not in out
        assert any("delta label found but no angle parsed" in w for w in warnings)
        assert out["radius"] == pytest.approx(269.96)  # the rest of the row is still recovered

    @pytest.mark.parametrize(
        "text",
        [
            "Δ=36°20'00\" R.=269.96' T.=88.59'",
            "∆ = 36º20′00″ R = 269.96 T = 88.59",
            "Delta: 36°20'00\" R=269.96",
            "Δ=36°20' R=269.96",
            "Curve Data R=327.01' T=107.31'",  # no delta at all: nothing to warn about
        ],
    )
    def test_clean_rows_do_not_warn_about_delta(self, text):
        from plat_curves.plat_notation import parse_curve_data_ex

        _, warnings = parse_curve_data_ex(text)
        assert not any("delta label found" in w for w in warnings)


class TestPlatDiscrepancies:
    """S2: Permanent regression test recording known surveyor discrepancies on Sheet 2."""

    def test_shellfish_cl_tangent_discrepancy(self):
        """Shellfish Dr CL printed T=82.35 vs formula T=82.4344 (residual 0.0844 ft > 0.02 ft).

        R=167.95, Delta=52°17'10". The 5 edge chords corroborate R=167.95 (inside edge R-30=137.95
        yields full-arc chord 121.5654 vs printed 121.56, residual 0.0054 ft).
        audit_reading flags 'inconsistent' at standard 0.02' tolerance, but passes at tol=0.10'.
        """
        r = PlatCurveReading(radius=167.95, delta_deg=dms_to_deg(52, 17, 10), tangent=82.35)
        out = audit_reading(r, tol=PLAT_TOL_FT)
        assert out["verdict"] == "inconsistent"
        assert abs(abs(out["residuals"]["tangent"]) - 0.0844) < 0.005

        out_lenient = audit_reading(r, tol=0.10)
        assert out_lenient["verdict"] == "consistent"

    def test_keel_north_edge_chord_discrepancy(self):
        """Keel Dr north edge chord printed 82.45' vs geometry 82.051' (diff 0.399 ft).

        With R_CL=143.93', R_edge=173.93', bearing N48°56'55"E implies piece Delta=27°17'10".
        Formula chord is 82.051', while ink reads 82.45'.
        """
        r_edge = 143.93 + 30.0  # 173.93
        delta_piece = dms_to_deg(27, 17, 10)
        chord_geom = 2.0 * r_edge * math.sin(math.radians(delta_piece) / 2.0)
        assert abs(chord_geom - 82.051) < 0.005
        residual = 82.45 - chord_geom
        assert abs(residual - 0.399) < 0.005


class TestEdgeFrontageChordSubdivisions:
    """S4: Verify all 39 boundary and frontage chord rows in readings_sheet2_sands_capehorn_boundary.json."""

    def test_sands_and_capehorn_row_edges_reconcile_to_cl_delta(self):
        f = DATA_DIR / "readings_sheet2_sands_capehorn_boundary.json"
        data = json.loads(f.read_text())
        assert len(data) == 39

        sands_n_angles = []
        sands_s_angles = []
        cape_n_angles = []

        for row in data:
            if row.get("kind") == "row_edge":
                chord = row["chord"]
                dc = row["derived_check"]
                r_edge = dc["edge_R_assumed"]
                # C = 2 * R * sin(delta / 2) -> delta = 2 * asin(C / (2*R))
                computed_delta_deg = 2.0 * math.degrees(math.asin(chord / (2.0 * r_edge)))
                if row["id"].startswith("S2-SANDS-N"):
                    sands_n_angles.append(computed_delta_deg)
                elif row["id"].startswith("S2-SANDS-S"):
                    sands_s_angles.append(computed_delta_deg)
                elif row["id"].startswith("S2-CAPEHORN-N"):
                    cape_n_angles.append(computed_delta_deg)

        # Sands North edge (5 lots): sum must equal centerline Delta 36°20'00"
        delta_sands_expected = dms_to_deg(36, 20, 0)
        assert len(sands_n_angles) == 5
        assert abs(sum(sands_n_angles) - delta_sands_expected) < 0.005

        # Sands South edge (4 lots): sum must equal centerline Delta 36°20'00"
        assert len(sands_s_angles) == 4
        assert abs(sum(sands_s_angles) - delta_sands_expected) < 0.005

        # Cape Horn North edge (3 lots): sum must equal centerline Delta 36°20'00"
        delta_cape_expected = dms_to_deg(36, 20, 0)
        assert len(cape_n_angles) == 3
        assert abs(sum(cape_n_angles) - delta_cape_expected) < 0.005

    def test_doubtful_reads_verification_s5(self):
        """S5: Re-verify doubtful reads in readings_sheet2_sands_capehorn_boundary.json.

        1. S2-CAPEHORN-CORNER-B8L22: Overprinted '25.0'' and 'N88°58'20\"E.' at Cape Horn PC corner.
           Consistent with R=25.0', Delta=90°00'00\", T=25.00'.
        2. S2-SANDS-S-B8L25-26-LINE: Stated divider N28°48'31\"E, 107.04'.
           Seconds '31' chosen over impossible glyph read '91'.
        3. S2-CAPEHORN-N-B8L22-21-LINE: Stated divider N17°48'58\"E, 102.17'.
           Seconds '58' verified by flat top bar and hooked tail vs '38'.
        """
        f = DATA_DIR / "readings_sheet2_sands_capehorn_boundary.json"
        data = {r["id"]: r for r in json.loads(f.read_text())}

        # 1. Cape Horn overprinted corner return
        ch_ret = data["S2-CAPEHORN-CORNER-B8L22"]
        assert ch_ret["line_distance"] == 25.0
        assert ch_ret["line_bearing"] == "N88°58'20\"E"
        assert ch_ret["derived_check"]["T_for_R25_90deg"] == 25.0

        # 2. Sands Lot 25/26 line
        sands_25_26 = data["S2-SANDS-S-B8L25-26-LINE"]
        assert sands_25_26["line_bearing"] == "N28°48'31\"E"
        assert sands_25_26["line_distance"] == 107.04
        assert "31" in sands_25_26["ambiguities"]

        # 3. Cape Horn Lot 22/21 line
        cape_22_21 = data["S2-CAPEHORN-N-B8L22-21-LINE"]
        assert cape_22_21["line_bearing"] == "N17°48'58\"E"
        assert cape_22_21["line_distance"] == 102.17
        assert "58 vs 38" in cape_22_21["ambiguities"]



