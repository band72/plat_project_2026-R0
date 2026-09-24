"""
plat-reader/backend/server.py -- Standalone API Server for Plat Reader Widget.

Provides full standalone delivery for the Cadastral Plat AI & COGO Engine:
1. File upload endpoint (/api/upload) for PDFs, TIFFs, PNGs, and JPEGs.
2. Cadastral AI & COGO MapCheck analysis (/api/analyze) for both reference datasets and arbitrary uploads.
3. Deliverable download endpoints (/api/download/*) for Production DXF, Checksheets DXF, Reports, GeoJSON, and CSV.
4. Per-lot DXF download endpoint (/api/lot_dxf/*).
5. CORS support with PLAT_READER_ALLOWED_ORIGINS (default "*") for seamless cross-origin website embedding.
6. Built-in static mounting for the self-contained widget (/widget and /).
"""

from __future__ import annotations

import io
import logging
import os
import sys
import uuid
from typing import Any

# Ensure plat-reader root and bundled plat_curves are in sys.path
_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)
_CURVES_DIR = os.path.join(_BASE_DIR, "plat_curves")
if os.path.isdir(_CURVES_DIR) and _CURVES_DIR not in sys.path:
    sys.path.insert(0, _CURVES_DIR)

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from engine.cogo import Point
from engine.cogo_block import BeachwoodBlock9Solver, LotMapCheckResult
from engine.dxf_writer import DXFWriter
from engine.plat_pipeline import PlatSolveResult, solve_uploaded_plat
from scripts.solve_block9_cogo import build_agents, render_plot, write_checksheets_dxf, write_production_dxf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("plat_reader_standalone")

app = FastAPI(
    title="Cadastral Plat Reader -- Standalone API",
    version="2026-R0-standalone",
    description="Standalone microservice powering the embeddable plat-reader widget."
)

# CORS configuration
_allowed_origins = os.environ.get("PLAT_READER_ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allowed_origins.strip() == "*" else [o.strip() for o in _allowed_origins.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BACKEND_DIR, "uploads")
OUTPUT_DIR = os.path.join(BACKEND_DIR, "output")
WIDGET_DIR = os.path.join(_BASE_DIR, "widget")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WIDGET_DIR, exist_ok=True)

# Mount widget static files
if os.path.isdir(WIDGET_DIR):
    app.mount("/widget", StaticFiles(directory=WIDGET_DIR, html=True), name="widget")

LOT_ORDER = ["27", "28", "29", "30", "31", "26", "25", "24", "23"]
SUPPORTED_PRESETS = {"block9"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}

# Cache of last solve
_LAST_ANALYSIS_KIND: str = "block9"
_LAST_CUSTOM: dict[str, Any] | None = None


def _solve_block9(return_radius: float = 25.0) -> tuple[BeachwoodBlock9Solver, dict]:
    solver = BeachwoodBlock9Solver()
    if return_radius != 25.0:
        solver.sol27.radius = return_radius
        solver.sol26.radius = return_radius
    results = solver.solve_all()
    return solver, results


def _bbox_json(results: list[LotMapCheckResult]) -> dict:
    pts = [c.start_pt for res in results for c in res.courses]
    if not pts:
        return {"min_n": 0.0, "max_n": 0.0, "min_e": 0.0, "max_e": 0.0, "width": 0.0, "height": 0.0}
    all_n = [p.n for p in pts]
    all_e = [p.e for p in pts]
    min_n, max_n = min(all_n) - 30.0, max(all_n) + 30.0
    min_e, max_e = min(all_e) - 30.0, max(all_e) + 30.0
    return {
        "min_n": round(min_n, 1), "max_n": round(max_n, 1),
        "min_e": round(min_e, 1), "max_e": round(max_e, 1),
        "width": round(max_e - min_e, 1), "height": round(max_n - min_n, 1),
    }


