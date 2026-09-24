"""Bridge tests: pin the audit's invariants for engine/cogo_road_centerlines.py and engine/curves.py.

Known-bad results are ``xfail(strict=True)`` so the suite stays green while each bug is on record; the day a bug is
fixed its xfail turns into a strict XPASS failure that says "delete the mark".  Findings are numbered as in
``plat_curves/AUDIT_ENGINE.md``.  Stated plat values are the ``STATED_CONST`` block of ``audit_engine_curves``
(reader JSONs are cross-checked in ``test_audit_constants_agree_with_readers``).
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # plugins/curves  (holds the plat_curves package)
ROOT = Path(__file__).resolve().parents[4]  # repo root (holds engine/, imported READ-ONLY)
for _p in (PLUGIN_ROOT, ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from engine.cogo import Point, azimuth_to_bearing, parse_bearing  # noqa: E402
from engine.curves import Curve as EngineCurve  # noqa: E402
from engine.curves import solve_curve_all_parameters, trace_curve_from_skeleton  # noqa: E402
from plat_curves import audit_engine_curves as A  # noqa: E402

SS, CH, MARINA, SANDS, KEEL = A.CIDS
BLVD = "C_BEACHWOOD_BLVD_CL"  # F7 fixed: no longer an engine curve; xfail entries keyed on it are inert
_ENGINE = A.build_engine()
_METRICS = {cid: A.engine_metrics(_ENGINE, cid) for cid in A.CIDS}
_READINGS = A.load_readings()


def _params(bad: dict[str, str], ids=None):
    """Parametrize over ids; ids listed in ``bad`` are strict-xfail with their reason."""
    out = []
    for i in ids if ids is not None else A.CIDS:
        out.append(pytest.param(i, marks=pytest.mark.xfail(strict=True, reason=bad[i])) if i in bad else i)
    return out


# ---------------------------------------------------------------------------------------------------------------
# 1. internal geometry identities per curve  (finding numbers refer to AUDIT_ENGINE.md)
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "cid",
    _params(
        {
            BLVD: "F7: centre set perpendicular to the CHORD (:1149), not to the back tangent",
        }
    ),
)
def test_pt_lies_on_circle_about_centre(cid):
    m = _METRICS[cid]
    assert abs(m["r_pc"] - m["R"]) <= A.GEOM_TOL_FT
    assert abs(m["r_pt"] - m["R"]) <= A.GEOM_TOL_FT


@pytest.mark.parametrize("cid", _params({BLVD: "F7: stored T=130.34 vs R*tan(7.608333/2)=130.317 (:1160)"}))
def test_pi_to_pc_distance_is_tangent_length(cid):
    m = _METRICS[cid]
    assert m["pc_pi"] == pytest.approx(m["T_formula"], abs=A.GEOM_TOL_FT)


@pytest.mark.parametrize(
    "cid",
    _params(
        {
            BLVD: "F7: PI is placed on the chord line, |PI-PT| = 129.66 vs T = 130.34",
        }
    ),
)
def test_pi_to_pt_distance_is_tangent_length(cid):
    m = _METRICS[cid]
    assert m["pi_pt"] == pytest.approx(m["T_formula"], abs=A.GEOM_TOL_FT)


@pytest.mark.parametrize(
    "cid",
    _params(
        {
            BLVD: "F7: PI is collinear with PC and PT (interior angle 180 deg)",
        }
    ),
)
def test_interior_angle_at_pi_is_180_minus_delta(cid):
    m = _METRICS[cid]
    assert m["pi_angle"] == pytest.approx(180.0 - m["delta"], abs=A.ANG_TOL_ARCSEC / 3600.0)


@pytest.mark.parametrize(
    "cid",
    _params(
        {
            BLVD: "F7: PI is on the chord so there is no turn at the PI at all",
        }
    ),
)
def test_turn_at_pi_matches_direction_flag(cid):
    m = _METRICS[cid]
    sense = "CW" if m["turn_at_pi"] > 1e-6 else "CCW" if m["turn_at_pi"] < -1e-6 else "STRAIGHT"
    assert sense == m["direction"]


@pytest.mark.parametrize(
    "cid",
    _params(
        {
        }
    ),
)
def test_centre_side_matches_direction_flag(cid):
    m = _METRICS[cid]
    side = "CW" if m["center_side"] > 0 else "CCW"  # centre right of travel <=> CW
    assert side == m["direction"]


@pytest.mark.parametrize(
    "cid",
    _params(
        {
        }
    ),
)
def test_drawn_arc_is_tangent_to_pi_ray_at_pc(cid):
    m = _METRICS[cid]
    assert abs(A.wrap180(m["drawn_tangent_az_at_pc"] - m["back_az"])) * 3600 <= A.ANG_TOL_ARCSEC


@pytest.mark.parametrize(
    "cid",
    _params(
        {
            BLVD: "F7: drawn arc ends 17.26 ft from pt_point",
        }
    ),
)
def test_drawn_arc_ends_at_pt(cid):
    assert _METRICS[cid]["drawn_end_gap"] <= A.GEOM_TOL_FT


@pytest.mark.parametrize(
    "cid",
    _params(
        {
            BLVD: "F7: chord az == back-tangent az (PI placed on the chord)",
        }
    ),
)
def test_hardcoded_chord_bearing_matches_analytic(cid):
    assert abs(_METRICS[cid]["chord_resid_arcsec"]) <= A.ANG_TOL_ARCSEC


@pytest.mark.parametrize(
    "cid",
    _params(
        {
            BLVD: "F7: P.I.-out ray labelled S10°01'00\"E (:1529) turns LEFT although direction='CW'",
        }
    ),
)
def test_pi_out_ray_label_matches_analytic_forward_tangent(cid):
    resid = _METRICS[cid]["pi_out_resid_deg"]
    assert resid is not None
    assert abs(resid) * 3600 <= A.ANG_TOL_ARCSEC


@pytest.mark.parametrize(
    "cid", _params({BLVD: "F7: hard-coded L/T/C (:1159-1161) disagree with R,delta by up to 0.06 ft"})
)
def test_stored_tangent_length_chord_follow_from_radius_and_delta(cid):
    m = _METRICS[cid]
    assert m["T"] == pytest.approx(m["T_formula"], abs=A.PLAT_TOL_FT)
    assert m["L"] == pytest.approx(m["L_formula"], abs=A.PLAT_TOL_FT)
    assert m["C"] == pytest.approx(m["C_formula"], abs=A.PLAT_TOL_FT)


def test_marina_is_the_one_geometrically_consistent_curve():
    """Marina passes every identity above; Keel and Cape Horn's stored T/L/C are also exact."""
    m = _METRICS[MARINA]
    assert m["r_pt"] == pytest.approx(m["R"], abs=0.01)
    assert m["drawn_end_gap"] < 0.01
    assert abs(m["chord_resid_arcsec"]) < 2.0


