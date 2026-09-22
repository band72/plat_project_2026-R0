# Implementation Plan: Solving Arbitrary Uploaded Plats End-to-End

Status: **proposed, not started.** Written before writing any code, per request.
Scope: backend/engine integration work. Lives in `plat-reader/` because that's
where it was asked to be saved, but the work described here is almost
entirely in `engine/` and `web/server.py` — the plugin itself needs no
changes to consume it (see "What the plugin needs" at the bottom).

---

## 1. What "solving a plat" actually means in this codebase today

Before proposing new code, it's worth being precise about the pattern this
repo already uses successfully 50+ times (`scripts/build_*.py`), because the
new pipeline should be an automated version of that pattern, not a different
approach:

1. Get an ordered list of **courses**: each one a bearing + distance, or a
   circular curve (radius, delta, chord bearing/length). This is the
   **authoritative legal record** — it's what's recorded, what a licensed
   surveyor certifies, and what closure is checked against. Every script in
   this repo gets courses one of two ways: hand-transcribed from reading the
   plat, or OCR'd from a printed call table.
2. Walk those courses from a known starting point (`engine.cogo.run_traverse`
   / `bowditch_balance`) to get real coordinates.
3. Check closure (`engine.cogo.closure_report`, `engine.verify`) — does the
   traverse return to its start within tolerance?
4. If it doesn't close, look for a plausible transcription/OCR error
   (`engine.repair`: inverse-solve a curve from any two of its four fields,
   cross-check radius against the rest of the table) and only auto-apply a
   fix when it's a single-digit edit away from what was read — otherwise
   flag it for a human rather than guess.
5. The **drawn linework** (vectorized from the raster) is used as a
   cross-check against the stated courses (`engine.blunder.classify`), not
   as the primary source of geometry. This matters: automatically tracing a
   polygon boundary out of raw Hough-transformed line segments with no
   semantic labels is a much less reliable problem than reading a
   structured table of numbers, and every existing script in this repo
   avoids relying on it for that reason.

**The plan below is the automated version of that same pipeline** — OCR the
call table, walk the traverse, check closure, repair what can be repaired
with confidence, flag what can't, use vectorization as a cross-check and for
the visual overlay. It deliberately does **not** try to auto-detect lot
boundaries from pixels alone with no table to anchor them.

## 2. What already exists vs. what's missing

**Already built and reusable as-is (no changes needed):**

| Capability | Module / function |
| --- | --- |
| Parse a quadrant bearing string → azimuth | `engine.cogo.parse_bearing` |
| Walk a course list from a start point | `engine.cogo.run_traverse` |
| Force-balance a closed traverse (Bowditch) | `engine.cogo.bowditch_balance` |
| Closure error / precision ratio | `engine.cogo.closure_report` |
| Circular curve math (all params from any 2) | `engine.curves.solve_curve_all_parameters` |
| Ring closure / self-intersection / simple-polygon checks | `engine.verify` |
| OCR digit-confusion repair, radius consensus | `engine.repair` |
| Curve-row/line-row table OCR, cell-grid OCR | `engine.ocr` (`find_table_regions`, `parse_table_with_header`, `parse_line_rows`, `parse_curve_rows`) |
| Generic raster→vector linework extraction | `engine.vectorize.vectorize_plat_sheet` (already takes *any* image, not plat-specific) |
| Drawn-vs-stated deviation classification (OK/WATCH/FLAG) | `engine.blunder.classify`, `.report` |
| DXF layers, lot/line/curve schedule tables | `engine.dxf_writer`, `engine.tables` |
| Area/perimeter, polygon validity | `engine.lots.shoelace_area`, `.is_simple_polygon`, `.safe_area` |

**Missing (the actual work):**

1. **PDF → raster image.** Uploads accept PDF; every vision function needs a
   raster. No PDF-rendering code exists yet. `poppler-utils` (`pdftoppm`,
   `pdftocairo`) is already installed on this system — cheapest path is
   shelling out to it, avoiding a new Python dependency. (`PyMuPDF` is the
   pip-installable alternative if a pure-Python path is preferred; not
   currently installed.)