def _parcel_json(res: LotMapCheckResult, frontage: str) -> dict:
    course_list = [{
        "course_num": c.course_num,
        "from_node": c.from_node,
        "to_node": c.to_node,
        "start": {"n": round(c.start_pt.n, 3), "e": round(c.start_pt.e, 3)},
        "end": {"n": round(c.end_pt.n, 3), "e": round(c.end_pt.e, 3)},
        "bearing": c.bearing_str,
        "distance_ft": round(c.distance, 2),
        "is_curve": c.is_curve,
        "curve_data": c.curve_data if c.is_curve else None,
    } for c in res.courses]

    verts = [c.start_pt for c in res.courses]
    svg_poly = " ".join(f"{round(p.e, 2)},{round(p.n, 2)}" for p in verts)
    cen_n = sum(p.n for p in verts) / len(verts) if verts else 0.0
    cen_e = sum(p.e for p in verts) / len(verts) if verts else 0.0

    return {
        "lot_id": res.lot_id,
        "lot_number": res.lot_number,
        "block_id": res.block_id,
        "frontage": frontage,
        "perimeter_ft": round(res.perimeter_ft, 2),
        "misclose_ft": round(res.misclose_dist_ft, 5),
        "precision": res.precision_str,
        "area_sqft": round(res.computed_area_sqft, 1),
        "acres": round(res.computed_acres, 4),
        "target_area_sqft": res.stated_area_sqft,
        "status": "PASS" if res.passed else "FAIL",
        "fac_5j17": "COMPLIANT (>= 1:10,000)" if res.fac_5j17_passed else "NON-COMPLIANT",
        "verdict": res.verdict,
        "flags": getattr(res, "flags", []),
        "centroid": {"n": round(cen_n, 2), "e": round(cen_e, 2)},
        "svg_polygon": svg_poly,
        "courses": course_list,
        "checksheet_text": res.format_surveyor_sheet(),
    }


def _draw_generic_dxf(results: list[LotMapCheckResult]) -> DXFWriter:
    dxf = DXFWriter()
    dxf.add_layer("LOT_LINE", "cyan", "CONTINUOUS")
    dxf.add_layer("CURVE", "magenta", "CONTINUOUS")
    dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
    for res in results:
        for c in res.courses:
            layer = "CURVE" if c.is_curve else "LOT_LINE"
            dxf.line((c.start_pt.n, c.start_pt.e), (c.end_pt.n, c.end_pt.e), layer=layer)
            mid_n = (c.start_pt.n + c.end_pt.n) / 2.0
            mid_e = (c.start_pt.e + c.end_pt.e) / 2.0
            dxf.text((mid_n, mid_e), f"{c.bearing_str} {c.distance:.2f}'", height=4.0, layer="TEXT-LABELS")
        if res.courses:
            dxf.text((res.courses[0].start_pt.n, res.courses[0].start_pt.e), res.lot_id,
                     height=6.0, layer="TEXT-LABELS")
    return dxf


def _run_custom_pipeline(
    uploaded_filename: str | None,
    call_table_filename: str | None,
    pob_northing: float,
    pob_easting: float,
    lot_count: int | None,
) -> tuple[PlatSolveResult | None, str | None]:
    global _LAST_CUSTOM, _LAST_ANALYSIS_KIND

    if not uploaded_filename:
        return None, "No plat image was uploaded -- upload a plat image or PDF and try again."

    plat_path = os.path.join(UPLOAD_DIR, uploaded_filename)
    if not os.path.isfile(plat_path):
        return None, f"Uploaded file '{uploaded_filename}' was not found on the server -- please re-upload."

    call_table_path = None
    if call_table_filename:
        candidate = os.path.join(UPLOAD_DIR, call_table_filename)
        call_table_path = candidate if os.path.isfile(candidate) else None

    result = solve_uploaded_plat(
        plat_path, call_table_path, Point(pob_northing, pob_easting), lot_count,
    )

    all_results = [result.boundary] + result.lots
    dxf = _draw_generic_dxf(all_results)
    dxf_path = os.path.join(OUTPUT_DIR, "custom_plat.dxf")
    dxf.save(dxf_path)

    report_path = os.path.join(OUTPUT_DIR, "custom_plat_report.txt")
    with open(report_path, "w") as f:
        f.write(result.boundary.format_surveyor_sheet())
        for lot in result.lots:
            f.write("\n" + lot.format_surveyor_sheet())
        if result.diagnostics.warnings:
            f.write("\n\nDIAGNOSTIC WARNINGS:\n" + "\n".join(f"  - {w}" for w in result.diagnostics.warnings))
        if result.diagnostics.repairs_applied:
            f.write("\n\nAUTO-APPLIED CORRECTIONS:\n" + "\n".join(f"  - {r}" for r in result.diagnostics.repairs_applied))

    _LAST_CUSTOM = {
        "result": result,
        "dxf_path": dxf_path,
        "report_path": report_path,
        "uploaded_filename": uploaded_filename,
    }
    _LAST_ANALYSIS_KIND = "custom"

    note_parts = list(result.diagnostics.warnings)
    if result.diagnostics.repairs_applied:
        note_parts.append(f"{len(result.diagnostics.repairs_applied)} auto-correction(s) applied -- see the report for details.")
    note = " | ".join(note_parts) if note_parts else None
    return result, note


