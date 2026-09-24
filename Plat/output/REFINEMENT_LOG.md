# Plat/ folder reconstruction — refinement log

Goal: an accurate, scan-verified reconstruction (DXF + PNG + metrics) of every plat
in `Plat/*.pdf`, refined every 10 minutes until it converges.

## Rules for every tick
1. Pick the top **open** backlog item. Work it from the **scan** (render the PDF crop at ≥200 dpi
   and read it); never invent a dimension. Anything not printed goes in `assumptions` / gets flagged.
2. **Every DXF written gets the `_claude` suffix** (user instruction, 2026-09-24).
3. Faithful builds live in `scripts/plat_folder/build_*.py` → `Plat/output/<plat_id>/`
   (`*_claude.dxf`, `.png`, `metrics.json`). Beachwood block fixes go in `engine/cogo_block.py`;
   run the `review-plat-notes` skill after touching any block solver.
4. Re-run `python3 -m pytest -q`. It must stay green (263 passed as of tick 1).
5. Don't commit (user commits via Antigravity).
6. Append a tick entry below: what changed, before → after numbers, what's next.
7. **Convergence**: stop the loop (CronDelete) when 2 consecutive ticks change nothing,
   because every remaining open item needs user input or is unreadable on the scan.

## Plats in Plat/
| PDF | Plat | State at loop start |
|---|---|---|
| 67-132.pdf (6 sheets) | Atlantic Beach Country Club Unit 2, PB 67/132-137 | only Sheet 3 built; 11 of 12 lots FLAG (assumed rear lines) |
| Beverly-Isle.pdf | Beverly Isle, Island No. 5 (1968) | 20 parcels built; provenance not yet re-verified against scan |
| Duval_Plat_Book_30_Page_82-2.pdf | Beachwood Unit Two, PB 30/82-82A | 10 blocks solved; Block 15 west end was wrong (fixed tick 0) |
| Plat_Book_15_Page_82.pdf | Ocean Grove Unit No. 1, PB 15/82 | old build is a schematic stand-in (2 rows of 50x120), not the plat |
| Plat_Book_4_Page_85.pdf | Hicks Subdivision (left) + John M. Stevens Subdivision (right), PB 4/85 | old build was a fabricated 4x4 grid; Hicks rebuilt tick 0 |

## Backlog (ranked)
User direction 2026-09-24: **do all plats, starting with the Beachwood full plat** (`scripts/plat_folder/build_beachwood_full.py` →
`Plat/output/PB30_P82_Beachwood/PB0030_P0082_Beachwood_FullPlat_claude.dxf`). Re-run that composer after every Beachwood change;
each block's extra corners must check within 0.10' against the street network.

Beachwood (full plat):
1. [x] **Block 14 rebuild** (tick 2). The solver models a 24-lot double row with a cul-de-sac, but the plat's Block 14 is the 11-lot strip + Tract 'A'
   west of Mangrove Ave on Sheet 2 (a mirror of Block 13 on Sheet 1). Anchors: F_STARFISH_MANGROVE_SW (Lot 1 NE),
   F_DRAIN40_MANGROVE_SW (Lot 11 NE), F_DRAIN40_MANGROVE_NW (Tract A SE). Tests pin the old 24 lots, so update them with the reason.
2. [x] **Block 8** (tick 3) (Sands Ave / Cape Horn Ave, Sheet 2; Lots 17-34 in Unit Two): new solver. Anchors: F_SANDS_MANGROVE_SE, F_DRAIN40_MANGROVE_NE/SE, F_CAPEHORN_MANGROVE_NE.
3. [x] **Block 7** (tick 4; actually Lots 11-37) (Marina Dr / Sands Ave, Sheet 2): new solver. Anchors: F_MARINA_MANGROVE_SE, F_SANDS_MANGROVE_NE.
4. [x] **Block 6** (tick 5; Lots 2-12) (east of Marina/Keel, Sheet 2): new solver. Anchors: F_MARINA_KEEL_S, F_KEEL_BEACHWOOD_SW.
5. [x] **Block 10** (tick 6): anchored on caption boundary vertices.
6. [x] **Block 12** (tick 7): Lots 8-10 certified from a 400 dpi re-read. Lot 3 is Unit One (dashed), so it isn't part of this plat.
7. [x] **Network artifact** (tick 8): handled in the composer; the engine is left as-is and the issue is reported. The Mangrove Ave N R/W lines ran up through Block 18 Lots 1-2 to the north boundary (the street starts at Starfish).
   Check the scan; `engine/centerline_geometry.py` belongs to another effort, so report it rather than edit unless it's clearly wrong.
