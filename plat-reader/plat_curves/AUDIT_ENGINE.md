# Engine curve audit — `engine/cogo_road_centerlines.py`, `engine/curves.py`

Auditor: engine-auditor (plat_curves swarm). Read-only: no engine file was edited; fixes below are **proposals**.
Audited against `engine/*` at `main` @ `d573c74`; re-verified at `9070ff5` (the only engine change is +26 lines inserted at `:1980`, so every line number cited below still holds).
Reproduce from the repo root: `python3 plugins/curves/plat_curves/audit_engine_curves.py` (62 failing checks) and
`python3 -m pytest plugins/curves/plat_curves/tests/test_engine_bridge.py -q` (104 pass, 72 strict-xfail = the bugs below, F-numbers in the reasons).

Evidence used, in order of weight: (1) the 300 dpi scans, looked at by the auditor (Sheet 1 Cape Horn/San Salvadore crops,
Sheet 2 Marina/Sands/Keel/Shellfish crops); (2) reader JSONs in `data/readings_*.json` (all four have landed and agree with (1));
(3) pure geometry identities that need no plat at all. Nothing in the prior-session table `BEACHWOOD_CURVE_DATA`
(`scripts/build_beachwood_vector_consensus.py:352`) is trusted except where a reader re-read it: its L/chord/chord-bearing
columns are *derived*, not printed (a plat `℄ Curve Data` block prints only **Δ, R, T**).

## 0. Verdict at a glance

| Curve | plat ℄ block (Δ, R, T) | engine R / T / L / C | R/T verdict | construction verdict |
|---|---|---|---|---|
| San Salvadore | 36°20'00", **269.96**, 88.59 | 299.96 / 98.43 / 190.22 / 187.04 | **WRONG (+30.00)** | **broken** (F3) |
| Cape Horn | 36°20'00", 327.01, 107.31 | 327.01 / 107.30 / 207.37 / 203.91 | ok | **broken** (F3, F5) |
| Marina | 37°42'50", **359.27**, 122.70 | 419.27 / 143.20 / 275.98 / 271.02 | **WRONG (+60.00)** | consistent, but on the wrong R |
| Sands | 36°20'00", 459.36, 150.73 | 459.36 / 150.73 / 291.30 / 286.44 | ok | **broken** (F3, F4) |
| Keel | 52°17'10", 143.93, 70.65 | 143.93 / 70.64 / 131.35 / 126.84 | ok | **broken** (F6) |
| Beachwood Blvd | *no block; curve not on plat* | 1959.86 / 130.34 / 260.19 / 260.00 | **fabricated** (F7) | broken |
| Shellfish (7th block) | 52°17'10", 167.95, 82.35 (plat T off by 0.084) | *not modelled* | missing (F13) | — |

Only Marina's PC/PI/PT/centre/direction are mutually consistent (all identities hold to 0.001 ft). Of the six drawn arcs, **five end at the
wrong point**: the DXF/PNG arc ends 116.6 (SS), 5.3 (CH), 538.5 (Sands), 253.7 (Keel), 17.3 (Blvd) ft from the stored `pt_point`.

## 1. What the code actually does, curve by curve

`solve_curve_all_parameters(radius, delta)` supplies L/T/C, so every T/L/C is just a function of the chosen R, Δ. What differs is where R comes
from and how PT / centre / labels are typed in by hand.