# ---------------------------------------------------------------------------------------------------------------
# 2. engine vs the plat's CL Curve Data (R, delta, T are the only values printed in a block)
# ---------------------------------------------------------------------------------------------------------------
_STATED_IDS = [c for c in A.CIDS if A.STATED_CONST[c] is not None]


@pytest.mark.parametrize(
    "cid",
    _params(
        {
        },
        _STATED_IDS,
    ),
)
def test_engine_radius_equals_plat_centerline_radius(cid):
    stated = A.stated_for(cid, _READINGS)
    assert _METRICS[cid]["R"] == pytest.approx(stated["radius"], abs=A.PLAT_TOL_FT)


@pytest.mark.parametrize(
    "cid",
    _params(
        {
        },
        _STATED_IDS,
    ),
)
def test_engine_tangent_equals_plat_tangent(cid):
    stated = A.stated_for(cid, _READINGS)
    assert _METRICS[cid]["T"] == pytest.approx(stated["tangent"], abs=A.PLAT_TOL_FT)


@pytest.mark.parametrize("cid", _STATED_IDS)
def test_engine_delta_equals_plat_delta(cid):
    stated = A.stated_for(cid, _READINGS)
    assert _METRICS[cid]["delta"] == pytest.approx(stated["delta_deg"], abs=1e-4)  # 0.36"


@pytest.mark.parametrize(
    "cid",
    _params(
        {
        },
        _STATED_IDS,
    ),
)
def test_row_edge_radii_are_stated_centerline_minus_and_plus_half_width(cid):
    stated = A.stated_for(cid, _READINGS)
    inner, outer = _METRICS[cid]["inner_R"], _METRICS[cid]["outer_R"]
    hw = _METRICS[cid]["hw"]
    assert inner == pytest.approx(stated["radius"] - hw, abs=A.PLAT_TOL_FT)
    assert outer == pytest.approx(stated["radius"] + hw, abs=A.PLAT_TOL_FT)