8. [x] **Block 17 east end** (tick 9): Lot 17 front/rear were swapped and both returns were missing. Fixed.
9. [x] **Block 9 / 11 / 13** (tick 10; 12 done in tick 7): re-read every block against the scan the way Blocks 15/16 were done (a hidden transcription error was found in each of those).

9b. [x] (tick 11) `scripts/draw_block9_mapcheck.py` builds its own 9 `BeachwoodLotAgent`s (a stale second copy: straight fronts, 83°30' Lot 26 return).
    Make it draw from `BeachwoodBlock9Solver` like `scripts/mapcheck_block15.py`, writing `_claude.dxf`.

Other plats:
10. [~] **Ocean Grove** (in progress, `scripts/plat_folder/build_ocean_grove.py` -> `Plat/output/PB15_P82_OceanGrove/`):
    [x] Block 8 (L1-20), [x] Block 7 (L1-8) (tick 12)
    [x] Block 6 (L1-12) (tick 13; Lots 9-11 FLAGGED, plat values conflict at the Coquina curve)
    [~] Block 4: [x] Lots 1, 2, 11, 3, 10, 4 (tick 14)  [?] NEEDS USER INPUT (depends on the Dewees line shared with Block 1): Lots 5-9 (west curve Ra=543.68: 52.3/54/23.8 + 81.6 to the 60°54' apex;
        Dewees curve Ra=291: 51/8.6; Dewees line 85/75; middle line 35/45 then 68.5 diagonal; 81.8/81.9/68.9) -- build with Block 1 (shared Dewees line)
    [?] Block 1 (L1-16) -- NEEDS USER INPUT: transcribed (`Plat/output/PB15_P82_OceanGrove/block1_transcription.json`), but the printed
        Beach-side values have no geometric solution (tick 15). Same class of conflict as Block 6's Coquina corner.
    [?] Blocks 5, 3, 2 (triangles: Ra=140/291; 193/109.1/17.15; 55.1/49.7/43.3) -- NEEDS USER INPUT: they're only tied to the rest via the Dewees line
11. [x] (tick 16) **Hicks R/W south line**: the 4-point circle fit leaves residuals up to 36 ft, and the two R/W lines aren't concentric. Re-read the ties at 300 dpi (266 / 382 / 432 / 202), then try a joint concentric fit or a tangent+curve model ("62.5' to P.C." note). Richard Hicks (E) is +5.6% on area.
12. [~] (ticks 17-18: 41 lots built; Lot 1, Lots 20-25 and 46+ need the railroad/Kings Road angles, which aren't printed) **John M. Stevens Subdivision** (right panel of PB 4/85, 1910): ~65 lots, not built at all.
13. [~] (ticks 19-21: Sheet 3 Lots 124-137 + 167-176 done (175/176 flagged); Sheet 3 Lots 138-166 and Sheets 1,2,4-6 todo) **Atlantic Beach CC**: read the real rear lines for Sheet 3 lots 126-137 (they're currently assumed), then Sheets 4-6.
14. [ ] **Beverly Isle**: re-verify parcels against the scan (claims 0.0000 misclosure on 20 parcels, so check that they aren't constructed-to-close).
15. [ ] `scripts/plat_folder/scorecard.py`: aggregate every `metrics.json` into `Plat/output/SCORECARD.md`.

## Ticks

### Tick 0 — 2026-09-24 (interactive)
- **Block 15 (Beachwood), reported wrong by the user.** Re-read from the scan; the solver had four transcription errors:
  the Shellfish curve Δ was 65°19'35" (plat: 52°17'10", chord 121.56'); Lot 1 had an invented 25'/25' jog instead of Marina
  115' to the P.I. + 25.0' to the curve P.C.; the Lot 15/16/17 rear line was 87.13/40.46 instead of 75/75/40.46; and Lot 15's west line
  was N9° instead of N3°08'07"W. Also: there's a spurious R=1959.86 "C2" curve on the Lots 9/10 east sides (Blvd is straight there), and all four R=25
  corner returns were missing. After the fix, every independent printed line closes within 0.015'. The one exception is the Lot 16 chord: the plat prints 82.45'
  but the geometry gives 82.05'. That's flagged as a plat inconsistency, not forced to fit. `scripts/mapcheck_block15.py` now draws from the solver (it used to keep a stale second copy).
- **Hicks** rebuilt faithfully: `scripts/plat_folder/build_hicks.py`. 9 of 10 parcels are within 2.5% of their stated acreage (no bearings on the plat, so orientation is assumed).

### Tick 1 — 2026-09-24 (interactive): Beachwood full plat
- New `scripts/plat_folder/build_beachwood_full.py`. It takes the street network (`engine/centerline_geometry.py`: 27-course boundary,
  0.042' closure, 90/90 checks) and places each block solver by translation onto one fillet P.I., using the others as checks.
  Output: `Plat/output/PB30_P82_Beachwood/PB0030_P0082_Beachwood_FullPlat_claude.dxf` + PNG + metrics. 9 blocks and 134 lots placed.
  Worst block-corner check is 0.021', including Block 16's east corners about 1,300 ft from its anchor (0.005').
- **Engine bug fixed** in `DeterministicLotSolver.compute_mapcheck`: curve segment areas were signed assuming clockwise rings.
  Counter-clockwise rings (Block 16 south row) reported ±2 segments versus the arcs they draw (+265.6 SF on Lots 30/31).
  Now winding-aware. Reported area equals drawn arc area for every lot.
- **Block 16**: the Lots 27/28/29 fronts are the Shellfish Dr **N R/W** curve, R=197.95 (CL 167.95 + 30). They were modelled as "Keel Dr R=167.95"
  (Lot 28) and a straight line (Lot 29). Chords 51.68/68.75/59.50 give Δ 15°+20°+17°17'10" = CL Δ, and all corners fit the circle within 0.015'.
  Added Lots 9-27 (Lots 17/18 with R=25 returns on Beachwood Blvd). Block 16 now has 33 lots. Registry key renamed
  `CURVE_BLK16_KEEL_L28` → `CURVE_BLK16_SHELLFISH_L28`.
- `MASTER_PROMPT.md`: new section "Procedure: building a plat from scratch (MANDATORY order)" (user request).
- Tests: 263 passed. The earlier centerline failures were fixed outside this loop.
- Next: backlog item 1 (Block 14 rebuild).

### Tick 2 — 2026-09-24 (cron): Block 14 rebuilt from the scan
- Read Block 14 at full resolution (Sheet 2, the strip between the 50' drainage R/W and Mangrove Ave W R/W). It's Lots 1-11 + Tract "A",
  not the old 24-lot double row with a cul-de-sac (no cul-de-sac exists on this plat).
  Lot 1 100x100 (R=25 at Starfish), Lot 2 91.88', Lots 3-5 90', Lot 6 across the Mangrove bend (east 60.45'+16.99', west 59.22'+15.78',
  north S87°35'30"W 100', south N88°58'20"E 100'), Lots 7-10 75', Tract A 40', the 40' drainage R/W, Lot 11 100x100 (R=25 at Cape Horn).
- Checks: the east chain from the Lot 1 NE P.I. lands 0.027' from the network's Tract A SE P.I. after 879'. The bend falls where the network has it
  (0.02'). The Lot 6 west split is 15.81' vs 15.78' printed. In the full plat, all 3 check corners are within 0.027'.
- Full plat: **10 blocks, 146 lots** placed. Not placed: Blocks 10, 6, 7, 8.
- Tests: the old cul-de-sac tests were replaced by `test_block14_strip_matches_scan`, and the snapshot totals updated (151 lots incl. Tract A). 263 passed.
  The plugin registry still has a `CURVE_BLK14_CULDESAC_BULB` entry nothing uses. I left it for the plugin owner (not on the plat).
- Next: backlog item 2 (Block 8).

### Tick 3 — 2026-09-24 (cron): Block 8 built from the scan
- New `BeachwoodBlock8Solver` (Lots 17-34). There are two rows split by the drainage & utilities R/W, whose lines bend N88°58'20"E → S72°51'40"E → S54°41'40"E.
  - North row: Sands S R/W, R=429.36 (CL 459.36 - 30). Chords 17.48/89.76/89.76/74.84 give Δ 2°20'+12°+12°+10° = CL 36°20'.
  - South row: Cape Horn N R/W, R=357.01 (CL 327.01 + 30). Chords 70.50/80.83/74.64 give Δ 11°20'+13°+12° = CL 36°20'.
  - R=25 returns at both Mangrove corners.
- **Reading correction during the tick:** the "33'" on the drainage S line belongs to Lot 22's north side (96.80' + 33' on the first diagonal), not to Lot 21.
  With 33' assigned to Lot 21, the side lines missed by 5-9'. With it on Lot 22, all 12 printed checks fit within 0.022'.
- Checks: all printed side lines and chords are within 0.022', and the 140.0' boundary tie within 0.014'. In the full plat, the 3 fillet corners are 0.000' and the 4 boundary corners
  are within 0.031' of the caption vertices (a new check type, independent of the street network).
  Lots 27-34 come out 0.022' shallow (1.6 SF each, 0.02%). That's plat slop, reported, not forced.
- Full plat: **11 blocks, 164 lots**. Not placed: Blocks 10, 6, 7. Tests: 265 passed (new `test_block8_printed_lines_close`).
- Next: backlog item 3 (Block 7).

### Tick 4 — 2026-09-24 (cron): Block 7 built from the scan
- New `BeachwoodBlock7Solver`, **Lots 11-37** (27 lots; the backlog's "17-37" was wrong, the south row runs to Lot 11 on the boundary).
  - North row on Marina S R/W, R=329.27 (CL 359.27 - 30): chords 99.37/99.36/17.24 reproduce CL Δ 37°42'50" to 0.000°.
  - South row on Sands N R/W, R=489.36 (CL 459.36 + 30): chords 17.08/76.78x3/62.59 give Δ 2°+9°x3+7°20' = CL 36°20'.
  - Shared rear line: 102.38/83.26, S77°35'15"E 66.85/66.86 (south side 20/83.71/30), then S54°41'40"E.
  - Returns: Lot 24 NW skewed (Δ 88°37'30", T 24.40'), Lot 23 SW 90°.
- Reading note: the Lot 28 chord I first read as "11.24" is **17.24** at 3x zoom, exactly the Δ 3° the curve requires.
- Checks: all 14 within 0.023'. Both rows' rear lines meet at the boundary with 0.000' gap. In the full plat: Sands corner 0.000',
  and Lot 11 SE is 0.043' from the caption boundary vertex (~850' from the anchor).
- Full plat: **12 blocks, 191 lots** placed. Not placed: Block 10 (no anchor), Block 6 (no solver). Tests: 267 passed.
- Next: backlog item 4 (Block 6).

### Tick 5 — 2026-09-24 (cron): Block 6 built from the scan
- New `BeachwoodBlock6Solver`, **Lots 2-12** (Lot 1 isn't in Unit Two). Built from the Keel x Blvd P.I.:
  - Keel S R/W with R=113.93 (CL 143.93 - 30); Lot 6 chord 100.40' = full CL Δ 52°17'10".
  - Marina N R/W 100/101.10/75'. The boundary S54°41'40"E 100.16' = 35' (Lot 4) + 65.16' (Lot 3).
  - Boundary curve R=894.08 with lot chords 15.98'/84.02' (together they are the caption's chord S57°53'59"E 99.98').
  - Boundary N28°53'42"E 100' and S65°48'08"E 90.51'. Blvd 90/84.79/110'.
  - Interior rear line S71°15'04"E: 80+75+19.29 = 93.87+80.42 = 174.29. Hub diagonal S40°30'16"E.
- **Reading corrections this tick (all caught by the checks):** the diagonal pieces are **76'** and **82'** (not 76.76/82.76), and the Lot 11/12 line
  is **134.90'** (not 194.90; a "3" read as "9"). Each computed value matched the corrected reading within 0.002'.
- Checks: 15 printed lines within 0.012'. In the full plat: Marina/Keel P.I. 0.034', and 5 caption-boundary vertices within 0.057-0.075'.
  That's a uniform ~0.06' offset, the same order as the caption's own 0.042' misclosure, and within the 0.10' tolerance.
- Full plat: **13 blocks, 202 lots** placed. Only Block 10 remains (no anchor). Tests: 269 passed.
- Next: backlog item 5 (Block 10 anchor).

### Tick 6 — 2026-09-24 (cron): Block 10 anchored, so every Beachwood block is placed
- The Block 10 solver already matched the scan (Lot 13 98.01'/97.43' with the S1°01'40"E west side, Lots 12-9 at 75', 100' deep). The only thing missing was an anchor.
  Its corners are caption boundary vertices: Lot 13 NW = start of c4, Lot 13 SW = c5, Lot 9 SE (P.R.M.) = c6, Lot 9 NE = c7.
- Composer: anchors may now be a caption vertex (`"BND:cN"`), not only a fillet P.I. Block 10 is anchored on c4, and its 3 other vertices check within 0.002'.
- **Full plat: all 13 blocks (6-18), 207 lots incl. Tract A; nothing unplaced.** Worst block check anywhere is 0.075' (Block 6, boundary noise).
- Tests: 269 passed.
- Next: backlog item 6 (Block 12 Lots 3 and 8-10, re-read at 400 dpi).

### Tick 7 — 2026-09-24 (cron): Block 12 re-read at 400 dpi, Lots 8-10 certified
- Rendered the Block 12 area of Sheet 1 at 400 dpi (`pdftoppm -r 400 -x/-y/-W/-H`). The "faint jog" that kept Lots 8-10 flagged is legible:
  San Salvadore S R/W R=239.96 (CL 269.96 - 30), chords 106.60' (Δ 25°40') + 44.61' (Δ 10°40') = CL 36°20', 57.92' + 75' to the P.R.M.
  The jog is 25.82' + 75.04' on S56°34'xx"E, plus N19°06'16"E 60.34'. Lot 8 east N22°32'48"E 72.37'. Lot 9/10 line N35°18'20"E 122.45'.
- **Also corrected Lots 4, 6, 7.** The old solver closed them as quadrilaterals by computation. Per the plat, Lot 7 is 100x75, and Lot 6 is a pentagon
  (north 120.00' = 100' + 20', then the jog). Lot 4 is a hexagon running up to the jog and the boundary's 12.07' course. Lot 5 gets its R=25 Bayou return.
- Checks: 10 printed values within 0.015'. The two jog pieces are collinear to 0.015°. In the full plat: street corner 0.000', and 4 caption
  vertices (c10-c13 starts) within 0.022'.
- Lot 3 is drawn dashed east of the heavy matchline, so it belongs to Unit One and isn't in this plat.
- Full plat: **13 blocks, 210 lots**. Tests: 268 passed. The old "must stay uncertified" / flagged-point tests were replaced by scan-based ones.
  `scripts/draw_block10_11_12_mapcheck.py` now writes `..._claude.dxf`.
- Next: backlog item 7 (Mangrove R/W lines through Block 18).

### Tick 8 — 2026-09-24 (cron): Mangrove R/W artifact through Block 18
- Scan (Sheet 2 top-left): Mangrove Ave starts at Starfish Ave. North of it, Block 18 Lots 1-3 run continuously (103.50', 75', 75'), with only
  the 50' drainage strip to the west. The network already has fillets only on the south side (a T-junction), but its Mangrove corridor
  starts at the north boundary c27.
- Tried capping that corridor at the Starfish centerline in `engine/centerline_geometry.py`. That made
  `engine/cogo_road_centerlines.py` fall back to drawing plain offset R/W LINEs for its own Mangrove centerline segment up to c27
  (its DXF test went from 74 to 76 lines). That module deliberately keeps Mangrove to c27 as a reference baseline, so **I reverted the engine change**
  and left it as a finding for the centerline effort.
- The full-plat composer now leaves out Mangrove pieces north of the Starfish centerline (2 R/W edges). Block 18 is clean in the full plat.
- **Report for the centerline effort:** `INT_MANGROVE_NORTH_END` and the Mangrove centerline segment/corridor north of Starfish aren't on the plat.
  The street is a T at Starfish, and `Road_Centerlines*.dxf` still draws Mangrove R/W through Block 18 Lots 1-2.
- Tests: 268 passed (engine unchanged). Next: backlog item 8 (Block 17 east edge).

### Tick 9 — 2026-09-24 (cron): Block 17 east end
- The "thin extra line" was the Lot 17/18 east side kinked to S04°07'E. The solver had Lot 17's widths **swapped** (front 108.55' / rear 111.54').
  The scan reads Starfish front **111.54'** to the P.I. and rear **108.55'**. Lot 18 is rear 108.55', Sail front 105.56'. Both east sides are 100.04' on the Blvd
  (the same 2.99'/100' skew as Blocks 15/16). The R=25 returns at both Blvd corners were also missing (the magenta arcs came from the network, not the lots).
- Fixed in `BeachwoodBlock17Solver`, with a new `checks` dict: both east sides are 100.045', and the bearing equals the Blvd bearing to 0.001°. In the full plat,
  Lot 17 NE and Lot 18 SE hit the network's Blvd fillet P.I.s within 0.001' and 0.005'.
- The existing test that asserted the swapped values was corrected, and totals were updated. Tests: 268 passed.
- Next: backlog item 9 (re-read Blocks 9, 11, 13 against the scan).

### Tick 10 — 2026-09-24 (cron): Blocks 9, 11, 13 re-read at 400 dpi
- **Block 13**: every printed value matches (Lot 1 100x100 + NE return, Lots 2-9 77.25', Lot 10 76.92', Lot 11 west 99.42' + SE return). No change.
- **Block 11**: dimensions match (93.83/93.25/92.67, 75' lots, matchline N0°41'40"W 200.0'). But the **R=25 returns at Lot 15 NW and Lot 14 SW**
  (drawn rounded on the scan) were missing, and every "stated" area was just the solver's own computed value. Added both returns (skewed corners,
  T 25.146'/24.855'); record areas are now quad-to-P.I. minus fillet.
- **Block 9**: all six frontage curves were modelled as **straight chords**.
  - Cape Horn S R/W, R=297.01: chords 72.39/108.25/6.91 give Δ 14°+21°+1°20'.
  - San Salvadore N R/W, R=299.96: chords 67.91/66.18/55.76 give Δ 13°+12°40'+10°40'.
  - Both sum to CL 36°20', and each solver chord reproduces its plat Δ to 0.001°.
  - Lot 28 alone was missing a 360 SF segment.
  - The Lot 26 SW return was filleted against the chord bearing (Δ 83°30', T 22.3'). The plat's "25.0' N88°58'20"E" makes it Δ 90°, T 25',
    and the curve P.C. lands 0.019' from that point.
- Tests: Block 9's "expected areas" (copied from the chord-only model; the plat prints none) and the 83°30' assertion were updated. 268 passed.
  Full plat: Block 9 0.000', Block 11 0.011'.
- New backlog item 9b: `draw_block9_mapcheck.py` keeps a stale second copy of Block 9.
- Next: item 9b, then the other plats (Ocean Grove).

### Tick 11 — 2026-09-24 (cron): Block 9 drawing script uses the solver
- `scripts/draw_block9_mapcheck.py` now builds its `BeachwoodLotAgent`s from `BeachwoodBlock9Solver.lots` instead of its own hand-built copy
  (which had straight frontages and the 83°30' return). It also gained the missing `sys.path` bootstrap (it only ran with PYTHONPATH set), the
  hardcoded "Arc=39.27' R=25.0'" label on *every* curve is now per-curve, and outputs are `PB0030_P0082_Block9_{MapCheck,CheckSheets}_claude.dxf`.
- Tests: 268 passed.
- Next: backlog item 10 (Ocean Grove faithful rebuild).

### Tick 12 — 2026-09-24 (cron): Ocean Grove started (Blocks 8 and 7)
- Read the whole sheet at 300 dpi. The 1937 plat prints **no bearings**: lines are dimensioned by angles (89°48', 90°12', 90°17', 189°35' ...), and the caption
  distances are "more or less". Frame assumption: 17th St S line due East.
- New `scripts/plat_folder/build_ocean_grove.py` builds **Block 8** (Lots 1-20: 45 + 8x50 + 54.3 across, rows 110', west/side lines S0°12'E from 89°48',
  east line S0°17'E from 90°17') and **Block 7** (Lots 1-8, 4x50', rows 105', across 40' Coral St). Output: `PB0015_P0082_OceanGrove_claude.dxf` + PNG + metrics.
- Checks: B8 south line 499.62' vs printed 499.5' (Lot 11 54.62 vs 54.5). A 0.12' difference is within what whole-minute angles allow over 220' (1' of angle ≈ 0.064').
  Lot 20 45.000, B7 south 200.000.
- The old schematic `dxf/PB0015_P0082_OceanGrove*.dxf` from `scripts/build_ocean_grove.py` is superseded (left in place, not deleted).
- Next: Ocean Grove Block 6.

### Tick 13 — 2026-09-24 (cron): Ocean Grove Block 6
- Read at 400/800 dpi. Lots 1-5 on Coral St, 12 and 6 in the middle row (chamfered 25' corner), 11-7 on Dewees Ave N line and the Coquina curve R=100.
  Beach Ave W line bends 156°58' and 192°44' (street side).
- **The plat's own values conflict here**, confirmed at 800 dpi: 80°42', 88° and 26.4' are all clear. Two builds were tried:
  - All-angles variant: misfits of 0.5-2.4' spread across the block.
  - Kept variant: the Beach line is fixed by Lot 5's printed 38' and Lot 7's own 88° angle. The middle and east lots then close within ~0.5':
    Lot 6 top 138.000, Lot 5 east 116.64, chamfer 25.5, Lot 12 south 102.99, Lot 7 south 49.6/east 115.1.
    The printed 80°42' and 192°44' come out 0.3° and 1.3° off.
  - The **Coquina curve corner** still doesn't fit: the 26.4' tangent computes 31.1' (4.7'), the Lot 9 arc 16.1 vs 18, the 10/11 line 120.5 vs 118.3.
- Lots 9, 10, 11 are drawn on `LOT-FLAGGED` (red) and listed in metrics `flagged_lots`. They're not certified. The conflict is recorded in the assumptions.
- Ocean Grove now has 40 lots (Blocks 8, 7, 6). Next: Ocean Grove Block 4.

### Tick 14 — 2026-09-24 (cron): Ocean Grove Block 4, top rows
- Read at 400/800 dpi. The labels along Block 4's middle easement line really are **35 / 35 / 45'** (not to drawn scale).
- Built Lots 1/2, 11/3, 10/4: Shell St top 100' + 110'; west 50/50/50; middle 50/50/35; east 50/50/55.6 on a line parallel to the west (90°12' at NE).
  Checks: Lot 4 south 111.983 vs 111.98 (confirms the 35'). Lot 10 south 101.07 vs 101.9 (0.83'), which implies a ~54.6' west side where 50' is printed; reported, not forced.
- Lots 5-9 wait for the Dewees Ave line, which Block 1 shares. Ocean Grove: 46 lots so far (Blocks 8, 7, 6, half of 4).
- Next: Ocean Grove Block 1 + Block 4 Lots 5-9 (Dewees Ave line and its curves).

### Tick 15 — 2026-09-24 (cron): Ocean Grove Block 1, parked for user input
- Read Block 1 at 400 dpi and saved every printed value to `Plat/output/PB15_P82_OceanGrove/block1_transcription.json` (16 lots, Dewees curves
  Ra=231/368, Beach curves Ra=55/103, the 59°08' spine, the 199°28' bend).
- **The printed values contradict each other.** With Lots 2/3 at 100' deep, Lot 4's west at 50' and its top at 123.2', the Beach W line (100' from Lot 3 SE, R=55 arc 44.45', then 16.9')
  can't reach Lot 4's NE corner. The closure equations have no solution (squared sums 3310.6 vs 3781.6). Together with Block 6's 4.7' Coquina conflict, this 1937
  plat's curve-side dimensions don't close as printed.
- Under the tick rules (never invent), the remaining curve-dependent Ocean Grove work (Block 1, Block 4 Lots 5-9, triangle Blocks 5/3/2) is marked
  **NEEDS USER INPUT**. Options for the user: (a) allow a documented least-squares fit, flagged as such; (b) supply another record (deed, survey,
  county GIS parcel lines); (c) leave those parcels unbuilt. Ocean Grove stays at 46 lots (Blocks 8, 7, 6, top of 4).
- No code change this tick; transcription saved. Next: backlog item 11 (Hicks R/W south line).

### Tick 16 — 2026-09-24 (cron): Hicks A.C.L. R.R. right-of-way
- Re-read the R/W ties at 300/800 dpi: 202', 266', **382'** (clear), 432', 719.7', 658.7', 74.5', 247.7'.
- Replaced the two independent 3-/4-point circle fits (radii 5378 vs 3248, south residuals up to 36') with **one constant-width corridor**
  (concentric circles, least squares). Result: R≈5875, width 90' (a standard R/W). Six ties fit within 2.2'.
- **The printed 382' is a probable drafting slip on the plat.** A constant-width corridor through the other six ties, the drawn scale, and both stated acreages
  (Richard W 2.8A, Richard E 3A) all put that line at ~332-335'. It's excluded from the fit, and its 38' residual is reported in metrics/assumptions.
- All 10 Hicks parcels are now within 2.1% of their stated acreage. Before, the worst was +5.6% and flagged; now nothing is flagged.
- Tests: 268 passed. Next: backlog item 12 (John M. Stevens Subdivision, right panel of PB 4/85).

### Tick 17 — 2026-09-24 (cron): John M. Stevens Subdivision, southern strip
- New `scripts/plat_folder/build_stevens.py` -> `Plat/output/PB4_P85_Stevens/PB0004_P0085_Stevens_claude.dxf` (+ PNG, metrics).
- Built **Lots 26-45** (20 lots) south of the Sibbald Grant south line, either side of 50' Stevens Ave. Lots 45-38 / 26-33 are 621.50' x 175.2' = 2.4997A (printed 2.5A).
  Lots 37/36 are 146.75' deep (west) and 35/34 are 156.75' (east): a south line skewed 10' across the 1293' width. Computed 2.13A / 2.20A; the plat's single 2.16A for all
  four is exactly their average (2.165A). Worst lot 1.95%.
- Assumption (no bearings on the plat): Section Line due South, lot lines square to it.
- Next: Stevens lots north of the Sibbald Grant line (Lots 1-25 and 46-65: A.C.L. R.R., Kings Road, Belle St, Park Ave).

### Tick 18 — 2026-09-24 (cron): Stevens, north of the Sibbald Grant line (dimensioned part)
- Added the Belle St south row: Lot 19 (120', west 391' / east 405') and Lots 18-9 (105' x 405'). Also the east column: Block 8 Lots 1-4 (105' x 105' under the 420'
  line), Lots 7/6/5 (105/105/90) up to Belle St's south line, Belle St 30', and Lots 4/3/2 (90/105/105), all 420' wide.
- Check: Block 8 + Lots 7, 6, 5 = **405.0'**, exactly Lot 9's printed depth. That confirms the stacking and the 90' readings.
- Acreage flags, shown red: Lots 4 and 5 (420x90 = 0.87A, printed "1.A", -13%) and Lot 19 (1.10A vs 1.02A, +7.5%). The geometry is certain; the printed
  acreages look rounded or wrong on the plat. Lots 18-9 are 0.976A vs 1A (-2.4%).
- Still unbuilt: Lot 1 (0.57A, 117.8'), Lots 20-23 and everything north of the railroad (46+, Kings Road, Park Ave). Their lines run along the A.C.L. R.R.,
  whose direction isn't printed. It could only be inferred from Lot 22/23's 185.6'/249.5' sides with unprinted widths, so this is **NEEDS USER INPUT** (same
  options as Ocean Grove). Stevens: 41 lots.
- Tests: 268 passed. Next: backlog item 13 (Atlantic Beach CC Sheet 3 rear lines).

### Tick 19 — 2026-09-24 (cron): Atlantic Beach CC Unit 2, Sheet 3 row (Lots 136-126)
- `scripts/build_forceclosed.py` had two real errors:
  1. **Off-by-one:** every printed side line was shifted one lot west. 119.72' is the 137/136 line, not Lot 137's side. It then invented an
     "assumed" 13th depth, although 118.64' *is* the 126/125 line.
  2. The Maritime Oak Dr frontage was drawn as "assumed" chords, claiming the plat doesn't say which curve belongs to which lot. It does:
     each lot's frontage is labelled (C201+45.89 | 34.12+C200 | C199+C198 | C197 | C196 | C195+11.42 | 55.12 | 60.13 | 55.12 | 55.12 | 60.13), and the curve
     table gives every chord bearing and length (read at 300 dpi). The straights sum exactly: 45.89+34.12 = 80.01 (80.00 printed), and the 307.87' tangent = 307.870.
- New `scripts/plat_folder/build_atlantic_sheet3.py` builds the row two independent ways: rear line + printed side lines, and a frontage chain from the
  curve table. **All 11 front corners agree within 0.014'.** The chain is tangent-consistent: R=150 turns left, R=700 turns right, C195 ends on S04°17'54"W.
- Gotcha: Sheet 3 is drawn with **north to the left** (Lot 137 is the north end). Walking the other way gave misfits of up to 44'.
- Output: `Plat/output/PB67_P132_AtlanticBeach_S3/PB0067_P0134_AtlanticBeachCC_Sheet3_Lots126-136_claude.dxf` + PNG + metrics. Tests: 268 passed.
- Next: Atlantic Sheet 3 Lot 137 (C202 R=150, 137.85' rear) and Lots 125-124 (C194/C190/C189), then the other sheets.

### Tick 20 — 2026-09-24 (cron): Atlantic Beach Sheet 3, row complete (Lots 137-124)
- **Lot 137**: rear 137.85' from the north-corner monument, 119.72' side, frontage curve C202 (R=150, L=196.30). C202 and C201 are one R=150 curve: C202's
  chord bearing follows from C201's start tangent. Check: C202 chord computed 182.580' vs 182.59' printed, bearing N41°30'46"E to 0.0003°.
  Rear widths close: 137.85 + 625.00 + 10.00 = 772.85 (printed).
- **Lots 125-124**: rear 10.00' + 45.78' / 55.95' on the N10°02'38"W course; sides 120.62', 104.67' (matchline); fronts 10.83' + C194 (R=100) and C190 (R=100) +
  C189 (R=235, reverse curve). Front corners agree within 0.007' / 0.005'.
- Output renamed `PB0067_P0134_AtlanticBeachCC_Sheet3_Lots124-137_claude.dxf` (my earlier 11-lot file was removed). Tests: 268 passed.
- Next: Atlantic Sheet 3 south of Maritime Oak Dr (Lots 138-176, Timber Bridge Lane / Coastal Oak Lane), then Sheets 1, 2, 4-6.

### Tick 21 — 2026-09-24 (cron): Atlantic Beach Sheet 3, Lots 167-176
- Tied across Maritime Oak Dr (50'): C41 (R=200, S R/W) = C206 + C207 and is concentric with C45 (R=150) = C200 + C199, so the S R/W P.C. lies 50' west of the
  N R/W P.C. From there: north line N89°27'38"W 75.72/50.28, 2.30' + 55' on N80°24'17"W, N75°38'28"W 60.21, N65°08'58"W 57.01, then 225' (55/60/55/55).
  Side lines S09°35'43"W 130/130/135/150/150/150/150/154.78.
- Checks: Lots 169-174 fronts come out 55.000/60.002/55.001/55.000/60.000/55.000 (printed 55/60/55/55/60/55). The 362.66' straight = 11.10 + 340 + 11.56 exactly.
  Lot 168 closes to 0.020' and Lot 167 to 0.023' after going all the way round through the street tie, but only once **C208 (4.05') is assigned to Lot 167**, not 168.
- Lots 175/176: corners are fixed by printed lines, but their frontage curves C212-C214 aren't in this sheet's curve table. As R=200 arcs they
  don't reproduce C37's Δ (30.25° vs 19.89°), so they're **flagged red**, not certified. Probably on another sheet's table.
- Output now `Plat/output/PB67_P132_AtlanticBeach_S3/PB0067_P0134_AtlanticBeachCC_Sheet3_claude.dxf` (24 lots). Next: Sheet 3 Lots 138-166.
