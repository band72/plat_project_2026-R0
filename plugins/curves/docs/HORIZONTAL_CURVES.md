# Horizontal Curves on Plats: Read, Place, Audit

Audience: a programmer who is not a surveyor. Subject: circular curves in the horizontal plane only (no profile
curves, no vertical anything). Worked examples use the real numbers on Beachwood Unit Two, PB 30 Pg 82/82A (1960,
Duval County FL; Sheet 1 = `Plat/training/drawings/page0_300dpi.png`, Sheet 2 = `page1_300dpi.png`).

Every formula and every number below was recomputed with a throwaway script on 2026-09-23. Ink readings are the
author's reading of the scan crops, not the record: the transcriptions in `plugins/curves/plat_curves/data/*.json` are the record.
Code for all of this already exists: `plugins/curves/plat_curves/` (`core.py`, `compound.py`, `plat_notation.py`, contract in
`plugins/curves/plat_curves/SPEC.md`). Use it; do not re-derive.

## 0. The ten rules that prevent most errors

1. A curve is fully determined by any two of R, Δ, L, C, T, M, E, D. Plats print three or four, so you can always
   check them against each other. Do it before trusting any of them.
2. `℄ Curve Data` blocks are CENTERLINE values. Lot-line and right-of-way (R/W) curves are concentric with the
   centerline: same centre, same Δ, radius = R_℄ ± half the R/W width.
3. Bearings and distances printed on curves are CHORD values (Note 1 of this plat), not tangent bearings or arc lengths.
4. Radii not shown are 25 ft (Note 4). Distances at block corners run to the street-line intersection, i.e. to the
   P.I. of the two R/W lines, not to the P.C./P.T. of the corner return (Note 2).
5. Corner-return T = R·tan(Δ/2) where Δ is the DEFLECTION angle (180° minus the interior angle). It equals R only at 90°.
6. CW/CCW only means something together with a direction of travel. The same arc is CW one way and CCW the other.
   Store the travel direction and where the radius point (RP) is, in compass terms ("RP is south of the street").
7. Chord bearing = back-tangent azimuth ± Δ/2, and it is the mean of the back and forward tangent azimuths.
8. Quadrant bearings never exceed 90°. `S91°01'40"E` is not a bearing.
9. A geometry validator that only checks lengths cannot see a mirrored, swapped or wrong-side curve. Also check
   |RP-PT| = R and that the tangent at PT is perpendicular to RP->PT.
10. Unreadable ink is `null`. Never back-fill a value by computing it from the others; that hides the very
    inconsistency an audit exists to find.

## 1. Glossary

```
                     PI
                    /|\
                   / | \
      back tangent/  |E \ forward tangent
       (length T) /   |   \ (length T)
                 /  .-*-.  \          * = midpoint of the arc
                / .'  |M '. \         M = middle ordinate (chord midpoint to arc)
               PC-----+-----PT        E = external distance (arc midpoint to PI)
                \     |     /         PC--PT straight line = chord C (bearing = LC bearing)
                 \    |    /          arc PC->*->PT = length L
                R \   |   / R
                   \  |  /            central angle at RP = Δ = deflection angle at PI
                    \ | /
                     \|/
                      RP              radii RP-PC and RP-PT are perpendicular to the tangents
```

