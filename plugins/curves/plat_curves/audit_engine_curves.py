#!/usr/bin/env python3
"""Read-only audit of engine/cogo_road_centerlines.py (and engine/curves.py) against the plat's CL Curve Data.

Run from the repo root:  python3 plat_curves/audit_engine_curves.py [--strict] [--json PATH]

What it prints, per centerline (CL) curve of the engine:
  A. engine R / delta / T / L / C vs the plat's "CL Curve Data" block (residuals + verdict),
  B. internal geometry identities (PC/PT on the circle, |PI-PC| = T = |PI-PT|, angle at PI = 180 - delta,
     turn sense vs the CW/CCW flag, centre side, drawn arc end vs PT, hard-coded chord / P.I.-ray bearings),
  C. R/W-edge radii from ``get_offset_arcs`` vs CL +/- half width, and PC/PT orientation vs the scan,
then engine-wide checks (validate_all_curves blindness probe, cul-de-sac construction, frontage summations,
parent-boundary curve c22, engine/curves.py fuzz).

Stated plat values come from ``data/readings_*.json`` when a reader has produced them; otherwise from the
constants below, printed as UNVERIFIED.  Nothing here edits engine/*; ``plat_curves.core`` is used only as an
optional cross-check when it imports.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]  # plugins/curves  (holds the plat_curves package)
REPO_ROOT = Path(__file__).resolve().parents[3]  # repo root (holds engine/, imported READ-ONLY)
for _p in (PLUGIN_ROOT, REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
ROOT = REPO_ROOT

from engine.cogo import Point, azimuth_to_bearing, parse_bearing  # noqa: E402
from engine.cogo_road_centerlines import RAW_BOUNDARY_COURSES, BeachwoodRoadCenterlineEngine  # noqa: E402
from engine.curves import Curve as EngineCurve  # noqa: E402
from engine.curves import solve_curve_all_parameters, trace_curve_from_skeleton  # noqa: E402

try:  # optional cross-check oracle (stdlib-only sibling package)
    from plat_curves import core as _core
except Exception:  # pragma: no cover - core may not exist yet
    _core = None

DATA_DIR = Path(__file__).resolve().parent / "data"
PLAT_TOL_FT = 0.02  # plat prints to 0.01 ft
GEOM_TOL_FT = 0.02  # internal-geometry identities (engine values are exact floats; this is generous)
ANG_TOL_ARCSEC = 5.0

D36 = 36.0 + 20.0 / 60.0
D37 = 37.0 + 42.0 / 60.0 + 50.0 / 3600.0
D52 = 52.0 + 17.0 / 60.0 + 10.0 / 3600.0

# F7 fixed 2026-09-24: the fictitious Beachwood Blvd curve is gone (the Blvd is straight, derived in
# engine/centerline_geometry.py), so it is no longer audited as a curve.
CIDS = ["C_SANSALVADORE_CL", "C_CAPEHORN_CL", "C_MARINA_CL", "C_SANDS_CL", "C_KEEL_CL"]
PI_KEY = {
    "C_SANSALVADORE_CL": "SANSALVADORE",
    "C_CAPEHORN_CL": "CAPEHORN",
    "C_MARINA_CL": "MARINA",
    "C_SANDS_CL": "SANDS",
    "C_KEEL_CL": "KEEL",
    "C_BEACHWOOD_BLVD_CL": "BLVD",
}

# --- plat "CL Curve Data" blocks: R, delta, T are the ONLY three values printed in each block. -----------------------
# Source of these constants: lead's training-image reading, re-checked by the auditor on the 300 dpi scans
# (Sheet 1: San Salvadore, Cape Horn; Sheet 2: Marina, Sands, Keel, Shellfish).  UNVERIFIED until a reader JSON lands.
STATED_CONST: dict[str, dict | None] = {
    "C_SANSALVADORE_CL": {"match": ("salvador",), "radius": 269.96, "delta_deg": D36, "tangent": 88.59},
    "C_CAPEHORN_CL": {"match": ("cape",), "radius": 327.01, "delta_deg": D36, "tangent": 107.31},
    "C_MARINA_CL": {"match": ("marina",), "radius": 359.27, "delta_deg": D37, "tangent": 122.70},
    "C_SANDS_CL": {"match": ("sands",), "radius": 459.36, "delta_deg": D36, "tangent": 150.73},
    "C_KEEL_CL": {"match": ("keel", "shellfish"), "radius": 143.93, "delta_deg": D52, "tangent": 70.65},
    "C_BEACHWOOD_BLVD_CL": None,  # no CL block on the plat; R=1959.86 is the East R/W curve C2
}
# The sixth plat CL block that the engine does not model at all (Shellfish Drive east branch, Sheet 2).
SHELLFISH_CL_STATED = {"radius": 167.95, "delta_deg": D52, "tangent": 82.35}

# Tangent orientation read off the scans (auditor's observation): travelling PC -> PT, west to east, all four
# diagonal-street curves turn RIGHT (CW) from an E-W tangent onto the diagonal N54 41'40"W / S54 41'40"E.
DIAG = "S54°41'40\"E"
EXPECTED_ORIENT = {
    "C_SANSALVADORE_CL": {"back": "N88°58'20\"E", "forward": DIAG, "direction": "CW"},
    "C_CAPEHORN_CL": {"back": "N88°58'20\"E", "forward": DIAG, "direction": "CW"},
    "C_SANDS_CL": {"back": "N88°58'20\"E", "forward": DIAG, "direction": "CW"},
    "C_MARINA_CL": {"back": "N87°35'30\"E", "forward": DIAG, "direction": "CW"},
    "C_KEEL_CL": {"back": "N35°18'20\"E", "forward": "N87°35'30\"E", "direction": "CW"},
}
# Plat lot-line chords that independently fix an R/W-edge radius (chord, delta of that lot arc, sheet evidence).
PLAT_EDGE_EVIDENCE = {
    "C_MARINA_CL": [("Marina N R/W, lots 29-31 (chord 85.24, d=12°34'17\")", 85.24, 12 + 34 / 60 + 17 / 3600, 389.27)],
    "C_KEEL_CL": [("Keel S R/W inner arc (chord 100.40, d=52°17'10\")", 100.40, D52, 113.93)],
}


# ----------------------------------------------------------------------------------------------------------------
# small independent geometry (deliberately NOT the engine's helpers)
# ----------------------------------------------------------------------------------------------------------------
def wrap180(x: float) -> float:
    return (x + 180.0) % 360.0 - 180.0


def az(a: Point, b: Point) -> float:
    return math.degrees(math.atan2(b.e - a.e, b.n - a.n)) % 360.0


def dms(deg: float, places: int = 0) -> str:
    deg = abs(deg)
    total = round(deg * 3600.0, places)
    d = int(total // 3600)
    m = int((total - d * 3600) // 60)
    s = total - d * 3600 - m * 60
    return f"{d}°{m:02d}'{s:0{3 + places if places else 2}.{places}f}\""


def tan_len(r: float, d: float) -> float:
    return r * math.tan(math.radians(d) / 2.0)


def arc_len(r: float, d: float) -> float:
    return r * math.radians(d)


def chord_len(r: float, d: float) -> float:
    return 2.0 * r * math.sin(math.radians(d) / 2.0)


def try_az(text: str) -> float | None:
    try:
        return parse_bearing(text)
    except (ValueError, TypeError):
        return None


def load_readings() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(DATA_DIR.glob("readings_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            data = data.get("readings", [])
        for r in data:
            if isinstance(r, dict):
                rows.append({**r, "_file": path.name})
    return rows


def stated_for(cid: str, readings: list[dict] | None = None) -> dict | None:
    """Stated CL block for an engine curve: reader JSON (when present) overrides the UNVERIFIED constants."""
    const = STATED_CONST.get(cid)
    if const is None:
        return None
    out = {k: const[k] for k in ("radius", "delta_deg", "tangent")}
    out["source"] = dict.fromkeys(out, "UNVERIFIED audit constant")
    cands = [
        r
        for r in (readings or [])
        if r.get("kind") == "centerline"
        and any(m in f"{r.get('street', '')} {r.get('id', '')}".lower() for m in const["match"])
        and r.get("radius") is not None
    ]
    if cands:  # Keel/Shellfish have two blocks: take the one whose radius is closest to the engine constant
        best = min(cands, key=lambda r: abs(r["radius"] - const["radius"]))
        for k in ("radius", "delta_deg", "tangent"):
            if best.get(k) is not None:
                out[k] = float(best[k])
                out["source"][k] = f"{best['_file']}:{best.get('id')} conf={best.get('confidence')}"
    return out


# ----------------------------------------------------------------------------------------------------------------
# per-curve metrics
# ----------------------------------------------------------------------------------------------------------------
def build_engine() -> BeachwoodRoadCenterlineEngine:
    return BeachwoodRoadCenterlineEngine()


def pi_rays(engine: BeachwoodRoadCenterlineEngine, cid: str) -> tuple:
    key = PI_KEY[cid]
    ray_in = next(s for s in engine.pi_tangents if s.id == f"PI_RAY_{key}_IN")
    ray_out = next(s for s in engine.pi_tangents if s.id == f"PI_RAY_{key}_OUT")
    return ray_in, ray_out


def drawn_arc_end(c) -> Point:
    """Arc end exactly as export_dxf / render_cad_centerlines_drawing build it (centre, PC azimuth, +/- delta)."""
    a0 = math.atan2(c.pc_point.e - c.center_point.e, c.pc_point.n - c.center_point.n)
    a1 = a0 + math.radians(c.delta_deg) * (1.0 if c.direction == "CW" else -1.0)
    return Point(c.center_point.n + c.radius * math.cos(a1), c.center_point.e + c.radius * math.sin(a1))


def engine_metrics(engine: BeachwoodRoadCenterlineEngine, cid: str) -> dict:
    c = engine.curves[cid]
    ray_in, ray_out = pi_rays(engine, cid)
    sgn = 1.0 if c.direction == "CW" else -1.0
    pc, pt, pi, ctr = c.pc_point, c.pt_point, c.pi_point, c.center_point
    back_az = az(pc, pi)
    d = c.delta_deg
    chord_az_label = parse_bearing(c.chord_bearing)
    chord_az_expected = (back_az + sgn * d / 2.0) % 360.0
    fwd_expected = (back_az + sgn * d) % 360.0
    out_label_az = try_az(ray_out.bearing)
    in_label_az = try_az(ray_in.bearing)
    # interior angle at the PI between PI->PC and PI->PT
    v1 = (pc.n - pi.n, pc.e - pi.e)
    v2 = (pt.n - pi.n, pt.e - pi.e)
    pi_angle = math.degrees(math.atan2(abs(v1[0] * v2[1] - v1[1] * v2[0]), v1[0] * v2[0] + v1[1] * v2[1]))
    ia, oa = c.get_offset_arcs()
    end = drawn_arc_end(c)
    inner_toward = az(pc, ctr)
    return {
        "id": cid,
        "street": c.street_name,
        "R": c.radius,
        "delta": d,
        "direction": c.direction,
        "L": c.arc_length,
        "T": c.tangent,
        "C": c.chord_length,
        "hw": c.half_width,
        "back_az": back_az,
        "pi_in_label": ray_in.bearing,
        "pi_out_label": ray_out.bearing,
        "pi_in_label_az": in_label_az,
        "pi_out_label_az": out_label_az,
        "r_pc": pc.dist_to(ctr),
        "r_pt": pt.dist_to(ctr),
        "pc_pi": pc.dist_to(pi),
        "pi_pt": pi.dist_to(pt),
        "pi_angle": pi_angle,
        "turn_at_pi": wrap180(az(pi, pt) - back_az),
        "center_side": wrap180(inner_toward - back_az),
        "chord_label": c.chord_bearing,
        "chord_label_az": chord_az_label,
        "chord_az_expected": chord_az_expected,
        "chord_resid_arcsec": wrap180(chord_az_label - chord_az_expected) * 3600.0,
        "chord_az_geom": az(pc, pt),
        "fwd_expected_az": fwd_expected,
        "pi_out_resid_deg": None if out_label_az is None else wrap180(out_label_az - fwd_expected),
        "pi_out_geom_az": az(pi, pt),
        "drawn_end_gap": end.dist_to(pt),
        "drawn_tangent_az_at_pc": (math.degrees(math.atan2(pc.e - ctr.e, pc.n - ctr.n)) + sgn * 90.0) % 360.0,
        "inner_R": ia["radius"],
        "outer_R": oa["radius"],
        "inner_dir_az": inner_toward,
        "T_formula": tan_len(c.radius, d),
        "L_formula": arc_len(c.radius, d),
        "C_formula": chord_len(c.radius, d),
    }


def checks_for(m: dict) -> list[tuple[str, float | str, str, bool]]:
    """(name, value, limit, ok) geometry identities for one curve (B section)."""
    turn_dir = "CW" if m["turn_at_pi"] > 1e-6 else ("CCW" if m["turn_at_pi"] < -1e-6 else "STRAIGHT")
    side_dir = "CW" if m["center_side"] > 0 else "CCW"
    tan_at_pc_err = abs(wrap180(m["drawn_tangent_az_at_pc"] - m["back_az"]))
    out = [
        ("|PC-CTR| = R", m["r_pc"] - m["R"], f"{GEOM_TOL_FT}", abs(m["r_pc"] - m["R"]) <= GEOM_TOL_FT),
        ("|PT-CTR| = R", m["r_pt"] - m["R"], f"{GEOM_TOL_FT}", abs(m["r_pt"] - m["R"]) <= GEOM_TOL_FT),
        ("|PC-PI| = T", m["pc_pi"] - m["T_formula"], f"{GEOM_TOL_FT}", abs(m["pc_pi"] - m["T_formula"]) <= GEOM_TOL_FT),
        ("|PI-PT| = T", m["pi_pt"] - m["T_formula"], f"{GEOM_TOL_FT}", abs(m["pi_pt"] - m["T_formula"]) <= GEOM_TOL_FT),
        (
            "angle at PI = 180-delta",
            m["pi_angle"] - (180.0 - m["delta"]),
            f'{ANG_TOL_ARCSEC}"',
            abs(m["pi_angle"] - (180.0 - m["delta"])) * 3600 <= ANG_TOL_ARCSEC,
        ),
        ("turn at PI matches flag", f"{turn_dir} vs {m['direction']}", "equal", turn_dir == m["direction"]),
        ("centre side matches flag", f"{side_dir} vs {m['direction']}", "equal", side_dir == m["direction"]),
        (
            "drawn tangent at PC = PC->PI",
            tan_at_pc_err,
            f"{ANG_TOL_ARCSEC / 3600:.4f} deg",
            tan_at_pc_err * 3600 <= ANG_TOL_ARCSEC,
        ),
        ("drawn arc ends at PT", m["drawn_end_gap"], f"{GEOM_TOL_FT}", m["drawn_end_gap"] <= GEOM_TOL_FT),
        (
            f"chord label {m['chord_label']} vs analytic",
            m["chord_resid_arcsec"],
            f'{ANG_TOL_ARCSEC}" (+/-)',
            abs(m["chord_resid_arcsec"]) <= ANG_TOL_ARCSEC,
        ),
    ]
    if m["pi_out_resid_deg"] is None:
        out.append((f"P.I. out label {m['pi_out_label']!r}", "NOT A VALID BEARING", "parses", False))
    else:
        out.append(
            (
                f"P.I. out label {m['pi_out_label']} vs analytic",
                m["pi_out_resid_deg"] * 3600.0,
                f'{ANG_TOL_ARCSEC}" (+/-)',
                abs(m["pi_out_resid_deg"]) * 3600 <= ANG_TOL_ARCSEC,
            )
        )
    out.append(
        (
            "T,L,C stored = formulas(R,delta)",
            max(abs(m["T"] - m["T_formula"]), abs(m["L"] - m["L_formula"]), abs(m["C"] - m["C_formula"])),
            f"{PLAT_TOL_FT}",
            max(abs(m["T"] - m["T_formula"]), abs(m["L"] - m["L_formula"]), abs(m["C"] - m["C_formula"]))
            <= PLAT_TOL_FT,
        )
    )
    return out


def orientation_check(engine: BeachwoodRoadCenterlineEngine, cid: str) -> dict | None:
    exp = EXPECTED_ORIENT.get(cid)
    if exp is None:
        return None
    m = engine_metrics(engine, cid)
    e_back = parse_bearing(exp["back"])
    e_fwd = parse_bearing(exp["forward"])
    return {
        "expected_back": exp["back"],
        "expected_forward": exp["forward"],
        "expected_direction": exp["direction"],
        "engine_back_az": m["back_az"],
        "engine_direction": m["direction"],
        "back_resid_deg": wrap180(m["back_az"] - e_back),
        "engine_pi_out_geom_az": m["pi_out_geom_az"],
        "fwd_resid_deg": wrap180(m["pi_out_geom_az"] - e_fwd),
        "ok": abs(wrap180(m["back_az"] - e_back)) < 1e-3 and m["direction"] == exp["direction"],
    }


def edge_check(m: dict, stated: dict | None) -> dict:
    """R/W-edge radii the engine would draw vs CL +/- half width of the STATED CL radius."""
    out = {"engine_edges": (m["inner_R"], m["outer_R"]), "expected_edges": None, "ok": None, "evidence": []}
    if stated is not None:
        exp = (stated["radius"] - m["hw"], stated["radius"] + m["hw"])
        out["expected_edges"] = exp
        out["ok"] = all(abs(a - b) <= PLAT_TOL_FT for a, b in zip(out["engine_edges"], exp, strict=True))
    for label, chord, d, r_expected in PLAT_EDGE_EVIDENCE.get(m["id"], []):
        r_from_chord = chord / (2.0 * math.sin(math.radians(d) / 2.0))
        in_engine = any(abs(r_from_chord - e) <= 0.05 for e in out["engine_edges"])
        out["evidence"].append((label, r_from_chord, r_expected, in_engine))
    return out


# ----------------------------------------------------------------------------------------------------------------
# engine-wide checks
# ----------------------------------------------------------------------------------------------------------------
def validator_probe() -> list[tuple[str, bool]]:
    """Does validate_all_curves() notice a corrupted curve?  (True = detected.)  It should for every probe."""
    results = []

    def run(label: str, mutate) -> None:
        eng = build_engine()
        mutate(eng.curves)
        res = eng.validate_all_curves()
        results.append((label, not all(v["is_valid"] for v in res.values())))

    def centre_500ft(cs):
        cs["C_SANDS_CL"].center_point = Point(cs["C_SANDS_CL"].center_point.n + 500.0, cs["C_SANDS_CL"].center_point.e)

    def centre_flip(cs):
        c = cs["C_MARINA_CL"]
        c.center_point = Point(2 * c.pc_point.n - c.center_point.n, 2 * c.pc_point.e - c.center_point.e)

    def dir_flip(cs):
        cs["C_MARINA_CL"].direction = "CCW"

    def radius_plus_30(cs):  # what the San Salvadore / Marina bug does: R+30 with T/L/C recomputed consistently
        c = cs["C_CAPEHORN_CL"]
        r = c.radius + 30.0
        c.radius = r
        c.arc_length, c.tangent, c.chord_length = (
            arc_len(r, c.delta_deg),
            tan_len(r, c.delta_deg),
            chord_len(r, c.delta_deg),
        )
        c.pt_point = c.pc_point.offset(parse_bearing(c.chord_bearing), c.chord_length)

    def pt_moved_15cm(cs):
        c = cs["C_KEEL_CL"]
        c.pt_point = Point(c.pt_point.n + 0.15, c.pt_point.e)

    run("Sands centre moved 500 ft", centre_500ft)
    run("Marina centre reflected to wrong side of PC", centre_flip)
    run("Marina direction flag flipped CW->CCW", dir_flip)
    run("Cape Horn R+30 with T/L/C/PT recomputed", radius_plus_30)
    run("Keel PT moved 0.15 ft (tolerance is 0.2 ft)", pt_moved_15cm)
    return results


def culdesac_checks(engine: BeachwoodRoadCenterlineEngine) -> list[tuple[str, float, bool]]:
    # The Keel cul-de-sac was removed from the engine 2026-09-24 (not on the plat: Block 7 Lots 30-37 are continuous
    # SW of Marina at Keel). Nothing to audit when no cul-de-sac is modelled.
    if not any(c["id"] == "CULDESAC_KEEL_DRIVE" for c in engine.culdesacs):
        return []
    g = engine.get_culdesac_geometry("CULDESAC_KEEL_DRIVE")
    cds = next(c for c in engine.culdesacs if c["id"] == "CULDESAC_KEEL_DRIVE")
    rb, rf, w = cds["bulb_radius_ft"], cds["reverse_fillet_radius_ft"], cds["right_of_way_width_ft"] / 2.0
    cp = g["center_point"]
    axis = parse_bearing("S35°18'20\"W")
    checks = []
    yf = math.sqrt((rb + rf) ** 2 - (w + rf) ** 2)
    checks.append(
        ("yf = sqrt((Rb+Rf)^2-(w+Rf)^2)", g["throat_distance_yf_ft"] - yf, abs(g["throat_distance_yf_ft"] - yf) < 1e-9)
    )
    th = math.degrees(math.asin((w + rf) / (rb + rf)))
    checks.append(("theta_prc = asin((w+Rf)/(Rb+Rf))", g["theta_prc_deg"] - th, abs(g["theta_prc_deg"] - th) < 1e-9))
    checks.append(
        (
            "delta_bulb = 360 - 2 theta",
            g["delta_bulb_deg"] - (360 - 2 * th),
            abs(g["delta_bulb_deg"] - (360 - 2 * th)) < 1e-9,
        )
    )
    for side, pc_key, c_key, prc_key in (
        ("left", "pc_left", "center_left_fillet", "prc_left"),
        ("right", "pt_right", "center_right_fillet", "prc_right"),
    ):
        c, pc, prc = g[c_key], g[pc_key], g[prc_key]
        checks.append((f"{side}: |C-PC| = Rf", c.dist_to(pc) - rf, abs(c.dist_to(pc) - rf) < 1e-9))
        radial = wrap180(az(pc, c) - axis)  # fillet radius must be perpendicular to the R/W edge line
        checks.append(
            (f"{side}: fillet radius perpendicular to edge", abs(radial) - 90.0, abs(abs(radial) - 90.0) < 1e-6)
        )
        checks.append(
            (
                f"{side}: |C-CP| = Rb+Rf (external tangency)",
                c.dist_to(cp) - (rb + rf),
                abs(c.dist_to(cp) - (rb + rf)) < 1e-9,
            )
        )
        checks.append((f"{side}: |PRC-CP| = Rb", prc.dist_to(cp) - rb, abs(prc.dist_to(cp) - rb) < 1e-9))
        cross = (c.n - cp.n) * (prc.e - cp.e) - (c.e - cp.e) * (prc.n - cp.n)
        checks.append((f"{side}: PRC on line CP-C", cross, abs(cross) < 1e-6))
    pts = g["boundary_pts"]
    gap = max(pts[i].dist_to(pts[i + 1]) for i in range(len(pts) - 1))
    checks.append(("polyline max vertex gap < 10 ft", gap, gap < 10.0))
    checks.append(
        (
            "throat width = 2 w",
            g["pc_left"].dist_to(g["pt_right"]) - 2 * w,
            abs(g["pc_left"].dist_to(g["pt_right"]) - 2 * w) < 1e-9,
        )
    )
    return checks


def frontage_reconciliation(engine: BeachwoodRoadCenterlineEngine) -> list[dict]:
    rows = []
    for s in engine.segments:
        if not s.summed_lot_frontages:
            continue
        total = sum(f["frontage_ft"] for f in s.summed_lot_frontages)
        geom_az = az(s.start_point, s.end_point)
        lab = try_az(s.bearing)
        rows.append(
            {
                "id": s.id,
                "sum": total,
                "distance": s.distance,
                "sum_minus_distance": total - s.distance,
                "label": s.bearing,
                "label_vs_geometry_deg": None if lab is None else wrap180(geom_az - lab),
                "plug": [f["frontage_ft"] for f in s.summed_lot_frontages if "component" in f],
            }
        )
    return rows


def parent_boundary_c22(engine: BeachwoodRoadCenterlineEngine) -> dict:
    r, chord = (
        894.08,
        99.98,
    )  # plat caption: "curve to the left ... radius 894.08 ... chord 99.98" (chord bearing S57 53'59"E)
    delta = 2.0 * math.asin(chord / (2.0 * r))
    seg = 0.5 * r * r * (delta - math.sin(delta))
    pts = engine.boundary_points
    signed = 0.5 * sum(pts[i].e * pts[i + 1].n - pts[i + 1].e * pts[i].n for i in range(len(pts) - 1))
    sign = 1.0 if signed > 0 else -1.0  # CCW traverse + left-turning curve => arc bulges outward => area increases
    c21_back = parse_bearing("S54°41'40\"E")
    c22_chord = parse_bearing("S57°53'59\"E")
    return {
        "delta_from_chord_deg": math.degrees(delta),
        "delta_from_tangents_deg": 2.0 * wrap180(c21_back - c22_chord),
        "arc_length_from_chord": r * delta,
        "segment_area_sqft": seg,
        "traverse_ccw": signed > 0,
        "engine_area": engine.boundary_metrics["parent_area_sqft"],
        "expected_area": engine.boundary_metrics["parent_area_sqft"] + sign * seg,
        "raw_course": next(c for c in RAW_BOUNDARY_COURSES if c[0] == "c22"),
    }


def curves_py_fuzz(trials: int = 60) -> dict:
    rnd = random.Random(7)
    keys = ["radius", "delta_deg", "length", "chord", "tangent", "mid_ordinate", "external", "degree_curve"]
    bad_pairs: dict[tuple[str, str], int] = {}
    n = 0
    for _ in range(trials):
        r = rnd.uniform(20, 2000)
        d = rnd.uniform(0.5, 90.0)
        h = math.radians(d) / 2
        truth = {
            "radius": r,
            "delta_deg": d,
            "length": r * 2 * h,
            "chord": 2 * r * math.sin(h),
            "tangent": r * math.tan(h),
            "mid_ordinate": r * (1 - math.cos(h)),
            "external": r * (1 / math.cos(h) - 1),
            "degree_curve": 5729.57795 / r,
        }
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                if {a, b} == {"radius", "degree_curve"}:
                    continue  # collinear by design (raises)
                n += 1
                try:
                    res = solve_curve_all_parameters(**{a: truth[a], b: truth[b]})
                    ok = abs(res["radius"] - r) / r < 2e-4 and abs(res["delta_deg"] - d) < 2e-3 * max(1.0, d / 10)
                except Exception:
                    ok = False
                if not ok:
                    bad_pairs[(a, b)] = bad_pairs.get((a, b), 0) + 1
    # out-of-domain (delta > ~100 deg): garbage returned instead of an error
    garbage = None
    r, d = 218.0, 134.8
    try:
        res = solve_curve_all_parameters(length=arc_len(r, d), tangent=tan_len(r, d))
        garbage = (res["radius"], res["delta_deg"])
    except Exception as exc:  # noqa: BLE001
        garbage = f"raised {type(exc).__name__}"
    # Curve.arc_points vs independent construction, both senses
    worst = 0.0
    for _ in range(300):
        r = rnd.uniform(20, 2000)
        d = rnd.uniform(1, 120)
        rot = rnd.choice(["CW", "CCW"])
        s = 1.0 if rot == "CW" else -1.0
        back = rnd.uniform(0, 360)
        pc = Point(rnd.uniform(0, 1e4), rnd.uniform(0, 1e4))
        chord_az = (back + s * d / 2) % 360
        cur = EngineCurve("x", arc_len(r, d), r, d, azimuth_to_bearing(chord_az, cardinal=False), chord_len(r, d), rot)
        rp = pc.offset(back + s * 90, r)
        pt = rp.offset(back + s * 90 + 180 + s * d, r)
        worst = max(worst, cur.arc_points(pc, 8)[-1].dist_to(pt))
    # trace_curve_from_skeleton with an infeasible chord (chord 74.86 vs R=25)
    silent_radius = None
    try:
        cv = trace_curve_from_skeleton("probe", Point(0.0, 0.0), Point(74.86, 0.0), 25.0, [], fallback_rot="CW")
        silent_radius = cv.radius
    except ValueError:
        silent_radius = "raised ValueError"
    return {
        "solver_pairs_tested": n,
        "solver_bad_pairs_delta_le_90": bad_pairs,
        "out_of_domain_result": garbage,
        "arc_points_worst_end_err_ft": worst,
        "trace_infeasible_chord_radius": silent_radius,
    }


def core_crosscheck(engine: BeachwoodRoadCenterlineEngine) -> list[dict] | None:
    if _core is None:
        return None
    rows = []
    for cid in CIDS:
        c = engine.curves[cid]
        try:
            cur = _core.Curve(c.radius, c.delta_deg, c.direction)
            placed = _core.PlacedCurve(cur, (c.pc_point.n, c.pc_point.e), az(c.pc_point, c.pi_point))
        except Exception as exc:  # noqa: BLE001
            rows.append({"id": cid, "error": str(exc)})
            continue
        rows.append(
            {
                "id": cid,
                "dT": c.tangent - cur.tangent,
                "dL": c.arc_length - cur.arc_length,
                "dC": c.chord_length - cur.chord,
                "pt_gap": math.hypot(placed.pt[0] - c.pt_point.n, placed.pt[1] - c.pt_point.e),
                "pi_gap": math.hypot(placed.pi[0] - c.pi_point.n, placed.pi[1] - c.pi_point.e),
                "core_chord": placed.chord_bearing,
            }
        )
    return rows


# ----------------------------------------------------------------------------------------------------------------
# report
# ----------------------------------------------------------------------------------------------------------------
def _hdr(title: str) -> None:
    print("\n" + "=" * 118 + f"\n{title}\n" + "=" * 118)


def _verdict(ok: bool | None) -> str:
    return "n/a " if ok is None else ("ok  " if ok else "FAIL")


def run_audit(strict: bool = False, json_path: str | None = None) -> int:
    engine = build_engine()
    readings = load_readings()
    n_fail = 0
    summary: dict[str, dict] = {}
    print("ENGINE CURVE AUDIT  (engine/cogo_road_centerlines.py, engine/curves.py)   READ-ONLY")
    print(
        f"reader JSON files found: {sorted({r['_file'] for r in readings}) or 'none'}  -> stated values marked UNVERIFIED when not from a reader"
    )
    print(f"plat_curves.core importable: {'yes' if _core else 'no (cross-check skipped)'}")

    for cid in CIDS:
        m = engine_metrics(engine, cid)
        stated = stated_for(cid, readings)
        _hdr(f"{cid}  ({m['street']})   engine: R={m['R']:.2f} delta={dms(m['delta'])} dir={m['direction']}")
        print("A. engine vs stated CL Curve Data")
        cur_fail = 0
        if stated is None:
            neg = next(
                (
                    r
                    for r in readings
                    if r.get("is_negative_result") and "beachwood" in str(r.get("street", "")).lower()
                ),
                None,
            )
            print(
                "   no CL Curve Data block for Beachwood Blvd on either sheet; the token 1959.86 does not appear on the scan."
            )
            if neg:
                print(
                    f"   reader NEGATIVE result ({neg['_file']}:{neg['id']}, conf {neg.get('confidence')}): {neg.get('derived_check')}"
                )
            print(
                f"   -> FAIL: engine models a CL curve the plat does not show (delta {dms(m['delta'])} back-derived from the 260.00 chord)."
            )
            cur_fail += 1
        else:
            print(f"   {'quantity':<9}{'engine':>12}{'stated':>12}{'residual':>11}  verdict  source")
            t_calc = tan_len(stated["radius"], stated["delta_deg"])
            rows = [
                ("R", m["R"], stated["radius"], stated["source"]["radius"]),
                ("delta", m["delta"], stated["delta_deg"], stated["source"]["delta_deg"]),
                ("T", m["T"], stated["tangent"], stated["source"]["tangent"]),
                (
                    "L",
                    m["L"],
                    arc_len(stated["radius"], stated["delta_deg"]),
                    "derived from stated R,delta (not printed on plat)",
                ),
                (
                    "C",
                    m["C"],
                    chord_len(stated["radius"], stated["delta_deg"]),
                    "derived from stated R,delta (not printed on plat)",
                ),
            ]
            for name, e, s_, src in rows:
                tol = 1e-4 if name == "delta" else PLAT_TOL_FT
                ok = abs(e - s_) <= tol
                cur_fail += 0 if ok else 1
                print(f"   {name:<9}{e:12.4f}{s_:12.4f}{e - s_:+11.4f}  {_verdict(ok)}    {src}")
            if abs(t_calc - stated["tangent"]) > PLAT_TOL_FT:
                print(
                    f"   note: stated T {stated['tangent']} vs T(R,delta) {t_calc:.4f}: plat block is itself inconsistent by {stated['tangent'] - t_calc:+.4f}"
                )
            dr = m["R"] - stated["radius"]
            for k in (30.0, 60.0):
                if abs(abs(dr) - k) < 0.02:
                    print(
                        f"   diagnosis: engine R differs from the stated CL R by {dr:+.2f} = {'one' if k == 30 else 'two'} half-width(s) of a 60' R/W"
                    )
        print("B. internal geometry")
        for name, val, lim, ok in checks_for(m):
            vs = f"{val:+.4f}" if isinstance(val, float) else str(val)
            cur_fail += 0 if ok else 1
            print(f"   [{_verdict(ok)}] {name:<42}{vs:>26}   limit {lim}")
        print("C. orientation / R/W edges")
        oc = orientation_check(engine, cid)
        if oc is None:
            print("   orientation: n/a")
        else:
            cur_fail += 0 if oc["ok"] else 1
            print(
                f"   [{_verdict(oc['ok'])}] plat: travel W->E, back tangent {oc['expected_back']} -> forward {oc['expected_forward']}, {oc['expected_direction']};"
                f" engine back az {oc['engine_back_az']:.4f} ({oc['back_resid_deg']:+.4f} deg), flag {oc['engine_direction']}"
            )
        ec = edge_check(m, stated)
        e_in, e_out = ec["engine_edges"]
        if ec["expected_edges"]:
            x_in, x_out = ec["expected_edges"]
            cur_fail += 0 if ec["ok"] else 1
            print(
                f"   [{_verdict(ec['ok'])}] get_offset_arcs radii {e_in:.2f} / {e_out:.2f}   vs stated CL -/+ {m['hw']:.0f}: {x_in:.2f} / {x_out:.2f}"
            )
        else:
            print(f"   get_offset_arcs radii {e_in:.2f} / {e_out:.2f} (no stated CL to compare)")
        print(
            f"        inner (R-hw) edge lies toward {azimuth_to_bearing(m['inner_dir_az'])} of the PC (centre side); outer edge opposite"
        )
        for label, r_chord, r_exp, in_engine in ec["evidence"]:
            print(
                f"   plat lot-chord evidence: {label} -> R={r_chord:.2f} (expected {r_exp}); engine draws that edge: {'yes' if in_engine else 'NO'}"
            )
        verdict = "OK" if cur_fail == 0 else f"FAIL ({cur_fail} checks)"
        print(f"   VERDICT {cid}: {verdict}")
        n_fail += cur_fail
        summary[cid] = {"fails": cur_fail, "engine_R": m["R"], "stated_R": None if stated is None else stated["radius"]}

    _hdr("C2. plat CL blocks the engine does not model")
    sh = SHELLFISH_CL_STATED
    print(
        f"   Shellfish Dr CL curve: R={sh['radius']} delta={dms(sh['delta_deg'])} T={sh['tangent']} (Sheet 2, west of Block 15); no engine curve, no PC/PT/PI, no R/W edges"
    )
    print(
        f"   T(R,delta) = {tan_len(sh['radius'], sh['delta_deg']):.4f} vs printed {sh['tangent']}: plat block itself disagrees by"
        f" {sh['tangent'] - tan_len(sh['radius'], sh['delta_deg']):+.4f} ft (> {PLAT_TOL_FT}); R supported by printed edge chords (121.56 on R-30, 51.68/68.75/59.50 on R+30)"
    )
    n_fail += 1  # a whole CL curve is absent from the engine

    _hdr("D. validate_all_curves() -- can it fail?  (a validator must flag every probe below)")
    res = engine.validate_all_curves()
    print(
        f"   as shipped: {sum(v['is_valid'] for v in res.values())}/{len(res)} curves valid; diff_arc/diff_tan/diff_chord are exactly 0 for "
        f"{sum(1 for v in res.values() if v['diff_arc'] < 1e-3)}/{len(res)} (compares stored L,T,C with formulas of the SAME R,delta)"
    )
    for label, detected in validator_probe():
        print(f"   [{_verdict(detected)}] detects: {label}")
        n_fail += 0 if detected else 1

    _hdr("E. cul-de-sac construction (get_culdesac_geometry)")
    for name, val, ok in culdesac_checks(engine):
        n_fail += 0 if ok else 1
        print(f"   [{_verdict(ok)}] {name:<46}{val:+.6f}")

    _hdr("F. frontage summations (summed_lot_frontages vs drawn distance / label bearing)")
    print(f"   {'segment':<30}{'sum':>10}{'dist':>10}{'sum-dist':>10}{'label vs geom':>15}  plug components")
    for r in frontage_reconciliation(engine):
        lg = "invalid" if r["label_vs_geometry_deg"] is None else f"{r['label_vs_geometry_deg']:+.2f} deg"
        bad = abs(r["sum_minus_distance"]) > 0.05 or (
            r["label_vs_geometry_deg"] is None or abs(r["label_vs_geometry_deg"]) > 0.01
        )
        n_fail += 1 if bad else 0
        print(
            f"   {r['id']:<30}{r['sum']:10.2f}{r['distance']:10.2f}{r['sum_minus_distance']:+10.2f}{lg:>15}  {r['plug'] or ''} {'<-- FAIL' if bad else ''}"
        )
    print("   arithmetic inside the entries:")
    sail = next(s for s in engine.segments if s.id == "SEG_SAIL_MAIN").summed_lot_frontages[0]
    par = 68.50 + 7 * 75.00
    print(
        f"   [{_verdict(abs(par - sail['frontage_ft']) < 0.01)}] SEG_SAIL_MAIN Block 16 lots 1-8 entry {sail['frontage_ft']:.2f} vs its own note '68.50 straight + 7x75.00' = {par:.2f}"
    )
    n_fail += 0 if abs(par - sail["frontage_ft"]) < 0.01 else 1
    lot1_arc = arc_len(167.95, D52)
    print(
        f"   [FAIL] SEG_ASSUMP_SHELLFISH_KEEL Block 15 lot 1 entry 153.25 = full CL arc L(R=167.95, 52°17'10\") = {lot1_arc:.2f};"
        f" the plat's lot-side chord there is 121.56 (R~{121.56 / chord_len(1.0, D52):.2f}, i.e. 167.95-30), arc {arc_len(121.56 / chord_len(1.0, D52), D52):.2f}"
    )
    n_fail += 1

    _hdr("G. parent-boundary curve c22 (R=894.08')")
    p = parent_boundary_c22(engine)
    print(f"   raw course: {p['raw_course']}")
    print(
        f"   delta from chord 99.98 & R: {dms(p['delta_from_chord_deg'], 1)};  from c21 back-tangent vs chord bearing: {dms(p['delta_from_tangents_deg'], 1)}"
        f"  (engine/prior notes carry 6°24'25\" / L=100.00; arc from chord = {p['arc_length_from_chord']:.2f})"
    )
    print(
        f"   traverse is {'CCW' if p['traverse_ccw'] else 'CW'}; plat says curve to the LEFT => arc bulges outward; parent area omits the segment:"
        f" engine {p['engine_area']:.2f} vs chord-polygon + segment ({p['segment_area_sqft']:.2f}) = {p['expected_area']:.2f}"
    )
    ok = abs(p["engine_area"] - p["expected_area"]) < 1.0
    n_fail += 0 if ok else 1
    print(f"   [{_verdict(ok)}] parent_area_sqft includes the curve segment")

    _hdr("H. engine/curves.py")
    fz = curves_py_fuzz()
    print(
        f"   solve_curve_all_parameters: {fz['solver_pairs_tested']} pair solves (delta<=90): bad pairs = {fz['solver_bad_pairs_delta_le_90'] or 'none'}"
    )
    print(
        f"   out-of-domain (length+tangent, delta=134.8): {fz['out_of_domain_result']}  <- garbage returned instead of ValueError"
    )
    print(
        f"   Curve.arc_points worst end error over 300 random CW/CCW curves: {fz['arc_points_worst_end_err_ft']:.2e} ft"
    )
    print(
        f"   trace_curve_from_skeleton(R=25, chord=74.86): radius silently becomes {fz['trace_infeasible_chord_radius']}"
        " (should raise: chord > 2R is the off-by-one-edge signature)"
    )
    n_fail += 1 if not isinstance(fz["trace_infeasible_chord_radius"], str) else 0
    n_fail += 0 if not fz["solver_bad_pairs_delta_le_90"] else 1

    cc = core_crosscheck(engine)
    if cc is not None:
        _hdr("I. plat_curves.core oracle vs engine (core placed from PC, back az = PC->PI, engine R/delta/flag)")
        for r in cc:
            if "error" in r:
                print(f"   {r['id']}: core error {r['error']}")
            else:
                print(
                    f"   {r['id']:<22} dT={r['dT']:+.4f} dL={r['dL']:+.4f} dC={r['dC']:+.4f}  PT gap={r['pt_gap']:.3f} ft  PI gap={r['pi_gap']:.3f} ft  core chord {r['core_chord']}"
                )

    _hdr("SUMMARY")
    for cid, s in summary.items():
        sr = "n/a" if s["stated_R"] is None else f"{s['stated_R']:.2f}"
        print(f"   {cid:<22} engine R {s['engine_R']:9.2f}   plat CL R {sr:>8}   failing checks: {s['fails']}")
    print(f"   TOTAL failing checks (all sections): {n_fail}")
    if json_path:
        Path(json_path).write_text(json.dumps({"summary": summary, "total_fail": n_fail}, indent=2), encoding="utf-8")
    return 1 if (strict and n_fail) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--strict", action="store_true", help="exit 1 if any check fails")
    ap.add_argument("--json", metavar="PATH", help="also write a small JSON summary")
    args = ap.parse_args(argv)
    return run_audit(strict=args.strict, json_path=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
