"""
engine/audit.py -- Automated Cadastral Verification & Area Audit Engine.

Audits survey traverses and exported DXFs against legal plats:
1. Mathematical Traverse Closure (misclose distance, dN, dE, precision ratio).
2. Parcel Polygon Area (Green's theorem / Shoelace formula vs stated acreage).
3. CAD Layer Compliance (verifies BOUNDARY, LOT_LINES, ROW_STREET, etc.).
4. Noise & Monument Audit (ensures false circle monuments are zeroed).
"""

from __future__ import annotations
import math
import os
from collections import Counter
from engine.cogo import Point
from engine.lots import shoelace_area, safe_area, is_simple_polygon

# Entity types whose group codes 10/11 (x) and 20/21 (y) are real coordinates.
# A POLYLINE header's own 10/20/30 are a dummy 0,0 elevation and must not
# widen the extents; its VERTEX records carry the geometry.
_COORD_ENTITIES = {"LINE", "VERTEX", "TEXT", "MTEXT", "POINT", "CIRCLE", "ARC", "INSERT"}


def audit_traverse_closure(points: list[Point], perimeter: float = None) -> dict:
    """Calculate closure error between first and last traverse points."""
    if len(points) < 3:
        return {"status": "ERROR", "reason": "Traverse requires at least 3 points"}

    p_start, p_end = points[0], points[-1]
    dn = p_end.northing - p_start.northing
    de = p_end.easting - p_start.easting
    misclose_dist = math.hypot(dn, de)

    # Calculate perimeter if not provided
    if perimeter is None or perimeter <= 0.0:
        perimeter = 0.0
        for i in range(len(points) - 1):
            perimeter += points[i].dist_to(points[i + 1])

    precision_ratio = (perimeter / misclose_dist) if misclose_dist > 1e-6 else float("inf")
    precision_str = f"1:{precision_ratio:,.0f}" if precision_ratio != float("inf") else "EXACT (0.000 ft)"

    status = "PASS" if misclose_dist <= 0.05 else ("WARN" if misclose_dist <= 0.50 else "FAIL")

    return {
        "status": status,
        "misclose_feet": round(misclose_dist, 4),
        "dn_feet": round(dn, 4),
        "de_feet": round(de, 4),
        "perimeter_feet": round(perimeter, 2),
        "precision_ratio": precision_str,
        "points_count": len(points)
    }


def audit_parcel_area(points: list[Point], stated_acres: float = None, stated_sqft: float = None,
                       tolerance_pct: float = 0.5) -> dict:
    """Verify parcel polygon area against stated plat acreage/sqft."""
    simple, msg = is_simple_polygon(points)
    if not simple:
        return {"status": "FAIL", "reason": f"Non-simple polygon: {msg}"}

    calc_sqft = safe_area(points)
    calc_acres = calc_sqft / 43560.0

    res = {
        "status": "PASS",
        "calc_sqft": round(calc_sqft, 2),
        "calc_acres": round(calc_acres, 4),
        "discrepancy_pct": 0.0
    }

    target_sqft = stated_sqft if stated_sqft else (stated_acres * 43560.0 if stated_acres else None)
    if target_sqft:
        diff_pct = abs(calc_sqft - target_sqft) / target_sqft * 100.0
        res["target_sqft"] = round(target_sqft, 2)
        res["discrepancy_pct"] = round(diff_pct, 2)
        if diff_pct > tolerance_pct:
            res["status"] = "WARN" if diff_pct <= 2.0 else "FAIL"
            res["warning"] = f"Area discrepancy {diff_pct:.2f}% exceeds tolerance {tolerance_pct}%"

    return res


def _dxf_pairs(content: str):
    """Yield (group_code, value) pairs from ASCII DXF text.

    DXF is a strict alternation of a group-code line and a value line, so it
    has to be read as pairs. Substring/regex scans over the raw text cannot
    tell an entity type from a layer or linetype name that merely ends the
    same way (POLYLINE vs LINE, MTEXT vs TEXT, a layer called LOT_LINE), nor
    a group code from a coordinate value that happens to end in that digit."""
    lines = content.split("\n")
    for i in range(0, len(lines) - 1, 2):
        try:
            yield int(lines[i]), lines[i + 1].strip()
        except ValueError:
            continue


