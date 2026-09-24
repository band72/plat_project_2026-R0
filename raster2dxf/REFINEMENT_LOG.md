# raster2dxf refinement log

Training set: `Plat/training/drawings/*.png` (81 images: scan crops of PB30 P82,
full 300-dpi sheets, our own dark-theme mapcheck renders, UI screenshots).
Outputs: `Plat/training/output/{dxf,png,overlay,json}/<name>.*`, `summary.{json,md}`.

## Tick protocol (every 10 minutes)

1. Read `Plat/training/output/summary.md`; choose ONE backlog item (top first),
   or the worst-scoring image class if the backlog item is blocked.
2. Implement it in `raster2dxf/` only (never `engine/*` except `engine/labels.py`,
   which the user authorized for the label-alignment fix; never commit —
   the user commits via Antigravity).
3. Add/adjust a test in `test_raster2dxf.py`; `python3 -m pytest test_raster2dxf.py -q`.
4. Re-run on the 8-image **probe set** first (fast):
   `python3 -m raster2dxf.run --only crop_lot23_24_detail,lots23_24_clean_scan,crop_block6,zoom_cape_horn_curve_data,block9_mapcheck_drawing,block13_mapcheck_drawing,zoom_lot28_29,street_north_of_24,mapcheck_individual_parcels_grid,block16_mapcheck_drawing,page1_300dpi,page0_300dpi -j 12`
   Keep the change only if probe mean score does not drop (> 0.005) and no
   probe image drops > 0.03; otherwise revert it and log why.
5. Every 3rd tick (or after a kept change touching linework), full batch in the
   background: `python3 -m raster2dxf.run -j 10`.
6. Append a dated entry below: item, measured before/after, kept/reverted.

## Backlog (ranked)

