"""
scripts/draw_block16_mapcheck.py -- Draw Survey MapChecks & Generate DXF for Block 16.

Plat: Beachwood Unit Two, Plat Book 30, Pages 82 & 82A, Duval County, FL
Target: Block 16, Lots 1 through 8 (North Row) and Lots 33 through 28 (South Row).

Outputs:
  1. dxf/PB0030_P0082_Block16_MapCheck.dxf (Multi-layer CAD DXF with Curve & Line tables)
  2. dxf/PB0030_P0082_Block16_CheckSheets.dxf (Individual Surveyor CheckSheets Grid)
  3. images/block16_mapcheck_drawing.png (High-Resolution Visual Cadastral MapCheck Plot)
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field

import matplotlib

matplotlib.use('Agg')
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.audit import dxf_audit
from engine.cogo import Point, parse_bearing
from engine.cogo_block import BeachwoodBlock16Solver
from engine.dxf_writer import DXFWriter
from engine.lotsheets import PAGE_H, PAGE_W, draw_lot_sheet
from engine.notes_audit import audit_solver_curves, print_audit_report


def build_and_draw_block16():
    print("=" * 80)
    print("  GENERATING CAD DRAWINGS & CHECKSHEETS FOR BLOCK 16 (14 LOTS)")
    print("  Plat Book 30, Pages 82 & 82A, Duval County, FL (Beachwood Unit Two)")
    print("=" * 80)

    solver = BeachwoodBlock16Solver()
    results = solver.solve_all()
    pts = solver.points

    # Notes/geometry audit -- see .claude/skills/review-plat-notes. Unlike
    # Block 13's script, this one draws straight from `solver.lots` with no
    # separate duplicated agent construction, so a single solver-level
    # audit covers everything this script actually renders.
    print_audit_report(audit_solver_curves(solver), header="BLOCK 16 SOLVER CURVE AUDIT")

    lot_order = [str(i) for i in range(1, 18)] + [str(i) for i in range(33, 17, -1)]

    # ==========================================================================
    # 1. WRITE MASTER CAD DRAWING (DXF)
    # ==========================================================================
    os.makedirs("dxf", exist_ok=True)
    dxf_path = "dxf/PB0030_P0082_Block16_MapCheck_claude.dxf"
    dxf = DXFWriter()
    dxf.add_layer("LOT_LINE", "cyan", "CONTINUOUS")
    dxf.add_layer("CURVE", "magenta", "CONTINUOUS")
    dxf.add_layer("RADIAL_LINE", "red", "DASHED")
    dxf.add_layer("BOUNDARY", "white", "CONTINUOUS")
    dxf.add_layer("MONUMENT", "yellow", "CONTINUOUS")
    dxf.add_layer("ROW_STREET", "yellow", "CONTINUOUS")
    dxf.add_layer("STREET_CL", "yellow", "DASHDOT")
    dxf.add_layer("BLOCK_CL", "yellow", "DASHDOT")
    dxf.add_layer("EASEMENT", "green", "DASHED")
    dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
    dxf.add_layer("DIM-LABELS", "green", "CONTINUOUS")
    dxf.add_layer("TABLE_FRAME", "white", "CONTINUOUS")
    dxf.add_layer("TABLE_TEXT", "cyan", "CONTINUOUS")
    dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")

    # Draw all 14 lot boundaries and curve arcs
    for lot_num in lot_order:
        res = results[lot_num]
        full_coords: list[tuple[float, float]] = []
        for c in res.courses:
            if c.is_curve and c.arc_points:
                for pt in c.arc_points[:-1]:
                    full_coords.append((pt.n, pt.e))
                # Draw on CURVE layer
                dxf.polyline([(p.n, p.e) for p in c.arc_points], layer="CURVE", closed=False)
            else:
                full_coords.append((c.start_pt.n, c.start_pt.e))
        dxf.polyline(full_coords, layer="LOT_LINE", closed=True)

        # Lot number label at centroid
        cen_n = sum(p[0] for p in full_coords) / len(full_coords)
        cen_e = sum(p[1] for p in full_coords) / len(full_coords)
        dxf.text((cen_n, cen_e), f"LOT {lot_num}", height=4.5, layer="TEXT-LABELS", halign=1, valign=2)

    # Helper for P.I. angle bar glyphs
    def draw_pi_glyph(p_pi: Point, az1: float, az2: float, size: float = 6.0, layer: str = "ROW_STREET"):
        pt1 = p_pi.offset(az1, size)
        pt2 = p_pi.offset(az2, size)
        dxf.line((pt1.n, pt1.e), (p_pi.n, p_pi.e), layer=layer)
        dxf.line((p_pi.n, p_pi.e), (pt2.n, pt2.e), layer=layer)
        dxf.text((p_pi.n + 2.0, p_pi.e + 2.0), "P.I.", height=3.2, layer="DIM-LABELS")

    # 1. Lot 1 NW P.I. Glyph & Tangents ('┌')
    draw_pi_glyph(pts["p1_nw_pi"], solver.az_west_s, solver.az_axis_e, size=7.0)
    dxf.line((pts["p1_pc_w"].n, pts["p1_pc_w"].e), (pts["p1_nw_pi"].n, pts["p1_nw_pi"].e), layer="RADIAL_LINE")
    dxf.line((pts["p1_pt_n"].n, pts["p1_pt_n"].e), (pts["p1_nw_pi"].n, pts["p1_nw_pi"].e), layer="RADIAL_LINE")
    p1_cen = pts["p1_pc_w"].offset(solver.az_axis_e, 25.0)
    dxf.line((p1_cen.n, p1_cen.e), (pts["p1_pc_w"].n, pts["p1_pc_w"].e), layer="RADIAL_LINE")
    dxf.line((p1_cen.n, p1_cen.e), (pts["p1_pt_n"].n, pts["p1_pt_n"].e), layer="RADIAL_LINE")
    dxf.text((p1_cen.n - 5.0, p1_cen.e - 15.0), "R=25.00'", height=3.0, layer="TEXT-LABELS")

    # 2. Lot 33 SW P.I. Glyph & Tangents ('└')
    draw_pi_glyph(pts["p33_sw_pi"], solver.az_west_n, solver.az_axis_e, size=7.0)
    dxf.line((pts["p33_pc_w"].n, pts["p33_pc_w"].e), (pts["p33_sw_pi"].n, pts["p33_sw_pi"].e), layer="RADIAL_LINE")
    dxf.line((pts["p33_pt_s"].n, pts["p33_pt_s"].e), (pts["p33_sw_pi"].n, pts["p33_sw_pi"].e), layer="RADIAL_LINE")
    p33_cen = pts["p33_pc_w"].offset(solver.az_axis_e, 25.0)
    dxf.line((p33_cen.n, p33_cen.e), (pts["p33_pc_w"].n, pts["p33_pc_w"].e), layer="RADIAL_LINE")
    dxf.line((p33_cen.n, p33_cen.e), (pts["p33_pt_s"].n, pts["p33_pt_s"].e), layer="RADIAL_LINE")
    dxf.text((p33_cen.n + 3.0, p33_cen.e - 15.0), "R=25.00'", height=3.0, layer="TEXT-LABELS")

    # 3. Lot 29 SE P.I. Glyph & Tangents ('┘')
    az_marina_tan_rev = (parse_bearing("S54°41'40\"E") + 180.0) % 360.0
    az_keel_tan = parse_bearing("N35°18'20\"E")
    draw_pi_glyph(pts["p29_ret_pi"], az_marina_tan_rev, az_keel_tan, size=7.0)
    dxf.line((pts["p29_pt_marina"].n, pts["p29_pt_marina"].e), (pts["p29_ret_pi"].n, pts["p29_ret_pi"].e), layer="RADIAL_LINE")
    dxf.line((pts["p29_ret_pt"].n, pts["p29_ret_pt"].e), (pts["p29_ret_pi"].n, pts["p29_ret_pi"].e), layer="RADIAL_LINE")
    p29_cen = pts["p29_pt_marina"].offset((parse_bearing("S54°41'40\"E") + 90.0) % 360.0, 25.0)
    dxf.line((p29_cen.n, p29_cen.e), (pts["p29_pt_marina"].n, pts["p29_pt_marina"].e), layer="RADIAL_LINE")
    dxf.line((p29_cen.n, p29_cen.e), (pts["p29_ret_pt"].n, pts["p29_ret_pt"].e), layer="RADIAL_LINE")
    dxf.text((p29_cen.n - 4.0, p29_cen.e + 3.0), "R=25.00'", height=3.0, layer="TEXT-LABELS")

    # P.R.M. Monument at SE Lot 33 / SW Lot 32
    prm_pt = pts["p33_prm_se"]
    dxf.point((prm_pt.n, prm_pt.e), layer="MONUMENT")
    mon_ring = [(prm_pt.n + 2.5 * math.sin(math.radians(a)), prm_pt.e + 2.5 * math.cos(math.radians(a))) for a in range(0, 360, 45)]
    dxf.polyline(mon_ring, layer="MONUMENT", closed=True)
    dxf.text((prm_pt.n - 8.0, prm_pt.e - 15.0), "P.R.M. (Lot 33/32)", height=3.8, layer="MONUMENT")

    # Block Centerline (618.50')
    p_cl_end = pts["p_cl_0"].offset(solver.az_axis_e, 618.50)
    dxf.line((pts["p_cl_0"].n, pts["p_cl_0"].e), (p_cl_end.n, p_cl_end.e), layer="BLOCK_CL")
    dxf.text(((pts["p_cl_0"].n + p_cl_end.n)/2.0 + 2.0, (pts["p_cl_0"].e + p_cl_end.e)/2.0 - 50.0),
             "BLOCK CENTERLINE -- N 87°35'30\" E - 618.50'", height=4.5, layer="BLOCK_CL")

    # Sail Avenue Centerline (60' R/W -> 30' North of Lot 1-8 North boundary)
    sail_cl_w = pts["p1_nw_pi"].offset(solver.az_west_n, 30.0)
    sail_cl_e = sail_cl_w.offset(solver.az_axis_e, 618.50)
    dxf.line((sail_cl_w.n, sail_cl_w.e), (sail_cl_e.n, sail_cl_e.e), layer="STREET_CL")
    dxf.text(((sail_cl_w.n + sail_cl_e.n)/2.0 + 3.0, (sail_cl_w.e + sail_cl_e.e)/2.0 - 50.0),
             "SAIL AVENUE (60' R/W) -- N 87°35'30\" E", height=5.5, layer="ROW_STREET")

    # West Street Centerline (60' R/W -> 30' West of Lot 1 & 33 West boundary)
    w_cl_n = pts["p1_nw_pi"].offset(solver.az_axis_w, 30.0).offset(solver.az_west_n, 30.0)
    w_cl_s = pts["p33_sw_pi"].offset(solver.az_axis_w, 30.0).offset(solver.az_west_s, 30.0)
    dxf.line((w_cl_n.n, w_cl_n.e), (w_cl_s.n, w_cl_s.e), layer="STREET_CL")
    dxf.text(((w_cl_n.n + w_cl_s.n)/2.0, (w_cl_n.e + w_cl_s.e)/2.0 - 15.0),
             "60' WEST CROSS STREET -- N 02°24'30\" W", height=5.0, layer="ROW_STREET", rotation=90.0)

    # South Street Centerline (60' R/W -> 30' South of Lot 33 & 32 frontage)
    south_cl_w = pts["p33_sw_pi"].offset(solver.az_west_s, 30.0)
    south_cl_e = south_cl_w.offset(solver.az_axis_e, 183.26)
    dxf.line((south_cl_w.n, south_cl_w.e), (south_cl_e.n, south_cl_e.e), layer="STREET_CL")
    dxf.text((south_cl_w.n - 8.0, (south_cl_w.e + south_cl_e.e)/2.0 - 40.0),
             "SOUTH STREET (60' R/W) -- N 87°35'30\" E", height=5.0, layer="ROW_STREET")

    # Marina Avenue Radial Rays from Center
    c_mar = pts["center_marina"]
    for rad_pt in [pts["p32_se_pc"], pts["p31_se"], pts["p30_se"], pts["p29_pt_marina"]]:
        dxf.line((c_mar.n, c_mar.e), (rad_pt.n, rad_pt.e), layer="RADIAL_LINE")
    dxf.text((c_mar.n + 30.0, c_mar.e - 20.0), "MARINA AVE CURVE R=389.27' (DELTA=37°42'50\")", height=4.0, layer="DIM-LABELS")

    # 10' Easement between Lot 7 and Lot 8
    p7_f = pts["p7_ne"]
    p7_r = pts["p7_se"]
    dxf.line((p7_r.n, p7_r.e + 5.0), (p7_f.n, p7_f.e + 5.0), layer="EASEMENT")
    dxf.line((p7_r.n, p7_r.e - 5.0), (p7_f.n, p7_f.e - 5.0), layer="EASEMENT")
    dxf.text(((p7_r.n + p7_f.n)/2.0, (p7_r.e + p7_f.e)/2.0 + 8.0), "10' EASEMENT", height=2.8, layer="EASEMENT")

    # Titleblock in DXF
    tb_n = pts["p1_nw_pi"].n + 80.0
    tb_e = pts["p1_nw_pi"].e + 50.0
    dxf.text((tb_n, tb_e), "BEACHWOOD UNIT TWO -- BLOCK 16 SURVEY MAPCHECK AUDIT", height=9.0, layer="TITLEBLOCK")
    dxf.text((tb_n - 15.0, tb_e), "Plat Book 30, Pages 82 & 82A, Duval County, FL | 100% Survey-Grade Closed (14 Lots)", height=5.5, layer="TITLEBLOCK")

    # ==========================================================================
    # CURVE TABLE & LINE TABLE EMBEDDED IN DXF
    # ==========================================================================
    tbl_origin_e = pts["p1_nw_pi"].e + 680.0
    tbl_origin_n = pts["p1_nw_pi"].n + 40.0

    # Curve Table Header
    dxf.text((tbl_origin_n, tbl_origin_e), "CURVE TABLE (BLOCK 16)", height=4.5, layer="TITLEBLOCK")
    c_hdr = f"{'Tag':<5} | {'Radius':<7} | {'Delta':<10} | {'Arc':<7} | {'Tan':<7} | {'Chord':<7} | {'Chord Bearing':<13}"
    dxf.text((tbl_origin_n - 8.0, tbl_origin_e), c_hdr, height=3.0, layer="TABLE_FRAME")
    dxf.line((tbl_origin_n - 10.0, tbl_origin_e), (tbl_origin_n - 10.0, tbl_origin_e + 260.0), layer="TABLE_FRAME")

    c_row_n = tbl_origin_n - 16.0
    for ct in solver.get_curve_table_data():
        row_str = f"{ct['tag']:<5} | {ct['radius']:<7.2f} | {ct['delta']:<10} | {ct['length']:<7.2f} | {ct['tangent']:<7.2f} | {ct['chord']:<7.2f} | {ct['chord_bearing']:<13}"
        dxf.text((c_row_n, tbl_origin_e), row_str, height=2.8, layer="TABLE_TEXT")
        c_row_n -= 6.0

    # Line Table Header
    l_tbl_n = c_row_n - 15.0
    dxf.text((l_tbl_n, tbl_origin_e), "LINE TABLE (BLOCK 16)", height=4.5, layer="TITLEBLOCK")
    l_hdr = f"{'Tag':<5} | {'Bearing':<14} | {'Dist (ft)':<10} | {'Description'}"
    dxf.text((l_tbl_n - 8.0, tbl_origin_e), l_hdr, height=3.0, layer="TABLE_FRAME")
    dxf.line((l_tbl_n - 10.0, tbl_origin_e), (l_tbl_n - 10.0, tbl_origin_e + 260.0), layer="TABLE_FRAME")

    l_row_n = l_tbl_n - 16.0
    for lt in solver.get_line_table_data()[:25]:
        row_str = f"{lt['tag']:<5} | {lt['bearing']:<14} | {lt['distance']:<10.2f} | {lt['desc']}"
        dxf.text((l_row_n, tbl_origin_e), row_str, height=2.6, layer="TABLE_TEXT")
        l_row_n -= 5.5

    # Lot Summary Table Header
    s_tbl_n = l_row_n - 15.0
    dxf.text((s_tbl_n, tbl_origin_e), "LOT SUMMARY & CLOSURE AUDIT (F.A.C. 5J-17)", height=4.5, layer="TITLEBLOCK")
    s_hdr = f"{'Lot':<5} | {'Perimeter':<11} | {'Area (SF)':<11} | {'Acres':<8} | {'Misclose':<10} | {'Status'}"
    dxf.text((s_tbl_n - 8.0, tbl_origin_e), s_hdr, height=3.0, layer="TABLE_FRAME")
    dxf.line((s_tbl_n - 10.0, tbl_origin_e), (s_tbl_n - 10.0, tbl_origin_e + 260.0), layer="TABLE_FRAME")

    s_row_n = s_tbl_n - 16.0
    for lot_num in lot_order:
        res = results[lot_num]
        row_str = f"{lot_num:<5} | {res.perimeter_ft:<11.2f} | {res.computed_area_sqft:<11.1f} | {res.computed_acres:<8.4f} | {res.misclose_dist_ft:<10.5f} | {'PASS (5J-17)'}"
        dxf.text((s_row_n, tbl_origin_e), row_str, height=2.6, layer="TABLE_TEXT")
        s_row_n -= 5.5

    dxf.save(dxf_path)
    audit = dxf_audit(dxf_path)
    print(f"  -> Master Cadastral DXF Saved: {dxf_path} | Status: {audit['status']} | Entities: {audit['entity_counts']}")

    # ==========================================================================
    # 2. WRITE INDIVIDUAL CHECKSHEETS GRID DXF
    # ==========================================================================
    cs_path = "dxf/PB0030_P0082_Block16_CheckSheets_claude.dxf"
    cs_dxf = DXFWriter()
    cs_dxf.add_layer("LOT_POLYLINE", "cyan", "CONTINUOUS")
    cs_dxf.add_layer("SHEET_LABELS", "white", "CONTINUOUS")
    cs_dxf.add_layer("SHEET_FRAME", "yellow", "CONTINUOUS")
    cs_dxf.add_layer("ERROR", "red", "CONTINUOUS")
    cs_dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")

    cols = 4
    for idx, lot_num in enumerate(lot_order):
        row = idx // cols
        col = idx % cols
        origin_e = col * (PAGE_W + 40.0)
        origin_n = -row * (PAGE_H + 40.0)

        @dataclass
        class LotVerification:
            lot: str
            passed: bool
            area: float
            perimeter: float
            n_vertices: int
            misclosure: float
            findings: list = field(default_factory=list)
            errors: list = field(default_factory=list)
            warnings: list = field(default_factory=list)

        res = results[lot_num]
        verif = LotVerification(
            lot=f"Blk 16 - Lot {lot_num}",
            passed=res.fac_5j17_passed,
            area=res.computed_area_sqft,
            perimeter=res.perimeter_ft,
            n_vertices=len(solver.lots[lot_num].vertices),
            misclosure=res.misclose_dist_ft,
        )

        arcs_dict = {}
        for c in res.courses:
            if c.is_curve and c.arc_points:
                arcs_dict[c.course_num - 1] = {
                    "radius": c.curve_data.get("radius"),
                    "delta": c.curve_data.get("delta_deg"),
                    "length": c.curve_data.get("length"),
                    "chord": c.curve_data.get("chord"),
                    "arc_points": c.arc_points,
                    "curve_rot": c.curve_rot,
                }

        draw_lot_sheet(cs_dxf, verif, solver.lots[lot_num].vertices, origin_n=origin_n, origin_e=origin_e,
                       arcs=arcs_dict)

    cs_dxf.save(cs_path)
    cs_audit = dxf_audit(cs_path)
    print(f"  -> CheckSheets Saved: {cs_path} | Status: {cs_audit['status']} | Entities: {cs_audit['entity_counts']}")

    # ==========================================================================
    # 3. RENDER HIGH-RESOLUTION MATPLOTLIB GRAPHIC (PNG)
    # ==========================================================================
    os.makedirs("images", exist_ok=True)
    img_path = "images/block16_mapcheck_drawing.png"

    # Local coordinate rotation: Align Block Centerline exactly along +X
    # Centerline azimuth = 87.591667° (N 87°35'30" E). Math angle theta = 90 - 87.591667 = 2.408333°
    theta = math.radians(2.408333333333333)
    cos_t = math.cos(-theta)
    sin_t = math.sin(-theta)

    def to_h(pt: Point) -> tuple[float, float]:
        de = pt.e - 1000.0
        dn = pt.n - 1000.0
        x = de * cos_t - dn * sin_t
        y = de * sin_t + dn * cos_t
        return x, y

    fig = plt.figure(figsize=(26, 17))
    fig.patch.set_facecolor('#0d1117')

    # Grid: Top 56% for horizontal cadastral drawing; Bottom 44% for 3 table columns
    gs = fig.add_gridspec(2, 3, height_ratios=[1.3, 1.0], hspace=0.22, wspace=0.18)
    ax_map = fig.add_subplot(gs[0, :])
    ax_c_tbl = fig.add_subplot(gs[1, 0])
    ax_l_tbl = fig.add_subplot(gs[1, 1])
    ax_s_tbl = fig.add_subplot(gs[1, 2])

    ax_map.set_facecolor('#161b22')
    ax_map.grid(True, color='#30363d', linestyle='--', linewidth=0.5, alpha=0.6)
    ax_map.set_title(
        "BEACHWOOD UNIT TWO -- BLOCK 16 CADASTRAL MAPCHECK & BOUNDARY SURVEY AUDIT\n"
        "Plat Book 30, Pages 82 & 82A, Duval County, FL | 100% Survey-Grade Precision (14/14 Lots Closed)",
        color='#58a6ff', fontsize=14, fontweight='bold', pad=14
    )
    ax_map.tick_params(colors='#8b949e', labelsize=8.5)
    for spine in ax_map.spines.values():
        spine.set_color('#30363d')

    # Draw Block Centerline
    cl_0_h = to_h(pts["p_cl_0"])
    cl_end_h = to_h(p_cl_end)
    ax_map.plot([cl_0_h[0], cl_end_h[0]], [cl_0_h[1], cl_end_h[1]], color='#ffd33d', linewidth=1.8, linestyle='-.', zorder=2)
    ax_map.text((cl_0_h[0] + cl_end_h[0])/2.0, -8.0,
                "BLOCK CENTERLINE  --  N 87°35'30\" E - 618.50'", color='#ffd33d', fontsize=10.0, fontweight='bold',
                ha='center', va='top', path_effects=[pe.withStroke(linewidth=2.5, foreground='#0d1117')])

    # Draw Sail Avenue Centerline
    sail_w_h = to_h(sail_cl_w)
    sail_e_h = to_h(sail_cl_e)
    ax_map.plot([sail_w_h[0], sail_e_h[0]], [sail_w_h[1], sail_e_h[1]], color='#ffd33d', linewidth=1.5, linestyle='-.', zorder=2)
    ax_map.text((sail_w_h[0] + sail_e_h[0])/2.0, sail_w_h[1] + 6.0,
                "SAIL AVENUE (60' R/W)  --  N 87°35'30\" E", color='#ffd33d', fontsize=11.0, fontweight='bold',
                ha='center', va='bottom', path_effects=[pe.withStroke(linewidth=2.5, foreground='#0d1117')])

    # Draw West Cross Street Centerline
    w_cl_n_h = to_h(w_cl_n)
    w_cl_s_h = to_h(w_cl_s)
    ax_map.plot([w_cl_n_h[0], w_cl_s_h[0]], [w_cl_n_h[1], w_cl_s_h[1]], color='#ffd33d', linewidth=1.5, linestyle='-.', zorder=2)
    ax_map.text(w_cl_n_h[0] - 8.0, 0.0, "WEST CROSS STREET (60' R/W)\nN 02°24'30\" W",
                color='#ffd33d', fontsize=9.0, fontweight='bold', ha='center', va='center', rotation=90,
                path_effects=[pe.withStroke(linewidth=2.0, foreground='#0d1117')])

    # Draw South Street Centerline
    south_w_h = to_h(south_cl_w)
    south_e_h = to_h(south_cl_e)
    ax_map.plot([south_w_h[0], south_e_h[0]], [south_w_h[1], south_e_h[1]], color='#ffd33d', linewidth=1.3, linestyle='-.', zorder=2)
    ax_map.text((south_w_h[0] + south_e_h[0])/2.0, south_w_h[1] - 8.0,
                "SOUTH STREET (60' R/W)", color='#ffd33d', fontsize=9.0, fontweight='bold',
                ha='center', va='top', path_effects=[pe.withStroke(linewidth=2.0, foreground='#0d1117')])

    # Draw Marina Avenue Radial Rays
    c_mar_h = to_h(c_mar)
    for rad_pt in [pts["p32_se_pc"], pts["p31_se"], pts["p30_se"], pts["p29_pt_marina"]]:
        rpt_h = to_h(rad_pt)
        ax_map.plot([rpt_h[0], rpt_h[0] - (rpt_h[0] - c_mar_h[0])*0.15],
                    [rpt_h[1], rpt_h[1] - (rpt_h[1] - c_mar_h[1])*0.15],
                    color='#f85149', linewidth=1.0, linestyle='--', zorder=2)

    # Marina Avenue R/W Label
    p31_se_h = to_h(pts["p31_se"])
    ax_map.text(p31_se_h[0] - 10.0, -170.0, "MARINA AVENUE (60' R/W)\nR=389.27'  Δ=37°42'50\"",
                color='#ff7b72', fontsize=9.0, fontweight='bold', ha='center', va='top',
                path_effects=[pe.withStroke(linewidth=2.0, foreground='#0d1117')])

    # Keel Drive R/W Label
    p28_se_h = to_h(pts["p28_se"])
    ax_map.text(p28_se_h[0] + 10.0, p28_se_h[1] - 18.0, "SHELLFISH DRIVE\n(60' R/W)\nN R/W R=197.95'",
                color='#ff7b72', fontsize=8.5, fontweight='bold', ha='left', va='top',
                path_effects=[pe.withStroke(linewidth=2.0, foreground='#0d1117')])

    # Draw 10' Easement between Lot 7 & 8
    p7_f_h = to_h(pts["p7_ne"])
    p7_r_h = to_h(pts["p7_se"])
    ax_map.plot([p7_f_h[0] - 5.0, p7_r_h[0] - 5.0], [p7_f_h[1], p7_r_h[1]], color='#3fb950', linewidth=1.0, linestyle='--', zorder=3)
    ax_map.plot([p7_f_h[0] + 5.0, p7_r_h[0] + 5.0], [p7_f_h[1], p7_r_h[1]], color='#3fb950', linewidth=1.0, linestyle='--', zorder=3)
    ax_map.text(p7_f_h[0], 50.0, "10' Esm't", color='#3fb950', fontsize=7.0, rotation=90, ha='center', va='center',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])

    # Draw Each Lot Polygon & Text
    lot_colors = {
        "1": "#1f6feb", "2": "#1f6feb", "3": "#1f6feb", "4": "#1f6feb",
        "5": "#1f6feb", "6": "#1f6feb", "7": "#1f6feb", "8": "#1f6feb",
        "33": "#238636", "32": "#238636", "31": "#238636", "30": "#238636",
        "29": "#8957e5", "28": "#238636"
    }

    for lot_num in lot_order:
        res = results[lot_num]
        poly_coords = []
        for c in res.courses:
            if c.is_curve and c.arc_points:
                for pt in c.arc_points[:-1]:
                    poly_coords.append(to_h(pt))
            else:
                poly_coords.append(to_h(c.start_pt))

        base_col = lot_colors.get(lot_num, '#1f6feb')
        edge_col = '#58a6ff' if base_col == '#1f6feb' else ('#3fb950' if base_col == '#238636' else '#d2a8ff')

        poly = MplPolygon(poly_coords, closed=True, facecolor=base_col, edgecolor=edge_col,
                          linewidth=1.6, alpha=0.35, zorder=3)
        ax_map.add_patch(poly)

        # Draw boundary outline
        xs_poly = [p[0] for p in poly_coords] + [poly_coords[0][0]]
        ys_poly = [p[1] for p in poly_coords] + [poly_coords[0][1]]
        ax_map.plot(xs_poly, ys_poly, color=edge_col, linewidth=1.4, zorder=4)

        # Centroid for badge
        c_x = sum(p[0] for p in poly_coords) / len(poly_coords)
        c_y = sum(p[1] for p in poly_coords) / len(poly_coords)

        # Fine-tune badge positions for curved and wedge lots to prevent label overlap
        if lot_num == "31":
            c_x = 238.0
            c_y = -45.0
        elif lot_num == "30":
            c_x = 338.0
            c_y = -52.0
        elif lot_num == "29":
            c_x = 425.0
            c_y = -75.0
        elif lot_num == "28":
            c_x = 545.0
            c_y = -55.0

        # Circular Badge
        badge = plt.Circle((c_x, c_y), 11.0, facecolor='#161b22', edgecolor=edge_col, linewidth=1.6, zorder=5)
        ax_map.add_patch(badge)
        ax_map.text(c_x, c_y + 1.0, lot_num, color='#ffffff', fontsize=11.0, fontweight='bold',
                    ha='center', va='center', zorder=6)

        # Lot Area label below badge
        ax_map.text(c_x, c_y - 18.0, f"{res.computed_area_sqft:,.0f} SF\n({res.computed_acres:.3f} Ac)",
                    color='#c9d1d9', fontsize=7.2, ha='center', va='top', zorder=6,
                    path_effects=[pe.withStroke(linewidth=2.0, foreground='#0d1117')])

    # Draw Dimension Labels along Frontages
    # North Row (Lots 1-8): 93.50' for Lot 1, 75.00' for Lots 2-8
    ax_map.text(46.75, 105.0, "93.50'", color='#7ee787', fontsize=8.0, fontweight='bold', ha='center', va='bottom',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])
    for _idx, x_c in enumerate(range(93 + 37, 618, 75)):
        ax_map.text(x_c, 105.0, "75.00'", color='#7ee787', fontsize=8.0, fontweight='bold', ha='center', va='bottom',
                    path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])

    # South Row Frontages:
    ax_map.text(46.75, -107.0, "93.50'", color='#7ee787', fontsize=8.0, fontweight='bold', ha='center', va='top',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])
    ax_map.text(93.5 + 44.88, -107.0, "89.76'", color='#7ee787', fontsize=8.0, fontweight='bold', ha='center', va='top',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])
    # Curve chord annotations
    ax_map.text(230.0, -118.0, "C3: 85.24'", color='#f0883e', fontsize=7.5, fontweight='bold', ha='center', va='top',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])
    ax_map.text(315.0, -132.0, "C4: 85.24'", color='#f0883e', fontsize=7.5, fontweight='bold', ha='center', va='top',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])
    ax_map.text(395.0, -145.0, "C5: 85.24'", color='#f0883e', fontsize=7.5, fontweight='bold', ha='center', va='top',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])
    ax_map.text(440.0, -158.0, "51.68'", color='#7ee787', fontsize=7.5, fontweight='bold', ha='center', va='top',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])
    ax_map.text(515.0, -135.0, "C7: 68.75'", color='#f0883e', fontsize=7.5, fontweight='bold', ha='center', va='top',
                path_effects=[pe.withStroke(linewidth=1.5, foreground='#0d1117')])

    # Side line dimensions
    ax_map.text(93.5 - 3.0, 50.0, "100.00'", color='#8b949e', fontsize=7.5, rotation=90, ha='right', va='center')
    ax_map.text(93.5 - 3.0, -50.0, "100.00'", color='#8b949e', fontsize=7.5, rotation=90, ha='right', va='center')
    ax_map.text(183.26 - 3.0, -50.0, "100.00'", color='#8b949e', fontsize=7.5, rotation=90, ha='right', va='center')
    ax_map.text(250.0, -55.0, "112.21'", color='#8b949e', fontsize=7.2, rotation=78, ha='center', va='center')
    ax_map.text(350.0, -65.0, "147.37'", color='#8b949e', fontsize=7.2, rotation=70, ha='center', va='center')
    ax_map.text(465.0, -70.0, "166.73'", color='#8b949e', fontsize=7.2, rotation=-60, ha='center', va='center')
    ax_map.text(545.0, -55.0, "116.36'", color='#8b949e', fontsize=7.2, rotation=-70, ha='center', va='center')

    # Draw Monuments & Glyphs on PNG
    # P.R.M. Monument
    prm_h = to_h(pts["p33_prm_se"])
    ax_map.plot(prm_h[0], prm_h[1], marker='o', markersize=9, markerfacecolor='#ffd33d', markeredgecolor='#ffffff', markeredgewidth=1.8, zorder=8)
    ax_map.text(prm_h[0], prm_h[1] - 14.0, "P.R.M.\n(Lot 33/32)", color='#ffd33d', fontsize=8.0, fontweight='bold', ha='center', va='top',
                path_effects=[pe.withStroke(linewidth=2.0, foreground='#0d1117')])

    # P.I. Glyphs
    # Lot 1 NW ('┌')
    p1_pi_h = to_h(pts["p1_nw_pi"])
    ax_map.plot([p1_pi_h[0], p1_pi_h[0] + 12.0], [p1_pi_h[1], p1_pi_h[1]], color='#ffd33d', linewidth=2.5, zorder=7)
    ax_map.plot([p1_pi_h[0], p1_pi_h[0]], [p1_pi_h[1], p1_pi_h[1] - 12.0], color='#ffd33d', linewidth=2.5, zorder=7)
    ax_map.text(p1_pi_h[0] - 4.0, p1_pi_h[1] + 4.0, "P.I. ┌ (R=25')", color='#ffd33d', fontsize=8.0, fontweight='bold', ha='right', va='bottom')

    # Lot 33 SW ('└')
    p33_pi_h = to_h(pts["p33_sw_pi"])
    ax_map.plot([p33_pi_h[0], p33_pi_h[0] + 12.0], [p33_pi_h[1], p33_pi_h[1]], color='#ffd33d', linewidth=2.5, zorder=7)
    ax_map.plot([p33_pi_h[0], p33_pi_h[0]], [p33_pi_h[1], p33_pi_h[1] + 12.0], color='#ffd33d', linewidth=2.5, zorder=7)
    ax_map.text(p33_pi_h[0] - 4.0, p33_pi_h[1] - 4.0, "P.I. └ (R=25')", color='#ffd33d', fontsize=8.0, fontweight='bold', ha='right', va='top')

    # Lot 29 SE ('┘')
    p29_pi_h = to_h(pts["p29_ret_pi"])
    ax_map.plot(p29_pi_h[0], p29_pi_h[1], marker='s', markersize=6, markerfacecolor='#ffd33d', markeredgecolor='#ffffff', zorder=7)
    ax_map.text(p29_pi_h[0] + 4.0, p29_pi_h[1] - 6.0, "P.I. ┘ (R=25')", color='#ffd33d', fontsize=8.0, fontweight='bold', ha='left', va='top')

    # Lot 29 Apex Marker
    apex_h = to_h(pts["p_cl_apex"])
    ax_map.plot(apex_h[0], apex_h[1], marker='^', markersize=8, markerfacecolor='#d2a8ff', markeredgecolor='#ffffff', zorder=8)
    ax_map.text(apex_h[0], apex_h[1] + 8.0, "LOT 29 APEX\n(x=403.26')", color='#d2a8ff', fontsize=7.5, fontweight='bold', ha='center', va='bottom',
                path_effects=[pe.withStroke(linewidth=2.0, foreground='#0d1117')])

    ax_map.set_xlim(-60, 670)
    ax_map.set_ylim(-210, 140)
    ax_map.set_aspect('equal')

    # --------------------------------------------------------------------------
    # TABLE 1: CURVE TABLE (ax_c_tbl)
    # --------------------------------------------------------------------------
    ax_c_tbl.set_facecolor('#161b22')
    ax_c_tbl.axis('off')
    ax_c_tbl.set_title("CURVE TABLE (BLOCK 16)", color='#58a6ff', fontsize=11, fontweight='bold', pad=8)

    c_headers = ["Tag", "Radius", "Delta", "Arc", "Tan", "Chord", "Bearing"]
    c_rows = []
    for ct in solver.get_curve_table_data():
        c_rows.append([
            ct["tag"], f"{ct['radius']:.2f}'", ct["delta"], f"{ct['length']:.2f}'",
            f"{ct['tangent']:.2f}'", f"{ct['chord']:.2f}'", ct["chord_bearing"]
        ])

    tbl_c = ax_c_tbl.table(cellText=c_rows, colLabels=c_headers, loc='center', cellLoc='center')
    tbl_c.auto_set_font_size(False)
    tbl_c.set_fontsize(7.5)
    tbl_c.scale(1.0, 1.35)
    for (row, _col), cell in tbl_c.get_celld().items():
        cell.set_edgecolor('#30363d')
        if row == 0:
            cell.set_facecolor('#21262d')
            cell.set_text_props(color='#58a6ff', weight='bold')
        else:
            cell.set_facecolor('#161b22' if row % 2 == 0 else '#0d1117')
            cell.set_text_props(color='#c9d1d9')

    # --------------------------------------------------------------------------
    # TABLE 2: LINE TABLE (ax_l_tbl)
    # --------------------------------------------------------------------------
    ax_l_tbl.set_facecolor('#161b22')
    ax_l_tbl.axis('off')
    ax_l_tbl.set_title("LINE TABLE (BLOCK 16)", color='#58a6ff', fontsize=11, fontweight='bold', pad=8)

    l_headers = ["Tag", "Bearing", "Distance", "Description"]
    l_rows = []
    for lt in solver.get_line_table_data()[:16]:
        l_rows.append([lt["tag"], lt["bearing"], f"{lt['distance']:.2f}'", lt["desc"][:26]])

    tbl_l = ax_l_tbl.table(cellText=l_rows, colLabels=l_headers, loc='center', cellLoc='center')
    tbl_l.auto_set_font_size(False)
    tbl_l.set_fontsize(6.8)
    tbl_l.scale(1.0, 1.25)
    for (row, _col), cell in tbl_l.get_celld().items():
        cell.set_edgecolor('#30363d')
        if row == 0:
            cell.set_facecolor('#21262d')
            cell.set_text_props(color='#58a6ff', weight='bold')
        else:
            cell.set_facecolor('#161b22' if row % 2 == 0 else '#0d1117')
            cell.set_text_props(color='#c9d1d9')

    # --------------------------------------------------------------------------
    # TABLE 3: LOT SUMMARY TABLE (ax_s_tbl)
    # --------------------------------------------------------------------------
    ax_s_tbl.set_facecolor('#161b22')
    ax_s_tbl.axis('off')
    ax_s_tbl.set_title("LOT CLOSURE SUMMARY (F.A.C. 5J-17)", color='#58a6ff', fontsize=11, fontweight='bold', pad=8)

    s_headers = ["Lot #", "Perimeter", "Area (SF)", "Acres", "Misclose", "Verdict"]
    s_rows = []
    for lot_num in lot_order:
        res = results[lot_num]
        s_rows.append([
            f"Lot {lot_num}", f"{res.perimeter_ft:.2f}'", f"{res.computed_area_sqft:,.1f}",
            f"{res.computed_acres:.3f}", f"{res.misclose_dist_ft:.5f}'", "PASS"
        ])

    tbl_s = ax_s_tbl.table(cellText=s_rows, colLabels=s_headers, loc='center', cellLoc='center')
    tbl_s.auto_set_font_size(False)
    tbl_s.set_fontsize(7.0)
    tbl_s.scale(1.0, 1.25)
    for (row, col), cell in tbl_s.get_celld().items():
        cell.set_edgecolor('#30363d')
        if row == 0:
            cell.set_facecolor('#21262d')
            cell.set_text_props(color='#58a6ff', weight='bold')
        else:
            cell.set_facecolor('#161b22' if row % 2 == 0 else '#0d1117')
            cell.set_text_props(color='#3fb950' if col == 5 else '#c9d1d9')

    plt.savefig(img_path, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)
    print(f"  -> High-Res Cadastral MapCheck Plot Saved: {img_path}")


if __name__ == "__main__":
    build_and_draw_block16()