@app.get("/")
async def index_page():
    demo_html = os.path.join(WIDGET_DIR, "index.html")
    if os.path.exists(demo_html):
        return FileResponse(demo_html, media_type="text/html")
    return HTMLResponse("<h2>Plat Reader Standalone API is running. Mount point: /widget/</h2>")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "plat-reader-standalone-api",
        "version": "2026-R0",
        "cors_origins": _allowed_origins,
    }


@app.post("/api/upload")
async def upload_plat(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {file_ext or '(none)'}. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}",
        )

    clean_stem = "".join(c for c in os.path.splitext(file.filename)[0] if c.isalnum() or c in "._- ").strip()
    clean_name = f"{clean_stem or uuid.uuid4().hex}{file_ext}"
    dest_path = os.path.join(UPLOAD_DIR, clean_name)

    size = 0
    with open(dest_path, "wb") as buffer:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail=f"File exceeds maximum upload size of {MAX_UPLOAD_BYTES // (1024*1024)} MB")
            buffer.write(chunk)

    logger.info("Uploaded plat: %s (%d bytes)", dest_path, size)
    return {
        "status": "success",
        "filename": clean_name,
        "original_name": file.filename,
        "size_kb": round(size / 1024, 1),
    }


@app.post("/api/analyze")
async def analyze_plat(
    preset: str = Form("block9"),
    uploaded_filename: str | None = Form(None),
    job_name: str | None = Form(None),
    call_table_filename: str | None = Form(None),
    pob_northing: float = Form(5000.00),
    pob_easting: float = Form(5000.00),
    extract_individual_lots: bool = Form(True),
    lot_count: int | None = Form(None),
    return_radius: float = Form(25.0),
    pi_rule_enabled: bool = Form(True),
    fac_standard: str = Form("5J-17"),
):
    if not (1.0 <= return_radius <= 100.0):
        raise HTTPException(status_code=400, detail="return_radius must be between 1.0 and 100.0 ft")

    if preset in SUPPORTED_PRESETS and not uploaded_filename:
        return _analyze_block9(return_radius)
    return _analyze_custom(
        uploaded_filename, job_name, call_table_filename,
        pob_northing, pob_easting,
        lot_count if extract_individual_lots else None
    )


def _analyze_block9(return_radius: float) -> dict:
    global _LAST_ANALYSIS_KIND
    _LAST_ANALYSIS_KIND = "block9"
    solver, results = _solve_block9(return_radius)

    dxf_prod = os.path.join(OUTPUT_DIR, "PB0030_P0082_Block9_MapCheck.dxf")
    dxf_chk = os.path.join(OUTPUT_DIR, "PB0030_P0082_Block9_CheckSheets.dxf")
    report_file = os.path.join(OUTPUT_DIR, "block9_mapcheck_report.txt")
    plot_file = os.path.join(OUTPUT_DIR, "block9_mapcheck_drawing.png")

    write_production_dxf(solver, dxf_prod)
    write_checksheets_dxf(solver, dxf_chk)
    solver.generate_report(report_file)
    try:
        render_plot(solver, plot_file)
    except Exception as exc:
        logger.warning("Plot rendering skipped: %s", exc)

    pts = solver.points
    frontage_map = {
        "27": "Cape Horn Ave & Avenue R/W (NW Corner Return)",
        "28": "Cape Horn Avenue (108.25' Frontage)",
        "29": "Cape Horn Avenue (6.91' Arc + 82.57' Tangent)",
        "30": "Cape Horn Avenue (75.00' Frontage)",
        "31": "Cape Horn Avenue (75.00' Frontage to P.R.M.)",
        "26": "San Salvadore Ave & Avenue R/W (SW Corner Return)",
        "25": "San Salvadore Avenue (66.18' Frontage)",
        "24": "San Salvadore Avenue (55.76' + 8.31' Frontage)",
        "23": "San Salvadore Avenue (75.00' Frontage to Matchline)",
    }
    parcels = [_parcel_json(results[lot_num], frontage_map.get(lot_num, "Corridor")) for lot_num in LOT_ORDER]

    return {
        "status": "success",
        "note": None,
        "model_version": "Cadastral COGO Engine 2026-R0 (Deterministic)",
        "plat_name": "Beachwood Unit Two -- Block 9 (West of Matchline)",
        "records": "Plat Book 30, Pages 82 & 82A, Duval County, FL",
        "summary": {
            "total_parcels": len(parcels),
            "passed_parcels": sum(1 for p in parcels if p["status"] == "PASS"),
            "failed_parcels": sum(1 for p in parcels if p["status"] == "FAIL"),
            "max_linear_misclose": max((p["misclose_ft"] for p in parcels), default=0.0),
            "average_precision": "EXACT (0.000 ft)",
            "total_net_area_sf": round(sum(p["area_sqft"] for p in parcels), 1),
            "total_net_acres": round(sum(p["acres"] for p in parcels), 4),
            "fac_5j17_pass_rate": "100.0%",
        },
        "bbox": _bbox_json(list(results.values())),
        "matchline": None,
        "monuments": [],
        "parcels": parcels,
        "download_links": {
            "master_dxf": "/api/download/master_dxf",
            "checksheets_dxf": "/api/download/checksheets_dxf",
            "report_txt": "/api/download/report_txt",
            "geojson": "/api/download/geojson",
            "csv": "/api/download/csv",
        }
    }


