---
name: horizontal-curves-platting
description: Use when reading, transcribing, placing, or auditing horizontal (circular) curves on a survey plat or in COGO code -- PC, PT, PI, RP, PRC, PCC, "℄ Curve Data" blocks, curve tables, chord bearings and distances, centerline vs right-of-way-edge radii, radial and non-radial lot lines, corner returns (25' radii), cul-de-sac bulbs and reverse fillets, or any time a stated T, L, C or Δ needs checking. Trigger BEFORE typing a curve value from a scan, BEFORE adding or changing a curve in engine/cogo_*.py, and when a drawn curve looks wrong (too big, wrong side, wrong edge). Points at plat_curves/ (stdlib toolkit) so nobody re-derives the formulas.
---

# Horizontal Curves on Plats

Teaching reference with the reasoning and real examples: `plugins/curves/docs/HORIZONTAL_CURVES.md`. Binding API and conventions:
`plugins/curves/plat_curves/SPEC.md`. This skill is the working procedure.

## 0. Use the tool, not fresh math

`plat_curves` lives in `plugins/curves/` and is stdlib-only (no numpy, no `engine.*`). Put `plugins/curves` on `sys.path`
(e.g. `PYTHONPATH=plugins/curves python3 ...` from the repo root).

```python
from plat_curves import Curve, PlacedCurve, bearing_to_az, az_to_bearing, dist, az, offset, PLAT_TOL_FT
from plat_curves.compound import (
    row_edges,
    concentric,
    corner_return,
    cul_de_sac,
    ReverseCurve,
    CompoundCurve,
    radial_line,
    nonradial_line,
    line_angle_to_radial,
    line_arc_intersections,
)
from plat_curves.plat_notation import parse_curve_data, PlatCurveReading, audit_reading, diagnose_offset, edge_radius
```

- `Curve.from_params(direction, radius=..., delta_deg=..., tangent=..., ...)`: any two determine it; extras are
  cross-checked and raise `ValueError` beyond 0.02 ft.
- `PlacedCurve(curve, pc, back_az)` gives `.pi .pt .rp .chord_bearing .forward_bearing .point_at(s) .arc_points()`;
  also `from_pi`, `from_pc_pt`, `from_rp`, `from_pt`.
- `audit_reading(reading)["verdict"]` is `consistent | inconsistent | underdetermined`; `diagnose_offset` tests
  R, R+-w/2, R+-w against the printed T/L/C.
- Verify with `python3 -m pytest plat_curves -q`.

## 1. Conventions (never deviate)

- Point = `(n, e)` feet, northing first. Azimuth = degrees clockwise from north. Quadrant bearings have angle <= 90°.
- `CW` = turns RIGHT going PC->PT, RP is 90° to the right of travel. `CCW` = turns left. The label is meaningless
  without the direction of travel: record the travel direction and where RP is in compass terms.
- Δ = deflection angle = 180° - interior angle at the PI; `0 < Δ < 180°` (a cul-de-sac bulb, 265.67°, is built from halves).
- Formulas: `L=RΔ  T=R·tan(Δ/2)  C=2R·sin(Δ/2)  M=R(1-cos(Δ/2))  E=R(sec(Δ/2)-1)`; fillet area `R·T - R²Δ/2`.
- Beachwood Unit Two (PB30 Pg82/82A): Note 1 bearings and distances on curves are CHORD values; Note 2 distances at
  block corners run to the street-line intersection (the P.I.), not to the P.C./P.T.; Note 4 radii not shown are 25 ft.
- `℄ Curve Data` (centerline) blocks give only Δ, R, T.

## 2. Reading a curve off the plat

1. Classify it: centerline (`℄` block), R/W edge, lot line, boundary, corner return. Note sheet and crop.
2. Crop and upscale the ink (PIL, LANCZOS x2-3, autocontrast) and LOOK at it. OCR confuses `'` `"`, `1` `7`, `6` `8` `0`, `Δ` `A`.
3. Transcribe exactly. Unreadable -> `null`. Never fill a value by computing it from others; put computed
   cross-checks under `derived_check`.
4. `parse_curve_data(text)`, build a `PlatCurveReading`, run `audit_reading`. Any residual > 0.02 ft (after the
   rounding widening it applies) is a finding, not noise.
5. If T/L/C disagree with R, run `diagnose_offset(reading, 60.0)` before re-reading. The usual cause is an edge radius
   mistaken for the centerline (R +- 30 for a 60 ft R/W). Decide from the source: a `℄` block IS the centerline.
6. For curved lot lines add the chord bookkeeping check (section 4).

## 3. Placing a curve

1. Get PC, back tangent azimuth (direction of travel AT the PC), direction, and any two of R/Δ/T/L/C.
2. `PlacedCurve(Curve(radius=R, delta_deg=D, direction="CW"), pc, back_az)`. If you have the PI instead, use
   `PlacedCurve.from_pi(pi, back_az, forward_az, R)`, which derives direction and Δ from the two tangents.
3. By hand (sgn = +1 CW, -1 CCW): `RP = PC + R along back_az + sgn*90`, `PI = PC + T along back_az`,
   `PT = PI + T along back_az + sgn*Δ`, `chord_az = back_az + sgn*Δ/2`.
4. ALWAYS assert the over-determined checks: `|PC-PT| = C`, `|RP-PC| = |RP-PT| = R`, `az(PC->PT) = chord_az`,
   `|PC-PI| = |PI-PT| = T`. A length-only validator cannot see a mirrored or wrong-side curve.
5. Edges: `row_edges(pl, 60.0)` -> `{"outside": R+30, "inside": R-30}` sharing RP and Δ. Inside is on the RP side:
   right-hand edge for CW, left-hand for CCW (`edge_radius(R, 60, "CW", "left")`).

```python
pl = PlacedCurve(
    Curve(radius=269.96, delta_deg=36 + 20 / 60, direction="CW"), (0.0, 0.0), bearing_to_az("N88°58'20\"E")
)
assert abs(dist(pl.rp, pl.pt) - 269.96) < 1e-6 and pl.chord_bearing == "S72°51'40\"E"  # forward S54°41'40"E
```

## 4. Edge vs centerline (the trap)

- Concentric curves share RP and Δ; R differs by half the R/W; L, C, T scale with R; the P.I.s are different points
  (30/cos(Δ/2) apart for 30 ft); the full-Δ chord has the same BEARING on all of them.
- Chord bookkeeping for consecutive lot fronts: adjacent chord azimuths differ by (θi+θi+1)/2 and the last chord
  differs from the tangent by θlast/2; chord = 2R·sin(θ/2); the θ must sum to Δ. Only the true edge radius reproduces
  every printed chord to 0.01 ft. Try R-30, R, R+30.
- A stated T that fails `T = R·tan(Δ/2)` means R was misread or belongs to another offset.

## 5. Corner returns, cul-de-sacs, reverse and compound curves

- Corner return: `corner_return(corner, az_in, az_out, radius=25.0)`. `az_in` = travel INTO the corner along line 1,
  `az_out` = travel OUT along line 2. Δ is the deflection, T = R·tan(Δ/2) (equals R only at 90°). Frontage to the
  straight part = printed dimension - T (Note 2). Never use the interior angle as Δ; never use undirected `mod 180`.
- Cul-de-sac: `cul_de_sac(center, Rb, w, Rf=25, axis_az)`; `yf = sqrt((Rb+Rf)²-(w+Rf)²)`, `theta_prc = asin((w+Rf)/(Rb+Rf))`,
  fillet Δ = `90° - theta_prc` (NOT theta_prc), bulb sweep = `360° - 2*theta_prc`; signed turning must total -180°.
- Reverse (PRC): centres on opposite sides, `|RP1-RP2| = R1+R2`. Compound (PCC): same side, `|RP1-RP2| = |R1-R2|`.
  `.check()["ok"]` on `ReverseCurve.from_curves(first, R2, D2)` / `CompoundCurve.from_curves(...)`.

## 6. Radial or not

Do not assume either. `line_angle_to_radial(pl, s, az)` returns the signed angle from the outward radial at arc
distance `s` (0 = radial, ±90 = tangent). Radial lot lines pass through RP. Real examples (Block 12): Lot 9|10 line
`N35°18'20"E` is exactly radial at the PT; Lot 8|9 line `N22°32'48"E` is ~2°06' off radial.

## 7. Checklist before you trust a curve

1. T vs R,Δ (0.02 ft); L = RΔ; C = 2R·sin(Δ/2); C <= 2R; C < L.
2. Chord bearing = back ± Δ/2 = mean of back and forward tangent azimuths; direction matches the RP side.
3. `|PC-PT| = C`, `|RP-PT| = R`, tangent at PT ⟂ RP->PT.
4. Centerline or edge? Chord or arc (default chord)? Radial or not?
5. Rounding: printed to 0.01 ft and 1"; 0.02 ft off is suspicious; 0.05 ft off is an error or another offset.
   Do not widen the tolerance until it passes.
6. Lot closure proves nothing about curves; run the `review-plat-notes` skill for solver-level audits.
7. Disagreement: record both values and the crop path, ask the user, do not average.

## 8. Failures already made in this repo (do not repeat)

- **+30 ft confusion**: `engine/cogo_road_centerlines.py` uses San Salvadore R=299.96 as "centerline" though the `℄`
  block says R=269.96, T=88.59 (T(299.96)=98.43 disagrees by 9.84 ft; both edges reproduce from 269.96). Marina
  (℄ R=359.27, engine 419.27) and Keel (℄ R=167.95, engine 143.93) disagree too. Cape Horn and Sands match.
- **`S91°01'40"E`** (`PI_RAY_SS_OUT`, `PI_RAY_CH_OUT`): not a bearing; it means `N88°58'20"E`. Generate bearings
  with `az_to_bearing`, never type them.
- **Swapped tangents / wrong side**: San Salvadore's PT is 99.97 ft off the circle about its RP, because chord
  `S72°51'40"E` is the CCW value while RP was placed CW. Five of six engine centerline curves fail `|RP-PT| = R`;
  `validate_all_curves()` cannot see it (lengths only, 0.2 ft threshold).
- **Off-by-one curve side** (Block 13): `curve_specs={"side_N"}` on the wrong edge; a 74.86 ft chord against R=25
  (C <= 2R = 50 violated). Closure was still perfect.
- **Stated T inconsistent with R,Δ** (Keel ℄: T=82.35 vs 82.43 computed): unresolved; record, do not fix.
- **Fillet Δ**: `README_ROAD_CENTERLINES.md` section 5 says 47.167° / 20.58 ft; correct is 42.833° / 18.69 ft.
- **MASTER_PROMPT** misquotes Note 2 as the 25' radius note (it is Note 4) and `Δ = |az2-az1| mod 180` is ambiguous.

## 9. Do not

- Guess a plat value; back-fill a null from computed numbers; edit `engine/cogo_road_centerlines.py` curve constants
  before the audit confirms the fix against the scan.
- Cite Florida statutes or F.A.C. sections from memory: say "check the current Chapter 177 Part I / F.A.C. 5J-17 text".
- Import `engine.*` inside `plat_curves/core.py`, `compound.py`, `plat_notation.py`.