| Curve | R (line) | how R was chosen | comment claims | direction | centre (line) | PT (line) | back / forward tangent labels |
|---|---|---|---|---|---|---|---|
| SS | 299.96 (`:642`) | stated 269.96 **+30** | "Stated curve C17 on North R/W" (`:640`, `:695`) | CW (`:692`) | PC + R along S35°18'20"W = right of SE travel (`:666-667`) | PC + C along **S72°51'40"E = left-turn chord** (`:668`) | in S54°41'40"E ✓; out `"S91°01'40"E"` (`:1495`) invalid |
| CH | 327.01 (`:1385`) | stated, used directly | "Centerline curve C16" (`:1384`) | CCW (`:1427`) | PC + R along N35°18'20"E = left of SE travel (`:1394`) | chord **S74°21'40"E** (`:1393`) | in ✓; out `"S91°01'40"E"` (`:1628`) invalid |
| Marina | 419.27 (`:968`) | stated 389.27 (a *North R/W* value) **+30** (`:1008`) | "derived from North R/W R=389.27' + 30'" | CW (`:1005`) | PC + R along S02°24'30"E = right (`:976-977`) | chord S73°33'06"E (`:980`) ✓ | in N87°35'30"E ✓; out `S49°52'40"E` (`:1463`,`:1012`,`:1028`) wrong |
| Sands | 459.36 (`:1347`) | stated, used directly | "Centerline Curve C11" (`:1346`) | CCW (`:1378`) | PC + R along N02°24'30"W = **right** of W travel (`:1355`) | chord **N70°41'40"W** (`:1354`) | in S87°35'30"W; out N53°55'30"W (`:1562`) |
| Keel | 143.93 (`:1064`) | stated, used directly | "Centerline Curve C14" (`:1063`) | CW (`:1106`) | PC + R along **N54°41'40"W = left** of NE travel (`:1073`) | chord N61°26'55"E (`:1072`) ✓ | in N35°18'20"E, out N87°35'30"E ✓ |
| Blvd | 1959.86 (`:1148`) | R/W-type number, no ℄ block | "arterial centerline curve" | CW (`:1163`) | PC + R along S87°35'30"W = perpendicular to the **chord** (`:1149`) | PT = Sail/Beachwood point, 260.00 from PC | in S02°24'30"E (= chord); out S10°01'00"E (`:1529`) |

**Comments contradict each other (and the geometry).**
* `:640` says 269.96 is the *North R/W* radius, but Cape Horn `:1384`, Sands `:1346`, Keel `:1063` treat the same kind of stated number as the
  centreline. All six are printed as `℄ Curve Data` blocks. The engine applies "+30" to exactly the two curves whose stated R it decided was an edge.
* Marina `:1008` adds 30 to the *north* edge to reach ℄. But `:975` says the curve "deflects CW to the south" and `:977` puts the centre south of the
  PC, so the north edge is the **outer** edge and ℄ = 389.27 − 30 = **359.27** — exactly the plat's ℄ value. The code is wrong even by its own logic.
* `test_beachwood_road_centerlines.py:285-289` ("CL 299.96 → inner 269.96 … Matches stated North R/W curve") is false in the engine's own model:
  the SS centre is south-west of the PC, so the north (NE) edge is the *outer* edge (329.96).
* `MASTER_PROMPT.md:1865-1866` ("inner/outer radii match stated plat curve tables: Marina 389.27/449.27, SS 269.96/329.96, Blvd 1909.86/2009.86") is
  false: plat edges are Marina 329.27/389.27, SS 239.96/299.96, and there is no Blvd curve.
* `validate_all_curves` docstring `:1748-1754` and `README_ROAD_CENTERLINES.md:253` say "within 0.05'"; the code uses `< 0.2` (`:1777`); the test uses 0.1.

## 2. Findings, ranked

Severity: **Critical** = a published number is wrong against the plat; **High** = geometry drawn/exported is wrong; **Medium** = hides or
propagates errors; **Low** = small/latent.

### F1 — San Salvadore ℄ radius is 30 ft too large (Critical)
* `engine/cogo_road_centerlines.py:642` `r_ss_cl = 299.96`; comments `:640-641`, `:658`, `:695`; README `:192`; test `:73`, `:289`.
* Evidence: plat block (Sheet 1) `℄ Curve Data Δ=36°20'00" R.=269.96' T.=88.59'` (reader `s1_ss_cl_curve_data`, conf 0.94); `269.96·tan(18°10')=88.584`.
  Independent: the N/S lot chords 55.76 (N, lot 24) and 44.61 (S, lot 9) carry the same bearing N60°01'40"W (same radials) and are in ratio 1.250
  ⇒ R_N = 300, R_S = 240, ℄ = 270; reader `s1_ss_cl_curve_data` also cites concentric edge chords on R−30 = 239.96 and R+30. So 299.96 is the **north (outer) R/W edge**, not ℄.
