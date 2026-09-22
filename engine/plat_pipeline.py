"""
engine/plat_pipeline.py -- generic, automatic solve for an ARBITRARY uploaded
plat, as opposed to the hand-curated Beachwood Block 9 reference solver in
engine/cogo_block.py. Implements plat-reader/IMPLEMENTATION_PLAN.md.

Pipeline (mirrors what every scripts/build_*.py file in this repo already
does by hand -- this automates that pattern, it does not invent a new one):

  1. Normalize input (PDF -> raster image).
  2. Locate and OCR the call table (line/curve schedule) into an ordered
     course list -- the call table is the AUTHORITATIVE source of geometry,
     matching standard surveying practice.
  3. Walk the traverse from a user-supplied P.O.B. (a scanned image has no
     inherent real-world coordinate system -- there is no way around this).
  4. Check closure against F.A.C. 5J-17 (1:10,000).
  5. If it doesn't close, attempt repair via engine.repair's existing
     single-digit-edit / redundancy logic. Auto-apply only high-confidence
     corrections; low-confidence ones are applied but the result is
     downgraded to FLAGGED, never silently presented as certain.
  6. (Phase 2, best-effort) Vectorize the plat image as a coarse sanity
     check -- see the module docstring on `vectorize_diagnostics` for why
     this does NOT do precise per-course cross-referencing.
  7. (Phase 3, opt-in) Uniform rectangular lot-row subdivision along the
     longest course, using engine.lots.rect_row -- pure COGO math on the
     already-solved traverse, no raster/pixel work involved.

Every result carries an honest verdict tier (see `Verdict`) instead of
asserting the certified-Block-9-style "EXACT" closure that this generic
path cannot promise for arbitrary source material.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field

from engine.cogo import Course, Point, azimuth_to_bearing, run_traverse
from engine.cogo_block import LotMapCheckResult, TraverseCourse
from engine.lots import Lot, check_orthogonal, is_simple_polygon, rect_row, safe_area
from engine.ocr import (
    find_table_regions_inside_border,
    load_gray,
    ocr_best,
    parse_curve_rows,
    parse_line_rows,
    parse_table_with_header,
)
from engine.repair import apply_corrections, inverse_solve_curve, radius_consensus
from engine.verify import verify_ring

FAC_5J17_RATIO = 10000.0          # F.A.C. 5J-17 minimum relative precision
CLOSE_TOL_FT = 0.1                # generic "closes" tolerance (OCR'd data has more
                                   # rounding noise than Block 9's hand-verified 0.05 ft)


class Verdict:
    """Honest result tiers -- see IMPLEMENTATION_PLAN.md section 3.
    Never collapse these into a bare PASS/FAIL; the tier IS the information."""
    PASS = "PASS"
    PASS_REPAIRED = "PASS_REPAIRED"
    WATCH = "WATCH"
    FLAGGED = "FLAGGED"
    FAILED = "FAILED"


@dataclass
class PipelineDiagnostics:
    """Everything about *how* a result was produced, so a human can judge
    how much to trust it -- never hidden, always returned alongside the
    result."""
    table_method: str | None = None
    table_region: tuple | None = None
    raw_line_count: int = 0
    raw_curve_count: int = 0
    ordering_is_heuristic: bool = False
    repairs_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    vectorize_ok: bool = False
    vectorize_summary: str | None = None


# ---------------------------------------------------------------------------
# 1. PDF -> raster
# ---------------------------------------------------------------------------

MAX_RASTER_EDGE_PX = 6000   # cap the long edge; OCR/vectorization cost scales
                           # with pixel count, and plat sheets range from
                           # letter-size to E-size (~56x40 in) -- a fixed DPI
                           # sized for the former makes the latter render at
                           # ~190 megapixels and take minutes (observed on
                           # Beverly-Isle.pdf, a 3898x2890 pt / ~54x40 in sheet).


def _pdf_page_points(pdf_path: str) -> tuple[float, float] | None:
    """First page size in points via `pdfinfo`, or None if unavailable."""
    try:
        out = subprocess.run(["pdfinfo", pdf_path], check=True, capture_output=True, text=True).stdout
        m = re.search(r"Page size:\s*([\d.]+)\s*x\s*([\d.]+)", out)
        if m:
            return float(m.group(1)), float(m.group(2))
    except Exception:
        pass
    return None


def rasterize_pdf_first_page(pdf_path: str, dpi: int | None = None) -> str:
    """Render page 1 of a PDF to a PNG via poppler's `pdftoppm` (already
    present on this system -- avoids adding a new Python dependency such as
    PyMuPDF; see IMPLEMENTATION_PLAN.md section 6). Returns the PNG path.

    DPI is chosen from the page's physical size (via `pdfinfo`) so the
    rendered image's long edge stays under MAX_RASTER_EDGE_PX regardless of
    sheet size, rather than using one fixed DPI that's reasonable for a
    letter-size sheet and disastrous for an E-size (34x44 in+) one."""
    if dpi is None:
        dpi = 300
        pts = _pdf_page_points(pdf_path)
        if pts:
            long_edge_in = max(pts) / 72.0
            dpi = max(72, min(300, int(MAX_RASTER_EDGE_PX / long_edge_in)))

    out_dir = tempfile.mkdtemp(prefix="plat_pdf_")
    out_prefix = os.path.join(out_dir, "page")
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1", pdf_path, out_prefix],
        check=True, capture_output=True,
    )
    # pdftoppm names single-page output "<prefix>-1.png" or "<prefix>.png"
    # depending on version; find whichever it produced.
    for candidate in (f"{out_prefix}-1.png", f"{out_prefix}.png", f"{out_prefix}-01.png"):
        if os.path.exists(candidate):
            return candidate
    matches = [f for f in os.listdir(out_dir) if f.endswith(".png")]
    if matches:
        return os.path.join(out_dir, matches[0])
    raise RuntimeError(f"pdftoppm produced no output for {pdf_path}")


def load_plat_image(path: str):
    """Load any accepted upload type (PDF or raster) as a grayscale image,
    downscaled to MAX_RASTER_EDGE_PX on the long edge if needed (a directly
    uploaded raster has no page-size hint to pre-size a render from, unlike
    a PDF, so the cap is applied after loading instead)."""
    if path.lower().endswith(".pdf"):
        path = rasterize_pdf_first_page(path)
    img = load_gray(path)
    h, w = img.shape[:2]
    long_edge = max(h, w)
    if long_edge > MAX_RASTER_EDGE_PX:
        import cv2
        scale = MAX_RASTER_EDGE_PX / long_edge
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


# ---------------------------------------------------------------------------
# 2. Call table -> ordered course list
# ---------------------------------------------------------------------------

def _numeric_key(row_id: str) -> int:
    m = re.search(r"\d+", row_id)
    return int(m.group()) if m else 0


def extract_call_table(img) -> tuple[dict, dict, PipelineDiagnostics]:
    """OCR the call table on `img` (a call-table image, or a full plat sheet
    if no dedicated table image was provided). Returns (curves, lines, diag)
    keyed by their own row ID (e.g. "C1", "L1"), same contract as
    engine.ocr's own parse functions.

    Tries the header-driven cell reader first (most reliable -- handles
    arbitrary column order, see engine.ocr.map_header's docstring on why
    column order can't be assumed), falls back to whole-region regex OCR
    for tables without clean cell ruling."""
    diag = PipelineDiagnostics()
    regions = find_table_regions_inside_border(img)
    if not regions:
        diag.warnings.append("no ruled table region found on this sheet")
        return {}, {}, diag

    regions = sorted(regions, key=lambda r: r[2] * r[3], reverse=True)[:3]
    best_curves, best_lines = {}, {}

    for rect in regions:
        curves, lines, _header = parse_table_with_header(img, rect)
        if len(curves) + len(lines) > len(best_curves) + len(best_lines):
            best_curves, best_lines = curves, lines
            diag.table_region = rect
            diag.table_method = "cell_header"

    if not best_curves and not best_lines:
        for rect in regions:
            text = ocr_best(img, rect)
            lines = parse_line_rows(text)
            curves = parse_curve_rows(text)
            if len(curves) + len(lines) > len(best_curves) + len(best_lines):
                best_curves, best_lines = curves, lines
                diag.table_region = rect
                diag.table_method = "regex_fallback"

    diag.raw_line_count = len(best_lines)
    diag.raw_curve_count = len(best_curves)
    if not best_curves and not best_lines:
        diag.warnings.append("table region(s) found but 0 rows OCR'd cleanly")
    return best_curves, best_lines, diag


def order_courses(curves: dict, lines: dict, diag: PipelineDiagnostics) -> tuple[list[Course], dict]:
    """Merge line + curve rows into one walk-ordered course list.

    HEURISTIC, not a certainty -- documented in IMPLEMENTATION_PLAN.md's
    risk list. Call tables are usually printed as separate line/curve
    tables with no positional link to an L-number; the only signal
    available without the drawing itself is each row's own numeric ID,
    assumed to increase in walk order and merged by taking whichever
    sequence's next ID is smaller. Flagged in diagnostics so this is never
    presented as read-from-the-drawing certainty.

    Rows whose ID label itself failed to OCR come back keyed '_lrowN'/
    '_rowN' (engine.ocr's own convention for "geometry is fine, the ID
    label wasn't"). Dropping those would silently throw away otherwise-good
    course data merely because one label smudged -- instead they're
    appended, in the row-discovery order engine.ocr already preserved,
    after every confidently-numbered row, with a diagnostic noting their
    position in the walk is uncertain."""
    line_items = sorted(((k, v) for k, v in lines.items() if not k.startswith("_")), key=lambda kv: _numeric_key(kv[0]))
    curve_items = sorted(((k, v) for k, v in curves.items() if not k.startswith("_")), key=lambda kv: _numeric_key(kv[0]))
    anon_lines = sorted(((k, v) for k, v in lines.items() if k.startswith("_")), key=lambda kv: _numeric_key(kv[0]))
    anon_curves = sorted(((k, v) for k, v in curves.items() if k.startswith("_")), key=lambda kv: _numeric_key(kv[0]))

    if line_items and curve_items:
        diag.ordering_is_heuristic = True
        diag.warnings.append(
            "both line and curve rows found; interleaved by numeric row ID -- "
            "a heuristic assumption, not read from the drawing"
        )
    if anon_lines or anon_curves:
        diag.ordering_is_heuristic = True
        diag.warnings.append(
            f"{len(anon_lines) + len(anon_curves)} row(s) had an unreadable ID label -- "
            "included at the end, in table order, but their position in the walk is uncertain"
        )

    courses: list[Course] = []
    curves_by_id: dict = {}

    def _emit(cid: str, rec: dict, is_curve: bool):
        if is_curve:
            curves_by_id[cid] = dict(rec)
            courses.append(Course(label=cid, curve_id=cid))
        else:
            courses.append(Course(label=cid, bearing=rec["bearing"], distance=rec["length"]))

    li = ci = 0
    while li < len(line_items) or ci < len(curve_items):
        take_line = (
            li < len(line_items) and
            (ci >= len(curve_items) or _numeric_key(line_items[li][0]) <= _numeric_key(curve_items[ci][0]))
        )
        if take_line:
            cid, rec = line_items[li]
            li += 1
            _emit(cid, rec, is_curve=False)
        else:
            cid, rec = curve_items[ci]
            ci += 1
            _emit(cid, rec, is_curve=True)

    for cid, rec in anon_lines:
        _emit(cid, rec, is_curve=False)
    for cid, rec in anon_curves:
        _emit(cid, rec, is_curve=True)

    return courses, curves_by_id


# ---------------------------------------------------------------------------
# 3-5. Traverse walk, closure, repair, verdict
# ---------------------------------------------------------------------------

def _closure(pob: Point, pts: list[Point]) -> tuple[float, float]:
    """Returns (misclosure_ft, perimeter_ft)."""
    misclose = pob.dist_to(pts[-1])
    perimeter = sum(pts[i].dist_to(pts[i + 1]) for i in range(len(pts) - 1))
    return misclose, perimeter


def _attempt_repair(pob: Point, courses: list[Course], curves: dict,
                    diag: PipelineDiagnostics) -> tuple[list[Point], dict, str | None]:
    """Try to fix curve-table OCR errors using engine.repair's existing
    inverse-solve / radius-consensus machinery. Returns
    (points, possibly-corrected curves, confidence|None)."""
    if not curves:
        return run_traverse(pob, courses, curves), curves, None

    candidates = {}
    for cid, rec in curves.items():
        cands = inverse_solve_curve(rec)
        if cands:
            candidates[cid] = cands[0]
    for cid, c in radius_consensus(curves).items():
        candidates.setdefault(cid, c)
    if not candidates:
        return run_traverse(pob, courses, curves), curves, None

    # High-confidence pass first (auto_only_high=True is apply_corrections's default).
    fixed_high, applied_high, _review = apply_corrections(curves, candidates)
    if applied_high:
        pts = run_traverse(pob, courses, fixed_high)
        misclose, _perim = _closure(pob, pts)
        if misclose <= CLOSE_TOL_FT:
            diag.repairs_applied.extend(
                f"{e['curve']}.{e['field']}: {e['read']} -> {e['solved']} ({e['why']})"
                for e in applied_high
            )
            return pts, fixed_high, "high"

    # Low-confidence (redundancy-only) pass -- only used if it actually
    # closes the traverse, and always downgrades the verdict to FLAGGED.
    fixed_all, applied_all, _review2 = apply_corrections(curves, candidates, auto_only_high=False)
    if applied_all:
        pts = run_traverse(pob, courses, fixed_all)
        misclose, _perim = _closure(pob, pts)
        if misclose <= CLOSE_TOL_FT:
            diag.repairs_applied.extend(
                f"{e['curve']}.{e['field']}: {e['read']} -> {e['solved']} "
                f"(redundancy-only, UNVERIFIED -- {e['why']})"
                for e in applied_all
            )
            return pts, fixed_all, "low"

    return run_traverse(pob, courses, curves), curves, None


def solve_generic_traverse(pob: Point, courses: list[Course], curves: dict,
                           diag: PipelineDiagnostics,
                           lot_id: str = "Boundary", block_id: str = "1",
                           lot_number: str = "B") -> LotMapCheckResult:
    """Walk `courses` from `pob`, check closure, repair if needed, and
    return a LotMapCheckResult -- the same data shape
    engine/cogo_block.py's BeachwoodBlock9Solver produces, so web/server.py
    and the frontend need no special case for a generic result.

    Deliberately does NOT reuse DeterministicLotSolver.compute_mapcheck():
    that class assumes its vertices form a ring CLOSED BY CONSTRUCTION and
    recomputes each course's bearing/distance from vertex positions, which
    is correct for Block 9 (built via known-exact COGO offsets) but wrong
    here -- an OCR'd traverse may genuinely not close, and the AS-STATED
    bearing/distance from the table must be preserved in the report even
    when the walk doesn't return exactly to the P.O.B."""
    if not courses:
        diag.warnings.append("no courses to walk -- cannot solve")
        return LotMapCheckResult(
            lot_id=lot_id, block_id=block_id, lot_number=lot_number, courses=[],
            perimeter_ft=0.0, misclose_n_ft=0.0, misclose_e_ft=0.0, misclose_dist_ft=0.0,
            precision_ratio=0.0, precision_str="N/A", raw_shoelace_sqft=0.0,
            curve_adj_sqft=0.0, computed_area_sqft=0.0, computed_acres=0.0,
            stated_area_sqft=0.0, area_diff_sqft=0.0, area_diff_pct=0.0,
            fac_5j17_passed=False, passed=False,
            verdict=f"{Verdict.FAILED} -- no courses extracted from the call table",
        )

    pts = run_traverse(pob, courses, curves)
    misclose, perimeter = _closure(pob, pts)
    repair_confidence = None

    if perimeter > 0 and misclose > CLOSE_TOL_FT and (perimeter / max(misclose, 1e-9)) < FAC_5J17_RATIO:
        pts, curves, repair_confidence = _attempt_repair(pob, courses, curves, diag)
        misclose, perimeter = _closure(pob, pts)

    tcourses: list[TraverseCourse] = []
    for i, c in enumerate(courses):
        p1, p2 = pts[i], pts[i + 1]
        is_curve = c.curve_id is not None
        if is_curve:
            crv = curves.get(c.curve_id, {})
            bearing_str = crv.get("chord_bearing") or ""
            distance = float(crv.get("length", p1.dist_to(p2)))
            curve_data = dict(crv)
        else:
            bearing_str = c.bearing or azimuth_to_bearing(
                math.degrees(math.atan2(p2.e - p1.e, p2.n - p1.n)) % 360.0)
            distance = c.distance if c.distance is not None else p1.dist_to(p2)
            curve_data = {}
        tcourses.append(TraverseCourse(
            course_num=i + 1, from_node=f"P{i + 1}", to_node=f"P{i + 2}",
            start_pt=p1, end_pt=p2, bearing_str=bearing_str, distance=distance,
            is_curve=is_curve, curve_data=curve_data,
        ))

    precision_ratio = (perimeter / misclose) if misclose > 1e-6 else float("inf")
    precision_str = "EXACT (0.000 ft)" if misclose < 1e-6 else f"1 : {int(precision_ratio):,}"
    fac_passed = precision_ratio >= FAC_5J17_RATIO
    passed = misclose <= CLOSE_TOL_FT or fac_passed

    ring_pts = pts[:-1]
    simple_ok, simple_msg = is_simple_polygon(ring_pts) if len(ring_pts) >= 3 else (False, "too few vertices")
    area = safe_area(ring_pts) if simple_ok else 0.0
    if not simple_ok and len(ring_pts) >= 3:
        diag.warnings.append(f"boundary is not a simple polygon: {simple_msg}")

    if not passed:
        tier = Verdict.FAILED
        detail = f"does not close -- {misclose:.2f} ft misclosure ({precision_str})"
    elif repair_confidence == "low":
        tier = Verdict.FLAGGED
        detail = "closed only via a redundancy-only (non-single-digit-edit) correction -- needs human review"
    elif repair_confidence == "high":
        tier = Verdict.PASS_REPAIRED
        detail = f"closed after an auto-applied high-confidence correction ({precision_str})"
    elif diag.warnings:
        tier = Verdict.WATCH
        detail = f"closes {precision_str}, but see diagnostics/warnings"
    else:
        tier = Verdict.PASS
        detail = f"closes {precision_str}"

    return LotMapCheckResult(
        lot_id=lot_id, block_id=block_id, lot_number=lot_number,
        courses=tcourses,
        perimeter_ft=perimeter,
        misclose_n_ft=pts[-1].n - pob.n,
        misclose_e_ft=pts[-1].e - pob.e,
        misclose_dist_ft=misclose,
        precision_ratio=precision_ratio,
        precision_str=precision_str,
        raw_shoelace_sqft=area,
        curve_adj_sqft=0.0,
        computed_area_sqft=area,
        computed_acres=area / 43560.0,
        stated_area_sqft=0.0,
        area_diff_sqft=0.0,
        area_diff_pct=0.0,
        fac_5j17_passed=fac_passed,
        passed=passed,
        verdict=f"{tier} -- {detail}",
    )


# ---------------------------------------------------------------------------
# 6. Phase 2: vectorization as a coarse, best-effort sanity check
# ---------------------------------------------------------------------------
#
# NOT a precise per-course cross-check against the drawn linework
# (engine.blunder.report can do that, but it needs the raster and the COGO
# traverse in the SAME coordinate system, i.e. registered -- and the only
# registration tool available, engine.vectorize.iterative_align_raster_to_cogo,
# requires already-known corresponding point PAIRS between the two, which
# does not exist for an arbitrary freshly-uploaded plat with no manual tie
# points). Solving automatic registration without tie points is a
# substantially harder problem than call-table OCR and is out of scope here
# (see IMPLEMENTATION_PLAN.md). What IS delivered: does this sheet actually
# contain plausible plat linework at all, as a sanity signal.

def vectorize_diagnostics(img, diag: PipelineDiagnostics) -> None:
    try:
        from engine.vectorize import vectorize_plat_sheet
        result = vectorize_plat_sheet(img)
        diag.vectorize_ok = result["num_segments"] > 0 or result["num_polylines"] > 0
        diag.vectorize_summary = (
            f"{result['num_polylines']} polylines, {result['num_segments']} segments, "
            f"~{result['total_linework_feet']:.0f} ft of linework at an assumed scale "
            f"(not registered to the solved traverse -- informational only)"
        )
    except Exception as e:  # vectorization is diagnostic-only; never fail the solve over it
        diag.warnings.append(f"vectorization cross-check skipped: {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# 7. Phase 3: opt-in uniform lot-row subdivision
# ---------------------------------------------------------------------------

def subdivide_uniform_lot_row(boundary: LotMapCheckResult, lot_count: int,
                              diag: PipelineDiagnostics) -> list[LotMapCheckResult]:
    """Split the solved boundary into `lot_count` equal-width rectangular
    lots along its longest straight course, assumed to be the frontage.

    Pure COGO math on the already-solved traverse -- no raster/pixel work,
    unlike engine.blocks.build_block's junction-scan approach (which needs
    per-block pixel coordinates this pipeline has no way to determine
    automatically; see the Phase 2 note above on why raster registration
    isn't attempted). This is therefore a UNIFORM-WIDTH approximation, not
    a read of each lot's actual individually-stated width -- flagged in
    every derived lot's verdict, never presented as a certified reading."""
    straight = [c for c in boundary.courses if not c.is_curve]
    if not straight or lot_count < 1:
        diag.warnings.append("lot subdivision skipped: no straight course to use as frontage")
        return []

    front = max(straight, key=lambda c: c.distance)
    front_idx = front.course_num - 1
    side = boundary.courses[(front_idx + 1) % len(boundary.courses)]
    if side.is_curve:
        diag.warnings.append("lot subdivision skipped: course after the assumed frontage is a curve")
        return []
    if not check_orthogonal(front.bearing_str, side.bearing_str):
        diag.warnings.append(
            f"lot subdivision skipped: frontage ({front.bearing_str}) and next course "
            f"({side.bearing_str}) are not ~90 deg apart -- not a simple rectangular row"
        )
        return []

    width = front.distance / lot_count
    depth = side.distance
    numbers = [str(i + 1) for i in range(lot_count)]
    lots: list[Lot] = rect_row(front.start_pt, front.bearing_str, side.bearing_str,
                               [width] * lot_count, depth, numbers)

    results = []
    for lot in lots:
        v = verify_ring(lot.number, lot.corners)
        tcourses = []
        pts = lot.corners
        n = len(pts)
        for i in range(n):
            p1, p2 = pts[i], pts[(i + 1) % n]
            az = math.degrees(math.atan2(p2.e - p1.e, p2.n - p1.n)) % 360.0
            tcourses.append(TraverseCourse(
                course_num=i + 1, from_node=f"{lot.number}-{i + 1}", to_node=f"{lot.number}-{(i + 1) % n + 1}",
                start_pt=p1, end_pt=p2, bearing_str=azimuth_to_bearing(az), distance=p1.dist_to(p2),
            ))
        detail = "uniform-width estimate (frontage / lot count) -- not an individually stated width"
        tier = Verdict.WATCH if v.passed else Verdict.FAILED
        results.append(LotMapCheckResult(
            lot_id=f"Lot-{lot.number}", block_id="1", lot_number=lot.number,
            courses=tcourses, perimeter_ft=v.perimeter, misclose_n_ft=0.0, misclose_e_ft=0.0,
            misclose_dist_ft=v.misclosure,
            precision_ratio=(v.perimeter / v.misclosure) if v.misclosure > 1e-6 else float("inf"),
            precision_str="EXACT (0.000 ft)" if v.misclosure < 1e-6 else f"1 : {int(v.perimeter / max(v.misclosure, 1e-9)):,}",
            raw_shoelace_sqft=lot.area_sqft, curve_adj_sqft=0.0,
            computed_area_sqft=lot.area_sqft, computed_acres=lot.area_sqft / 43560.0,
            stated_area_sqft=0.0, area_diff_sqft=0.0, area_diff_pct=0.0,
            fac_5j17_passed=v.passed, passed=v.passed,
            verdict=f"{tier} -- {detail}",
        ))
    return results


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

@dataclass
class PlatSolveResult:
    boundary: LotMapCheckResult
    lots: list[LotMapCheckResult]
    diagnostics: PipelineDiagnostics


def solve_uploaded_plat(plat_image_path: str, call_table_image_path: str | None,
                        pob: Point, lot_count: int | None = None) -> PlatSolveResult:
    """Main entry point -- see module docstring for the full pipeline."""
    diag = PipelineDiagnostics()

    plat_img = load_plat_image(plat_image_path)
    table_img = load_plat_image(call_table_image_path) if call_table_image_path else plat_img

    curves, lines, table_diag = extract_call_table(table_img)
    diag.table_method = table_diag.table_method
    diag.table_region = table_diag.table_region
    diag.raw_line_count = table_diag.raw_line_count
    diag.raw_curve_count = table_diag.raw_curve_count
    diag.warnings.extend(table_diag.warnings)

    courses, curves_by_id = order_courses(curves, lines, diag)
    boundary = solve_generic_traverse(pob, courses, curves_by_id, diag)

    vectorize_diagnostics(plat_img, diag)

    lots: list[LotMapCheckResult] = []
    if lot_count and boundary.courses:
        lots = subdivide_uniform_lot_row(boundary, lot_count, diag)

    return PlatSolveResult(boundary=boundary, lots=lots, diagnostics=diag)