| Term | Meaning |
|---|---|
| PC (also P.C., BC) | Point of Curvature: where the back tangent ends and the arc begins. "Back" and "forward" refer to the direction of travel you chose. |
| PT (also P.T., EC) | Point of Tangency: where the arc ends and the forward tangent begins. |
| PI (P.I.) | Point of Intersection of the two tangent lines. Horizontal only ("PVI" is the vertical one; ignore it). PI = PC + T along the back tangent. The PI is usually not on the ground you can see; it is the corner of the extended lines. |
| RP, centre, C.P. | Radius point: centre of the circle. On the concave (inside) side of the arc. RP-PC and RP-PT are both R. |
| POC | Ambiguous on plats: Point of Commencement (start of a legal description), Point on Curve (any point along the arc, e.g. a lot corner), rarely "point of centre". Decide from context; never treat it as PC. |
| POT | Point on Tangent: a point on the straight line before PC or after PT (e.g. a lot corner on a straight run). |
| Back / forward tangent | The straight line arriving at PC / leaving PT, in the direction of travel. |
| Δ (delta) | Central angle at RP = deflection angle at PI = (forward tangent azimuth) - (back tangent azimuth) = 180° minus the interior angle at PI. Always 0 < Δ < 180° for a simple street curve (a cul-de-sac bulb is the exception: 265.67° in the Keel Drive example). |
| R, L, T, C | Radius; arc length; tangent length (PC->PI = PI->PT); chord length (PC->PT straight). |
| LC bearing | Long-chord (chord) bearing: azimuth of PC->PT. Also "CB", "Ch. Brg." |
| M | Middle ordinate: chord midpoint to arc midpoint. M = R(1 - cos(Δ/2)). |
| E | External distance: PI to arc midpoint. E = R(sec(Δ/2) - 1). |
| D, degree of curve | Highway measure of sharpness. Arc definition: central angle per 100 ft of ARC, D = 5729.5779513/R. Chord definition: central angle per 100 ft of CHORD, sin(D/2) = 50/R. They differ (R=269.96: 21°13'26" vs 21°20'49"). Plats of subdivisions almost never print D; if a D appears, find out which definition. |
| Radial lot line | Lot line lying on a radius, i.e. passing through RP; it meets the arc at 90° to the tangent. Plats often (not on this one) mark them "R" or "Radial". |
| Non-radial (non-tangent) lot line | Meets the arc at some other angle. Abbreviated "NR". On this plat nothing is labelled either way: every line carries its own bearing and you test it (section 6). |
| Concentric curves | Same RP, same Δ, different R. Edge curves of a street are concentric with its centerline. |
| PRC | Point of Reverse Curvature: two arcs sharing a tangent at the junction and turning opposite ways (S-curve). Centres on opposite sides, dist(RP1,RP2) = R1+R2. |
| PCC | Point of Compound Curvature: two arcs sharing a tangent, turning the SAME way, different radii. Centres on the same side, dist(RP1,RP2) = abs(R1-R2). |
| Spiral | Transition curve of continuously changing radius (TS, SC, CS, ST). Highway design only; subdivision plats like this one use circular arcs. Not handled here. |
| ℄ (U+2104) | Centerline symbol (also written CL or a C with a bar). |

## 2. Formulas and a worked example

With Δ in radians where needed, h = Δ/2:

```
L = R·Δ            T = R·tan(h)              C = 2R·sin(h)
M = R(1 - cos h)   E = R(sec h - 1) = T·tan(Δ/4)
C = 2T·cos(h)      M = E·cos(h)
R = T/tan(h) = L/Δ = C/(2 sin h)             Δ = 2·atan(T/R) = L/R = 2·asin(C/2R)   (minor arc)
sector area  = R²Δ/2
segment area = R²(Δ - sinΔ)/2            (between chord and arc)
fillet area  = R·T - R²Δ/2               (spandrel between the two tangents and the arc)
chord bearing = back azimuth ± Δ/2        (+ for CW/right turn, - for CCW/left turn)
```

Any two parameters solve the rest. Some pairs (for example T with M) have two mathematical solutions; `Curve.solutions`
returns all of them and `Curve.from_params` cross-checks extras.

**Worked example: `℄ Curve Data  Δ=36°20'00"  R.=269.96'  T.=88.59'` (Sheet 1, San Salvadore Avenue)**

Δ = 36.333333° = 0.634159 rad, h = 18°10'00", tan h = 0.328139.

| Quantity | Value | Note |
|---|---|---|
| T | 88.584 | plat prints 88.59: off by 0.006, fine (plat rounding) |
| L | 171.191 | not printed on the plat |
| C | 168.337 | |
| M | 13.457 | |
| E | 14.162 | |
| sector / segment / fillet area | 23,107.42 / 1,517.85 / 806.81 sq ft | |
| chord bearing, travelling west to east, CW, back tangent N88°58'20"E | 88°58'20" + 18°10'00" = 107°08'20" = S72°51'40"E | forward tangent = 88°58'20" + 36°20'00" = 125°18'20" = S54°41'40"E, which is on the plat |

Concentric edges of the same street (60 ft R/W, half-width 30 ft; Δ unchanged):

| Curve | R | T | L | C | RP to its P.I. = R/cos h |
|---|---|---|---|---|---|
| inside edge | 239.96 | 78.74 | 152.17 | 149.63 | 252.55 |
| centerline | 269.96 | 88.58 | 171.19 | 168.34 | 284.12 |
| outside edge | 299.96 | 98.43 | 190.22 | 187.04 | 315.70 |

L, C and T scale in proportion to R (inside/centerline = 0.8889). The three PIs lie on one line through RP (the
bisector) but are 30/cos h = 31.57 ft apart, not 30 ft. The full-Δ chord has the same BEARING on all three curves
(S72°51'40"E) because the PC and PT lie on the same radials; only its length changes.

Tolerances of printed data: R, T, L, C are rounded to 0.01 ft, Δ to 1". A half-unit of rounding in Δ (0.5") moves
L by R·2.4e-6 ft (0.0007 ft here, 0.005 ft at R=1960). `PLAT_TOL_FT = 0.02` is the audit threshold for printed values;
use 1e-9 when checking your own math against itself.

## 3. How curves are actually annotated on this plat

I found no curve table on either sheet of this 1960 plat. Curve information is scattered, and each kind of label means something different:

1. **`℄ Curve Data` blocks** sit along the street centerline: `Δ=`, `R.=`, `T.=` and nothing else (no L, no chord).
   Sheet 1: San Salvadore (269.96 / 88.59) and Cape Horn (327.01 / 107.31). Sheet 2: Marina (R=359.27, T=122.70,
   Δ=37°42'50"), Sands (459.36 / 150.73), Keel Drive (R=167.95, Δ=52°17'10", T=82.35; see section 7), Cape Horn again.
   Crops: `Plat/training/drawings/centerline-curve-data.png`, `zoom_cape_horn_curve_data.png`,
   `zoom_san_salvadore_curve_data.png`.
2. **Curved lot lines** carry a chord distance and a chord bearing written along the chord, e.g. Block 12 Lot 8 front
   `106.60'  N.78°11'40"W.`. Note 1: *"Bearings and distances shown on curves are chord bearings and distances."*
   The lots' central angles add up to Δ (Appendix A shows this for San Salvadore, Cape Horn and Marina).
3. **Corner returns**: `25.0'` with a leader arrow at the corner (Note 4: *"All radii not shown are 25 feet"*), often
   with the bearing of the tangent line beside it (`N.88°58'20"E`). Note 2: *"Distances shown on block corners are
   to street line intersections"*: a lot frontage of 100' at a 90° corner is 100' to the P.I., so the straight part is
   100 - 25 = 75'. The small L-shaped tick drawn at block corners is read in this repo (`MASTER_PROMPT.md` Rule 2) as
   marking that P.I.; Note 2 is the authority. Note 3: setbacks are 25 ft from the street line.
4. **Radial vs non-radial** is not marked; compute it. Block 12 Lot 9|10 line `N.35°18'20"E` is exactly radial at the
   PT (forward tangent 125°18'20" - 90° = 35°18'20"). The Lot 8|9 line `N.22°32'48"E` is about 2°06' off the radial
   (radial there is N24°38'20"E). Non-radial side lines are normal when a rectangular lot meets a curved frontage.
5. **Statutes**: the plat's clerk's approval cites Chapter 10275, Laws of Florida 1925. For what a plat must show
   today, check the current text of Chapter 177 Part I, Florida Statutes, and F.A.C. 5J-17; this document does not
   restate them and a 1960 plat is judged by the rules of its day, not by 5J-17.

Modern tables (the Clay Co. and Duval 2014 examples in `MASTER_PROMPT.md`) list CURVE | LENGTH | RADIUS | DELTA | CHORD
BEARING | CHORD (sometimes TANGENT). Those are over-determined too, so the same checks apply.

### The R/W-edge vs centerline trap

A drafter prints whichever radius fits the label. A lot line shows the edge radius (implied by chords); the `℄` block
shows the centerline radius. Going from one to the other needs the side:

| Turn (direction of travel) | RP is | Right-hand edge | Left-hand edge |
|---|---|---|---|
| CW (turns right) | on the right | INSIDE: R - w/2 | OUTSIDE: R + w/2 |
| CCW (turns left) | on the left | OUTSIDE: R + w/2 | INSIDE: R - w/2 |

Lots on the inside edge sit on the RP side: their radial side lines converge toward RP, so frontage is longer than the
rear. Lots on the outside edge fan out: the rear is longer than the frontage.

Diagnostic: a stated T that fails T = R·tan(Δ/2) is a strong sign that R was misread or belongs to another offset.
`plat_notation.diagnose_offset` tests R + {0, ±w/2, ±w} against the printed T/L/C. Numbers alone cannot say which figure
is the centerline; the source can (`℄ Curve Data` block = centerline).

## 4. Reverse, compound, cul-de-sac fillets, corner returns

**Reverse and compound curves.** Both need a common tangent at the junction (equal tangent azimuth) with the two centres
and the junction collinear. Reverse: centres on opposite sides, |RP1-RP2| = R1+R2, signed turning Δ1 - Δ2. Compound:
same side, |RP1-RP2| = |R1-R2|, turning Δ1 + Δ2. `ReverseCurve.from_curves(...).check()` and
`CompoundCurve.from_curves(...).check()` return the residuals.

**Corner return (fillet) between two street lines meeting at corner K.** Δ = |az_out - az_in| (directions of TRAVEL,
INTO and OUT OF the corner) = 180° - interior angle I. T = R·tan(Δ/2) = R/tan(I/2). RP lies on the bisector at
R/cos(Δ/2) from K, on the block (lot) side: the arc rounds the block corner. Area removed from the lot = R·T - R²Δ/2 (134.13 sq ft for R=25, Δ=90°).

| Δ (deflection) | Interior I | T (R=25) | L | C |
|---|---|---|---|---|
| 60° | 120° | 14.43 | 26.18 | 25.00 |
| 88°17'15" | 91°42'45" | 24.2637 | 38.52 | 34.82 |
| 90° | 90° | 25.0000 | 39.27 | 35.36 |
| 91°42'45" | 88°17'15" | 25.7586 | 40.02 | 35.88 |
| 120° | 60° | 43.30 | 52.36 | 43.30 |

The trap: using the interior angle as Δ (interior 70°, true Δ 110°: T = 35.70; misuse gives 17.51). Undirected line
azimuths mod 180° cannot tell I from 180° - I; always use directed travel azimuths.

**Cul-de-sac with reverse fillets** (Keel Drive example: bulb R_b = 50, R/W half-width w = 30, fillet R_f = 25).
Each fillet circle is externally tangent to the bulb circle (that tangent point is a PRC) and tangent to the street edge:
centre offset from the axis = w + R_f = 55, distance from bulb centre = R_b + R_f = 75.

```
yf        = sqrt((Rb+Rf)² - (w+Rf)²) = 50.990   distance from bulb centre back along the axis to the fillet PC/RP
theta_prc = asin((w+Rf)/(Rb+Rf))     = 47.167°  angle at bulb centre between the axis and each PRC radial
fillet Δ  = acos((w+Rf)/(Rb+Rf))     = 42.833°  (= 90° - theta_prc);   L_fillet = 18.69
bulb sweep= 360° - 2·theta_prc       = 265.667° (L = 231.84)
check: 2·42.833 - 265.667 = -180.000  (fillet, bulb, fillet make a U-turn)
```

A symmetric bulb-and-throat solution whose signed turnings do not sum to -180° (or +180° mirrored) is wrong.

## 5. COGO placement recipe (this repo's conventions)

Point = `(n, e)`, feet, northing first. Azimuth = degrees clockwise from north. `sgn = +1` for CW (turns right going
PC->PT), `-1` for CCW.

```
inputs:  PC, back_az (direction of travel at PC), direction, and any two of R/Δ/T/L/C...
RP    = PC + R along (back_az + sgn·90°)            # 90° to the right for CW
PI    = PC + T along back_az
fwd   = back_az + sgn·Δ
PT    = PI + T along fwd                             # equivalently RP + R along (az(RP->PC) + sgn·Δ)
point at arc distance s:  RP + R along ( (back_az + sgn·90° + 180°) + sgn·(s/R in degrees) )
outward radial at s:      RP->point azimuth;   tangent at s = radial + sgn·90°
```

where `offset(p, az, d) = (n + d·cos az, e + d·sin az)`. Check: CW, back_az = 0 => RP due east of PC; azimuth RP->PC = 270°
sweeping toward 360°.

```python
from plat_curves import Curve, PlacedCurve, bearing_to_az

pl = PlacedCurve(
    Curve(radius=269.96, delta_deg=36 + 20 / 60, direction="CW"), (0.0, 0.0), bearing_to_az("N88°58'20\"E")
)
pl.pt, pl.pi, pl.rp, pl.chord_bearing  # -> ..., S72°51'40"E ; forward_bearing S54°41'40"E
```

Other entry points: `PlacedCurve.from_pi(pi, back_az, forward_az, R)` (direction and Δ come from the two tangents),
`from_pc_pt(pc, pt, R, direction)` (small arc only), `from_rp(...)`, `from_pt(pt, forward_az, curve)`. Edges:
`compound.row_edges(pl, 60.0)`, `concentric(pl, 30.0, "inside")`. Radial and non-radial lot lines:
`radial_line`, `nonradial_line`, `line_angle_to_radial`, `line_arc_intersections`.

Cross-check every placement, which is cheap because plat data is over-determined: |PC-PT| = C, |RP-PC| = |RP-PT| = R, azimuth
PC->PT = back_az + sgn·Δ/2, tangent at PT perpendicular to RP->PT, PC and PT each ≈ T from PI. If a source gives
PC and PT as coordinates plus R, the direction is what selects between the two circles through them.

## 6. Checklist before you trust a curve

1. What is it: centerline, R/W edge, lot line, boundary or corner return? Which sheet, which label?
2. Parsed cleanly? `°`, `'`, `"` (OCR confuses `'` and `"`, `1` and `7`, `6`/`8`/`0`, `Δ` and `A`). Quadrant angle <= 90°.
3. **T = R·tan(Δ/2)** within 0.02 ft (widen by the rounding of the inputs). Also L = RΔ and C = 2R·sin(Δ/2).
   `plat_notation.audit_reading` does all of it and says consistent / inconsistent / underdetermined.
4. C <= 2R, C < L, Δ < 180°, R > 0. A chord longer than 2R is impossible (see off-by-one below).
5. Chord bearing = back ± Δ/2 = mean of back and forward tangent azimuths. Direction agrees with the RP side.
6. |PC-PT| = C; |RP-PC| = |RP-PT| = R; tangent at PT ⟂ RP->PT.
7. Edge or centerline? Test R - w/2, R, R + w/2 against every printed T/L/C and lot chord (`diagnose_offset`).
   The lots' central angles must sum to Δ.
8. Chord or arc? Default on this plat: chord (Note 1). A distance equal to R·(angle in rad) is an arc.
9. Radial or not? Angle between the lot line and the radial at that arc point (`line_angle_to_radial`).
   Do not assume radial; do not assume non-radial.
10. Tolerance: 0.01 ft and 1" of rounding are normal; a 0.02 ft mismatch is suspicious; 0.05 ft or more means an
    error in the data or a different offset. Do not loosen the tolerance until it passes.
11. Closure of a lot is not evidence about curves (it depends only on vertex positions). See the `review-plat-notes` skill.
12. If unreadable: `null` with a note. If it disagrees: record both values and the crop; ask, do not pick.

## 7. Failure catalogue (real, from this repo)

| # | What went wrong (measured on the engine at main 9070ff5, 2026-09-23) | How to see it | Fix |
|---|---|---|---|
| 1 | **The "+30 ft" edge/centerline confusion.** `engine/cogo_road_centerlines.py` sets San Salvadore `r_ss_cl = 299.96` ("stated on North R/W 269.96 + 30"). The `℄ Curve Data` block says R.=269.96, T.=88.59, so 269.96 IS the centerline. T(269.96) = 88.58 matches the plat; T(299.96) = 98.43 is off by 9.84. Both R/W edges reproduce from 269.96: north (outside, left of a west-to-east right turn) lot chords 67.91, 66.18, 55.76 need R=299.96; south (inside) lot fronts 106.60 and 44.61 need R=239.96. The engine then reports L=190.22, C=187.05 (outside-edge values) as centerline. | T check; chord bookkeeping (Appendix A); `diagnose_offset` reports "stated R is a R/W edge (outside), implied centerline 269.96". | Use the ℄ values (once the reader transcriptions confirm the ink). Same pattern found at Marina (℄ R=359.27, lot chords need 389.27; engine uses 419.27) and Keel (℄ 167.95; engine 143.93, unexplained). Cape Horn (327.01) and Sands (459.36) match their ℄ blocks. `MASTER_PROMPT.md` Iter 48 also says Sands "R=429.36": that is an R/W-edge radius (459.36 - 30), not the centerline. |
| 2 | **`S91°01'40"E`** hard-coded as the outgoing tangent of San Salvadore and Cape Horn (`PI_RAY_SS_OUT`, `PI_RAY_CH_OUT`, ~lines 1495 and 1628). | 91° is not a quadrant angle; `engine.cogo.parse_bearing` and `plat_curves.bearing_to_az` both raise "out of range". 180° - 91°01'40" = 88°58'20", so it means `N88°58'20"E`, the Block 12 Lot 8 line bearing on the plat. Survives only because the string is printed, never parsed. | Generate bearings with `az_to_bearing`; never type them. |
| 3 | **Back/forward tangents swapped, RP on the wrong side.** San Salvadore: engine uses S54°41'40"E as the back tangent from PC with CW. CW from that tangent gives chord S36°31'40"E; the engine's chord S72°51'40"E is the CCW value. On the plat, west-to-east, N88°58'20"E is the back tangent and S54°41'40"E the forward one. | `dist(RP,PT) - R` = +99.97 ft (San Salvadore), +86.05 (Keel), +17.17 (Beachwood Blvd), -16.98 (Sands), -5.09 (Cape Horn); only Marina is 0.001. `validate_all_curves()` checks lengths only, with a 0.2 ft threshold (the README says 0.05), so it passes. | Placement recipe in section 5; assert the dist(RP,PT) = R check. |
| 4 | **Off-by-one curve side** (Block 13, from the `review-plat-notes` skill): `curve_specs={"side_N": ...}` pointed at the neighbouring straight edge, in a second copy of the geometry inside the drawing script. Closure was perfect. | A 74.86 ft chord against a declared 25 ft radius: C <= 2R = 50 is violated. | `engine/notes_audit.py`; audit every independent construction. |
| 5 | **A stated T that fails T = R·tan(Δ/2).** Keel `℄`: R.=167.95, Δ=52°17'10" give T=82.43; the ink reads T.=82.35 (0.08 off, beyond tolerance). The inside-edge chord `121.56' N.61°26'55"E`, if it spans the full Δ, gives R=137.94 = 167.95 - 30, agreeing with R. So R and Δ are corroborated and T is the odd one: a misread digit or a 1960 arithmetic slip. Unresolved. | `audit_reading` verdict "inconsistent". | Record all three values and the crop; do not average or "fix". |
| 6 | **Iter 44 Marina numbers**: `MASTER_PROMPT.md` gives R=389.27, Δ=37°42'50", T=133.04, arc 256.34. Computed: T=132.95, L=256.23, and the printed sub-chords 85.24 fit R=389.27 only. The T and arc are not from R and Δ, and are not on the plat (the plat's T is 122.70 for R=359.27). | T check. | Treat as unverified. |
| 7 | **Loose validators.** README claims curves are validated "within 0.05'" but the code threshold is 0.2 ft; Beachwood Blvd's L (260.19 vs 260.25 computed) and C (260.00 vs 260.06) differ by 0.06 and pass. | Recompute with plat tolerance (0.02). | Match the plat's rounding, not a convenience number. |

## Appendix A. Chord bookkeeping shows which radius a lot-line curve belongs to

Adjacent lot chords along a concentric arc: consecutive chord azimuths differ by (θ_i + θ_i+1)/2, and the last chord
differs from the tangent by θ_last/2, where θ_i is the lot's central angle and chord_i = 2R·sin(θ_i/2). All ink readings.

San Salvadore, north (outside) lot fronts (lots north of the street, Block 9), Sheet 1: chord bearings N84°31'40"W, N71°41'40"W, N60°01'40"W, then
tangent N54°41'40"W. The bearing steps 5°20' (= θ_last/2), 11°40' (= (θ_mid + θ_last)/2) and 12°50'
(= (θ_first + θ_mid)/2) give θ = 10°40', 12°40', 13°00' (sum 36°20' = Δ).

| θ | printed chord | R=239.96 | R=269.96 | R=299.96 |
|---|---|---|---|---|
| 13°00' | 67.91 | 54.33 | 61.12 | **67.91** |
| 12°40' | 66.18 | 52.94 | 59.56 | **66.18** |
| 10°40' | 55.76 | 44.61 | 50.19 | **55.76** |

South (inside) Block 12 Lots 8 and 9: 106.60 (θ = 25°40') and 44.61 (θ = 10°40'), sum 36°20': both need R = 239.96
(the centerline radius 269.96 would give 119.92 and 50.19). Cape Horn south (inside) Block 9 lots 27, 28, 29: chords
72.39, 108.25, 6.91 with θ = 14°00', 21°00', 1°20' (sum 36°20') need R = 297.01 = 327.01 - 30 (with 327.01
they would be 79.70, 119.19, 7.61). Marina north lot fronts: three chords of 85.24 with θ = 12°34'17" (bearings
S86°07'22"E, S73°33'06"E, S60°58'49"E) need R = 389.27 = 359.27 + 30.

