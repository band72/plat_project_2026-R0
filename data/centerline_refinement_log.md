# Centerline math & geometry — refinement log

Goal (user, 2026-09-24): every road ℄, intersection and curve of Beachwood Unit Two (PB30 Pg82/82A) computed from
plat values, every R/W corner a **25' fillet**, Beachwood Blvd computed, all intersections/schedules verified.
Curves are computed with the curves plugin (`plugins/curves/plat_curves`).

Source of truth: `engine/centerline_geometry.py` (derived, no typed coordinates, every value checked against a
second plat source). `engine/cogo_road_centerlines.py` takes its geometry from it street by street.
Run: `python3 -m engine.centerline_geometry` (schedule + checks), `python3 -m pytest test_centerline_geometry.py
test_beachwood_road_centerlines.py -q`, `python3 -m pytest plugins/curves -q`,
`python3 scripts/build_beachwood_road_centerlines.py` (report/DXF/PNG).

## Rules for each tick
- One backlog item per tick; derive, add a check against an independent plat value, test, regenerate outputs.
- Never type a coordinate. Never fudge a value to make a check pass: a failing check is reported as FAIL.
- Do not commit (the user commits). Do not touch `engine/cogo_block.py` (another agent is editing it).
- Read the scan (`Plat/Duval_Plat_Book_30_Page_82-2.pdf`, 300 dpi crops) before trusting any engine number.

## Backlog (in order)
6. **Surfwood Ave, Bayou Rd**, Unit One matchline ties.
7. **25' fillets on curved corners** (line x arc, e.g. Marina x Shellfish mouth, Mangrove x Sands/Cape Horn/SS):
   fillet tangent to a line and a circle; check against printed 25.0'/25.18' tangent-leg labels.
8. **Engine boundary** still uses `RAW_BOUNDARY_COURSES` (7 transcription errors, Bowditch hides 1.809'); the
   derived solver uses the caption (closes 0.042'). Switching changes the parent area — ask the user first.
8b. **User rule 2026-09-24: ALL block corner radii are 25'.** Add 25' fillets at the drainage-R/W block
   corners too: Block 18 NW/NE/SW (north 50' strip, west 50' strip, Blvd), Block 14 NW (Starfish x west strip),
   Starfish west end, Cape Horn west end, 40' drainage R/W west end. The scan draws some of these square
   (reader CR-S2-18) — note that in the report, but the user's rule governs.
9. PNG drawing: fillets + trimmed R/W now drawn (tick 4); remaining: de-clutter overlapping curve/P.I. labels.
9a. 40' drainage R/W east of Mangrove: only derived to the S-side frontage (96.80'); its bend onto S72°51'40"E
    and 60' width are not derived yet (R/W end left open in the linework).
9c. Plugin audit (`audit_engine_curves.py` CIDS) does not audit C_SHELLFISH_CL yet (F13) — add it.
9d. `engine/curves.py` `solve_curve_all_parameters` returns garbage for an impossible length+tangent pair (Δ>~134°)
    instead of raising (plugin audit section H). Small guard; engine/curves.py has someone else's uncommitted edits.
10. Report to user (not auto-fixed): `engine/cogo_block.py` Block 15 Lots 9/10 use a fictitious R=1959.86 east
    curve; the plat's Blvd W R/W is straight N00°41'40"W with 100.04' lot lines.

## DONE
- 2026-09-24 tick 0 — `engine/centerline_geometry.py` created. Sheet 2 grid (Mangrove N leg, Starfish, Sail,
  Shellfish E-W, Keel E-W) + **Beachwood Blvd**: 80' R/W, ℄ 40' west of and parallel to c26 N00°41'40"W,
  from the north line c27 to Unit One line c25. Lot-frontage sums reproduce it to ≤0.005' (Blocks 16/17/18 rows,
  111.54, 113.34, 80.04, 85.32, 100.04). Engine's fictitious Blvd curve R=1959.86 and "south projection" removed;
  Starfish/Sail x Blvd moved 52.5'/60.3' west to the derived points; Shellfish/Keel x Blvd and Blvd ends added.
  12 x 25' fillets (Mangrove x Starfish/Sail Δ=90°, Blvd x 4 streets Δ=91°42'50" T=25.759) on DXF layer
  C-ROAD-FILLET and in report §6b; derived checks in report §6c (20/20 PASS).
  Tests: root 249 passed (+10 new in test_centerline_geometry.py); plugin 3054 passed + 46 strict xfail.