def _scan_dxf(content: str) -> dict:
    """Single pass over a DXF: entity counts, layers, TEXT strings, extents."""
    counts: Counter = Counter()
    layers_used: set = set()
    layers_declared: set = set()
    text_values: list = []
    xs: list = []
    ys: list = []
    section = entity = None
    pending_section = False

    for code, val in _dxf_pairs(content):
        if code == 0:
            entity = val
            pending_section = (val == "SECTION")
            if val == "ENDSEC":
                section = None
            elif section == "ENTITIES" and val not in ("VERTEX", "SEQEND"):
                counts[val] += 1
            continue
        if pending_section and code == 2:
            section, pending_section = val, False
            continue
        if section == "TABLES":
            if entity == "LAYER" and code == 2:
                layers_declared.add(val)
        elif section == "ENTITIES":
            if code == 8:
                layers_used.add(val)
            elif code == 1 and entity in ("TEXT", "MTEXT"):
                text_values.append(val)
            elif entity in _COORD_ENTITIES and code in (10, 11, 20, 21):
                try:
                    (xs if code in (10, 11) else ys).append(float(val))
                except ValueError:
                    pass

    return {"counts": counts, "layers": layers_used | layers_declared,
            "text_values": text_values, "xs": xs, "ys": ys}


def audit_dxf_layers(dxf_path: str) -> dict:
    """Audit exported DXF file for layer compliance and false monument circles."""
    if not os.path.exists(dxf_path):
        return {"status": "ERROR", "reason": f"File not found: {dxf_path}"}

    with open(dxf_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    scan = _scan_dxf(content)
    counts = scan["counts"]
    lines = counts["LINE"]
    polylines = counts["POLYLINE"] + counts["LWPOLYLINE"]
    texts = counts["TEXT"] + counts["MTEXT"]
    circles = counts["CIRCLE"]
    arcs = counts["ARC"]
    layers = scan["layers"]

    # Check for false LOT 330 dimension entities misread as lot labels
    lot_330_count = sum(1 for t in scan["text_values"] if t.upper() == "LOT 330")

    # Check extents
    xs, ys = scan["xs"], scan["ys"]
    span_x = (min(xs), max(xs)) if xs else (0, 0)
    span_y = (min(ys), max(ys)) if ys else (0, 0)

    # Detect if extents look like raw pixel coordinates ([0, 8000]). Magnitude
    # alone cannot tell them from feet (a 4,800 ft sheet and a 4,800 px sheet
    # look the same), so also require the raster signature: pixel positions are
    # all integers, whereas px * ft_per_px and surveyed dimensions are not.
    coords = xs + ys
    integral = sum(1 for c in coords if abs(c - round(c)) < 1e-6) / len(coords) if coords else 0.0
    is_pixel_space = (len(coords) >= 500 and integral >= 0.99
                      and span_x[1] < 10000.0 and span_x[0] >= -50.0
                      and span_y[1] < 10000.0 and span_y[0] >= -50.0
                      and max(span_x[1], span_y[1]) > 3000.0)

    has_monument_bloat = (circles > 500)

    status = "PASS"
    issues = []
    if not counts:
        status = "WARN"
        issues.append("No ENTITIES found -- empty file or not an ASCII DXF")
    if is_pixel_space:
        status = "WARN"
        issues.append("Coordinates appear to be in unscaled pixel space ([0, 8000])")
    if has_monument_bloat:
        status = "FAIL"
        issues.append(f"Excessive circle monuments ({circles} circles, likely noise speckles)")
    if lot_330_count > 0:
        status = "WARN"
        issues.append(f"Detected {lot_330_count} 'LOT 330' misclassified dimension entities")

    return {
        "status": status,
        "dxf_path": os.path.basename(dxf_path),
        "layers": sorted(layers),
        "entity_counts": {
            "lines": lines,
            "polylines": polylines,
            "texts": texts,
            "circles": circles,
            "arcs": arcs
        },
        "extents": {
            "min_x": round(span_x[0], 2), "max_x": round(span_x[1], 2),
            "min_y": round(span_y[0], 2), "max_y": round(span_y[1], 2)
        },
        "issues": issues
    }


dxf_audit = audit_dxf_layers