## Appendix B. Statements in the repo's own docs that are wrong or ambiguous

- `MASTER_PROMPT.md` Rule 2 and Iter 41 quote "Plat Note 2: All block corners have R = 25.00 ft radii". The plat's
  Note 4 says "All radii not shown are 25 feet"; Note 2 is "Distances shown on block corners are to street line intersections".
- `MASTER_PROMPT.md` Rule 2 / Iter 41: `Δ = |az2 - az1| mod 180°` is ambiguous (see section 4): it cannot distinguish the
  deflection from the interior angle. Use directed travel azimuths, Δ = |wrap180(az_out - az_in)|.
- `README_ROAD_CENTERLINES.md` section 5: fillet Δ = 47.167°, L = 20.58. The correct fillet turn is 42.833°, L = 18.69
  (47.167° is the PRC angle at the bulb centre). Net turning check in section 4 fails with 47.167°.
- `README_ROAD_CENTERLINES.md` section 7 and Rule 6: San Salvadore R=299.96/T=98.42 is the outside-edge curve, not the
  centerline; Marina R=419.27 and Keel R=143.93 disagree with the ℄ blocks (failure #1). Directions "CW"/"CCW" are printed
  without a direction of travel (failure #3).
- `README_ROAD_CENTERLINES.md` section 8, "bearings along each edge of the R/W generally are the same as the centerline":
  true for straight runs; on a curve it holds only for the full-Δ chord between the same radials (sub-chords differ),
  and edge distances scale with (R ± w/2)/R (0.889 or 1.111 for San Salvadore), so summing lot frontages does not
  give the centerline length. Note 1 also makes those frontages chords, not arcs.
- `README_ROAD_CENTERLINES.md` section 11 uses `w/2` for the half-width (30 ft) where section 5 uses `w` for it.
- "100% F.A.C. 5J-17 compliance" in `MASTER_PROMPT.md`/README is a label, not a finding: the rule postdates this 1960 plat.