000. **page1 monument miss — parked.**  (7338, 2608) is rejected by the
   fixed-band hollow test (0.58 > 0.5: the band lands on its inner ring) and
   its 0.4 r inner reads 0.53.  Threshold sweeps (0.55–0.7) change nothing;
   a radial-profile rewrite regressed the truth set (block9 F1 1 → 0, page1
   0.9 → 0.83).  Monument F1 is 1.0 on 6/7 truth images and 0.9 on page1 —
   good enough; move on to render OCR (#0000).
0000. **Table panels — parked (two approaches failed).**  (a) frames: the
   renders' table-panel borders are too faint (< ink 35) to extract; only
   lot polygons / callout boxes come out as rectangles.  (b) text density
   (≥ 12 labels within 10 char_h, far from lines): re-kinds real scan
   dimensions in dense street areas (crop_lot23_24's centreline bearing
   N 87°35'30" E, 89.76').  A working version would need the render's own
   faint panel border (a dedicated low threshold ~15 on renders only, for
   rectangles ≥ 20 char_h) — try only if render assoc matters to the user.
00a. **Curve coverage** — 5/6 catalog curves now read on the two sheets
   (not yet: Marina 359.27/122.70, Keel 143.93/70.65).  Check whether their
   anchors are among the first MAX_ANCHORS=6 (raise the cap or rank
   anchors by fragment strength), and consider curve-number (C#) → curve
   table linking on the renders (block13/16) as the other half of the
   user's curve requirement.
00. **beachwood_road_centerlines** (0.585) — combined calls parse, but most
   of its labels sit beside dashed/colour-coded centerlines; check whether
   the dashed centerlines survive merge_collinear (coverage) and are near
   enough for _near_lines.  Next: overlay-driven, one hypothesis per tick.
0. **Render-text OCR** (blocked on approach) — upscaling small crops by
   glyph height was tried twice in tick 3 and REVERTED both times (probe
   0.721 → 0.711 / 0.713).  Next idea: renders are digital, so OCR the
   *original colour* crop (anti-aliased grey, no Otsu binarization) and/or
   dilate 1 px before binarizing; don't touch the scan crop path.
1. ~~Geometry-constrained decoding~~ — done tick 1 (see log). Follow-ups:
   QA layer is noisy (17-19 flags on scan crops) because
   unverified misreads disagree with geometry: only QA-flag labels whose
   *best* OCR confidence >= 60.
2. **Scan label clustering** — lot numbers split into single digits when a
   nearby line forces a vertical direction; stacked bearing/distance pairs
   merge. Try: per-glyph direction vote from the 3 nearest lines; reject
   joins whose glyph heights differ > 1.8x.
3. **Tesseract variants** — add shear 0.18 and 0.4; psm 7 per-crop re-OCR only
   for crops whose best read is not grammar-valid (bounded cost).
4. **Line under text** — labels sitting ON a (dashed) line lose glyph pixels to
   the linework raster. Remove only the skeleton ±sw/2, not ±0.8sw+1.
5. **Tangent points** — greedy line prefix eats ≈ ½·chord(tol) of the arc; after
   an arc is chosen, backtrack the previous line end to where the circle
   residual exceeds the line residual.
6. **Curve-table radius snap** — when scale is known and a C# label is attached
   to an arc with table R, refit that arc with fixed R (least squares centre)
   and QA-flag if |R_fit − R_table| > 3%.
7. **Render class** — gridlines/axes/title of our own mapcheck PNGs: classify
   faint low-saturation full-width lines as `PLAT-GRID` (off by default);
   lot fill boundaries vs stroke colors.
8. ~~Dimension-free images~~ — notes panels done tick 24.  Web UI
   screenshots (web_interface_*) still score as renders; low priority.
9. Performance: trace_paths/fit_path are pure Python; page0/page1 (9000×5400)
   are the long poles — vectorize or cythonize if a full batch > 8 min.

## Log

- 2026-09-23 v0.1 — package built: polarity-independent ink, skeleton-graph
  line/arc fit, direction-aware glyph clustering, batched shear-variant OCR,
  label↔geometry association, scale from distance labels, rotation from
  bearings, curve-table column inference by L=RΔ consistency, ezdxf R2010
  output with NCS-style layers + XDATA, DXF-render PNG + overlay PNG.
  Label alignment fixed both here and in `engine/labels.py` (bearing was below
  the line, 270° text upside down, left-baseline anchor made below-line text
  overprint the line). Metric: Hough-reference line recall/precision (not
  circular), association, classification, scale consistency.
- 2026-09-23 tick 0 — first full batch: 81/81 DXF+PNG, 0 errors, mean score
  0.691, line F1 0.959, label assoc 0.56, scale found on 10 images; slowest
  image 155 s after vectorizing merge_collinear/snap/planarize/associate
  (36 s → 2.6 s on lots_east_of_24_23). Fixed: PNG render drew ACI-7 lines
  white-on-white (COLOR_NEGATIVE → COLOR); unvalidated OCR fragments now go to
  frozen PLAT-TEXT-LOWCONF; misc text height capped at 1.6× median; upright
  flip got a ±5° band so near-vertical labels all read bottom-to-top (was
  270.2° vs 87.6° on neighbouring lines) — same band in engine/labels.py.
  Seen, queued as backlog #1: "99.80'" OCR'd upside down as "866'", "4177'".
- 2026-09-23 tick 1 — backlog #1 geometry-constrained decoding. Every OCR
  variant (rotations × shears) of every label now votes scale (distance ÷
  nearby parallel line length) and rotation (bearing − image azimuth, incl.
  degree-mark digit-split readings like N2024'30"W → N 02°24'30" W); the
  value agreed by most distinct labels wins; each label then takes the
  reading its geometry confirms and is pinned to that line (verified).
  Readings needing ≥2 edits must match within 0.35° (raster pins bearings to
  ~1° only — a 1°48'00" vs true 1°58'48" false match was caught this way).
  calibrate() now takes reconcile's scale/rotation as authoritative (it was
  re-deriving with a stricter rule and discarding it). Probe mean
  0.6959 → 0.7120, no image regressed; scaled probes 1 → 3. KEPT.
  +2 tests (misread '866'' → flipped 99.80'; digit-split bearing).
- 2026-09-23 tick 2 — render class: blue lot lines on navy fill (diff ~66)
  fell under an Otsu threshold set by white text (t=79), so block9 had 8
  lines of ~40.  Digital images (render/screenshot) now use a fixed ink
  threshold 35 (noise-free: fills differ by 0; gridlines ~27 stay out); scans
  unchanged.  block9 lines 8 → 83, assoc 0 → 0.375, score 0.591 → 0.660.
  Probe mean 0.712 → 0.721, no regression. KEPT. +1 test. Scale still not
  found on renders → new backlog #0 (small-text OCR scale).
- 2026-09-23 tick 3 — backlog #0 small-text OCR scale. (a) scale every crop
  so glyph height → 32 px: probe 0.721 → 0.711, zoom_cape_horn −0.063,
  REVERTED. (b) only labels < 14 px: probe → 0.713, street_north_of_24
  −0.064, REVERTED. Renders still get ~9 distance votes either way; the
  limit is binarization of anti-aliased render text, not size. Code restored
  to post-tick-2 state; test removed with it. Full batch started (3rd tick).
- 2026-09-23 full batch after tick 3 — 81/81, 0 errors. Mean score
  0.6934 → 0.7028, assoc 0.566 → 0.578, images with scale 13 → 24. One
  image regressed > 0.03: beachwood_road_centerlines_drawing 0.657 → 0.603
  (label noise from tick-2 threshold; lines unaffected) → backlog #00.
- 2026-09-23 tick 4 — (a) renders: text mask now built from a strict
  threshold (max(Otsu·0.8, 80)); low threshold 35 kept for linework only.
  (b) NEW failure found and fixed: block9's scale 0.457 ft/px was wrong
  (true ≈0.2 from its axes) — distances printed ON the line over knock-out
  boxes cut each course in two and the halves agreed on a 2.3× scale.
  linework.bridge_label_gaps rejoins collinear pieces across a label-covered
  gap (only a real gap ≥ max(3·sw, 0.5·char_h), never at a junction — first
  version merged lot-corner frontage pieces on scans: probe 0.710, fixed).
  block9 now honestly unscaled; block13 scale 0.2749 verified against its
  axis ticks (0.274). Probe 0.721 → 0.730, no probe image regressed. KEPT.
  beachwood_road_centerlines not fixed (0.603 → 0.575) → backlog #00. +3 tests.
- 2026-09-23 tick 5 — beachwood_road_centerlines overlay showed combined
  course calls ("N87°35'30"E - 1453.5'") classified as plain text.  Added
  combined-call parsing (bearing + dist; votes scale and rotation; exported
  as "BRG - DIST'"), and costed quadrant-letter repairs in bearing_readings
  ('$'→S, leading digit misread for N/S, lost trailing E/W; cost ≥2, never
  vote, must verify within 0.35°).  Repairs first produced false rotations
  (zoom_lot28_29 −39.4°, beachwood −89.8° on north-up drawings) → rotation
  now needs ≥3 agreeing labels & ≥25% of voters, only strict readings vote,
  and calibrate() no longer falls back to its own 2-vote rule once
  reconcile has decided.  Probe 0.7300 → 0.7297 (within tolerance, no image
  −0.03); beachwood 0.575 → 0.585. KEPT (safety). +4 tests (88 total).
- 2026-09-23 tick 6 — rotation recall. crop_lot23_24 had only 3 strict
  bearing voters, 2 agreeing on −2.9° (the third, "N1°S8'48"E", is
  N1°58'48"E with 5→S).  (a) digit-lookalike letters (S→5, B→8, O→0,
  I/L→1, Z→2) inside a bearing's numeric run — guarded to runs with ≥3 real
  digits and ≤2 mapped letters, after the unguarded version turned words
  like "NORTH LINE" into N 01°11'… and voted a false −89° on beachwood;
  (b) small rotations (≤5°, scan skew) need 2 agreeing labels, larger ones
  still ≥3 & ≥25%.  crop_lot23_24 rot −2.86° (6/6), 11 verified; beachwood
  rot 0.01° (correct: true-coordinate plot).  Probe 0.7297 → 0.7310. KEPT.
  +6 tests (94).  Full batch started (6th tick).
- 2026-09-23 full batch after tick 6 — 81/81, 0 errors, mean 0.7033 (flat),
  25 scaled.  Rotation now found on 10 images, all consistent: every crop /
  full scan of PB30 P82 sheet agrees on −2.2° … −3.0° (page1_300dpi −2.52°
  from 28 agreeing bearings; page0 −0.69°), i.e. the scan sits ~2.5° off its
  basis of bearings.  Regressions > 0.03: block16_mapcheck_drawing −0.033,
  mapcheck_individual_parcels_grid −0.054 → backlog #000.
- 2026-09-23 tick 7 — backlog #000. Text threshold 80 vs 35 A/B on the two
  regressed renders: block16 0.652 vs 0.651 (not the cause); parcels grid
  0.826 vs 0.871, entirely scale_consistency — and every scale vote there is
  junk ("20" ×3 at conf 34–53 → 0.034 ft/px). Tried: distance votes need
  '.'/foot mark or conf ≥ 70 → probe 0.7416 → 0.7165 (block13 lost its
  axis-verified scale, street_north −0.064). REVERTED. Kept: parcels grid +
  block16 added to the probe set (render text now gated).
- 2026-09-23 tick 8 — junk-scale guard: reject a scale whose inliers are all
  the same value AND all weak (no '.', no foot mark, conf < 70); identical
  strong reads (three 75' frontages) still count.  Effect on probe: only
  mapcheck_individual_parcels_grid changed — its junk 0.034 ft/px scale
  removed, score 0.826 → 0.762 (probe 0.7327 → 0.7262). Every other scale
  (incl. axis-verified block13) unchanged. REVERTED per protocol — but the
  drop is the metric rewarding a false calibration, so backlog #000 now
  adds ground-truth scales to the metric before re-trying this guard.
- 2026-09-23 tick 9 — ground truth in the metric.  raster2dxf/truth.json:
  ft/px measured from matplotlib axis tick labels by an OCR script that
  shares no code with the pipeline (block13 0.27416, block16 0.17506,
  block10_11_12 0.27701, beachwood_road 0.46136, beverly_isle 0.30286) +
  block9 0.1995 by hand + parcels grid = "no scale" (viewed: no dimensions).
  Scale term now 1 right / 0 wrong / 0.5 abstain for truth images.  Truth
  confirms block13 (0.2749) and block16 (0.17545, 0.2% off) scales correct.
  New-metric baseline 0.7534; re-applied tick-8 junk-scale guard →
  0.7684, only change = parcels grid now correctly unscaled. KEPT. Summary
  aggregate reports scale right/wrong/abstained. +2 tests (96). Full batch
  started (9th tick).
- 2026-09-23 full batch after tick 9 — 81/81, 0 errors, mean 0.7100 (score
  now truth-aware for 7 renders), no image regressed > 0.03.  Scale vs
  truth: 4 right, 0 wrong, 3 abstained (block9, beachwood_road,
  beverly_isle).  block10_11_12 0.27696 vs 0.27701 (0.02%), block13 0.3%,
  block16 0.2%, parcels grid correctly unscaled.
- 2026-09-23 tick 10 — scan ground truth.  Hand-measured crop_lot23_24_detail
  with dark-pixel line profiles: lot 23 102.38' = 303.5 px (0.3373 ft/px),
  lot 25 W 103.17' = 305.5 px (0.3377), but lot 25 83.26' = 232 px (0.3586):
  the hand-drafted plat is only ~6% to scale — an exact scan "truth" does
  not exist.  truth.json gets crop_lot23_24_detail 0.3375 with tol 0.06
  (per-entry tol now read by the metric).  Consequence: scans use scale
  consensus tolerance 4% (SCAN_SCALE_TOL), digital stays 1.5%.  Baseline =
  old algorithm under the same metric (0.7803) → 0.7809; crop_lot23_24
  verified labels 11 → 15, scale unchanged & truth-correct. KEPT. +1 test.
- 2026-09-23 tick 11 — unscaled scans. zoom_lot28_29 is 210×200 px with
  10 px text: resolution-limited, dropped.  lots23_24_clean_scan: "/02.38"
  is 102.38' with the italic 1 read as "/" (normalize stripped it → 2.38).
  normalize now maps "/" before a digit (not after one: fractions kept) →
  "1".  Probe 0.7809 → 0.7793 (−0.0016, within 0.005; worst image −0.014,
  from more correctly-classified distances entering the assoc denominator).
  KEPT. Scale still not found there: remaining blocker is arc-shortened
  courses → backlog #000. +4 tests (101).
- 2026-09-23 tick 12 — arc-shortened courses: linework.course_lengths()
  measures each line to the P.I. of a corner-return arc it runs into
  (intersection with the arc's far-end tangent, ≤ 1.5 R beyond the drawn
  end); scale votes / verification / calibrate() QA accept either the drawn
  or the to-P.I. length.  block9 now scaled 0.19710 vs truth 0.1995
  (1.2%, correct; its lots have R=25' returns); crop_block6 +1 inlier.
  Probe 0.7793 → 0.7874, no regression. KEPT. +1 test (102).  Full batch
  started (12th tick).
- 2026-09-23 full batch after tick 12 — 81/81, 0 errors, mean 0.7114 →
  0.7197, images with scale 24 → 30, none regressed > 0.03.  Scale vs
  truth: 6 right, 0 wrong, 2 abstained (beachwood_road, beverly_isle).
- 2026-09-23 tick 13 — lots23_24_clean_scan: both corner arcs found with the
  right radius (76 px ≈ 25' at 0.33) but the NW arc's sweep fitted 117°
  (not ~90°), so its far-end tangent was ~27° off and 99.93' got no P.I.
  course_lengths now intersects with the straight line leaving the arc's
  far end (fallback: arc tangent).  lots23_24_clean_scan now scaled
  0.33245 (3/5), consistent with crop_lot23_24_detail's hand truth 0.3375
  (same scan); street_north +1 inlier.  Probe 0.7874 → 0.7980, worst
  image −0.006. KEPT. +1 test (103).
- 2026-09-24 tick 14 — QA noise.  crop_lot23_24's 11 flags were mostly
  misreads ('46', '12,04,', '4177)') and ordinary ~6% drafting error.  A
  distance is QA-flagged only when conf ≥ 60, the (normalized) read is
  strong, and the disagreement is > 2× scale tolerance but < 100%.  Probe
  QA flags 59 → 20; crop_lot23_24 keeps exactly 93.50' (→139, line runs
  through the P.R.M. — real), 80' (→96.5), 100' (→89.3).  Score unchanged
  (QA isn't scored). KEPT. +1 test (104).
- 2026-09-24 tick 15 — monuments. linework.find_monuments: Hough small
  circles (0.3–0.8 char_h), refined ±4 px, ring ≥ 80% ink, hollow band ≤ 50%
  ink, a line within r, centre not inside a label box; centre pinned by a
  least-squares fit to the ring's ink (synthetic: 0.5 px).  Lines split at
  monuments; DXF gets CIRCLE+POINT on PLAT-MON.  crop_lot23_24: upper P.R.M.
  found, 93.50' course now split there (measured 139 → 78 ft; residual is
  the arc end).  block13: both yellow P.R.M.s found + 1 digit false
  positive; block9 P.R.M. and one crop_lot23_24 P.R.M. missed (label box
  veto).  Shrunk-box variant tried → digit false positives back, reverted.
  Probe 0.7980 → 0.7986, no regression. KEPT (strict veto). +2 tests (106).
  Full batch started (15th tick).
- 2026-09-24 full batch after tick 15 — 81/81, 0 errors, mean 0.7210 →
  0.7233, scaled 31 → 32, none regressed > 0.03.  Scale vs truth 6 right /
  0 wrong / 2 abstained.  30 monuments on 13 images (precision unmeasured
  beyond the probe's ~3:1).  Slowest image 204 s.
- 2026-09-24 tick 16 — monument precision/recall.  Measured features of all
  candidates on 3 images with known P.R.M. positions: centre ink ("core")
  was 0.0 on all 5 real symbols (ring-in-ring, paper centre) vs > 0.2 on 13
  of 17 false ones (looped digits/letters); real corners have ≥ 2 line
  directions through them.  New rule: core (ignoring pixels on extracted
  lines, so lines drawn through a symbol don't count) < 0.2, and a label-box
  veto only for single-line candidates.  Probe monuments 4 → 8, all 4 new
  ones hand-checked real (block9 Cape Horn P.R.M., lots23_24_clean_scan,
  street_north, crop_lot23_24's lower P.R.M.); precision ~3:1 → 7:1.  Score
  flat (monuments unscored). KEPT.  Synthetic fixture changed to the real
  symbol (paper centre). +1 test (107).
- 2026-09-24 tick 17 — monument truth + metric.  truth.json "monuments":
  hand-verified P.R.M. centres, complete per image (crop_lot23_24 ×2,
  lots23_24_clean_scan, street_north_of_24, block9, block13 ×2); symbols
  cut by the image edge ignored both ways.  pipeline.monument_f1 (match
  ≤ 8 px) enters the score at 10% on truth images.  Quantified tick 16:
  monument F1 tick-15 detector 0.67/0/0/0.8/0 → tick-16 1/1/1/0.8/1; probe
  under the new metric 0.7723 (tick-15 detector) vs 0.8056 (current) — new
  baseline 0.8056.  Metric-only tick. +1 test (108).
- 2026-09-24 tick 18 — block13's false monument was the hollow "0" of the
  vertical green "10' Esm't" beside the easement line (paper centre, and the
  dim green text is under the render text threshold, so no label box to
  veto it).  Added a circularity test: radial spread (per-30° median ring
  radius, max−min / r) 0.03–0.19 on all 7 verified P.R.M.s vs 0.57 on the
  zero → reject > 0.35.  Monument F1 = 1.0 on all 5 truth images.  Probe
  0.8056 → 0.8076, no regression. KEPT. +1 test (109). Full batch started
  (18th tick).
- 2026-09-24 full batch after tick 18 — 81/81, 0 errors, mean 0.7244, none
  regressed > 0.03, scale 6 right / 0 wrong / 2 abstained.  Monuments
  30 on 13 images → 51 on 20 (ticks 16+18).  Only the 5 truth images are
  verified: spot-check a few of the others (page0/page1_300dpi, block_strip)
  before trusting the batch-wide count.
- 2026-09-24 tick 19 — monument spot-check outside the truth set: other
  crops 3/3 real, but page1_300dpi (dense full sheet) was ~70% precise —
  false hits on a hatched "N", an "E", "02" (letters crossing a ring).
  Rule: the ring interior at 0.4 r must be either solidly inked (≥ 0.7,
  ring-in-ring P.R.M.) or empty (≤ 0.1, plain hollow render marker);
  half-inked (letter strokes: 0.38 / 0.56) rejected.  Line pixels are now
  ignored when sampling rings (_ring_frac ignore=), as for the core test.
  page1 13 → 10 detections, ~90% precise (1 false, 1 real lost at the 0.7
  edge).  Truth-set monument F1 still 1.0 ×5; probe flat 0.8076. KEPT.
  +1 test (110).
- 2026-09-24 tick 20 — page1 monument truth.  Reviewed by eye every raw
  Hough ring candidate with ring ≥ 0.8 and empty centre (314 tiles) plus the
  detector's hits: 10 monuments (8 ring-in-ring P.R.M., 1 heavily-inked
  P.R.M. at (3453, 4732), 1 diamond P.C.P.); the legend's "◎" symbol in the
  notes text is excluded (not a surveyed point).  page1 monument F1 = 0.9.
  page1 added to the probe set.  Metric/data-only tick; +1 test (truth.json
  well-formed) → 111.
- 2026-09-24 tick 21 — page1 monument miss at (7338, 2608).  INNER_RING
  sweep 0.55–0.7: F1 stays 0.9 (not the binding filter).  Traced it: the
  fixed-band hollow test rejects it (0.58).  Tried a radial ink profile
  (paper band anywhere inside; inner ring = profile max ≤ 0.6 r): truth-set
  monument F1 block9 1.0 → 0.0, block13 1.0 → 0.8, page1 0.9 → 0.833 —
  the max lets letter strokes pass. REVERTED; item parked.  Full batch
  started (21st tick).
- 2026-09-24 full batch after tick 21 — 81/81, 0 errors, mean 0.7245, none
  regressed > 0.03; scale 6 right / 0 wrong / 2 abstained; monuments 41 on
  20 images (51 before ticks 19's letter filter); monument F1 1.0 on 5
  truth images, 0.9 on page1.
- 2026-09-24 tick 22 — render OCR item re-diagnosed: block13 already reads
  105 distances; only 28 are in the drawing (12 associate) — 78 are table
  cells, which can't associate and aren't dimensions.  Added
  associate.mark_table_cells → kind "table" (PLAT-TABLE layer; skipped by
  reconcile).  v1 (far from lines + ≥2 row neighbours): probe 0.8104 →
  0.8289, block13 assoc 0.10 → 0.48 — but it re-kinded scan fragments and
  page1 LOT NUMBERS ("25", "26") too: unearned. Final rule: label must be a
  strong numeric read (bearing / decimal), far from lines, row has ≥ 2
  neighbours incl. ≥ 1 other strong numeric.  Scans 0 cells (page1 4),
  block13 10, block16 18; probe 0.8104 → 0.8111, no regression. KEPT
  (conservative). +2 tests (113).
- 2026-09-24 tick 23 — table panels by geometry.  Rectangle frames from
  linework: renders' table borders too faint (found only lot polygons and
  callout boxes).  Text-density rule (≥ 12 labels / 10 char_h, far from
  lines): probe 0.8111 → 0.8121 but re-kinded crop_lot23_24's street
  centreline bearing and a real 89.76' dimension as "table" — unearned.
  REVERTED; item parked.
- 2026-09-24 tick 24 — worst images were the text-only notes panels
  (plat_notes 0.015, note2_clean 0.075): no linework, and line precision was
  defined as 0 when nothing is drawn.  (a) metric: no vectors where the
  independent Hough reference finds no lines = precision 1.  (b) text-only
  images get paragraph OCR (text.ocr_block: psm 6, best of shear 0/0.2/0.3 —
  mean conf 40 → 60) as MTEXT on PLAT-NOTES; word fragments go to the frozen
  review layer.  plat_notes 0.015 → 0.565, note2_clean 0.075 → 0.825; probe
  unchanged 0.8111. KEPT. +1 test (114). Full batch started (24th tick).
- 2026-09-24 full batch after tick 24 — 81/81, 0 errors, mean 0.7246 →
  0.7408 (line F1 0.9595 → 0.9842, from the two notes panels no longer
  scored as linework failures), none regressed > 0.03; scale 6 right /
  0 wrong / 2 abstained.
- 2026-09-24 tick 25 — curve data (user requirement: curves labelled on the
  lots / curve tables).  Audit: only 2 images parse a curve table, 2 of 14
  curve ids associate, and PB30 P82 labels curves with Δ/R/T/L blocks that
  OCR fragments.  New raster2dxf/curvedata.py: tolerant field parsing
  (Δ read as A/4/D, "=" as > : .), 4·char_h block grouping, solve() with
  T = R tan(Δ/2), L = RΔ, CH = 2R sin(Δ/2) (derives the missing value,
  flags over-determined blocks consistent within 1%), attach to nearest
  arc; DXF gets one solved curve label per block (derived values starred,
  "(UNCHECKED)" if not over-determined) + arc XDATA.  block13: R=25/T=25 →
  Δ=90° (matches its table C1).  Scans: fragments only → backlog #00a.
  Probe flat 0.8111. KEPT. +8 tests (121).
- 2026-09-24 tick 26 — curve-data block OCR prototype (no code change):
  paragraph OCR of zoom_cape_horn_curve_data over 12 rotation/scale
  combos reads Δ=36°20'00" correctly but never R=327.01 or T=107.31
  (~11 px text).  Parked as a source-resolution limit; next attempt should
  target the 300-dpi sheets.
- 2026-09-24 tick 27 — curve blocks on the 300-dpi sheets: legible, and a
  rotated paragraph crop anchored on the "Curve" title reads Δ=36°20'00" and
  T=150.73 → R 459.35 (plat 459.36).  But T reads 450.73 about as often
  (1→4), and there's no page scale to disambiguate against the arc; the
  wired version found no block and cost 44 s on page1. REVERTED (no code
  kept).  New prerequisite: scale on page0/page1.
- 2026-09-24 full batch after tick 27 — 81/81, 0 errors (see AGG in
  batch.log), no image regressed > 0.03.
- 2026-09-24 tick 28 — corrected tick 27: both 300-dpi sheets ARE scaled
  (page1 0.3325, 148/255; page0 0.3346) — consistent with crop_lot23_24's
  hand truth 0.3375.  Built arc-verified curve re-OCR (candidate with the
  smallest derived-R vs drawn-arc error, ≤ 25%; identity-consistent first).
  On page1 nothing verified: the only arc near Sands' "℄ Curve Data" is
  the R/W edge (406.7 ft) and the paragraph OCR reads Δ+T at 14.0° but only
  Δ at 13.8° — sub-degree fragility.  REVERTED (pipeline + curvedata);
  item parked with a dewarping plan.
- 2026-09-24 tick 29 — curve data by dewarping: polar-unwrap the text
  along the nearest drawn arc (orientation from the anchor's own reading
  direction / "up" vs the arc centre), 8 windows either side, per-field
  vote, drop T/L that disagree > 5% with read R & Δ, verify by identity or
  drawn arc (R within 25% of arc r × ft/px).  Parser now accepts R keys
  misread as & / B / P / 8 before ".=" and "_" decimals.  page1: Δ 36°20',
  R 459.36 read, T 150.72 / L 291.27 derived — plat Sands 459.36 / 150.73 /
  L 291.30.  Probe unchanged 0.8111 (curves unscored), no regression. KEPT.
  +3 tests (124).
- 2026-09-24 tick 30 — curve truth + fragment anchors.  truth.json
  "curve_catalog": the plat's six ℄ curves (R/T from the scan readings in
  the project notes); a dewarped read is right if R within 1% of a catalog
  R (and T within 1% if read); scored at 5% on page0/page1, abstaining
  neutral.  Dewarp anchors now include curve-field fragments ("A= 269"),
  ≤ 6 per image, ≥ 12 char_h apart.  Result: page1 Sands (Δ 36°20',
  R 459.36, arc-verified), Shellfish (Δ 52°, R 167.95, T 82.35, identity),
  Cape Horn (R 327.01, T 107.31, identity); page0 Cape Horn (arc) and San
  Salvadore (R 269.96, T 88.59, identity).  5 right / 0 wrong.  Probe
  0.8111 → 0.8118; page0 0.779 → 0.790; page0 added to the probe.  KEPT.
  +1 test (125).  Full batch started (30th tick).
- 2026-09-24 full batch after tick 30 — 81/81, 0 errors, mean 0.7410, none
  regressed > 0.03, slowest image 239 s.  Dewarped curves batch-wide:
  page0 Cape Horn + San Salvadore, page1 Sands + Shellfish + Cape Horn,
  plus block_strip_small R 359.30 (= Marina 359.27) and
  lots23_24_block_search R 459.36 (= Sands) — 7 reads, all matching the
  catalog; 0 wrong.  (Those two crops aren't in the catalog's image list:
  every PB30 P82 scan crop could be added.)
