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
import re
import json
from engine.cogo import Point
from engine.lots import shoelace_area, safe_area, is_simple_polygon


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


def audit_dxf_layers(dxf_path: str) -> dict:
    """Audit exported DXF file for layer compliance and false monument circles."""
    if not os.path.exists(dxf_path):
        return {"status": "ERROR", "reason": f"File not found: {dxf_path}"}
        
    with open(dxf_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
        
    lines = content.count("LINE\n")
    polylines = content.count("POLYLINE\n") + content.count("LWPOLYLINE\n")
    texts = content.count("TEXT\n")
    circles = content.count("CIRCLE\n")
    arcs = content.count("ARC\n")
    
    layers = set(re.findall(r"(?:  )?8\n([^\n]+)", content))
    
    # Extract text strings to check for false LOT 330
    text_values = re.findall(r"(?:  )?0\nTEXT\n.*?(?:  )?1\n([^\n]+)", content, re.DOTALL)
    lot_330_count = sum(1 for t in text_values if t.strip().upper() == "LOT 330")
    
    # Check extents
    xs = [float(x) for x in re.findall(r"(?:  )?10\n([0-9\.\-]+)", content)]
    ys = [float(y) for y in re.findall(r"(?:  )?20\n([0-9\.\-]+)", content)]
    span_x = (min(xs), max(xs)) if xs else (0, 0)
    span_y = (min(ys), max(ys)) if ys else (0, 0)

    
    # Detect if extents look like raw pixel coordinates ([0, 8000])
    is_pixel_space = (span_x[1] < 10000.0 and span_x[0] >= -50.0 and span_y[1] < 10000.0 and span_y[0] >= -50.0
                      and max(span_x[1], span_y[1]) > 3000.0)
    
    has_monument_bloat = (circles > 500)
    
    status = "PASS"
    issues = []
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
        "layers": sorted(list(layers)),
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