* Downstream: T 98.43 (plat 88.59), L 190.22 (171.19), C 187.04 (168.34); P.I. `:1470`; R/W edges drawn 269.96/329.96 instead of 239.96/299.96
  (`get_offset_arcs`, DXF `:2061-2071`, PNG `:2216-2225`); guild strings `:1673-1676`; `total_centerline_length` fed to the consensus solver `:1710`.
* Fix (minimal): `r_ss_cl = 269.96`; comments → "plat ℄ block R=269.96, T=88.59; R/W edges 239.96 / 299.96"; PI note `:1473-1478` T=88.59; flip the
  test/README expectations (inner 239.96, outer 299.96).

### F2 — Marina ℄ radius is 60 ft too large; the sign of the half-width is wrong (Critical)
* `:968` `r_marina_cl = 419.27`; note `:1008`; README `:191`; test `:66-69`; `:1441-1446` ("T=143.20'"); guild strings `:1682-1683`.
* Evidence: plat block `R=359.27' T.=122.70' Δ=37°42'50"` (reader `S2-MARINA-CL`, conf 0.98; my own crop agrees; `359.27·tan(18°51'25")=122.704`).
  North R/W arc chords 85.24 (lots 29-31, Δ_lot 12°34'17") ⇒ R=389.27, so 389.27 is the *north* edge = ℄ + 30 for this right-turning curve.
* Downstream: L 275.98 vs 236.48 (+39.49), C 271.02 vs 232.24. `get_centerline_reference_alignments` (`:1949`) puts Marina P.T. at STA 7+14.24 and the
  Keel intersection at 9+24.24; with the plat R they are 6+74.74 and 8+84.75. R/W edges drawn 389.27/449.27 vs plat 329.27/389.27: the engine's *inner* edge has the plat's
  north-edge radius (389.27) but is drawn on the south (centre) side; its outer edge (449.27) matches nothing on the plat.
* Fix: `r_marina_cl = 359.27`; note → "℄ = North R/W 389.27 − 30 (north edge is the outer edge of this CW curve)"; regenerate T/L strings.

### F3 — San Salvadore / Cape Horn / Sands are built mirrored; San Salvadore contradicts itself (High)
* `:660-696` (SS), `:1392-1431` (CH), `:1354-1382` (Sands); straight runs `:699-716`, `:775-791`, `:1222-1240`.
* Plat (both sheets, looked at directly): each of these streets runs **west→east**: an E-W tangent `N88°58'20"E` (the bearing printed on the lot lines
  along the Mangrove-side stubs) bends **right (CW) by 36°20'** onto the diagonal `S54°41'40"E`; the diagonal is *after* the curve, the ℄ block sits
  at the west end, the centre is on the **south** side (inner edge = south lots; reader: "turning right/CW going west->east, centre on the south side").
  The engine puts 650'/800' of diagonal *before* the PC and curves away from it: a mirror image.
* San Salvadore is additionally self-contradictory: centre `:666-667` is on the right of the SE approach (⇒ CW, flag `:692` says CW) but the PT `:668` is
  placed by the **left-turn** chord S72°51'40"E and the P.I.→P.T. ray (`:1495`) heads N88°58'20"E, a left turn. `|PT−centre| = 399.93` vs R=299.96;
  the drawn (CW) arc ends 116.6 ft from `pt_point` (`export_dxf :2052-2059`, `render :2203-2211`).
* Fix (minimal, same recipe for all three): keep the existing diagonal anchor as the curve's *diagonal tangent point* and build the curve in the
  engine's PC→PT sense from it: back az `N54°41'40"W`, `direction="CCW"`, centre = anchor + R along **S35°18'20"W**, PI = anchor + T along
  `N54°41'40"W`, PT = PI + T along `S88°58'20"W` (chord `N72°51'40"W`), then move the straight run to start at the anchor and go **SE** (not NW).
  Better: build every curve with `plat_curves.core.PlacedCurve.from_pi(pi, back_az, forward_az, radius)` and *derive* `center_point`, `pt_point`,
  `chord_bearing`, `pi_tangents[*].bearing` from it — never type them (backlog item 2 in `REFINEMENT_LOG.md`). Absolute anchors `:650`, `:1211`
  are hard-coded points not tied to the traverse; re-anchor from the Mangrove R/W and the Unit One P.R.M.

### F4 — Sands: centre and chord disagree with the flag (High)
* `:1354-1355`, `:1377-1378`, ray `:1562`.
* `direction="CCW"` but the centre is on the *right* of the S87°35'30"W approach and `PT` is placed by chord `N70°41'40"W` (a right turn). Analytic for the
  approach as coded: CW chord `N74°14'30"W`, forward `N56°04'30"W`; coded chord is 3°32'50" off, coded out-ray `N53°55'30"W` is 2°09'00" off.
  `|PT−centre| = 442.38` vs R 459.36; `|PI−PT| = 156.66` vs T 150.73; interior angle at PI off by 6.23°; drawn arc leaves the PC 180° opposite to the approach and ends 538.5 ft from PT.
* The plat's west tangent is N88°58'20"E (crop: "N.88°58'20"E." beside the Sands ℄ block), not the hedged S87°35'30"W. Fix: as F3.

### F5 — Cape Horn: hard-coded chord bearing 1°30' off analytic (High)
* `:1393`, `:1426` `S74°21'40"E`; analytic for the coded back tangent S54°41'40"E, Δ=36°20', CCW is **S72°51'40"E** (=`:668`, San Salvadore's chord).
* `|PT−centre| = 321.92` vs 327.01 (−5.09), `|PI−PT| = 109.02` vs T 107.30, drawn arc ends 5.34 ft from PT; out-ray label `S91°01'40"E` (`:1628`) invalid.
  The same `74°21'40"` appears in the prior-session table for C16/C17 (a derived column, not printed on the plat), so it was probably carried over. Fix: derive the chord (F3).

