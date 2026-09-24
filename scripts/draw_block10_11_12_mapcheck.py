"""
scripts/draw_block10_11_12_mapcheck.py -- Draw Survey MapChecks & Generate DXF
for Blocks 10, 11 and 12 (the portion of each west of the Beachwood Unit One
matchline).

Plat: Beachwood Unit Two, Plat Book 30, Page 82, Duval County, FL.

Block 10: Lots 9-13 (5 lots, fronting Surfwood Ave).
Block 11: Lots 12-17 (6 lots, fronting Bayou / Surfwood Ave).
Block 12: Lots 4-7 CERTIFIED (fronting the 50' drainage R/W and Bayou).
          Lots 8-10 NOT CERTIFIED -- the plat's San Salvadore Ave curve
          transition jog courses could not be transcribed with confidence
          from the scan. The one corner this reading can defend (Lot 8's
          approximate NE corner, from BeachwoodBlock12Solver.flagged_points)
          is drawn in RED, per Rule 3 -- see .claude/skills/review-plat-notes
          and engine/notes_audit.py.

Outputs:
  1. dxf/PB0030_P0082_Block10_11_12_MapCheck_claude.dxf
  2. images/block10_11_12_mapcheck_drawing.png
"""
from __future__ import annotations

import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.cogo_block import (
    BeachwoodBlock10Solver,
    BeachwoodBlock11Solver,
    BeachwoodBlock12Solver,
)
from engine.dxf_writer import DXFWriter, writer_suffix
from engine.notes_audit import audit_solver_curves, print_audit_report


