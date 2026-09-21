"""
vectorize.py -- raster-to-vector for plat linework.

Used when a plat's lot fabric is too large to transcribe dimension by
dimension (Atlantic Beach Unit 2: ~176 lots over 4 detail sheets). The
geometry is scaled off the scan itself, which is legitimate because the
scale is EXACTLY derivable:

    plat drawn at 1" = 50 ft, rendered at D dpi
    => 1 pixel = 50 / D feet        (at 300 dpi: 0.166667 ft/px)

This is not estimation -- it is a unit conversion. What it does NOT give is
the surveyed precision of the recorded dimensions: line positions carry the
scan's own error (line width, paper distortion, scanner skew), so a
vectorized line is good to roughly a foot, not to 0.01 ft. Vectorized
geometry must therefore be labelled as SCALED, never mixed silently with
transcribed dimensions.

Pipeline: threshold -> drop small components (text) -> Hough segments ->
merge collinear -> convert px to feet -> DXF.
"""
from __future__ import annotations
import math
import warnings
import cv2
import numpy as np
from typing import Any


def map_mask(img: np.ndarray, rect: tuple, min_diag=150) -> np.ndarray:
    """Binarise a map region and strip text by dropping small components.

    Plat linework connects into a few very large components while text
    characters are isolated blobs; on Atlantic Beach sheet 3 the split was
    unambiguous (text diag 33-80 px, linework up to 7047 px)."""
    x, y, w, h = rect
    sub = img[y:y + h, x:x + w]
    thr = cv2.threshold(cv2.bitwise_not(sub), 0, 255,
                        cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(thr, 8)
    keep = np.zeros_like(thr)
    for i in range(1, n):
        wd, ht = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if math.hypot(wd, ht) >= min_diag:
            keep[lab == i] = 255
    return keep


def skeletonize(mask: np.ndarray) -> np.ndarray:
    """Thin drawn strokes to a 1-px-wide centerline before line-fitting.

    CRITICAL FIX: running HoughLinesP directly on a multi-pixel-wide stroke
    detects EACH EDGE of the stroke as its own near-duplicate line (plus
    fragments at slightly different angles near corners/intersections).
    Measured on Atlantic Beach sheet 3: 578 Hough/merge segments contained
    1,308 near-duplicate pairs (same angle within 2 deg, offset under 3 ft)
    -- this is what produced the "sketch, multiple overlapping lines" look
    the user flagged. Skeletonizing first (Zhang-Suen thinning via
    cv2.ximgproc) collapses each stroke to its single centerline, so Hough
    finds one line per drawn line instead of several."""
    try:
        import cv2.ximgproc as xi
        return xi.thinning(mask, thinningType=xi.THINNING_ZHANGSUEN)
    except Exception:
        pass  # opencv-contrib not installed
    try:
        # scikit-image thinning is the same family as Zhang-Suen and keeps strokes
        # connected. On the Beachwood sheet it gives 20 connected pieces where the
        # morphological fallback below gives 2,744, and on a clean drawn arc 1,991
        # ink points where the fallback keeps 112 -- so silently falling through to
        # it (as this function used to whenever cv2.ximgproc was missing) wrecked
        # every curve-following and linework result downstream.
        from skimage.morphology import skeletonize as _sk_skeletonize
        return (_sk_skeletonize(mask > 0) * 255).astype(np.uint8)
    except Exception:
        warnings.warn(
            "skeletonize(): neither cv2.ximgproc nor scikit-image is available; using the "
            "crude morphological fallback, which fragments strokes. Install opencv-contrib-python "
            "or scikit-image for reliable centerlines.", RuntimeWarning, stacklevel=2)
        # last resort: morphological thinning
        skel = np.zeros_like(mask)
        working = mask.copy()
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        while True:
            opened = cv2.morphologyEx(working, cv2.MORPH_OPEN, kernel)
            temp = cv2.subtract(working, opened)
            eroded = cv2.erode(working, kernel)
            skel = cv2.bitwise_or(skel, temp)
            working = eroded
            if cv2.countNonZero(working) == 0:
                break
        return skel


def segments(mask: np.ndarray, min_len_px=48, max_gap=6, thresh=60):
    """Hough segments from the cleaned mask.

    On a SKELETONIZED (1px) mask, thinning can nick a line into several
    collinear pieces at pixel-level gaps -- max_gap must be generous enough
    to bridge those, and threshold can drop since a 1px line has much less
    accumulator support than a thick stroke of the same length."""
    lines = cv2.HoughLinesP(mask, 1, np.pi / 720, threshold=max(20, thresh // 2),
                            minLineLength=min_len_px, maxLineGap=max(max_gap, 10))
    return [] if lines is None else [tuple(int(v) for v in l) for l in lines[:, 0]]


def _ang(s):
    x1, y1, x2, y2 = s
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180


def _len(s):
    x1, y1, x2, y2 = s
    return math.hypot(x2 - x1, y2 - y1)


def merge_collinear(segs, ang_tol=1.2, perp_tol=2.0, gap_tol=20.0):
    """Collapse the many short Hough fragments along one drawn line into a
    single segment. Without this a single lot line becomes a dozen
    near-duplicate entities in the DXF."""
    used = [False] * len(segs)
    order = sorted(range(len(segs)), key=lambda i: -_len(segs[i]))
    out = []
    for i in order:
        if used[i]:
            continue
        x1, y1, x2, y2 = segs[i]
        a = _ang(segs[i])
        pts = [(x1, y1), (x2, y2)]
        used[i] = True
        ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
        for j in order:
            if used[j]:
                continue
            b = _ang(segs[j])
            da = abs(a - b)
            da = min(da, 180 - da)
            if da > ang_tol:
                continue
            # perpendicular distance of j's midpoint from i's line
            mx, my = (segs[j][0] + segs[j][2]) / 2, (segs[j][1] + segs[j][3]) / 2
            vx, vy = mx - x1, my - y1
            perp = abs(vx * uy - vy * ux)
            if perp > perp_tol:
                continue
            # projection overlap / gap
            t_i = sorted([0.0, (x2 - x1) * ux + (y2 - y1) * uy])
            tj = sorted([(segs[j][0] - x1) * ux + (segs[j][1] - y1) * uy,
                         (segs[j][2] - x1) * ux + (segs[j][3] - y1) * uy])
            if tj[0] > t_i[1] + gap_tol or tj[1] < t_i[0] - gap_tol:
                continue
            pts += [(segs[j][0], segs[j][1]), (segs[j][2], segs[j][3])]
            used[j] = True
        ts = [((px - x1) * ux + (py - y1) * uy) for px, py in pts]
        lo, hi = min(ts), max(ts)
        out.append((x1 + ux * lo, y1 + uy * lo, x1 + ux * hi, y1 + uy * hi))
    return out


def px_to_feet(segs, ft_per_px, origin_px=(0, 0), img_h=0):
    """Convert pixel segments to plat feet, flipping the image Y axis so the
    result is a right-handed (Northing, Easting) system."""
    ox, oy = origin_px
    out = []
    for x1, y1, x2, y2 in segs:
        e1 = (x1 - ox) * ft_per_px
        n1 = (img_h - (y1 - oy)) * ft_per_px
        e2 = (x2 - ox) * ft_per_px
        n2 = (img_h - (y2 - oy)) * ft_per_px
        out.append((n1, e1, n2, e2))
    return out


def map_mask_excluding(img, border_frac=0.012, exclude=None, min_diag=150,
                       skeleton=True):
    """Keep the WHOLE sheet inside its border and subtract known non-map
    regions (curve/line tables, title block, legend).

    A single crop rectangle is too blunt for a plat sheet: the map often
    wraps around the table stack, so cropping to the right of a curve table
    silently discards the lot column to its left. Observed on Atlantic Beach
    sheet 3 -- a rectangular crop captured only 58% of the page linework and
    lost the lots 105-123 column and Tract K.

    skeleton=True (default) thins strokes to 1px before returning -- see
    skeletonize() docstring for why this is required, not optional, to avoid
    duplicate near-parallel lines from each stroke's two edges."""
    import numpy as np, cv2
    h, w = img.shape
    m = map_mask(img, (0, 0, w, h), min_diag=min_diag)
    b = int(min(h, w) * border_frac)
    m[:b, :] = 0; m[-b:, :] = 0; m[:, :b] = 0; m[:, -b:] = 0
    for (fx, fy, fw, fh) in (exclude or []):
        x, y = int(w * fx), int(h * fy)
        m[y:y + int(h * fh), x:x + int(w * fw)] = 0
    if skeleton:
        m = skeletonize(m)
    return m


def break_at_junctions(skel: np.ndarray) -> np.ndarray:
    """
    Find junction pixels (pixels with >2 neighbors) in the skeleton and remove them.
    This breaks the skeleton into independent branches (lot lines) that don't cross,
    ensuring cv2.findContours traces them as separate lines ending at corners.
    """
    # A simple neighbor count via convolution
    kernel = np.array([[1, 1, 1],
                       [1, 0, 1],
                       [1, 1, 1]], dtype=np.uint8)
    
    # Binary mask where foreground is 1
    skel_bin = (skel > 0).astype(np.uint8)
    
    # Count neighbors
    neighbors = cv2.filter2D(skel_bin, -1, kernel)
    
    # Junctions are pixels in the skeleton that have >2 neighbors
    junctions = (skel_bin == 1) & (neighbors > 2)
    
    # Optional: dilate junctions slightly to ensure clean breaks at complex corners
    j_mask = (junctions * 255).astype(np.uint8)
    j_mask = cv2.dilate(j_mask, np.ones((3,3), np.uint8), iterations=1)
    
    # Subtract junctions from skeleton
    broken_skel = cv2.bitwise_and(skel, cv2.bitwise_not(j_mask))
    return broken_skel


def extract_polylines(mask: np.ndarray, epsilon: float = 1.5, break_junctions: bool = True) -> list[list[tuple]]:
    """
    Extract continuous polylines from a skeletonized mask using cv2.findContours.
    This replaces HoughLinesP for hand-drawn plats to preserve exact curves and organic lines.
    
    epsilon: approximation accuracy for approxPolyDP. A smaller value preserves more
             of the original wiggles.
    """
    if break_junctions:
        mask = break_at_junctions(mask)
        
    # Use RETR_LIST to get all contours
    # Use CHAIN_APPROX_SIMPLE to compress horizontal, vertical, and diagonal segments
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    
    polylines = []
    for cnt in contours:
        # Approximate contour to smooth out tiny pixel jitters
        approx = cv2.approxPolyDP(cnt, epsilon, closed=False)
        
        # We need at least two points to make a line
        if len(approx) < 2:
            continue
            
        points = []
        for p in approx:
            x, y = p[0]
            points.append((x, y))
            
        polylines.append(points)
        
    return polylines


def px_to_feet_polylines(polylines: list[list[tuple]], ft_per_px: float, origin_px=(0, 0), img_h=0) -> list[list[tuple]]:
    """Convert pixel polylines to plat feet, flipping the image Y axis (Northing, Easting)."""
    ox, oy = origin_px
    out = []
    for poly in polylines:
        conv_poly = []
        for x, y in poly:
            e = (x - ox) * ft_per_px
            n = (img_h - (y - oy)) * ft_per_px
            conv_poly.append((n, e))
        out.append(conv_poly)
    return out


def filter_speckle_monuments(candidate_circles: list[tuple], img_shape: tuple,
                             min_radius_px: int = 12, max_radius_px: int = 60,
                             min_margin_px: int = 50) -> list[tuple]:
    """Filter out scanner noise, dust specks, and text characters that masquerade
    as circle monuments.
    
    Candidate circles: list of (cx, cy, radius).
    Returns only verified survey monument circles.
    """
    h, w = img_shape[:2]
    filtered = []
    for (cx, cy, r) in candidate_circles:
        # 1. Reject tiny speckles and gigantic rings
        if r < min_radius_px or r > max_radius_px:
            continue
        # 2. Reject circles outside the valid image margin
        if cx < min_margin_px or cx > (w - min_margin_px) or cy < min_margin_px or cy > (h - min_margin_px):
            continue
        filtered.append((cx, cy, r))
    return filtered


def derive_scale_factor(scale_feet: float, dpi: float = 300.0) -> float:
    """Derive exact feet-per-pixel from graphic scale (e.g. 1" = 50' at 300 dpi -> 50 / 300 = 0.166667 ft/px)."""
    return float(scale_feet) / float(dpi)


def transform_to_state_plane(coords: list[tuple], anchor_sp: tuple, anchor_local: tuple = (0.0, 0.0),
                             rotation_deg: float = 0.0) -> list[tuple]:
    """Transform local survey coordinates (Northing, Easting) into Florida State Plane East (EPSG:2236).
    anchor_sp: (Northing, Easting) in State Plane
    anchor_local: (Northing, Easting) in local frame
    rotation_deg: CCW rotation in degrees
    """
    rad = math.radians(rotation_deg)
    cos_r, sin_r = math.cos(rad), math.sin(rad)
    sp_n0, sp_e0 = anchor_sp
    loc_n0, loc_e0 = anchor_local
    
    transformed = []
    for n, e in coords:
        dn = n - loc_n0
        de = e - loc_e0
        rn = dn * cos_r - de * sin_r
        re = dn * sin_r + de * cos_r
        transformed.append((sp_n0 + rn, sp_e0 + re))
    return transformed


def vectorize_plat_sheet(
    img_or_path,
    scale_feet: float = 100.0,
    dpi: float = 200.0,
    border_frac: float = 0.015,
    exclude: list[tuple] | None = None,
    min_diag: int = 150,
    epsilon: float = 1.5,
    break_junctions: bool = True,
) -> dict[str, Any]:
    """Automated survey-grade raster-to-vector pipeline for subdivision plat sheets.
    
    Extracts continuous polylines, Hough segments, and converts all linework to feet.
    """
    if isinstance(img_or_path, str):
        img = cv2.imread(img_or_path, 0)
        if img is None:
            raise FileNotFoundError(f"Cannot read image from {img_or_path}")
    else:
        img = img_or_path

    h, w = img.shape[:2]
    ft_per_px = derive_scale_factor(scale_feet, dpi)

    # 1. Clean mask with text suppression & skeleton thinning
    mask = map_mask_excluding(
        img,
        border_frac=border_frac,
        exclude=exclude,
        min_diag=min_diag,
        skeleton=True,
    )

    # 2. Extract continuous polylines
    polys_px = extract_polylines(mask, epsilon=epsilon, break_junctions=break_junctions)
    polys_ft = px_to_feet_polylines(polys_px, ft_per_px=ft_per_px, origin_px=(0, 0), img_h=h)

    # 3. Extract straight line segments
    raw_segs = segments(mask, min_len_px=int(25.0 / ft_per_px), max_gap=int(6.0 / ft_per_px), thresh=40)
    merged_segs = merge_collinear(raw_segs, ang_tol=1.5, perp_tol=3.0, gap_tol=20.0)
    segs_ft = px_to_feet(merged_segs, ft_per_px=ft_per_px, origin_px=(0, 0), img_h=h)

    # Compute total linear feet
    tot_len_ft = 0.0
    for poly in polys_ft:
        for idx in range(len(poly) - 1):
            tot_len_ft += math.hypot(poly[idx + 1][0] - poly[idx][0], poly[idx + 1][1] - poly[idx][1])

    return {
        "polylines_ft": polys_ft,
        "segments_ft": segs_ft,
        "ft_per_px": ft_per_px,
        "total_linework_feet": tot_len_ft,
        "num_polylines": len(polys_ft),
        "num_segments": len(segs_ft),
        "image_shape": (h, w),
    }


def iterative_align_raster_to_cogo(
    raster_pts: list[tuple[float, float]],
    cogo_pts: list[tuple[float, float]],
    max_iters: int = 50,
    tol: float = 1e-6,
) -> dict[str, Any]:
    """Iteratively computes optimal 2D Helmert transformation (scale, rotation, translation)
    between vectorized raster points and surveyed COGO control points until convergence.
    
    Points are (Northing, Easting).
    """
    if len(raster_pts) != len(cogo_pts) or len(raster_pts) < 2:
        raise ValueError("At least 2 corresponding point pairs are required for alignment.")

    r_arr = np.array(raster_pts, dtype=np.float64)  # shape (N, 2): [N, E]
    c_arr = np.array(cogo_pts, dtype=np.float64)

    # Center of mass
    r_mean = np.mean(r_arr, axis=0)
    c_mean = np.mean(c_arr, axis=0)

    r_centered = r_arr - r_mean
    c_centered = c_arr - c_mean

    # Initial estimates
    scale = 1.0
    theta_rad = 0.0
    t_n = float(c_mean[0] - r_mean[0])
    t_e = float(c_mean[1] - r_mean[1])

    history = []
    converged = False

    for iteration in range(1, max_iters + 1):
        prev_scale = scale
        prev_theta = theta_rad
        prev_t = (t_n, t_e)

        # Procrustes rotation calculation
        # H = r_centered.T @ c_centered
        H = r_centered.T @ c_centered
        U, S, Vt = np.linalg.svd(H)
        R_mat = Vt.T @ U.T
        if np.linalg.det(R_mat) < 0:
            Vt[-1, :] *= -1
            R_mat = Vt.T @ U.T

        theta_rad = math.atan2(R_mat[1, 0], R_mat[0, 0])

        # Optimal scale
        var_r = np.sum(r_centered ** 2)
        if var_r > 1e-12:
            scale = float(np.sum(S) / var_r)
        else:
            scale = 1.0

        # Translation
        cos_t, sin_t = math.cos(theta_rad), math.sin(theta_rad)
        R_rot = np.array([[cos_t, -sin_t], [sin_t, cos_t]])
        t_vec = c_mean - scale * (R_rot @ r_mean)
        t_n, t_e = float(t_vec[0]), float(t_vec[1])

        delta_theta = abs(theta_rad - prev_theta)
        delta_scale = abs(scale - prev_scale)
        delta_t = math.hypot(t_n - prev_t[0], t_e - prev_t[1])
        residual = float(np.mean(np.linalg.norm(c_arr - (scale * (r_arr @ R_rot.T) + t_vec), axis=1)))

        history.append({
            "iteration": iteration,
            "scale": scale,
            "rotation_deg": math.degrees(theta_rad),
            "translation": (t_n, t_e),
            "residual": residual,
            "delta": max(delta_theta, delta_scale, delta_t),
        })

        if delta_theta < tol and delta_scale < tol and delta_t < tol:
            converged = True
            break

    return {
        "converged": converged,
        "iterations": len(history),
        "scale": scale,
        "rotation_deg": math.degrees(theta_rad),
        "translation_n": t_n,
        "translation_e": t_e,
        "residual_ft": residual,
        "history": history,
    }


def extract_skeleton_points(
    mask: np.ndarray,
    ft_per_px: float,
    origin_px: tuple[int, int] = (0, 0),
    img_h: int = 0,
    downsample: int = 1,
) -> list[Any]:
    """Extract 1-pixel-wide skeleton centerline points from a binary mask
    and convert them to plat coordinates (Northing, Easting) in feet.
    
    downsample: optional integer stride to reduce point density if desired.
    """
    from engine.cogo import Point
    ys, xs = np.where(mask > 0)
    ox, oy = origin_px
    points = []
    for i in range(0, len(xs), max(1, downsample)):
        x, y = int(xs[i]), int(ys[i])
        e = (x - ox) * ft_per_px
        n = (img_h - (y - oy)) * ft_per_px
        points.append(Point(n, e))
    return points


def align_skeleton_to_vector(
    skeleton_pts: list[Any],
    helmert_params: dict[str, Any] | None = None,
    control_pairs: tuple[list[tuple[float, float]], list[tuple[float, float]]] | None = None,
) -> list[Any]:
    """Align skeleton scan points to vector survey coordinates (Northing, Easting)
    using a 2D Helmert similarity transformation (scale, rotation, translation).
    
    Either helmert_params (from iterative_align_raster_to_cogo) or control_pairs
    (raster_pts, cogo_pts) can be provided.
    """
    from engine.cogo import Point
    if helmert_params is None:
        if control_pairs is None:
            return skeleton_pts
        r_ctrl, c_ctrl = control_pairs
        helmert_params = iterative_align_raster_to_cogo(r_ctrl, c_ctrl)

    scale = float(helmert_params.get("scale", 1.0))
    rot_deg = float(helmert_params.get("rotation_deg", 0.0))
    t_n = float(helmert_params.get("translation_n", 0.0))
    t_e = float(helmert_params.get("translation_e", 0.0))

    rad = math.radians(rot_deg)
    cos_t, sin_t = math.cos(rad), math.sin(rad)

    aligned = []
    for pt in skeleton_pts:
        pn = pt.n if hasattr(pt, "n") else pt[0]
        pe = pt.e if hasattr(pt, "e") else pt[1]
        an = scale * (pn * cos_t - pe * sin_t) + t_n
        ae = scale * (pn * sin_t + pe * cos_t) + t_e
        aligned.append(Point(an, ae))
    return aligned


def sample_skeleton_corridor(
    p1: Any,
    p2: Any,
    skeleton_pts: list[Any],
    max_dist: float = 60.0,
    margin_frac: float = 0.05,
) -> list[tuple[Any, float, float]]:
    """Sample skeleton points in the lateral corridor along the chord from p1 to p2.
    
    Returns list of tuples: (point, t_along_chord, signed_offset)
    where:
      t_along_chord: normalized position along chord [0, 1]
      signed_offset: perpendicular signed distance from chord line in feet:
                     > 0 implies point is to the LEFT of chord vector p1 -> p2
                     < 0 implies point is to the RIGHT of chord vector p1 -> p2
    """
    p1n = p1.n if hasattr(p1, "n") else p1[0]
    p1e = p1.e if hasattr(p1, "e") else p1[1]
    p2n = p2.n if hasattr(p2, "n") else p2[0]
    p2e = p2.e if hasattr(p2, "e") else p2[1]

    dn = p2n - p1n
    de = p2e - p1e
    c = math.hypot(dn, de)
    if c < 1e-9:
        return []

    corridor = []
    for pt in skeleton_pts:
        pn = pt.n if hasattr(pt, "n") else pt[0]
        pe = pt.e if hasattr(pt, "e") else pt[1]

        # Fast bounding box cull
        min_n = min(p1n, p2n) - max_dist
        max_n = max(p1n, p2n) + max_dist
        min_e = min(p1e, p2e) - max_dist
        max_e = max(p1e, p2e) + max_dist
        if pn < min_n or pn > max_n or pe < min_e or pe > max_e:
            continue

        # Projection along chord
        t = ((pn - p1n) * dn + (pe - p1e) * de) / c
        t_frac = t / c
        if t_frac < margin_frac or t_frac > (1.0 - margin_frac):
            continue

        # Perpendicular signed offset
        offset = (de * (pn - p1n) - dn * (pe - p1e)) / c
        if abs(offset) <= max_dist:
            corridor.append((pt, t_frac, offset))

    return corridor



