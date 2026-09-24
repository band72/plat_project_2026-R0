# plat_curves — SPEC (shared contract for all agents)

Isolated, **stdlib-only** horizontal-curve toolkit for plat reading / COGO.
`core.py`, `compound.py`, `plat_notation.py` MUST NOT import `engine.*`, numpy, or anything third-party.
Only `audit_engine_curves.py` and `tests/test_engine_bridge.py` may import `engine.*` (read-only comparison).
Style: py3.12, ruff line-length 120, double quotes, `from __future__ import annotations`, short docstrings.

## Conventions (non-negotiable — every module uses these)
- Point = `(n, e)` tuple of floats, feet (Northing first, like the rest of this repo's COGO).
- Azimuth = degrees clockwise from north, `[0, 360)`. Bearing strings look like `S57°53'59"E` / `N 89°18'20" E`.
- `direction`: `"CW"` = curve turns RIGHT going PC→PT (radius point RP is 90° to the right of travel);
  `"CCW"` = turns LEFT (RP is 90° to the left). Same words the engine already uses.
- Δ (`delta_deg`) is always positive and `0 < Δ < 180` for simple curves (reject otherwise, `ValueError`).
- Geometry (travel PC→PT, sgn = +1 for CW, −1 for CCW):
  `back_az` = azimuth of the back tangent (direction of travel at PC);
  `rp_az`(PC→RP) = back_az + sgn·90°;  `forward_az` = back_az + sgn·Δ;  `chord_az` = back_az + sgn·Δ/2;
  PI = PC + T along `back_az`;  PT = PI + T along `forward_az`;  RP = PC + R along `rp_az`.
  Point at arc distance s from PC: `offset(RP, rp_az + 180° + sgn·degrees(s/R), R)`  (azimuth RP→PC is `rp_az+180°`;
  it increases for CW, decreases for CCW). Check: CW, back_az=0 ⇒ RP due east of PC, RP→PC = 270°, sweeping toward 360°.
- Formulas: `L = R·Δrad`, `T = R·tan(Δ/2)`, `C = 2R·sin(Δ/2)`, `M = R·(1−cos(Δ/2))`, `E = R·(1/cos(Δ/2) − 1)`,
  arc definition `Da = 5729.5779513/R` (per 100 ft of arc), chord definition `sin(Dc/2) = 50/R`.
  `sector_area = R²Δ/2`, `segment_area = R²(Δ−sinΔ)/2`, `fillet_area (spandrel between tangents and arc) = R·T − sector_area`.
- Plat rounding reality: radii to 0.01 ft, T/L/C to 0.01 ft, Δ to 1″. `PLAT_TOL_FT = 0.02` for audits of plat-stated values;
  internal math consistency tests use `1e-9`.
- Plat reading rule (Beachwood Unit Two, PB30 Pg82/82A Sheet 2 Note 1): **bearings and distances shown on curves are CHORD
  values**. Note 4: **all radii not shown are 25 ft**. `℄ Curve Data` blocks are CENTERLINE (℄) curve data.

## Public API (builders implement exactly these names; tests/auditors code against them)

### `plat_curves/core.py`
```
dms_to_deg(d, m=0, s=0) -> float ; deg_to_dms(deg, places=0) -> str   # 36°20'00"
bearing_to_az(s: str) -> float ; az_to_bearing(az: float, places=0) -> str
offset(pt, az_deg, dist) -> Pt          # move dist along azimuth
dist(a, b) -> float ; az(a, b) -> float
class Curve(frozen dataclass): radius, delta_deg, direction="CW"
    .arc_length .tangent .chord .middle_ordinate .external .degree_arc .degree_chord
    .sector_area .segment_area .fillet_area
    Curve.from_params(direction="CW", **two_or_more_of{radius, delta_deg, arc_length, chord, tangent, middle_ordinate, external, degree_arc})
        # any 2 determine the curve; extras are cross-checked (ValueError if inconsistent beyond tol=PLAT_TOL_FT)
class PlacedCurve(frozen dataclass): curve, pc, back_az
    .pi .pt .rp .forward_az .chord_az .chord_bearing (str) .back_bearing .forward_bearing
    .point_at(s) -> Pt                 # s = arc distance from PC, 0..L
    .azimuth_at(s) -> float            # direction of travel at s
    .radial_az_at(s) -> float          # azimuth from RP to the point (outward radial)
    .arc_points(n_segments=24) -> list[Pt]
    .station_table(pc_station=0.0, spacing=100.0) -> list[dict]   # PC, full stations, PT with deflection angle & chord from PC
    PlacedCurve.from_pi(pi, back_az, forward_az, radius)           # derives direction+Δ from the two tangents
    PlacedCurve.from_pc_pt(pc, pt, radius, direction, back_az=None)# from chord; small arc only
    PlacedCurve.from_rp(rp, radius, start_az_from_rp, delta_deg, direction)
    PlacedCurve.from_pt(pt, forward_az, curve)                     # place backwards from the PT
```

### `plat_curves/compound.py`
```
concentric(placed, offset, side="outside"|"inside") -> PlacedCurve   # same RP & Δ; R±offset; PC/PT on the same radials
    # "outside" = away from RP (R+offset); "inside" = toward RP (R−offset); raise if R−offset <= 0
row_edges(placed_centerline, row_width) -> {"outside": PlacedCurve, "inside": PlacedCurve}   # ±row_width/2
class ReverseCurve / CompoundCurve:   # PRC (point of reverse curvature) / PCC (point of compound curvature)
    ReverseCurve.from_curves(first: PlacedCurve, second_radius, second_delta_deg) -> pair with .prc, tangency check
    CompoundCurve.from_curves(first: PlacedCurve, second_radius, second_delta_deg) -> pair with .pcc
    .check() -> dict(residuals)  # common tangent az equal at junction, centers collinear with junction, |RP1-RP2| = R1+R2 (reverse) or |R1-R2| (compound)
corner_return(corner, az_in, az_out, radius=25.0) -> PlacedCurve      # tangent fillet between two street lines meeting at `corner`
    # az_in = direction of travel INTO the corner along line 1; az_out = direction of travel OUT of it along line 2
cul_de_sac(center, bulb_radius, throat_half_width, fillet_radius=25.0, axis_az=...) -> dict   # reverse-fillet throat solution
    # yf = sqrt((Rb+Rf)^2 − (w+Rf)^2) ; theta_prc = asin((w+Rf)/(Rb+Rf))
radial_line(placed, s, length, inward=False) -> (Pt, Pt)              # lot line on the radial at arc distance s
nonradial_line(placed, s, az, length) -> (Pt, Pt)                     # lot line leaving the arc at s along a given azimuth
line_arc_intersections(p0, p1, placed) -> list[dict(point, s)]        # segment/arc intersections with arc-distance s
```

### `plat_curves/plat_notation.py`
```
parse_curve_data(text) -> dict     # "Δ=36°20'00\" R.=269.96' T.=88.59'" -> {"delta_deg":..., "radius":..., "tangent":...} (tolerant of OCR: R., R=, ∆/Δ/A, ′ ″ marks)
class PlatCurveReading: id, sheet, street, kind("centerline"|"row_edge"|"lot_line"|"boundary"|"corner_return"), radius, delta_deg, tangent, arc_length, chord, chord_bearing, confidence, notes
audit_reading(reading, tol=PLAT_TOL_FT) -> dict   # recompute every derived value from the best-determined pair; per-parameter residuals; verdict "consistent"|"inconsistent"|"underdetermined"
diagnose_offset(reading, row_width=60.0) -> dict  # if stated T/L/C disagree with stated R but agree with R ± row_width/2 (or ± row_width), say so:
    # {"hypothesis": "stated R is a R/W edge, not centerline", "implied_centerline_R": ..., "which_edge": "inside"|"outside"}
```

## Data readings (transcribed from the scans) — `plat_curves/data/*.json`
List of objects with keys: `id, sheet (1|2), street, kind, radius, delta_deg, tangent, arc_length, chord, chord_bearing,
confidence (0..1), crop (path of the crop you actually looked at), evidence (what the ink says, verbatim incl. unreadable bits),
ambiguities`. **Unreadable ⇒ `null`. Never fill a value by computing it from other values** (that would hide errors from the audit) —
put a computed cross-check under `derived_check` instead.
Scan pixel mapping: full-res sheets are `Plat/training/drawings/page0_300dpi.png` (Sheet 1, PB30 Pg82) and `page1_300dpi.png`
(Sheet 2, Pg82A), 9000×5400 px. Use PIL (`Image.MAX_IMAGE_PIXELS=None`) to crop, upscale 2–3× (LANCZOS, autocontrast) and LOOK at the crop.
Full-res px ≈ (x,y seen in a 2000×1200 overview) × 4.5.

## File ownership (write ONLY your own files; never edit anyone else's; never run git commit/checkout/stash/reset/add)
| agent | owns |
|---|---|
| reader-sheet1 | `data/readings_sheet1.json` |
| reader-sheet2-marina-keel | `data/readings_sheet2_marina_keel.json` |
| reader-sheet2-sands-capehorn | `data/readings_sheet2_sands_capehorn_boundary.json` |
| reader-corners | `data/readings_corner_returns.json` |
| builder-core | `core.py`, `__init__.py` |
| builder-compound | `compound.py` |
| builder-notation | `plat_notation.py` |
| oracle-tests | `tests/oracle.py`, `tests/test_core.py`, `tests/test_compound.py`, `tests/test_notation.py` |
| engine-auditor | `AUDIT_ENGINE.md`, `audit_engine_curves.py`, `tests/test_engine_bridge.py` |
| teacher | `../docs/HORIZONTAL_CURVES.md`, `../skills/horizontal-curves-platting/SKILL.md` |
Plugin root: `plugins/curves/` inside the main project. Write ONLY inside it; `engine/*` and everything else in the repo is read-only from here
(an IDE agent commits to those files every ~10 min). Paths such as `Plat/training/drawings/...` are relative to the REPO root (`../..`).