2. **The glue function**: raster/call-table image → ordered course list.
   `engine.ocr` has the pieces (table region detection, cell OCR, row
   parsing) but no single function that goes from "here's an image" to
   "here's a list of `Course` objects ready for `run_traverse`." This is the
   core new code.
3. **A generic result shape.** The current `/api/analyze` response is
   hardcoded to Beachwood Block 9's 9 named lots (`lot_order`,
   `frontage_map`, fixed point names like `p23_se`). A generic plat has an
   unknown number of parcels (often exactly one — the overall boundary —
   unless a lot table is also parsed). The API and frontend both need a
   parcel-count-agnostic shape.
4. **Confidence-aware verdicts.** Block 9 is hand-verified to achieve
   `0.000 ft` exact closure; that's what "EXACT" and "PASS" mean today. A
   freshly-OCR'd plat will not, in general, close exactly — the response
   needs real PASS / WATCH / FLAG / FAILED states driven by actual computed
   closure and OCR confidence, not a hardcoded "EXACT" string.
5. **P.O.B. is unavoidably manual.** A scanned image has no inherent
   real-world coordinate system. The existing UI already has a P.O.B.
   northing/easting field for this — it needs to actually be used as the
   traverse's starting point instead of being accepted-and-ignored.

## 3. Proposed pipeline (`engine/plat_pipeline.py`, new file)

```
solve_uploaded_plat(plat_image_path, call_table_image_path | None,
                     pob: Point, scale_feet=None, dpi=None) -> PlatSolveResult
```

Steps:

1. **Normalize inputs.** If either input is a PDF, rasterize page 1 at
   ~300 DPI via `pdftoppm` (subprocess) to a temp PNG. Load with
   `engine.ocr.load_gray` / `cv2.imread`.
2. **Locate the call table.** If a dedicated call-table image was uploaded,
   use it directly. Otherwise run `engine.ocr.find_table_regions` on the
   plat image itself and use the largest candidate region — matching how
   `scripts/benchmark_ocr.py` already does this.
3. **OCR the table** via `engine.ocr.parse_table_with_header` (preferred —
   handles arbitrary column order) with a fallback to
   `parse_line_rows`/`parse_curve_rows` (fixed-format regex parse) if header
   detection fails. Produces raw row dicts (line: bearing+distance; curve:
   radius/length/delta/chord/chord_bearing).
4. **Build `Course` objects** (`engine.cogo.Course`) in table order. Curves
   get registered in a `curves: dict[str, dict]` keyed by an assigned ID
   (`C1`, `C2`, ...) for `run_traverse`'s curve-lookup contract.
5. **Walk the traverse** from the user-supplied P.O.B.
   (`engine.cogo.run_traverse(pob, courses, curves)`).
6. **Check closure** (`engine.cogo.closure_report`). If misclosure exceeds
   tolerance (F.A.C. 5J-17: 1:10,000 relative precision, same standard the
   rest of this repo already certifies against):
   a. Run `engine.repair.inverse_solve_curve` / `radius_consensus` /
      `apply_corrections` against any curve rows.
      For straight-course rows, apply the equivalent single-digit-edit
      check directly against distance/bearing (same `digit_edit_ok` logic
      `engine.repair` already exports) rather than duplicating it.
   b. Re-walk and re-check closure with corrections applied.
   c. If it still doesn't close: return the traverse anyway with an
      explicit `FAILED`/`FLAGGED` verdict and the raw misclosure — never
      silently force a fake close via `bowditch_balance` and report it as
      exact. (Bowditch balancing is legitimate *when a surveyor has
      certified the courses as recorded and wants to distribute known
      random error* — it is not legitimate to hide an OCR mistake. The
      pipeline must not blur that distinction.)
7. **Cross-check against drawn linework (best-effort, non-blocking).** Run
   `engine.vectorize.vectorize_plat_sheet` on the plat image and
   `engine.blunder.report(courses, raster_segs)` to flag any course whose
   stated bearing/distance doesn't track the drawn line within tolerance.
   Failure of this step (e.g. a scan too noisy to vectorize) degrades to
   "no cross-check available," not a pipeline failure — it's corroborating
   evidence, not a dependency.