### F6 — Keel: centre on the wrong side of the PC (High)
* `:1073` `p_keel_center = p_keel_pc.offset(N54°41'40"W, R)`. Travel PC→PI is N35°18'20"E and the curve turns **right** to N87°35'30"E (`:1106` CW, and the
  PI/PT geometry agree), so the centre must be S54°41'40"E of the PC. As coded, `|PT−centre| = 229.98` vs 143.93, the DXF/PNG arc leaves the PC heading
  SW (180° from the approach) and ends 253.7 ft from PT. Plat check: south R/W chord 100.40 ⇒ R=113.93 = 143.93 − 30 (inner edge lies on the SE side).
* Fix: `:1073` → `parse_bearing("S54°41'40\"E")`. Note also `SEG_KEEL_MAIN :1051-1061` runs 380' **S35°18'20"W** from Marina and the PC is placed 259.4 ft
  down it (`:1071`, "T+50" is arbitrary); in the Sheet 2 crop Keel Drive leaves Marina's NE R/W heading N35°18'20"E and its ℄ curve starts close to that R/W (reader:
  "west end, curve into Marina Dr"), so the 259.4 ft is arbitrary. The Keel R/Δ/T themselves are right.

### F7 — Beachwood Blvd ℄ curve is not on the plat (High)
* `:1146-1167`, `:1501-1533`, R/W width 100 (`:1164`), README `:193`, test `:80`.
* Evidence: reader negative result (`NEG_beachwood_blvd_arterial_curve`, conf 0.97): east boundary is a straight `N.0°41'40"W 1247.95'`; pixel test over 1223 ft
  shows ≤1.2 ft (rms 0.26) deviation where a R=1959.86, Δ=7°36'30" arc would bow 4.3 ft; the tokens 1959.86 / 1909.86 / 2009.86 / 7°36'30" do not occur
  on either sheet; every block east line is a straight `N.2°24'30"W`. There is no ℄ block for it. (`R=1959.86` is asserted as "C2" in
  `scripts/build_beachwood_boundary.py:441-443` — no support on the scan.)