@pytest.mark.parametrize(
    "cid",
    _params(
        {
        },
        list(A.EXPECTED_ORIENT),
    ),
)
def test_pc_pt_orientation_matches_scan(cid):
    oc = A.orientation_check(_ENGINE, cid)
    assert oc["ok"], oc


@pytest.mark.xfail(
    strict=True,
    reason="F13: engine omits Shellfish Dr (R=167.95) (F7 Blvd curve removed 2026-09-24)",
)
def test_engine_curve_set_equals_plat_centerline_block_set():
    plat = {"salvador", "cape", "marina", "sands", "keel", "shellfish"}
    engine_streets = {m["street"].lower().split()[0] for m in _METRICS.values()}
    assert {s for s in plat if s != "shellfish"} <= engine_streets
    assert "beachwood" not in engine_streets
    assert any("shellfish" in c.street_name.lower() for c in _ENGINE.curves.values())


def test_audit_constants_agree_with_readers():
    """If a reader JSON covers a block, the audit constant must equal the reader's value (keeps the audit honest)."""
    checked = 0
    for cid in _STATED_IDS:
        stated = A.stated_for(cid, _READINGS)
        const = A.STATED_CONST[cid]
        for key in ("radius", "delta_deg", "tangent"):
            if not stated["source"][key].startswith("UNVERIFIED"):
                checked += 1
                assert stated[key] == pytest.approx(const[key], abs=1e-4), (cid, key, stated["source"][key])
    if not checked:
        pytest.skip("no reader JSON covers the centerline blocks yet")


def test_stated_blocks_are_internally_consistent_except_shellfish():
    """T = R tan(delta/2) to 0.02 ft for every block except the Shellfish block, where the PLAT disagrees by 0.084 ft."""
    for cid in _STATED_IDS:
        s = A.stated_for(cid, _READINGS)
        assert s["tangent"] == pytest.approx(A.tan_len(s["radius"], s["delta_deg"]), abs=A.PLAT_TOL_FT), cid
    sh = A.SHELLFISH_CL_STATED
    assert abs(sh["tangent"] - A.tan_len(sh["radius"], sh["delta_deg"])) == pytest.approx(0.0844, abs=0.001)


def test_parse_bearing_rejects_azimuth_style_bearing():
    """'S91°01'40\"E' (used at cogo_road_centerlines.py:1495 and :1628) is not a quadrant bearing."""
    with pytest.raises(ValueError):
        parse_bearing("S91°01'40\"E")


# ---------------------------------------------------------------------------------------------------------------
# 3. validate_all_curves() has no teeth
# ---------------------------------------------------------------------------------------------------------------
_PROBES = A.validator_probe()


@pytest.mark.parametrize(
    "label,detected",
    [
        pytest.param(
            label,
            detected,
            marks=pytest.mark.xfail(
                strict=True,
                reason="F9: validate_all_curves (:1747-1779) compares stored L/T/C with formulas of the same R,delta",
            ),
        )
        for label, detected in _PROBES
    ],
)
def test_validate_all_curves_flags_corrupted_curve(label, detected):
    assert detected, label


@pytest.mark.parametrize(
    "cid",
    _params(
        dict.fromkeys((BLVD,), "F9: validator reports is_valid=True although PT is off the circle"),
        A.CIDS,
    ),
)
def test_validate_all_curves_verdict_agrees_with_pt_on_circle(cid):
    valid = _ENGINE.validate_all_curves()[cid]["is_valid"]
    on_circle = abs(_METRICS[cid]["r_pt"] - _METRICS[cid]["R"]) <= A.GEOM_TOL_FT
    assert valid == on_circle


# ---------------------------------------------------------------------------------------------------------------
# 4. get_offset_arcs / cul-de-sac construction (correct as built)
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cid", A.CIDS)
def test_get_offset_arcs_algebra(cid):
    c = _ENGINE.curves[cid]
    inner, outer = c.get_offset_arcs()
    hw = c.half_width
    assert inner["radius"] == pytest.approx(c.radius - hw)
    assert outer["radius"] == pytest.approx(c.radius + hw)
    for arc in (inner, outer):
        assert arc["arc_length"] == pytest.approx(A.arc_len(arc["radius"], c.delta_deg), abs=1e-3)
        assert arc["tangent"] == pytest.approx(A.tan_len(arc["radius"], c.delta_deg), abs=1e-3)
        assert arc["chord_length"] == pytest.approx(A.chord_len(arc["radius"], c.delta_deg), abs=1e-3)
    assert inner["type"] == "INNER_ROW" and outer["type"] == "OUTER_ROW"


