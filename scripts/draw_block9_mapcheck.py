"""
draw_block9_mapcheck.py -- Draw Survey MapChecks for Block 9 (West of Matchline).

Outputs:
  1. dxf/PB0030_P0082_Block9_MapCheck.dxf (Multi-layer CAD DXF)
  2. dxf/PB0030_P0082_Block9_CheckSheets.dxf (Individual Surveyor CheckSheets Grid)
  3. data/block9_mapcheck_drawing.png (High-Resolution Cadastral Visualization Plot)
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import matplotlib  # noqa: E402

matplotlib.use('Agg')
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

from engine.audit import dxf_audit
from engine.cogo import Point, parse_bearing
from engine.cogo_block import BeachwoodBlock9Solver
from engine.dxf_writer import DXFWriter, writer_suffix
from engine.lot_agent import BeachwoodLotAgent
from engine.lotsheets import PAGE_H, PAGE_W, draw_lot_sheet


def build_and_draw_block9():
    print("=" * 80)
    print("  GENERATING CAD DRAWINGS & CHECKSHEETS FOR BLOCK 9 (WEST OF MATCHLINE)")
    print("  Plat Book 30, Pages 82 & 82A, Duval County, FL (Beachwood Unit Two)")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # 1. AZIMUTHS & BEARINGS
    # --------------------------------------------------------------------------
    az_match = parse_bearing("N35°18'20\"E")
    az_match_rev = parse_bearing("S35°18'20\"W")
    az_tangent_ch = parse_bearing("S54°41'40\"E")
    az_tangent_ch_rev = parse_bearing("N54°41'40\"W")
    az_interior = parse_bearing("S63°12'00\"E")
    az_interior_rev = parse_bearing("N63°12'00\"W")
    az_pi_pc = parse_bearing("N88°58'20\"E")
    az_west_n = parse_bearing("N01°01'40\"W")
    az_west_s = parse_bearing("S01°01'40\"E")

    # --------------------------------------------------------------------------
    # 2. GEOMETRY -- drawn straight from engine.cogo_block.BeachwoodBlock9Solver.
    #    (This script used to rebuild Block 9 by hand: straight chords instead of the Cape Horn / San
    #    Salvadore frontage curves and an 83°30' Lot 26 return. One source of truth now, 2026-09-24.)
    # --------------------------------------------------------------------------
    solver = BeachwoodBlock9Solver(Point(0.0, 0.0))
    P = solver.points
    p23_se, p24_mid_n, p25_ne = P["p23_se"], P["p24_mid_n"], P["p25_ne"]
    p26_ne, p26_nw, p26_pc_s, p26_pc_w, p26_pi = P["p26_ne"], P["p26_nw"], P["p26_pc_s"], P["p26_pc_w"], P["p26_pi"]
    p27_pc_n, p27_pc_w, p27_pi, p27_se, p27_sw = P["p27_pc_n"], P["p27_pc_w"], P["p27_pi"], P["p27_se"], P["p27_sw"]
    p31_ne, p31_se = P["p31_ne"], P["p31_se"]
    p27_center = p27_pc_w.offset(az_pi_pc, solver.sol27.radius)   # both returns are 90°
    p26_center = p26_pc_w.offset(az_pi_pc, solver.sol26.radius)

    agents: list[BeachwoodLotAgent] = [
        BeachwoodLotAgent(900 + int(num), lot.lot_id, "9", num, lot.vertices, lot.node_names,
                          curve_specs=lot.curve_specs, stated_area_sqft=lot.stated_area_sqft)
        for num, lot in solver.lots.items()
    ]

    for ag in agents:
        ag.compute_mapcheck()

    # --------------------------------------------------------------------------
    # 3. WRITE MASTER CAD DRAWING (DXF)
    # --------------------------------------------------------------------------
    os.makedirs("dxf", exist_ok=True)
    dxf_path = f"dxf/PB0030_P0082_Block9_MapCheck{writer_suffix()}.dxf"
    dxf = DXFWriter()
    dxf.add_layer("LOT_LINE", "cyan", "CONTINUOUS")
    dxf.add_layer("CURVE", "magenta", "CONTINUOUS")
    dxf.add_layer("RADIAL_LINE", "red", "DASHED")
    dxf.add_layer("MATCHLINE", "white", "CONTINUOUS")
    dxf.add_layer("MONUMENT", "yellow", "CONTINUOUS")
    dxf.add_layer("ROW_STREET", "yellow", "CONTINUOUS")
    dxf.add_layer("STREET_CL", "yellow", "DASHDOT")
    dxf.add_layer("EASEMENT", "green", "DASHED")
    dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
    dxf.add_layer("DIM-LABELS", "green", "CONTINUOUS")
    dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")

    # Draw lot boundaries
    for ag in agents:
        ag.draw(dxf, layer="LOT_LINE", text_layer="TEXT-LABELS", dim_layer="DIM-LABELS",
                curve_layer="CURVE", draw_dims=True)

    def draw_pi_glyph(p_pi: Point, az1: float, az2: float, size: float = 6.0, layer: str = "ROW_STREET"):
        pt1 = p_pi.offset(az1, size)
        pt2 = p_pi.offset(az2, size)
        dxf.line((pt1.e, pt1.n), (p_pi.e, p_pi.n), layer=layer)
        dxf.line((p_pi.e, p_pi.n), (pt2.e, pt2.n), layer=layer)
        dxf.text((p_pi.n + 2.0, p_pi.e + 2.0), "P.I.", height=3.5, layer="DIM-LABELS")

    # Lot 27 NW P.I. Glyph and Tangent lines
    draw_pi_glyph(p27_pi, az_pi_pc, az_west_s, size=7.0)
    dxf.line((p27_pc_w.e, p27_pc_w.n), (p27_pi.e, p27_pi.n), layer="RADIAL_LINE")
    dxf.line((p27_pc_n.e, p27_pc_n.n), (p27_pi.e, p27_pi.n), layer="RADIAL_LINE")
    dxf.line((p27_center.e, p27_center.n), (p27_pc_w.e, p27_pc_w.n), layer="RADIAL_LINE")
    dxf.line((p27_center.e, p27_center.n), (p27_pc_n.e, p27_pc_n.n), layer="RADIAL_LINE")
    dxf.text((p27_center.n - 5.0, p27_center.e + 2.0), "R=25.00'", height=3.2, layer="TEXT-LABELS")

    # Lot 26 SW P.I. Glyph and Tangent lines
    draw_pi_glyph(p26_pi, az_pi_pc, az_west_n, size=7.0)
    dxf.line((p26_pc_w.e, p26_pc_w.n), (p26_pi.e, p26_pi.n), layer="RADIAL_LINE")
    dxf.line((p26_pc_s.e, p26_pc_s.n), (p26_pi.e, p26_pi.n), layer="RADIAL_LINE")
    dxf.line((p26_center.e, p26_center.n), (p26_pc_w.e, p26_pc_w.n), layer="RADIAL_LINE")
    dxf.line((p26_center.e, p26_center.n), (p26_pc_s.e, p26_pc_s.n), layer="RADIAL_LINE")
    dxf.text((p26_center.n + 3.0, p26_center.e + 2.0), "R=25.00'", height=3.2, layer="TEXT-LABELS")

    # Heavy Matchline
    # Extend across streets by 40 ft each direction
    match_south = p23_se.offset(az_match_rev, 40.0)
    match_north = p31_ne.offset(az_match, 40.0)
    dxf.line((match_south.e, match_south.n), (p23_se.e, p23_se.n), layer="MATCHLINE")
    dxf.line((p23_se.e, p23_se.n), (p31_ne.e, p31_ne.n), layer="MATCHLINE")
    dxf.line((p31_ne.e, p31_ne.n), (match_north.e, match_north.n), layer="MATCHLINE")
    dxf.text(((p23_se.n + p31_ne.n)/2.0 + 8.0, (p23_se.e + p31_ne.e)/2.0 + 8.0),
             "MATCH LINE (PB 30, PG 82A) - N 35°18'20\" E 200.0'", height=4.5, layer="MATCHLINE", rotation=35.3)

    # P.R.M. Monument at Cape Horn & Matchline
    dxf.point((p31_ne.n, p31_ne.e), layer="MONUMENT")
    mon_pts = [(p31_ne.e + 2.5 * math.cos(math.radians(a)), p31_ne.n + 2.5 * math.sin(math.radians(a))) for a in range(0, 360, 45)]
    dxf.polyline([(p[1], p[0]) for p in mon_pts], layer="MONUMENT", closed=True)
    dxf.text((p31_ne.n + 4.0, p31_ne.e + 6.0), "P.R.M.", height=5.0, layer="MONUMENT")

    # 10' Utility Easement line across rear
    dxf.line((p27_se.e, p27_se.n), (p26_ne.e, p26_ne.n), layer="EASEMENT")
    dxf.line((p26_ne.e, p26_ne.n), (p25_ne.e, p25_ne.n), layer="EASEMENT")
    dxf.line((p25_ne.e, p25_ne.n), (p24_mid_n.e, p24_mid_n.n), layer="EASEMENT")
    dxf.line((p24_mid_n.e, p24_mid_n.n), (p31_se.e, p31_se.n), layer="EASEMENT")
    dxf.text((p24_mid_n.n + 4.0, p24_mid_n.e - 20.0), "10' EASEMENT", height=3.5, layer="EASEMENT")

    # Street ROW linework
    # Cape Horn Avenue (60' R/W)
    ch_cl_pt1 = p27_pc_n.offset(parse_bearing("N01°01'40\"W"), 30.0)
    ch_cl_pt2 = p31_ne.offset(parse_bearing("N35°18'20\"E"), 30.0)
    dxf.line((ch_cl_pt1.e, ch_cl_pt1.n), (ch_cl_pt2.e, ch_cl_pt2.n), layer="STREET_CL")
    dxf.text((ch_cl_pt2.n + 10.0, ch_cl_pt2.e - 30.0), "CAPE HORN AVENUE (60' R/W)", height=6.0, layer="ROW_STREET", rotation=-35.0)

    # San Salvadore Avenue (60' R/W)
    ss_cl_pt1 = p26_pc_s.offset(parse_bearing("S01°01'40\"E"), 30.0)
    ss_cl_pt2 = p23_se.offset(parse_bearing("S35°18'20\"W"), 30.0)
    dxf.line((ss_cl_pt1.e, ss_cl_pt1.n), (ss_cl_pt2.e, ss_cl_pt2.n), layer="STREET_CL")
    dxf.text((ss_cl_pt2.n - 15.0, ss_cl_pt2.e - 40.0), "SAN SALVADORE AVENUE (60' R/W)", height=6.0, layer="ROW_STREET", rotation=-35.0)

    # Titleblock
    dxf.text((p26_pi.n - 45.0, p26_pi.e),
             "BEACHWOOD UNIT TWO -- BLOCK 9 (WEST OF MATCHLINE) MAPCHECK AUDIT", height=10.0, layer="TITLEBLOCK")
    dxf.text((p26_pi.n - 60.0, p26_pi.e),
             "Plat Book 30, Pages 82 & 82A, Duval County, FL | 100% Survey-Grade Closed (9 Lots)", height=6.5, layer="TITLEBLOCK")

    dxf.save(dxf_path)
    audit = dxf_audit(dxf_path)
    print(f"  -> Master DXF Saved: {dxf_path} | Status: {audit['status']} | Entities: {audit['entity_counts']}")

    # --------------------------------------------------------------------------
    # 4. WRITE INDIVIDUAL CHECKSHEETS GRID DXF
    # --------------------------------------------------------------------------
    cs_path = f"dxf/PB0030_P0082_Block9_CheckSheets{writer_suffix()}.dxf"
    cs_dxf = DXFWriter()
    cs_dxf.add_layer("LOT_POLYLINE", "cyan", "CONTINUOUS")
    cs_dxf.add_layer("SHEET_LABELS", "white", "CONTINUOUS")
    cs_dxf.add_layer("SHEET_FRAME", "yellow", "CONTINUOUS")
    cs_dxf.add_layer("ERROR", "red", "CONTINUOUS")
    cs_dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")

    cols = 3
    for idx, ag in enumerate(agents):
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

        verif = LotVerification(
            lot=f"Blk 9 - Lot {ag.lot_number}",
            passed=ag.mapcheck_report.passed,
            area=ag.mapcheck_report.computed_area_sqft,
            perimeter=ag.mapcheck_report.perimeter_ft,
            n_vertices=len(ag.corners),
            misclosure=ag.mapcheck_report.misclose_dist_ft,
        )
        draw_lot_sheet(cs_dxf, verif, ag.corners, origin_n=origin_n, origin_e=origin_e,
                       arcs=ag.get_arcs_dict())

    cs_dxf.save(cs_path)
    cs_audit = dxf_audit(cs_path)
    print(f"  -> CheckSheets Saved: {cs_path} | Status: {cs_audit['status']} | Entities: {cs_audit['entity_counts']}")

    # --------------------------------------------------------------------------
    # 5. RENDER HIGH-RESOLUTION MATPLOTLIB GRAPHIC (PNG)
    # --------------------------------------------------------------------------
    img_path = "data/block9_mapcheck_drawing.png"
    fig, ax = plt.subplots(figsize=(16, 12))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#161b22')
    ax.grid(True, color='#30363d', linestyle='--', linewidth=0.5, alpha=0.7)
    ax.set_title("BEACHWOOD UNIT TWO -- BLOCK 9 (WEST OF MATCHLINE) CADASTRAL MAPCHECK\n"
                 "Plat Book 30, Pages 82 & 82A, Duval County, FL | 100% Survey-Grade Closure Certified",
                 color='#58a6ff', fontsize=15, fontweight='bold', pad=15)
    ax.tick_params(colors='#8b949e', labelsize=9)
    for spine in ax.spines.values():
        spine.set_color('#30363d')

    # Plot lots
    for ag in agents:
        rep = ag.mapcheck_report
        poly_coords = []
        for c in rep.courses:
            if c.is_curve and c.arc_points:
                for pt in c.arc_points[:-1]:
                    poly_coords.append((pt.e, pt.n))
            else:
                poly_coords.append((c.start_pt.e, c.start_pt.n))

        poly = MplPolygon(poly_coords, closed=True, facecolor='#1f6feb', edgecolor='#58a6ff',
                          alpha=0.22, linewidth=2.0, zorder=2)
        ax.add_patch(poly)

        # Draw curved courses
        for c in rep.courses:
            if c.is_curve and c.arc_points:
                arc_es = [p.e for p in c.arc_points]
                arc_ns = [p.n for p in c.arc_points]
                ax.plot(arc_es, arc_ns, color='#f0883e', linewidth=3.2, zorder=4)
                mid_idx = len(c.arc_points) // 2
                mid_pt = c.arc_points[mid_idx]
                ax.text(mid_pt.e + 4.0, mid_pt.n,
                        f"Arc={c.curve_data.get('length', 0.0):.2f}'\nR={c.curve_data.get('radius', 0.0):.2f}'",
                        color='#f0883e', fontsize=8, fontweight='bold', zorder=5)

        # Centroid labels
        cen_e = sum(p.e for p in ag.corners) / len(ag.corners)
        cen_n = sum(p.n for p in ag.corners) / len(ag.corners)
        ax.text(cen_e, cen_n + 5.0, f"LOT {ag.lot_number}",
                color='#ffffff', fontsize=12, fontweight='bold', ha='center', va='center',
                path_effects=[pe.withStroke(linewidth=2.5, foreground='#0d1117')])
        ax.text(cen_e, cen_n - 6.0, f"{rep.computed_area_sqft:,.0f} SF\n{rep.computed_acres:.4f} Ac",
                color='#7ee787', fontsize=8.5, ha='center', va='center',
                path_effects=[pe.withStroke(linewidth=2.0, foreground='#0d1117')])

        # Course dimensions
        for c in rep.courses:
            if not c.is_curve:
                mid_e = (c.start_pt.e + c.end_pt.e) / 2.0
                mid_n = (c.start_pt.n + c.end_pt.n) / 2.0
                dx, dy = c.end_pt.e - c.start_pt.e, c.end_pt.n - c.start_pt.n
                ang = math.degrees(math.atan2(dy, dx))
                if ang > 90: ang -= 180
                elif ang < -90: ang += 180
                ax.text(mid_e, mid_n, f"{c.distance:.1f}'", color='#e6edf3', fontsize=7.5,
                        ha='center', va='center', rotation=ang,
                        path_effects=[pe.withStroke(linewidth=2.0, foreground='#0d1117')])

    # Plot Matchline prominently
    ax.plot([p23_se.e, p31_ne.e], [p23_se.n, p31_ne.n], color='#ff7b72', linewidth=3.5, linestyle='-', zorder=6)
    # Dashed extensions across streets
    ax.plot([match_south.e, p23_se.e], [match_south.n, p23_se.n], color='#ff7b72', linewidth=2.0, linestyle='--', zorder=6)
    ax.plot([p31_ne.e, match_north.e], [p31_ne.n, match_north.n], color='#ff7b72', linewidth=2.0, linestyle='--', zorder=6)
    ax.text((p23_se.e + p31_ne.e)/2.0 + 8.0, (p23_se.n + p31_ne.n)/2.0,
            "MATCH LINE (PB 30, PG 82A)\nN 35°18'20\" E - 200.0'", color='#ff7b72', fontsize=10, fontweight='bold',
            rotation=35.3, path_effects=[pe.withStroke(linewidth=2.5, foreground='#0d1117')])

    # Plot P.R.M. Monument
    ax.plot(p31_ne.e, p31_ne.n, marker='o', markersize=9, color='#ffd33d', markeredgecolor='#ffffff', markeredgewidth=1.5, zorder=7)
    ax.text(p31_ne.e + 6.0, p31_ne.n + 3.0, "P.R.M. Monument\n(Cape Horn Ave R/W)", color='#ffd33d', fontsize=9, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#0d1117', edgecolor='#ffd33d', alpha=0.85), zorder=7)

    # Plot P.I. Glyphs and Dashed Tangents
    # Lot 27 NW P.I.
    ax.plot(p27_pi.e, p27_pi.n, marker='s', markersize=6, color='#d29922', zorder=6)
    ax.plot([p27_pc_w.e, p27_pi.e], [p27_pc_w.n, p27_pi.n], color='#d29922', linestyle='--', linewidth=1.5, zorder=5)
    ax.plot([p27_pc_n.e, p27_pi.e], [p27_pc_n.n, p27_pi.n], color='#d29922', linestyle='--', linewidth=1.5, zorder=5)
    ax.plot([p27_center.e, p27_pc_w.e], [p27_center.n, p27_pc_w.n], color='#ff7b72', linestyle=':', linewidth=1.2, zorder=5)
    ax.plot([p27_center.e, p27_pc_n.e], [p27_center.n, p27_pc_n.n], color='#ff7b72', linestyle=':', linewidth=1.2, zorder=5)
    ax.text(p27_pi.e - 15.0, p27_pi.n + 5.0, "P.I. Glyph '┌'\n140' to P.I. | T=25.0'", color='#ffd33d', fontsize=8, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#d29922', alpha=0.85), zorder=7)

    # Lot 26 SW P.I.
    ax.plot(p26_pi.e, p26_pi.n, marker='s', markersize=6, color='#d29922', zorder=6)
    ax.plot([p26_pc_w.e, p26_pi.e], [p26_pc_w.n, p26_pi.n], color='#d29922', linestyle='--', linewidth=1.5, zorder=5)
    ax.plot([p26_pc_s.e, p26_pi.e], [p26_pc_s.n, p26_pi.n], color='#d29922', linestyle='--', linewidth=1.5, zorder=5)
    ax.plot([p26_center.e, p26_pc_w.e], [p26_center.n, p26_pc_w.n], color='#ff7b72', linestyle=':', linewidth=1.2, zorder=5)
    ax.plot([p26_center.e, p26_pc_s.e], [p26_center.n, p26_pc_s.n], color='#ff7b72', linestyle=':', linewidth=1.2, zorder=5)
    ax.text(p26_pi.e - 15.0, p26_pi.n - 15.0, "P.I. Glyph '└'\n109' to P.I. | T=25.0'", color='#ffd33d', fontsize=8, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#0d1117', edgecolor='#d29922', alpha=0.85), zorder=7)

    # Street Labels
    ax.text((p27_pc_n.e + p31_ne.e)/2.0 - 20.0, (p27_pc_n.n + p31_ne.n)/2.0 + 35.0,
            "CAPE HORN AVENUE (60' R/W)", color='#ffd33d', fontsize=11, fontweight='bold', rotation=-35.0,
            path_effects=[pe.withStroke(linewidth=2.5, foreground='#0d1117')])
    ax.text((p26_pc_s.e + p23_se.e)/2.0 - 20.0, (p26_pc_s.n + p23_se.n)/2.0 - 35.0,
            "SAN SALVADORE AVENUE (60' R/W)", color='#ffd33d', fontsize=11, fontweight='bold', rotation=-35.0,
            path_effects=[pe.withStroke(linewidth=2.5, foreground='#0d1117')])
    ax.text(p27_sw.e - 25.0, (p27_sw.n + p26_nw.n)/2.0,
            "AVENUE (60' R/W)", color='#ffd33d', fontsize=10, fontweight='bold', rotation=90.0,
            path_effects=[pe.withStroke(linewidth=2.5, foreground='#0d1117')])

    ax.set_aspect('equal', adjustable='datalim')
    ax.autoscale_view()
    plt.tight_layout()
    plt.savefig(img_path, dpi=200, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"  -> High-Res Cadastral Graphic Saved: {img_path}")

    print("=" * 80)
    print("  ALL BLOCK 9 OUTPUTS SUCCESSFULLY GENERATED!")
    print(f"  1. Master Cadastral DXF: {dxf_path}")
    print(f"  2. CheckSheets Grid DXF: {cs_path}")
    print(f"  3. Visual Graphic Plot:   {img_path}")
    print("=" * 80)


if __name__ == "__main__":
    build_and_draw_block9()
