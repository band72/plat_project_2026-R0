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
4. Re-run `python3 -m pytest -q`. The **8 road-centerline failures** in `test_beachwood_road_centerlines.py` /
   `test_centerline_geometry.py` were already failing before this loop began. They are not ours; don't "fix" them
   blindly. Any other failure blocks the tick.
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
1. [ ] **Ocean Grove**: faithful rebuild of Blocks 1–8 from the scan (streets 16th/17th/Coral/Shell, Dewees Ave diagonal, Coquina Pl, Beach Ave). Old `scripts/build_ocean_grove.py` is schematic.
2. [ ] **Hicks R/W south line**: the 4-point circle fit leaves residuals up to 36 ft, and the two R/W lines aren't concentric. Re-read the ties at 300 dpi (266 / 382 / 432 / 202), then try a joint concentric fit or a tangent+curve model ("62.5' to P.C." note). Richard Hicks (E) is +5.6% on area.
3. [ ] **John M. Stevens Subdivision** (right panel of PB 4/85, 1910): ~65 lots, Sibbald Grant; not built at all.
4. [ ] **Atlantic Beach CC**: read the real rear lines for Sheet 3 lots 126–137 (they're currently assumed), then Sheets 4–6.
5. [ ] **Beverly Isle**: re-verify parcels against the scan (claims 0.0000 misclosure on 20 parcels, so check that they aren't constructed-to-close).
6. [ ] **Beachwood other blocks**: audit each block against the scan the way Block 15 was done (the Block 16 Lots 28–30 wedge looks suspicious in the all-blocks drawing; Block 12 Lots 8–10 is honestly flagged).
7. [ ] `scripts/plat_folder/scorecard.py`: aggregate every `metrics.json` into `Plat/output/SCORECARD.md`.

## Ticks

### Tick 0 — 2026-09-24 (interactive)
- **Block 15 (Beachwood), reported wrong by the user.** Re-read from the scan; the solver had four transcription errors:
  the Shellfish curve Δ was 65°19'35" (plat: 52°17'10", chord 121.56'); Lot 1 had an invented 25'/25' jog instead of Marina
  115' to the P.I. + 25.0' to the curve P.C.; the Lot 15/16/17 rear line was 87.13/40.46 instead of 75/75/40.46; and Lot 15's west line
  was N9° instead of N3°08'07"W. Also: there's a spurious R=1959.86 "C2" curve on the Lots 9/10 east sides (Blvd is straight there), and all four R=25
  corner returns were missing. After the fix, every independent printed line closes within 0.015'. The one exception is the Lot 16 chord: the plat prints 82.45'
  but the geometry gives 82.05'. That's flagged as a plat inconsistency, not forced to fit. `scripts/mapcheck_block15.py` now draws from the solver (it used to keep a stale second copy).
- **Hicks** rebuilt faithfully: `scripts/plat_folder/build_hicks.py`. 9 of 10 parcels are within 2.5% of their stated acreage (no bearings on the plat, so orientation is assumed).