@pytest.mark.parametrize("cid", list(A.PLAT_EDGE_EVIDENCE))
def test_plat_lot_chord_evidence_pins_engine_edge_radii(cid):
    """Marina N R/W (389.27) and Keel S R/W (113.93) recovered from printed lot chords are among the engine's edges."""
    for label, r_from_chord, r_expected, _in_engine in A.edge_check(_METRICS[cid], A.stated_for(cid, _READINGS))[
        "evidence"
    ]:
        assert r_from_chord == pytest.approx(r_expected, abs=0.02), label


def test_no_culdesac_modelled():
    """C9 resolved 2026-09-24: no cul-de-sac bulb on either sheet; Keel Dr ends at Marina Dr."""
    assert _ENGINE.culdesacs == []
    assert A.culdesac_checks(_ENGINE) == []


def test_engine_corner_returns_are_note4_default():
    """Every R/W corner return in the engine is R = 25' (Sheet 2 Note 4 + user rule)."""
    assert _ENGINE.corner_fillets
    assert all(f.radius == 25.0 for f in _ENGINE.corner_fillets)


# ---------------------------------------------------------------------------------------------------------------
# 5. frontage summations
# ---------------------------------------------------------------------------------------------------------------
_FRONT = {r["id"]: r for r in A.frontage_reconciliation(_ENGINE)}
_FRONT_BAD = {
    "SEG_ASSUMP_SS_SURFWOOD_TIE": "F10: label S23°14'20\"W vs geometry S44°41'E; sum 86.16 vs distance 86.57",
    "SEG_ASSUMP_SANDS_APPROACH": "F10: sum 365.46 vs drawn 60.24; label S87°35'30\"W vs geometry N65°38'W",
    "SEG_SHELLFISH_MAIN": "F10: sum 901.34 vs drawn 651.49; label 0.83 deg off",
    "SEG_ASSUMP_SHELLFISH_KEEL": "F10: sum 839.69 vs drawn 498.67; label 1.09 deg off",
}


@pytest.mark.parametrize("sid", _params(_FRONT_BAD, list(_FRONT)))
def test_summed_frontages_equal_drawn_distance(sid):
    assert _FRONT[sid]["sum_minus_distance"] == pytest.approx(0.0, abs=0.05)


@pytest.mark.parametrize("sid", _params(_FRONT_BAD, list(_FRONT)))
def test_bearing_label_matches_segment_geometry(sid):
    dev = _FRONT[sid]["label_vs_geometry_deg"]
    assert dev is not None and abs(dev) < 0.01


@pytest.mark.xfail(
    strict=True, reason="F10: SEG_SAIL_MAIN Block 16 lots 1-8 entry is 618.50 but its own note sums to 593.50"
)
def test_sail_lot_entry_matches_its_own_arithmetic():
    entry = next(s for s in _ENGINE.segments if s.id == "SEG_SAIL_MAIN").summed_lot_frontages[0]["frontage_ft"]
    assert entry == pytest.approx(68.50 + 7 * 75.00, abs=0.01)


@pytest.mark.xfail(
    strict=True,
    reason="F10: Block 15 lot 1 'frontage' 153.25 is the full CL arc of R=167.95 (plat lot-side chord is 121.56)",
)
def test_lot_frontage_is_not_the_centerline_arc_length():
    entry = next(s for s in _ENGINE.segments if s.id == "SEG_ASSUMP_SHELLFISH_KEEL").summed_lot_frontages[0][
        "frontage_ft"
    ]
    assert abs(entry - A.arc_len(167.95, A.D52)) > 1.0


# ---------------------------------------------------------------------------------------------------------------
# 6. parent-boundary curve c22
# ---------------------------------------------------------------------------------------------------------------
def test_c22_chord_bearing_and_distance_follow_from_c21_tangent_and_radius():
    p = A.parent_boundary_c22(_ENGINE)
    assert p["delta_from_chord_deg"] == pytest.approx(p["delta_from_tangents_deg"], abs=2.0 / 3600.0)
    assert p["raw_course"][2] == 99.98  # plat caption: chord distance 99.98


@pytest.mark.xfail(
    strict=True, reason="F11: parent_area_sqft is the chord polygon; the curve to the left bulges out by 93.24 sq ft"
)
def test_parent_area_includes_c22_curve_segment():
    p = A.parent_boundary_c22(_ENGINE)
    assert p["engine_area"] == pytest.approx(p["expected_area"], abs=1.0)


