"""
lotsheets.py -- emit one check-sheet page per lot.

Each page is a self-contained closure check: the lot drawn as a single
closed polyline at its own scale, every side labeled with bearing and
distance, area and perimeter stated, and the verification verdict printed.
Any geometry a check objected to is redrawn on a red ERROR layer directly
on top of the offending side, so a failure is visible without reading the
report text.

Pages are laid out on a grid in one DXF so the whole block can be reviewed
by panning, while each page remains an independent closed figure.
"""
from __future__ import annotations
import math
from engine.cogo import Point, azimuth_to_bearing
from engine.labels import course_label_positions

PAGE_W = 300.0      # drawing units (ft) per check sheet cell
PAGE_H = 260.0
MARGIN = 26.0


def _bounds(pts):
    ns = [p.n for p in pts]; es = [p.e for p in pts]
    return min(ns), max(ns), min(es), max(es)


def draw_lot_sheet(dxf, verification, pts, origin_n, origin_e,
                   arcs=None, layer_ok="LOT_POLYLINE", layer_err="ERROR",
                   layer_lbl="SHEET_LABELS", layer_frame="SHEET_FRAME"):
    """Draw one lot's check sheet with its lower-left at (origin_n, origin_e)."""
    arcs = arcs or {}
    all_bounds_pts = list(pts)
    for arc in arcs.values():
        all_bounds_pts.extend(arc.get("arc_points") or [])
    minn, maxn, mine, maxe = _bounds(all_bounds_pts)
    span_n = max(maxn - minn, 1e-6)
    span_e = max(maxe - mine, 1e-6)
    avail_n = PAGE_H - 2 * MARGIN - 34      # leave headroom for the title block
    avail_e = PAGE_W - 2 * MARGIN
    scale = min(avail_n / span_n, avail_e / span_e)

    def place(p: Point):
        return (origin_n + MARGIN + (p.n - minn) * scale,
                origin_e + MARGIN + (p.e - mine) * scale)

    # page frame
    fr = [(origin_n, origin_e), (origin_n, origin_e + PAGE_W),
          (origin_n + PAGE_H, origin_e + PAGE_W), (origin_n + PAGE_H, origin_e)]
    for i in range(4):
        dxf.line(fr[i], fr[(i + 1) % 4], layer=layer_frame)

    n = len(pts)
    placed = [place(p) for p in pts]

    # the lot as ONE closed polyline (explicitly closed)
    dxf.polyline([(q[0], q[1]) for q in placed], layer=layer_ok, closed=True)

    # arcs drawn as their own polyline along the same side
    for idx, arc in arcs.items():
        apts = arc.get("arc_points") or []
        if len(apts) >= 2:
            dxf.polyline([place(p) for p in apts], layer=layer_ok, closed=False)

    # side labels: bearing + distance
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        pa, pb = placed[i], placed[(i + 1) % n]
        d = a.dist_to(b)
        az = math.degrees(math.atan2(b.e - a.e, b.n - a.n)) % 360
        pos = course_label_positions(pa[0], pa[1], pb[0], pb[1], 3.0, 3.0)
        if pos:
            dxf.text(pos["bearing_pos"], azimuth_to_bearing(az), height=3.4,
                     layer=layer_lbl, rotation=pos["angle"])
            dxf.text(pos["distance_pos"], f"{d:.2f}'", height=3.2,
                     layer=layer_lbl, rotation=pos["angle"])
        dxf.point(pa, layer=layer_lbl)

    # error geometry drawn red, on top
    for f in verification.findings:
        if f.severity != "ERROR":
            continue
        for (n1, e1, n2, e2) in f.geometry:
            a = place(Point(n1, e1)); b = place(Point(n2, e2))
            dxf.line(a, b, layer=layer_err)
        for (vn, ve) in f.vertices:
            v = place(Point(vn, ve))
            r = 3.0
            dxf.line((v[0] - r, v[1] - r), (v[0] + r, v[1] + r), layer=layer_err)
            dxf.line((v[0] - r, v[1] + r), (v[0] + r, v[1] - r), layer=layer_err)

    # title block
    v = verification
    ty = origin_n + PAGE_H - 10
    tx = origin_e + 8
    status = "PASS" if v.passed else f"FAIL ({len(v.errors)} error(s))"
    dxf.text((ty, tx), f"LOT {v.lot}   {status}", height=8.0,
             layer=layer_err if not v.passed else layer_lbl)
    area_txt = f"{v.area:,.0f} SF ({v.area/43560:.3f} ac)" if v.area else "NO AREA"
    dxf.text((ty - 11, tx), f"AREA {area_txt}", height=4.6, layer=layer_lbl)
    dxf.text((ty - 18, tx), f"PERIMETER {v.perimeter:.2f}'   "
             f"VERTICES {v.n_vertices}   CLOSING SIDE {v.misclosure:.2f}'",
             height=4.0, layer=layer_lbl)
    row = ty - 25
    if layer_ok == "LOT_LINE_APPROX":
        dxf.text((row, tx), "STATUS: ASSUMED (SCALED FROM SCAN - FOR REFINEMENT)",
                 height=3.4, layer="LOT_LINE_APPROX")
        row -= 5.2
    for f in v.findings[:5]:
        dxf.text((row, tx), f"[{f.severity}] {f.code}: {f.message[:62]}",
                 height=3.4,
                 layer=layer_err if f.severity == "ERROR" else layer_lbl)
        row -= 5.2
    if v.passed and not v.warnings and layer_ok != "LOT_LINE_APPROX":
        dxf.text((row, tx), "all geometric checks passed: closed single "
                 "polyline, no self-intersection, no overlap, no spikes",
                 height=3.4, layer=layer_lbl)


def plot_all(dxf, verifications: dict, parcels: dict, arcs_by_lot=None,
             cols=4, origin_n=0.0, origin_e=0.0, lot_layers=None,
             layer_ok="LOT_POLYLINE", layer_err="ERROR",
             layer_lbl="SHEET_LABELS", layer_frame="SHEET_FRAME"):
    """Lay out every lot's check sheet on a grid."""
    arcs_by_lot = arcs_by_lot or {}
    lot_layers = lot_layers or {}
    order = list(parcels.keys())
    for k, lot in enumerate(order):
        r, c = divmod(k, cols)
        on = origin_n - r * (PAGE_H + 20)
        oe = origin_e + c * (PAGE_W + 20)
        lyr = lot_layers.get(lot, layer_ok)
        draw_lot_sheet(dxf, verifications[lot], parcels[lot], on, oe,
                       arcs=arcs_by_lot.get(lot), layer_ok=lyr,
                       layer_err=layer_err, layer_lbl=layer_lbl,
                       layer_frame=layer_frame)
    return len(order)