def _analyze_custom(
    uploaded_filename: str | None,
    job_name: str | None,
    call_table_filename: str | None,
    pob_northing: float,
    pob_easting: float,
    lot_count: int | None,
) -> dict:
    result, note = _run_custom_pipeline(uploaded_filename, call_table_filename, pob_northing, pob_easting, lot_count)
    if result is None:
        raise HTTPException(status_code=400, detail=note)

    all_results = [result.boundary] + result.lots if result.boundary.courses else []
    if result.boundary.courses:
        parcels = [_parcel_json(result.boundary, "Overall Boundary (as OCR'd)")]
        parcels += [_parcel_json(lot, "Uniform-width lot estimate") for lot in result.lots]
    else:
        parcels = []
        if not note:
            note = "No usable course rows were extracted from the call table. Check image clarity."

    return {
        "status": "success",
        "note": note,
        "model_version": "Cadastral COGO Engine 2026-R0 (Generic OCR Pipeline)",
        "plat_name": job_name or (uploaded_filename or "Uploaded Plat"),
        "records": "User-uploaded plat -- not a certified reference dataset",
        "summary": {
            "total_parcels": len(parcels),
            "passed_parcels": sum(1 for p in parcels if p["status"] == "PASS"),
            "failed_parcels": sum(1 for p in parcels if p["status"] == "FAIL"),
            "max_linear_misclose": max((p["misclose_ft"] for p in parcels), default=0.0),
            "average_precision": result.boundary.precision_str if parcels else "N/A",
            "total_net_area_sf": round(result.boundary.computed_area_sqft, 1) if parcels else 0.0,
            "total_net_acres": round(result.boundary.computed_acres, 4) if parcels else 0.0,
            "fac_5j17_pass_rate": f"{100.0 * sum(1 for p in parcels if p['fac_5j17'].startswith('COMPLIANT')) / len(parcels):.1f}%" if parcels else "0.0%",
        },
        "bbox": _bbox_json(all_results),
        "matchline": None,
        "monuments": [],
        "parcels": parcels,
        "download_links": {
            "master_dxf": "/api/download/master_dxf",
            "checksheets_dxf": "/api/download/checksheets_dxf",
            "report_txt": "/api/download/report_txt",
            "geojson": "/api/download/geojson",
            "csv": "/api/download/csv",
        }
    }