# ---------------------------------------------------------------------------------------------------------------
# 7. engine/curves.py
# ---------------------------------------------------------------------------------------------------------------
def test_solver_roundtrip_every_pair_for_delta_up_to_90():
    rnd = random.Random(11)
    keys = ["radius", "delta_deg", "length", "chord", "tangent", "mid_ordinate", "external", "degree_curve"]
    for _ in range(25):
        r, d = rnd.uniform(20, 2000), rnd.uniform(0.5, 90.0)
        h = math.radians(d) / 2
        truth = {
            "radius": r,
            "delta_deg": d,
            "length": 2 * r * h,
            "chord": 2 * r * math.sin(h),
            "tangent": r * math.tan(h),
            "mid_ordinate": r * (1 - math.cos(h)),
            "external": r * (1 / math.cos(h) - 1),
            "degree_curve": 5729.57795 / r,
        }
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                if {a, b} == {"radius", "degree_curve"}:
                    continue
                res = solve_curve_all_parameters(**{a: truth[a], b: truth[b]})
                assert res["radius"] == pytest.approx(r, rel=2e-4), (a, b, r, d)
                assert res["delta_deg"] == pytest.approx(d, abs=2e-3 * max(1.0, d / 10)), (a, b, r, d)


@pytest.mark.parametrize("rot", ["CW", "CCW"])
def test_curve_arc_points_follow_the_spec_construction(rot):
    rnd = random.Random(5)
    for _ in range(50):
        r, d, back = rnd.uniform(20, 2000), rnd.uniform(1, 120), rnd.uniform(0, 360)
        s = 1.0 if rot == "CW" else -1.0
        pc = Point(rnd.uniform(0, 1e4), rnd.uniform(0, 1e4))
        chord_bearing = azimuth_to_bearing((back + s * d / 2) % 360, cardinal=False)
        cur = EngineCurve("x", A.arc_len(r, d), r, d, chord_bearing, A.chord_len(r, d), rot)
        rp = pc.offset(back + s * 90, r)
        pt = rp.offset(back + s * 90 + 180 + s * d, r)
        assert cur.arc_points(pc, 8)[-1].dist_to(pt) < 0.01
        assert abs(A.wrap180(parse_bearing(cur.tangent_in_bearing()) - back)) < 1e-3
        assert abs(A.wrap180(parse_bearing(cur.tangent_out_bearing()) - (back + s * d))) < 1e-3


def test_solver_out_of_domain_raises_or_recovers():
    r, d = 218.0, 134.8
    try:
        res = solve_curve_all_parameters(length=A.arc_len(r, d), tangent=A.tan_len(r, d))
    except ValueError:
        return
    assert res["radius"] == pytest.approx(r, rel=1e-3)


def test_trace_curve_rejects_chord_longer_than_diameter():
    with pytest.raises(ValueError):
        trace_curve_from_skeleton("probe", Point(0.0, 0.0), Point(74.86, 0.0), 25.0, [], fallback_rot="CW")


# ---------------------------------------------------------------------------------------------------------------
# 8. optional oracle: plat_curves.core
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cid", _params({BLVD: "F7: hard-coded L/T/C differ from core's R,delta values"}))
def test_core_oracle_agrees_with_engine_formulas(cid):
    core = pytest.importorskip("plat_curves.core")
    c = _ENGINE.curves[cid]
    cur = core.Curve(c.radius, c.delta_deg, c.direction)
    assert c.tangent == pytest.approx(cur.tangent, abs=A.PLAT_TOL_FT)
    assert c.arc_length == pytest.approx(cur.arc_length, abs=A.PLAT_TOL_FT)
    assert c.chord_length == pytest.approx(cur.chord, abs=A.PLAT_TOL_FT)


@pytest.mark.parametrize(
    "cid",
    _params(
        dict.fromkeys(
            (BLVD,),
            "F3-F7: core places PT off the engine's pt_point (engine PC/PI/direction inconsistent)",
        )
    ),
)
def test_core_placed_pt_equals_engine_pt(cid):
    core = pytest.importorskip("plat_curves.core")
    c = _ENGINE.curves[cid]
    placed = core.PlacedCurve(
        core.Curve(c.radius, c.delta_deg, c.direction), (c.pc_point.n, c.pc_point.e), _METRICS[cid]["back_az"]
    )
    assert math.hypot(placed.pt[0] - c.pt_point.n, placed.pt[1] - c.pt_point.e) <= A.GEOM_TOL_FT