def build_and_draw():
    print("=" * 80)
    print("  GENERATING CAD DRAWINGS FOR BLOCKS 10, 11, 12 (WEST OF MATCHLINE)")
    print("  Plat Book 30, Page 82, Duval County, FL (Beachwood Unit Two)")
    print("=" * 80)

    b10 = BeachwoodBlock10Solver()
    b11 = BeachwoodBlock11Solver()
    b12 = BeachwoodBlock12Solver()

    print_audit_report(audit_solver_curves(b10), header="BLOCK 10 SOLVER CURVE AUDIT")
    print_audit_report(audit_solver_curves(b11), header="BLOCK 11 SOLVER CURVE AUDIT")
    print_audit_report(audit_solver_curves(b12), header="BLOCK 12 SOLVER CURVE AUDIT")

    b10.generate_report()
    b11.generate_report()
    b12.generate_report()
    print("Reports written: data/block10_mapcheck_report.txt, block11_mapcheck_report.txt, block12_mapcheck_report.txt")

    # Each solver uses its own independent local origin (matching every other
    # Beachwood*Solver in this engine -- see BeachwoodBlock13Solver's
    # docstring), so they don't share one coordinate system. For this
    # combined drawing only (never for the certified per-lot geometry
    # itself), shift Block 11 and Block 12 north by each street's 60' R/W
    # width so the three blocks plot in their true relative positions
    # instead of stacking on top of each other.
    ROW_WIDTH = 60.0

    def shift(pt, dn, de):
        return type(pt)(pt.n + dn, pt.e + de)

    d11_n = (b10.points["p13_nw"].n + ROW_WIDTH) - b11.points["p14_sw"].n
    d11_e = b10.points["p13_nw"].e - b11.points["p14_sw"].e
    d12_n = (b11.points["p15_nw"].n + d11_n + ROW_WIDTH) - b12.points["p5_sw"].n
    d12_e = (b11.points["p15_nw"].e + d11_e) - b12.points["p5_sw"].e
    offsets = {"10": (0.0, 0.0), "11": (d11_n, d11_e), "12": (d12_n, d12_e)}

    # ==========================================================================
    # 1. DXF
    # ==========================================================================
    os.makedirs("dxf", exist_ok=True)
    dxf_path = f"dxf/PB0030_P0082_Block10_11_12_MapCheck{writer_suffix()}.dxf"
    dxf = DXFWriter()
    dxf.add_layer("LOT_LINE", "cyan", "CONTINUOUS")
    dxf.add_layer("BOUNDARY", "white", "CONTINUOUS")
    dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
    dxf.add_layer("DIM-LABELS", "green", "CONTINUOUS")
    dxf.add_layer("FLAGGED", "red", "DASHED")
    dxf.add_layer("FLAGGED-TEXT", "red", "CONTINUOUS")

    def draw_block(solver, lot_order, block_id):
        dn, de = offsets[block_id]
        for num in lot_order:
            lot = solver.lots[num]
            coords = [(v.e + de, v.n + dn) for v in lot.vertices]
            dxf.polyline(coords, layer="LOT_LINE", closed=True)
            cx = sum(c[0] for c in coords) / len(coords)
            cy = sum(c[1] for c in coords) / len(coords)
            dxf.text((cx, cy), f"BLK{block_id}\nLOT {num}", height=3.0, layer="TEXT-LABELS")

    draw_block(b10, ["13", "12", "11", "10", "9"], "10")
    draw_block(b11, ["15", "16", "17", "14", "13", "12"], "11")
    draw_block(b12, ["7", "6", "5", "4"], "12")

    # Flagged point(s) -- Block 12 Lots 8-10, drawn in red, not certified.
    dn12, de12 = offsets["12"]
    for name, info in b12.flagged_points.items():
        p = info["point"]
        px, py = p.e + de12, p.n + dn12
        dxf.point((px, py), layer="FLAGGED")
        dxf.text((px + 2, py + 2), f"{name}\nNOT CERTIFIED - SEE NOTES", height=2.5, layer="FLAGGED-TEXT")
        # Dashed tie showing how the point was constructed, from Lot 7's NE corner.
        p7_ne = b12.points["p7_ne"]
        dxf.line((p7_ne.e + de12, p7_ne.n + dn12), (px, py), layer="FLAGGED")

    dxf.save(dxf_path)
    print(f"Saved: {dxf_path}")

    # ==========================================================================
    # 2. PNG
    # ==========================================================================
    fig, ax = plt.subplots(figsize=(20, 24), dpi=150)

    def plot_lot(solver, num, block_id, facecolor):
        dn, de = offsets[block_id]
        lot = solver.lots[num]
        coords = [(v.e + de, v.n + dn) for v in lot.vertices]
        poly = MplPolygon(coords, closed=True, fill=True, facecolor=facecolor,
                           edgecolor="black", linewidth=1.4, alpha=0.5)
        ax.add_patch(poly)
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        ax.text(cx, cy, f"BLK {block_id}\nLOT {num}", ha="center", va="center",
                fontsize=9, fontweight="bold",
                path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])
        n = len(coords)
        for i in range(n):
            p1, p2 = coords[i], coords[(i + 1) % n]
            dist = ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5
            mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
            ax.text(mx, my, f"{dist:.2f}'", ha="center", va="center", fontsize=6.5,
                    color="darkgreen",
                    path_effects=[pe.withStroke(linewidth=2, foreground="white")])

    for num in ["13", "12", "11", "10", "9"]:
        plot_lot(b10, num, "10", "lightblue")
    for num in ["15", "16", "17", "14", "13", "12"]:
        plot_lot(b11, num, "11", "lightyellow")
    for num in ["7", "6", "5", "4"]:
        plot_lot(b12, num, "12", "lightgreen")

    # Flagged / not-certified area, in red.
    dn12, de12 = offsets["12"]
    for _name, info in b12.flagged_points.items():
        p = info["point"]
        px, py = p.e + de12, p.n + dn12
        p7_ne = b12.points["p7_ne"]
        p7x, p7y = p7_ne.e + de12, p7_ne.n + dn12
        p8_sw = b12.points["p8_sw"]
        p8x, p8y = p8_sw.e + de12, p8_sw.n + dn12
        ax.plot([p8x, px], [p8y, py], color="red", linestyle="--", linewidth=1.5)
        ax.plot(px, py, marker="x", color="red", markersize=12, markeredgewidth=3)
        ax.text(px + 3, py + 3,
                "NOT CERTIFIED\nLots 8, 9, 10 (Block 12)\napprox. corner via line\nintersection -- see report",
                color="red", fontsize=8, fontweight="bold",
                path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])
        ax.annotate("", xy=(px, py), xytext=(p7x, p7y),
                    arrowprops={"arrowstyle": "->", "color": "red", "linewidth": 1.5})

    ax.set_title(
        "Beachwood Unit Two -- Blocks 10, 11, 12 (West of Matchline)\n"
        "Plat Book 30, Page 82, Duval County, FL\n"
        "Block 12 Lots 8-10 NOT CERTIFIED -- see red flag and mapcheck report",
        fontsize=13, fontweight="bold")
    ax.set_xlabel("Easting (local, ft)")
    ax.set_ylabel("Northing (local, ft)")
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.margins(0.08)
    ax.grid(True, linestyle=":", alpha=0.4)

    os.makedirs("images", exist_ok=True)
    png_path = "images/block10_11_12_mapcheck_drawing.png"
    plt.savefig(png_path, bbox_inches="tight")
    print(f"Saved: {png_path}")


if __name__ == "__main__":
    build_and_draw()