- 2026-09-24 tick 1 — **Mangrove south leg**: ℄ 180' inside c2, deflection INT_MANGROVE_DEFL 552.67' south of
  Starfish ℄ (engine had 550.50'; outside offset of a 1°22'50" right turn adds 180·tan(Δ/2) = 2.17'). Checked by
  Block 14 Lot 6 splits (W R/W 461.88+60.45 → −0.023'; lot west line 461.88+59.22 → +0.002'; Lot 6/7 width 100.000).
  Sands / 40' drainage R/W / Cape Horn ℄ placed square to the south leg from the east-side lots (100.74, 100, 60,
  100, 40, 100) and confirmed by the west-side Block 14 sums (both residuals 0.004'). Marina W leg ℄ = Shellfish
  E-W ℄. 12 more 25' fillets (Marina x Mangrove NE/SE — SE is Δ88°37'10" T=24.405, tangent past the E R/W bend;
  Sands NE/SE; drainage and Cape Horn all 4 quadrants). Engine: INT_MANGROVE_DEFL now derived; "South St" renamed
  Marina Dr (west leg). Removed my own invalid tick-0 check (Block 16 south row is not all-straight 75' lots).
  26/26 checks; root 251 passed; plugin 3054 + 46 xfail; DXF PASS 130 lines / 48 polylines.
- 2026-09-24 tick 2 — **Marina Drive**: ℄ curve placed with plat_curves `PlacedCurve` (R=359.27, Δ=37°42'50" CW,
  T=122.70). P.C. 213.26' east of Mangrove ℄ from the NE lots (93.50+89.76 to radial Lot 31/32 line) = SW lots
  (99.93+83.26) to 0.003' (engine had 258.26'). All 6 printed edge chord bearings (85.24 x3 on R=389.27; 99.37/
  99.36/17.24 on R=329.27) reproduced to <3"; edge Δ sums to 37°42'50" within 2". Forward tangent S54°41'40"E
  (engine S49°52'40"E). Boundary c20 ends on Marina NE R/W (30.013'); ℄ exits at c20 (INT_MARINA_BOUNDARY).
  Engine: C_MARINA_CL from the placed curve (R 419.27 → 359.27), P.I. T=122.70, SE tangent to c20; removed the
  fictitious Sail and "South St" west stubs (Block 14 is continuous). INT_MARINA_KEEL kept at legacy 210' on the
  corrected tangent and flagged RED pending item 3. Plugin audit: Marina 6 → 0 failing checks; 4 strict xfails
  (F2 x3, F8) now pass and were removed. 37/37 derived checks; root 252 passed; plugin 3058 + 42 xfail.
- 2026-09-24 tick 3 — **Shellfish Dr east branch + Keel Dr west end**: both ℄ curves (R=167.95 / 143.93,
  Δ=52°17'10") placed with plat_curves from their E-W legs; P.T. fixed from the east lot rows (Shellfish N R/W
  97.78+8x75+5.45 stub; Keel N R/W 90+4x75 to radial Lot 14/15). Independent checks: printed mouth tangent legs
  25.0' → 24.986', 25.18' → 25.158'; mouth spacing on Marina ℄ 410.008' vs Blk 15 Lots 1/18/17 115+110+125+60;
  Shellfish SE chord 121.565 vs 121.56 (bearing exact), Keel SE chord 100.398 vs 100.40, Keel Lot 15 chord bearing
  0.4"; Shellfish NW chords sum to Δ within 12.8" (rounding bound ~15"). Keel 82.45' chord is the pinned plat
  discrepancy, not used. 4 more 25' fillets (mouth corners, 90°, line x line: mouths are on Marina's tangent).
  Engine: INT_MARINA_KEEL derived (no longer RED); C_KEEL_CL from placed curve; new C_SHELLFISH_CL (6th curve, F13)
  with P.I. rays; removed fictitious Shellfish west stub, Shellfish x Mangrove node, hard-coded INT_SHELLFISH_KEEL
  and the "Shellfish-Keel" assumption; Mangrove south chain now runs through derived Sands / drainage / Cape Horn
  nodes (Surfwood station still legacy). Keel SW corridor + cul-de-sac flagged RED "NOT ON PLAT" (item 9b).
  48/48 derived checks; root 254 passed; plugin 3058 + 38 xfail; audit 35 → 33; DXF PASS 138 lines / 55 polylines.