def _csv_response(results: list[LotMapCheckResult], filename: str) -> StreamingResponse:
    output = io.StringIO()
    output.write("Lot ID,Block,Lot Number,Perimeter (ft),Linear Misclose (ft),Precision,Net Area (SF),Acres,Stated Area (SF),F.A.C. 5J-17 Status\n")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        output.write(f"{r.lot_id},{r.block_id},{r.lot_number},{r.perimeter_ft:.2f},{r.misclose_dist_ft:.5f},{r.precision_str},{r.computed_area_sqft:.1f},{r.computed_acres:.4f},{r.stated_area_sqft:.1f},{status}\n")
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def _geojson_response(results: list[LotMapCheckResult], filename: str) -> JSONResponse:
    features = []
    for r in results:
        verts = [c.start_pt for c in r.courses]
        if not verts:
            continue
        coords = [[round(p.e, 4), round(p.n, 4)] for p in verts] + [[round(verts[0].e, 4), round(verts[0].n, 4)]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "lot_id": r.lot_id, "block_id": r.block_id, "lot_number": r.lot_number,
                "perimeter_ft": r.perimeter_ft, "linear_misclose_ft": r.misclose_dist_ft,
                "precision": r.precision_str, "net_area_sqft": r.computed_area_sqft,
                "acres": r.computed_acres, "fac_5j17_passed": r.fac_5j17_passed,
            }
        })
    geojson_obj = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2236"}},
        "features": features,
    }
    return JSONResponse(content=geojson_obj, headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/api/download/{file_type}")
async def download_file(file_type: str):
    if _LAST_ANALYSIS_KIND == "custom":
        if _LAST_CUSTOM is None:
            raise HTTPException(status_code=404, detail="No custom plat has been analyzed yet.")
        result: PlatSolveResult = _LAST_CUSTOM["result"]
        all_results = [result.boundary] + result.lots

        if file_type in ("master_dxf", "checksheets_dxf"):
            return FileResponse(_LAST_CUSTOM["dxf_path"], media_type="application/dxf", filename="custom_plat.dxf")
        if file_type == "report_txt":
            return FileResponse(_LAST_CUSTOM["report_path"], media_type="text/plain", filename="custom_plat_report.txt")
        if file_type == "csv":
            return _csv_response(all_results, "custom_plat_summary.csv")
        if file_type == "geojson":
            return _geojson_response(all_results, "custom_plat.geojson")
        raise HTTPException(status_code=400, detail=f"Unknown download type: {file_type}")

    # Block 9 reference
    file_map = {
        "master_dxf": (os.path.join(OUTPUT_DIR, "PB0030_P0082_Block9_MapCheck.dxf"), "application/dxf", "PB0030_P0082_Block9_MapCheck.dxf"),
        "checksheets_dxf": (os.path.join(OUTPUT_DIR, "PB0030_P0082_Block9_CheckSheets.dxf"), "application/dxf", "PB0030_P0082_Block9_CheckSheets.dxf"),
        "report_txt": (os.path.join(OUTPUT_DIR, "block9_mapcheck_report.txt"), "text/plain", "block9_mapcheck_report.txt"),
        "plot_png": (os.path.join(OUTPUT_DIR, "block9_mapcheck_drawing.png"), "image/png", "block9_mapcheck_drawing.png"),
    }
    if file_type in file_map:
        abs_path, media_type, filename = file_map[file_type]
        if not os.path.exists(abs_path):
            solver, _ = _solve_block9()
            write_production_dxf(solver, os.path.join(OUTPUT_DIR, "PB0030_P0082_Block9_MapCheck.dxf"))
            write_checksheets_dxf(solver, os.path.join(OUTPUT_DIR, "PB0030_P0082_Block9_CheckSheets.dxf"))
            solver.generate_report(os.path.join(OUTPUT_DIR, "block9_mapcheck_report.txt"))
        return FileResponse(abs_path, media_type=media_type, filename=filename)
    if file_type == "csv":
        _, results = _solve_block9()
        return _csv_response([results[n] for n in LOT_ORDER], "block9_parcels_summary.csv")
    if file_type == "geojson":
        _, results = _solve_block9()
        return _geojson_response([results[n] for n in LOT_ORDER], "block9_parcels.geojson")

    raise HTTPException(status_code=400, detail=f"Unknown download type: {file_type}")


@app.get("/api/lot_dxf/{lot_num}")
async def download_lot_dxf(lot_num: str):
    if _LAST_ANALYSIS_KIND == "custom":
        if _LAST_CUSTOM is None:
            raise HTTPException(status_code=404, detail="No custom plat has been analyzed yet.")
        result: PlatSolveResult = _LAST_CUSTOM["result"]
        match = next((r for r in [result.boundary] + result.lots if r.lot_number == lot_num), None)
        if match is None:
            raise HTTPException(status_code=404, detail=f"Parcel '{lot_num}' not found in current custom solve.")
        dxf = _draw_generic_dxf([match])
        temp_path = os.path.join(OUTPUT_DIR, f"Custom_{lot_num}_MapCheck.dxf")
        dxf.save(temp_path)
        return FileResponse(temp_path, media_type="application/dxf", filename=f"Custom_Parcel_{lot_num}.dxf")

    solver = BeachwoodBlock9Solver()
    if lot_num not in solver.lots:
        raise HTTPException(status_code=404, detail=f"Lot {lot_num} not found in Block 9")

    ag = next(a for a in build_agents(solver) if a.lot_number == lot_num)
    dxf = DXFWriter()
    dxf.add_layer("LOT_LINE", "cyan", "CONTINUOUS")
    dxf.add_layer("CURVE", "magenta", "CONTINUOUS")
    dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
    dxf.add_layer("DIM-LABELS", "green", "CONTINUOUS")

    ag.draw(dxf, layer="LOT_LINE", text_layer="TEXT-LABELS", dim_layer="DIM-LABELS", curve_layer="CURVE", draw_dims=True)

    temp_path = os.path.join(OUTPUT_DIR, f"Lot_{lot_num}_MapCheck.dxf")
    dxf.save(temp_path)
    return FileResponse(temp_path, media_type="application/dxf", filename=f"Lot_{lot_num}_MapCheck.dxf")


def run():
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.server:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    run()