* The engine's Δ is a chord-260 artefact: PC/PT are just the Starfish and Sail street ends 260.00 apart along S02°24'30"E. Internally: hard-coded Δ=7.608333, L=260.19,
  T=130.34, C=260.00 (`:1158-1161`) are mutually inconsistent (L −0.06, C −0.06, T +0.02); the centre (`:1149`) is perpendicular to the **chord**, so
  `|PT−centre| = 1977.03`; the P.I. (`:1503`) is put **on the chord** (`|PI−PT| = 129.66`, interior angle 180°); out-ray `S10°01'00"E` (`:1529`) turns *left* though CW.
  Analytic for chord 260, R 1959.86: Δ=7°36'23.7", T=130.29, back S06°12'45"E, forward S01°23'45"W. The 100' width is unsupported (`scripts/generate_lot_images_dxf.py:204` says 80').
* Fix: delete `C_BEACHWOOD_BLVD_CL` and its P.I. ray/intersection (or move it to an "assumed, not on plat" list excluded from validate/DXF/consensus counts);
  keep Starfish/Sail as straight ties to the boundary. Update README row, test `:80`, `total_curves_count`.

### F8 — Invalid and wrong hard-coded bearings (Medium-High)
* `"S91°01'40"E"` at `:1495` (SS) and `:1628` (CH): not a quadrant bearing (`parse_bearing` raises `ValueError`; verified: `PI_RAY_SS_OUT.get_offset_lines()` raises).
  91°01'40" is the *azimuth complement* (180−88°58'20"); the bearing is `N88°58'20"E`. Latent crash for anyone who iterates `pi_tangents` through `get_offset_lines`.
* **Marina forward tangent** `S49°52'40"E` (`:1012`, `:1028`, `:1463`): the analytic forward tangent of N87°35'30"E + 37°42'50" is **S54°41'40"E** (the diagonal
  system bearing; 4°49'00" different). `SEG_MARINA_SE_TANGENT` therefore leaves the P.T. with a 4°49' kink and `INT_MARINA_KEEL` (`:1012`) is mis-placed.
* `:1529` Blvd, `:1562` Sands: see F7, F4. Keel and Marina chord labels are fine (Marina 1", Keel 0").
* Fix: generate every label with `azimuth_to_bearing((back ± Δ) % 360)`; add `assert parse_bearing(label)` in `CenterlineSegment.__post_init__`.

### F9 — `validate_all_curves` cannot fail (Medium; explains why F1-F7 were invisible)
* `:1747-1779`. `diff_arc`, `diff_chord`, `diff_tan` compare stored L/C/T with formulas of the **same** R, Δ (they are equal by construction: 0.0000 for 5/6
  curves; the 6th passes only because the tolerance is 0.2 ft). `diff_euclid` compares `|PC−PT|` with the chord that was used to *place* PT, so it is also a
  tautology. It never checks: PT on the circle, `|PI−PC| = T = |PI−PT|`, angle at PI, direction vs turn sense, centre side, any stated plat value.
  Probes (`audit_engine_curves.validator_probe`): centre moved 500 ft, centre reflected to the wrong side, direction flipped, R+30 with L/T/C/PT recomputed, PT moved 0.15 ft
  — **none detected**. The "100-agent consensus" (`run_100_agent_consensus`) certifies the same numbers.
* Fix: take a `plat_blocks` dict of stated (R, Δ, T) and add the identities in `audit_engine_curves.checks_for` (tolerance 0.02); return `is_valid = all(...)`.
  The bridge tests already assert the desired behaviour (strict-xfail today).