8. **Assemble the result**: points, courses, closure report, per-course
   blunder flags, overall verdict, plus DXF + report text via the existing
   `engine.dxf_writer` / `engine.tables` building blocks.

### Confidence / verdict model

Replaces the implicit "always EXACT" assumption with real states:

| Verdict | Meaning |
| --- | --- |
| `PASS` | Closes within F.A.C. 5J-17 (1:10,000); no unresolved blunder flags. |
| `PASS_REPAIRED` | Closed only after an auto-applied, high-confidence single-digit-edit correction — result is shown, correction is disclosed in the report, not hidden. |
| `WATCH` | Closes, but a course's drawn line deviates enough to flag (`engine.blunder` WATCH tier) or OCR confidence on a field was low. |
| `FLAGGED` | Misclosure resolved only by a redundancy-based (non-single-digit-edit) correction — plausible, not certain; needs human review before being trusted. |
| `FAILED` | Does not close and no repair candidate found. Still returned (points, raw misclosure, draw the traverse) so a human can see exactly where it breaks, never hidden behind a generic error. |

This is a direct generalization of the honesty-note mechanism already in
`web/server.py` (`[[web-plugin-and-downloads-2026-09-22]]`) applied at the
per-result level instead of only at the per-request-field level.

## 4. API contract changes (`web/server.py`)

- `/api/analyze`: when `preset == "custom"` **and** a real `uploaded_filename`
  is present, call `solve_uploaded_plat(...)` instead of unconditionally
  falling back to `_solve_block9()`. `preset == "block9"` keeps behaving
  exactly as it does today — the certified reference case is not touched by
  any of this.
- Response shape becomes parcel-count-agnostic: `parcels: []` already is a
  list, so the frontend rendering code mostly Just Works; what needs to
  change is everything that currently assumes exactly the 9 Beachwood lot
  IDs (`LOT_ORDER`, `frontage_map`, hardcoded `p23_se`/`p31_ne` matchline
  points for the SVG). For a generic solve there is typically **one**
  parcel (the overall boundary traverse) unless a separate lot-subdivision
  table was also provided — v1 only produces the one overall boundary.
- New field on each parcel: `"verdict"` already exists in the schema
  (currently always `"EXACT (0.000 ft)"` for Block 9) — reuse it to carry
  the real verdict from §3, and add `"flags": [...]` (per-course blunder
  notes) for the UI to render.
- `pob_northing`/`pob_easting` become real inputs (`Point(pob_northing,
  pob_easting)`), not accepted-and-logged.
- `call_table_filename`, if present, is looked up in `UPLOAD_DIR` and passed
  as the dedicated call-table image.
- If OCR finds **zero** usable course rows, return a normal 200 response with
  `parcels: []` and a clear `note` explaining extraction failed and why
  (e.g. "no table region found" / "0 rows parsed") — not a 500, and not a
  fabricated result.

## 5. Frontend changes

Given the JSON contract stays parcel-list-shaped, `app.js`'s render
functions need only:
- Stop assuming a fixed 9-entry `LOT_ORDER`/`frontage_map` for anything
  other than the `block9` preset's own rendering path.
- Render `verdict` as shown (not just PASS/FAIL) and add a small flags list
  per parcel in the checksheet modal.
- The `note` banner already built (`[[web-plugin-and-downloads-2026-09-22]]`)
  is reused as-is for the "0 rows parsed" case.

## 6. New dependency