- 2026-09-24 tick 4 (user flagged the Mangrove/Marina/Keel area in the DXF) — fixed what the screenshot showed:
  (1) R/W edges were full-length offsets crossing every opening → new corridor model + `trim_row_linework`: each
  edge split at fillet tangent points / corners / other edges, kept only if outside every other street's R/W and
  every return's corner zone; DXF/PNG draw it for all derived streets (59 pieces). New topology check: every 25'
  return joins trimmed edges at both tangent points. (2) That check exposed mis-oriented returns (tangent points
  inside the street opening at Sail/Mangrove SE, all Blvd NW, Mangrove south-leg NE/SE) — `fillet_at` now takes the
  directions the block lines run away from the corner; Blvd NW returns are Δ88°17'10" (were wrongly 91°42'50").
  (3) Orphan returns at Sands / drainage / Cape Horn → **Sands** (item 4) and **Cape Horn** derived: P.C. 80' /
  25.0' past the Mangrove E R/W corner, every printed edge chord reproduced from the bearing pattern (≤0.009'),
  ℄s pass through the midpoints of boundary jogs c19 (0.034') and c15 (0.014'), Sands ℄ 260.026' SW of Marina ℄.
  Engine: fictitious Sands chain off the Blvd and mirrored Cape Horn replaced (helper `_add_derived_curved_street`).
  (4) **Keel SW corridor + cul-de-sac removed** (user: "this area needs attention"; not on the plat).
  Extra check: Shellfish N mouth return starts 0.008' from Marina NE edge P.T. (Blk 16 Lot 29). Keel mouth has a
  0.158' straight between the return and the edge P.C. (printed 25.18' leg). 72/72 checks; root 256 passed;
  plugin 3055 + 23 xfail (13 strict xfails for F3/F4/F9 now pass → removed); audit 33 → 21 (all San Salvadore).
- 2026-09-24 tick 5 — **San Salvadore Ave**: ℄ R=269.96' (engine had 299.96' = the N edge, F1), built W->E CW
  (engine mirrored it from a typed P.C. (8350, 10250), F3). N R/W 140' + 109' (Blk 9 Lots 27/26, read on the Sheet 1
  scan) below Cape Horn S R/W; P.C. 25.0' past the corner (printed tangent legs at Blk 9 Lot 26 and Blk 12 Lot 8).
  Checks: N edge chords 67.91/66.18/55.76 and S edge 106.60/44.61 all ≤0.003' from the printed bearing pattern;
  ℄ through the c13 midpoint (0.012'); 260.017' SW of Cape Horn ℄ (Blk 9 depths). +2 x 25' returns at Mangrove.
  Removed the fictitious "San Salvadore-Surfwood tie" (the Block 12 Lot 8-10 labels are lot lines, not a street).
  81/81 derived checks; root 258 passed; plugin 3064 + 10 xfail (11 strict xfails F1/F3/F8/F9 for SS now pass →
  removed). Plugin audit: every ℄ curve 0 failing checks; total 21 → 9 (5 x F9 validator blindness, 2 stale audit
  checks, 1 parent-area/boundary item). DXF PASS 81 lines / 108 polylines.
- 2026-09-24 tick 6 — **F9 validator**: `validate_all_curves` now checks independent identities at 0.02' (RP-PC =
  RP-PT = R; PI-PC = PI-PT = T; signed deflection at PI = ±Δ per CW/CCW; RP side of the back tangent; R and T vs the
  plat ℄ Curve Data block via the derived network, Shellfish T vs formula) instead of formulas of its own R, Δ.
  All 6 curves valid; the plugin's 5 corruption probes (centre +500', centre reflected, direction flipped, R+30
  recomputed, PT +0.15') are now all detected (were 0/5). New root test corrupts 3 curves and expects failure.
  Removed the 2 stale audit arithmetic items (their metadata was deleted with the fictitious geometry).
  Root 262 passed + 1 failure in untracked raster2dxf (another loop's work, unrelated); plugin 3069 + 5 xfail;
  plugin audit 9 → 2 (parent area / boundary item 8, and engine/curves.py domain guard item 9d).

## LOG
- 2026-09-24 02:20 — tick 0 (manual) complete, loop started (every 10 min).
- 2026-09-24 02:45 — tick 1 (manual, right after loop start): Mangrove south leg done.
- 2026-09-24 03:00 — tick 2: Marina Drive done.
- 2026-09-24 03:20 — tick 3: Shellfish + Keel branch curves done; cul-de-sac question raised.
- 2026-09-24 04:00 — tick 4: user-flagged area fixed (trimmed R/W, return orientation, Sands, Cape Horn, no cul-de-sac).
- 2026-09-24 04:20 — tick 5: San Salvadore done; all 6 plat ℄ curves now derived and audit-clean.
- 2026-09-24 04:35 — tick 6: validator now has teeth (5/5 probes detected).