### F10 — Frontage summations (Medium/Low)
* `summed_lot_frontages` are metadata; the geometry uses hard-coded points, so they do not reconcile: `SEG_SHELLFISH_MAIN` sum 901.34 vs drawn 651.49
  (bearing label 0.83° off, `:1282`); `SEG_ASSUMP_SHELLFISH_KEEL` 839.69 vs 498.67 (1.09° off); `SEG_ASSUMP_SANDS_APPROACH` 365.46 vs 60.24 (label S87°35'30"W vs
  actual N65°38'W, `:1211`, `:1227`); `SEG_ASSUMP_SS_SURFWOOD_TIE` label S23°14'20"W vs actual S44°41'E (67.9°, `:734`).
* Plug entries make sums hit pre-chosen totals: `149.92` (=350.00−200.08), `46.59`, `60.17`, `89.76`, `350.00`, `425.00`.
  `SEG_SAIL_MAIN :903` Block 16 lots 1-8 = **618.50** but its own note "68.50' straight + 7x75.00'" = **593.50**.
* Chord vs arc: `:1324` Block 15 lot 1 "153.25 R=167.95' Arc" is the full ℄ arc `167.95·Δ = 153.27`. Sheet 2 Note 1: distances on curves are chords, and the lot-side chord
  printed at that corner is **121.56** on R=137.95 (=167.95−30; arc 125.88). It is a ℄ length added into a lot-frontage sum. Lots 9/10 "Curve C2 Arc 100.04" (`:1194-1195`) are on the
  non-existent C2 (F7); arc/chord differ by only 0.011 ft there.
* Fix: either drive the segment length from the summation or label it informational; drop plugs or mark them `"plug": True`; use chord 121.56.

### F11 — Parent boundary c22 (Low)
* `:169` chord 99.98 S57°53'59"E is exactly what the plat caption prints ("curve to the left, R=894.08, chord bearing S57°53'59"E, chord 99.98") — correct as a traverse course.
  `Δ` from chord = 6°24'37.5", from the c21 tangent S54°41'40"E = 6°24'38" (agree). But the note `L=100.00'` is not printed on the plat: arc from chord is **100.03**
  (prior tables carry Δ=6°24'25", 12" short). Reader: 894.08 is the R/W edge of Unit One's ℄ R=924.08 (924.08−30).
* `:251` `parent_area = shoelace_area(...)` is the **chord polygon**. The traverse is CCW and the curve turns left, so the arc bulges outward and the true area is
  larger by the segment `R²(Δ−sinΔ)/2 = +93.24 sq ft` (2,794,285.0 vs 2,794,191.8; 64.15 ac unchanged to 2 places). Fix: add the segment at `:251`.

### F12 — `engine/curves.py` (Low; math is correct)
* Verified: 1620 randomized solves over all 27 non-collinear pair combinations for Δ≤90° recover R and Δ (rel 2e-4); `Curve.arc_points`,
  `tangent_in_bearing`, `tangent_out_bearing` match the SPEC construction for CW and CCW to 7e-5 ft (bearing-string rounding).
* `solve_curve_all_parameters` returns garbage instead of raising for Δ ≳ 100° in four pairs (`length+tangent`, `length+external`, `chord+external`,
  `tangent+mid_ordinate`): e.g. `length,tangent` at Δ=134.8° → radius −0.0, Δ −1.3e13 (`curves.py:334-352`, `:367-383`, `:405-419`, `:435-450`). Fix: reject Δ>~170° results / raise `ValueError`.
* `trace_curve_from_skeleton :684-685`: `if chord_dist > 2R: radius = chord_dist/2` silently replaces a stated radius (R=25, chord 74.86 → 37.43). `chord > 2R` is
  the off-by-one-edge signature `engine/notes_audit.py` exists to catch; raise `ValueError` instead.
* `Curve.rot` defaults to `"CCW"` (`:29`) — silent for callers that forget it; `determine_curve_direction_from_skeleton` falls back to `"CCW"` (`:551`). Prefer required.

### F13 — Shellfish ℄ curve is missing; the engine has a Blvd curve instead (Medium)
* The plat has six ℄ blocks: SS, CH, Marina, Sands, Keel **and Shellfish (R=167.95, Δ=52°17'10", T=82.35)**. The engine has no Shellfish curve (no PC/PT/PI, no R/W edges 137.95/197.95),
  while it carries the Blvd one (F7). The plat's own T for Shellfish disagrees with R,Δ (`167.95·tan(26°08'35") = 82.434` vs printed 82.35; reader: "keep T as printed").
  Keel vs Shellfish radii differ by 24.02, not 60, so they are two different ℄ curves, not the two edges of one corridor.

### F14 — Three copies of the arc construction (Low, design)
* `export_dxf :2047-2076`, `render :2199-2233` (both direction-aware) and `get_centerline_reference_alignments :1953-1959` (CW-only) each rebuild the arc from
  `center_point`+`pc_point`. This is exactly the "second independent construction" hazard of the `review-plat-notes` skill. Add one `CenterlineCurve.arc_points(n)` (SPEC:
  `offset(RP, rp_az + 180° + sgn·degrees(s/R), R)`) and call it from all three.

## 3. Spill-over outside the audited files (not edited; for the lead)

The same ℄-vs-R/W-edge confusion exists in the block solvers, invisible to closure checks:
* Sheet 2 Shellfish curve: edge chords 51.68 / 68.75 / 59.50 sum to Δ=52°17'10" **only for R=197.95 (=167.95+30)** (Δ 15°00'05" + 20°00'03" + 17°17'15" = 52°17'23", 13" from 52°17'10", i.e. chord rounding);
  with R=167.95 they sum to 61.73°. `test_block16_cogo.py:104-115` (`R=167.95`, chord 68.75 ⇒ Δ=23°37'15") and `scripts/compute_block16_mapcheck.py:15` use the ℄ radius; the true edge is
  R=197.95, Δ_lot=20°00'03".
* `scripts/mapcheck_block15.py:120-132`: Block 15 lot 1 `curve_specs` R=167.95, Δ=52.286° while `stated_dimensions` says chord 121.56; on R=167.95 that arc has chord 148.00.
  R=137.95 gives 121.56 (Δ 52°17'01").
* `MASTER_PROMPT.md:1756` "R=269.96 … same curve as Block 9 Lots 23-26": lots 24-26 are on the north edge, R≈299.96.
Run `engine/notes_audit.audit_typical_radius` reasoning as **Step 4** of the review skill on these before certifying Blocks 9/15/16.

## 4. What checked out (do not re-litigate)

* `get_offset_arcs` (`:117-144`): R∓hw with the same Δ, T/L/C recomputed — algebra correct for any direction; the *labels* INNER/OUTER are relative to the centre, so the caller must map
  them to N/S/E/W from the centre side (F1, F2 error is in R, not here). Keel edges 113.93/173.93 and Sands 429.36/489.36 are right.
* `get_culdesac_geometry` (`:1781-1868`): all 15 construction identities hold to 1e-9 — `yf=√((Rb+Rf)²−(w+Rf)²)=50.99`, `θ=asin((w+Rf)/(Rb+Rf))=47.17°`,
  fillet radius ⟂ R/W edge, fillet–bulb external tangency `|C−CP|=Rb+Rf=75`, PRC collinear with the two centres, bulb sweep `360−2θ=265.67°`, throat 60.00, polyline gap ≤6.4 ft.
  Fillet radius 25' = Note 4. (Whether Keel Drive has a dead-end at all is an assumption outside this audit — see F6 layout note.)
* Marina PC/PI/PT/centre/direction/chord label (`:968-1009`) — geometry correct; only R is wrong (F2). Keel R/Δ/T/chord label correct (centre is F6). Cape Horn and Sands R/Δ/T correct.
* Delta in every block equals the exact turn between the plat's own tangent bearings (Marina 37°42'50" = N87°35'30"E → S54°41'40"E; Keel 52°17'10" = N35°18'20"E → N87°35'30"E;
  SS/CH/Sands 36°20'00" = N88°58'20"E → S54°41'40"E).
* `engine/curves.py` numerics (F12 aside).