None required if using `pdftoppm` via `subprocess`. If a pure-Python PDF path
is preferred instead, add `PyMuPDF` to `requirements.txt`. Recommend
`pdftoppm` first — zero new pip dependency, already installed, this repo has
consistently preferred zero/minimal external dependencies
(`engine/dxf_writer.py`'s hand-rolled DXF writer is the precedent).

## 7. Phasing

- **Phase 1 (core, this plan's main deliverable):** steps 1–6 above —
  call-table OCR → traverse → closure → repair → verdict. No vectorization
  cross-check yet. This alone makes `/api/analyze` do something real for an
  uploaded plat + call table image, with honest PASS/FLAGGED/FAILED
  results.
- **Phase 2 (cross-check):** step 7, `engine.blunder` integration against
  vectorized linework, surfaced as per-course flags and an SVG overlay of
  the raw drawn lines behind the solved traverse.
- **Phase 3 (stretch, not scoped in detail here):** multi-lot subdivision —
  parsing a *lot* schedule table (not just a line/curve table) to split the
  overall boundary into individual numbered parcels the way Block 9 does
  today. Meaningfully harder (needs to associate lot rows with specific
  traverse segments) and not required for "does this solve a plat
  end-to-end."

Phase 1 is the one that makes the "yes" from this conversation true. Phases
2–3 improve confidence and coverage but aren't blocking.

## 8. Honest risk list

- **OCR reliability varies a lot with source quality.** This repo's own
  `engine/repair.py` docstring records a 36% exact-recovery rate on a real
  batch of OCR'd rows from a difficult scan, and `data/*.py` files contain
  explicit notes like *"Tesseract cannot read this hand-lettered 200 DPI
  scan -- measured: 0 bearings parsed."* A cleanly-typed modern plat will
  OCR far better than a 1920s hand-lettered one. Expect `FAILED`/`FLAGGED`
  results to be common on the hardest source material, by design — the
  pipeline's job is to be honest about that, not to inflate confidence.
- **Table layout variance.** `parse_table_with_header` needs ruled cell
  borders to segment columns reliably; a plat whose call table isn't a
  clean ruled grid may need the regex fallback (`parse_line_rows`), which
  is more brittle.
- **Scale/DPI ambiguity.** `vectorize_plat_sheet` needs a `scale_feet`/`dpi`
  guess for the cross-check step to be in real units; wrong scale doesn't
  break the traverse solve (that's table-driven) but will throw off the
  blunder cross-check and the SVG overlay proportions.
- **P.O.B. is always user-supplied**, not detected. No way around this
  without a georeferencing step (out of scope here).

## 9. Testing strategy

Validate against real source material already in this repo before calling
Phase 1 done:
- `Plat/Duval_Plat_Book_30_Page_82-2.pdf` — the Beachwood source PDF itself,
  a good sanity check since ground truth (Block 9) is already known.
- `Plat/Plat_Book_15_Page_82.pdf`, `Plat/Beverly-Isle.pdf`,
  `Plat/67-132.pdf`, `Plat/Plat_Book_4_Page_85.pdf` — different scan
  quality/typography/era, good stress test for the honesty-under-failure
  behavior in §3/§8, not just the happy path.
- Add real pytest coverage (this repo's `test_repair.py` was previously a
  print-only script with zero assertions until the 2026-09-22 pass fixed
  that — new pipeline code should not repeat that mistake): assert on
  verdict correctness for at least one known-good and one known-bad
  synthetic course list, not just "it runs."

## 10. Explicit non-goals for this plan

- Not attempting automatic multi-lot subdivision in Phase 1 (see Phase 3).
- Not attempting automatic georeferencing/P.O.B. detection.
- Not silently forcing closure on OCR'd data via Bowditch balancing (see
  §3 step 6c) — that would misrepresent an uncertain read as a certified
  survey, which is the one thing this whole codebase's design is careful
  never to do.
- Not reusing `BeachwoodBlock9Solver` machinery for generic plats — that
  class is intentionally Beachwood-Block-9-specific (hardcoded point IDs,
  corner-return logic tuned to that plat's P.I. angle-bar convention); the
  generic path is new, parallel code, not a generalization of it.

## What the plugin (`plat-reader/`) needs once this ships

Nothing structural. `plat-reader.js` already POSTs to `/api/analyze` and
renders whatever `parcels[]`/`summary`/`note` comes back generically (it was
built against the same contract as the main app, not against Block-9-shaped
assumptions). The only likely follow-up is rendering a `verdict` per row
instead of assuming PASS, and that's a small, additive change once Phase 1's
response shape is final.
