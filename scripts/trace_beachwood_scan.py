"""
trace_beachwood_scan.py -- Pure Computer Vision Skeletonization and Curve-Aware Tracing for Beachwood Unit Two.

Processes:
  1. Scan: Ingests 200 DPI raster scan (temp_images/bw_page-2.png).
  2. Skeleton: Morphological & Zhang-Suen 1px skeletonization with text blob exclusion.
  3. Tracing with Computer Vision:
     - Junction-break contour extraction.
     - High-precision circular curve detection and least-squares arc parameter fitting.
     - Separation of straight polylines vs circular arcs.
  4. Vector Alignment: Rigid Helmert/survey registration onto the parent vector coordinate frame.
  5. DXF Output: Dedicated traced DXF with separate layers for traced straight lines and traced curves (AutoCAD ARC entities).
"""
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, ".")
from engine import scan_align as SA
from engine.audit import dxf_audit
from engine.cogo import parse_bearing
from engine.curve_follow import InkField
from engine.dxf_writer import DXFWriter
from engine.vectorize import (
    break_at_junctions,
    derive_scale_factor,
    extract_polylines,
    map_mask_excluding,
    px_to_feet_polylines,
)


def fit_circle_least_squares(pts: np.ndarray) -> tuple[float, float, float, float] | None:
    """
    Fit circular arc parameters (cx, cy, radius, rmse) to an Nx2 array of points
    using algebraic linear least squares: x^2 + y^2 + D*x + E*y + F = 0.
    """
    if len(pts) < 8:
        return None
    x = pts[:, 0]
    y = pts[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = -(x**2 + y**2)
    try:
        sol, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
    except Exception:
        return None
    D, E, F = sol
    cx = -D / 2.0
    cy = -E / 2.0
    r_sq = cx**2 + cy**2 - F
    if r_sq <= 0:
        return None
    R = math.sqrt(r_sq)
    dists = np.hypot(x - cx, y - cy)
    rmse = float(np.sqrt(np.mean((dists - R) ** 2)))
    return cx, cy, R, rmse


def trace_beachwood_scan(
    scan_path: str = "temp_images/bw_page-2.png",
    scale_feet: float = 100.0,
    dpi: float = 200.0,
    corner_px: tuple[int, int] = (2047, 372),
    out_dxf: str = "dxf/PB0030_P0082_Beachwood_Traced_Vector.dxf",
):
    print("=" * 80)
    print("  BEACHWOOD UNIT TWO: COMPUTER VISION SKELETON TRACING & CURVE EXTRACTION")
    print("  Plat Book 30, Pages 82 & 82A, Duval County, FL (1960)")
    print("================================================================================")

    if not os.path.exists(scan_path):
        raise FileNotFoundError(f"Plat scan not found at {scan_path}")

    # 1. Load Scan
    img = cv2.imread(scan_path, 0)
    if img is None:
        raise ValueError(f"Could not load scan image: {scan_path}")
    h, w = img.shape
    ft_per_px = derive_scale_factor(scale_feet, dpi)
    print(f"[1/4] Loaded Plat Scan: {w}x{h} px | Scale: {scale_feet}'/inch @ {dpi} DPI ({ft_per_px:.4f} ft/px)")

    # 2. Extract 1px Skeleton using Computer Vision
    print("[2/4] Generating 1-pixel morphological skeleton & filtering text blobs...")
    mask = map_mask_excluding(img, border_frac=0.015, min_diag=150, skeleton=True)
    raw_polys = extract_polylines(mask)
    scan_polys = px_to_feet_polylines(raw_polys, ft_per_px, (0, 0), h)
    ink = InkField.from_polylines(scan_polys)

    # Solve Vector Frame Registration
    street_bearing = "S87°35'30\"W"
    side_bearing = "N02°24'30\"W"
    north_distance = 1626.37
    east_az = (parse_bearing(street_bearing) + 180.0) % 360.0
    south_az = (parse_bearing(side_bearing) + 180.0) % 360.0
    corner_hint = ((h - corner_px[1]) * ft_per_px, corner_px[0] * ft_per_px)

    al = SA.align_from_corner(
        ink, corner_hint, anchor_vec=(0.0, 0.0),
        baseline_vec_az=east_az, baseline_len_ft=north_distance, cross_vec_az=south_az
    )
    params = al["params"]
    rot_deg = float(params["rotation_deg"])
    rad = math.radians(rot_deg)
    cos_r, sin_r = math.cos(rad), math.sin(rad)
    sc = float(params["scale"])
    tn, te = float(params["translation_n"]), float(params["translation_e"])

    print(f"      Survey Alignment: Scale={sc:.5f}, Rotation={rot_deg:+.4f}°, Translation=(N={tn:+.2f}, E={te:+.2f})")

    def px_to_vector(px_x: float, px_y: float) -> tuple[float, float]:
        # Pixel -> Scan Feet -> Vector (Northing, Easting)
        es = px_x * ft_per_px
        ns = (h - px_y) * ft_per_px
        vn = sc * (cos_r * ns - sin_r * es) + tn
        ve = sc * (sin_r * ns + cos_r * es) + te
        return vn, ve

    # 3. Tracing with Computer Vision: Junction Breaking & Circular Curve Fitting
    print("[3/4] Tracing continuous strokes and fitting circular curves...")
    broken = break_at_junctions(mask)
    contours, _ = cv2.findContours(broken, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    traced_curves: list[dict] = []
    traced_straights: list[list[tuple[float, float]]] = []

    for cnt in contours:
        if len(cnt) < 10:
            continue
        # In a 1-pixel wide skeleton, findContours traverses forward along one side and back on the other
        # The forward stroke is represented by cnt[:half + 1]
        half = len(cnt) // 2
        pts_px = cnt[:half + 1, 0, :]
        if len(pts_px) < 5:
            continue
        p_start, p_end = pts_px[0], pts_px[-1]

        # Chord vector
        vx = float(p_end[0] - p_start[0])
        vy = float(p_end[1] - p_start[1])
        L = math.hypot(vx, vy)
        if L < 4.0:
            continue
        nx = -vy / L
        ny = vx / L

        # Calculate deviation (sagitta) from chord
        dists = np.abs((pts_px[:, 0] - p_start[0]) * nx + (pts_px[:, 1] - p_start[1]) * ny)
        max_dev = float(np.max(dists))

        is_curve = False
        if max_dev >= 2.5:  # Sagitta >= 2.5 px (~1.25 ft)
            fit = fit_circle_least_squares(pts_px)
            if fit is not None:
                cx_px, cy_px, r_px, rmse = fit
                r_ft = r_px * ft_per_px * sc
                # Valid cadastral curve range: 15 ft to 3500 ft, low fitting error
                if rmse <= 2.8 and 15.0 <= r_ft <= 3500.0:
                    cen_n, cen_e = px_to_vector(cx_px, cy_px)
                    p1_n, p1_e = px_to_vector(float(pts_px[0, 0]), float(pts_px[0, 1]))
                    p2_n, p2_e = px_to_vector(float(pts_px[-1, 0]), float(pts_px[-1, 1]))

                    # AutoCAD angles (CCW from East)
                    sa = math.degrees(math.atan2(p1_n - cen_n, p1_e - cen_e)) % 360.0
                    ea = math.degrees(math.atan2(p2_n - cen_n, p2_e - cen_e)) % 360.0

                    # Convert sample points along the curve
                    approx_poly = cv2.approxPolyDP(pts_px[:, None, :], 1.5, closed=False)
                    vec_poly = [px_to_vector(float(p[0][0]), float(p[0][1])) for p in approx_poly]

                    traced_curves.append({
                        "center": (cen_n, cen_e),
                        "radius": r_ft,
                        "sa": sa,
                        "ea": ea,
                        "rmse_px": rmse,
                        "pts_vector": vec_poly,
                    })
                    is_curve = True

        if not is_curve:
            approx_poly = cv2.approxPolyDP(pts_px[:, None, :], 1.5, closed=False)
            if len(approx_poly) >= 2:
                vec_poly = [px_to_vector(float(p[0][0]), float(p[0][1])) for p in approx_poly]
                traced_straights.append(vec_poly)

    print(f"      Extracted {len(traced_curves)} Circular Curves and {len(traced_straights)} Straight Lines.")

    # 4. Save Dedicated Traced DXF
    print(f"[4/4] Exporting Traced DXF -> {out_dxf}...")
    os.makedirs(os.path.dirname(out_dxf), exist_ok=True)
    dxf = DXFWriter()
    dxf.add_layer("TRACED_LINE", "blue", "CONTINUOUS")
    dxf.add_layer("TRACED_CURVE", "magenta", "CONTINUOUS")
    dxf.add_layer("CONTROL", "red", "CENTER")
    dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")

    # Draw straight polylines on TRACED_LINE
    for poly in traced_straights:
        dxf.polyline(poly, layer="TRACED_LINE", closed=False)

    # Draw curves on TRACED_CURVE (native CAD ARC + smooth polylines)
    for c in traced_curves:
        # Native AutoCAD ARC
        dxf.arc(c["center"], c["radius"], c["sa"], c["ea"], layer="TRACED_CURVE")
        # Polyline stroke
        dxf.polyline(c["pts_vector"], layer="TRACED_CURVE", closed=False)

    # Add Title Block
    tb_top = 250.0
    tb_left = 0.0
    dxf.text((tb_top, tb_left), "BEACHWOOD UNIT TWO -- COMPUTER VISION TRACED SKELETON & CURVES", height=12.0, layer="TITLEBLOCK")
    dxf.text((tb_top - 20.0, tb_left), f"Extracted from 200 DPI Plat Scan: {len(traced_curves)} Curves | {len(traced_straights)} Lines", height=8.0, layer="TITLEBLOCK")
    dxf.text((tb_top - 36.0, tb_left), "Layer TRACED_LINE (Blue): Straight Linework | Layer TRACED_CURVE (Magenta): Native CAD ARCs", height=7.5, layer="TITLEBLOCK")

    dxf.save(out_dxf)
    audit = dxf_audit(out_dxf)
    print(f"Audit Result: Status={audit['status']} | Entities={audit['entity_counts']} | Issues={audit['issues']}")
    print(f"SUCCESS: Saved Pure Traced Vector Layer with all Curves to: {out_dxf}")
    return {
        "status": "SUCCESS",
        "dxf_path": out_dxf,
        "curves_count": len(traced_curves),
        "straights_count": len(traced_straights),
        "audit": audit,
    }


if __name__ == "__main__":
    trace_beachwood_scan()
