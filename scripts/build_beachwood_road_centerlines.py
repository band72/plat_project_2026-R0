"""
scripts/build_beachwood_road_centerlines.py -- Complete Road Centerline Network Generator
for Beachwood Unit Two (Duval_Plat_Book_30_Page_82-2.pdf).

Generates:
1. ASCII Report: data/beachwood_road_centerlines_report.txt
2. CAD DXF: dxf/PB0030_P0082_Road_Centerlines.dxf
3. Visual Cadastral Drawing: images/beachwood_road_centerlines_drawing.png
"""

import math
import os
import sys

sys.path.insert(0, '.')
import matplotlib.pyplot as plt

from engine.audit import dxf_audit
from engine.cogo_road_centerlines import BeachwoodRoadCenterlineEngine


def main():
    print("=" * 80)
    print("  BEACHWOOD UNIT TWO -- COMPLETE ROAD CENTERLINE NETWORK PIPELINE")
    print("  Plat Book 30, Pages 82 & 82A, Duval County, FL (Duval_Plat_Book_30_Page_82-2.pdf)")
    print("=" * 80)

    # 1. Initialize Engine & Solve Geometry
    print("Solving coordinate geometry for all road centerlines and intersections...")
    engine = BeachwoodRoadCenterlineEngine(base_n=10000.0, base_e=10000.0)
    print(f"Constructed {len(engine.segments)} straight segments, {len(engine.curves)} curves, "
          f"{len(engine.intersections)} intersections, and {len(engine.assumptions)} red-line assumptions.")

    # 2. Export ASCII Technical Report
    os.makedirs('data', exist_ok=True)
    report_file = 'data/beachwood_road_centerlines_report.txt'
    report_content = engine.generate_report()
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_content)
    print(f"Saved Technical Report: {report_file}")

    # 3. Export Multi-Layer CAD DXF
    os.makedirs('dxf', exist_ok=True)
    dxf_file = 'dxf/PB0030_P0082_Road_Centerlines.dxf'
    engine.export_dxf(dxf_file)
    print(f"Saved CAD DXF: {dxf_file}")

    # 4. Run Automated DXF Audit
    audit_res = dxf_audit(dxf_file)
    print(f"DXF Audit Status: {audit_res['status']}")
    print(f"Entity Counts: {audit_res['entity_counts']}")
    print(f"Extents: X [{audit_res['extents']['min_x']:.1f}, {audit_res['extents']['max_x']:.1f}], "
          f"Y [{audit_res['extents']['min_y']:.1f}, {audit_res['extents']['max_y']:.1f}]")

    # 5. Generate High-Resolution Visual Plot with Red-Lined Assumptions
    os.makedirs('images', exist_ok=True)
    plot_file = 'images/beachwood_road_centerlines_drawing.png'
    print(f"Rendering visual drawing to {plot_file}...")

    fig, ax = plt.subplots(figsize=(20, 16), dpi=220)
    ax.set_facecolor('#0d1117')
    fig.patch.set_facecolor('#0d1117')

    # Draw straight centerline segments
    seen_labels = set()
    for seg in engine.segments:
        p1, p2 = seg.start_point, seg.end_point
        if seg.is_assumed:
            lbl = 'Assumed / Projected Centerline (RED)'
            lbl_arg = lbl if lbl not in seen_labels else ""
            if lbl_arg:
                seen_labels.add(lbl)
            # Drawn in bold RED
            ax.plot([p1.e, p2.e], [p1.n, p2.n], color='#ff3333', linestyle='--', linewidth=2.8,
                    zorder=5, label=lbl_arg)
            # Midpoint label
            mid_e, mid_n = (p1.e + p2.e)/2.0, (p1.n + p2.n)/2.0
            ax.text(mid_e, mid_n + 15.0, f"{seg.street_name}\n[RED ASSUMPTION]",
                    color='#ff5555', fontsize=8, weight='bold', ha='center', va='bottom',
                    bbox={"boxstyle": "square,pad=0.2", "facecolor": "#300000", "edgecolor": "#ff3333", "alpha": 0.8})
        else:
            lbl = 'Established Road Centerline (Plat Stated)'
            lbl_arg = lbl if lbl not in seen_labels else ""
            if lbl_arg:
                seen_labels.add(lbl)
            # Established centerline (yellow, dashed)
            ax.plot([p1.e, p2.e], [p1.n, p2.n], color='#f1e05a', linestyle='--', linewidth=2.0,
                    zorder=4, label=lbl_arg)
            # Midpoint label
            mid_e, mid_n = (p1.e + p2.e)/2.0, (p1.n + p2.n)/2.0
            ax.text(mid_e, mid_n + 8.0, f"{seg.street_name}\n({seg.bearing} - {seg.distance:.1f}')",
                    color='#e6edf3', fontsize=7.5, ha='center', va='bottom', alpha=0.85)

    # Draw centerline curves
    for cid, c in engine.curves.items():
        n_segs = 40
        pts_e, pts_n = [], []
        az_pc = math.atan2(c.pc_point.e - c.center_point.e, c.pc_point.n - c.center_point.n)
        delta_rad = math.radians(c.delta_deg) * (1.0 if c.direction == "CW" else -1.0)
        for step in range(n_segs + 1):
            ang = az_pc + delta_rad * (step / float(n_segs))
            pn = c.center_point.n + c.radius * math.cos(ang)
            pe = c.center_point.e + c.radius * math.sin(ang)
            pts_e.append(pe)
            pts_n.append(pn)

        curve_col = '#ff3333' if c.is_assumed else '#bc8cff'
        lbl = f"Centerline Curve: {c.street_name} ({cid})"
        ax.plot(pts_e, pts_n, color=curve_col, linestyle='-', linewidth=2.5, zorder=6,
                label=lbl)

        # Curve label
        mid_idx = len(pts_e) // 2
        ax.text(pts_e[mid_idx] + 20.0, pts_n[mid_idx],
                f"{c.street_name} Curve\nR={c.radius:.2f}', L={c.arc_length:.2f}'\nDelta={c.delta_deg:.2f}°",
                color='#d2a8ff', fontsize=8, weight='bold', va='center')

    # Draw Intersections
    seen_intx_lbl = set()
    for _iid, intx in engine.intersections.items():
        p = intx.point
        if intx.is_assumed:
            lbl = 'Assumed Intersection / P.I. (RED)'
            lbl_arg = lbl if lbl not in seen_intx_lbl else ""
            if lbl_arg:
                seen_intx_lbl.add(lbl)
            # Assumed intersection in bright RED
            ax.plot(p.e, p.n, marker='X', color='#ff3333', markersize=10, zorder=7, label=lbl_arg)
            ax.text(p.e + 15.0, p.n - 12.0, f"[ASSUMED P.I.]\n{intx.name}",
                    color='#ff5555', fontsize=8, weight='bold', va='top')
        else:
            lbl = 'Established Intersection'
            lbl_arg = lbl if lbl not in seen_intx_lbl else ""
            if lbl_arg:
                seen_intx_lbl.add(lbl)
            # Certified intersection in cyan circle
            ax.plot(p.e, p.n, marker='o', color='#58a6ff', markersize=7, zorder=7, label=lbl_arg)
            ax.text(p.e + 12.0, p.n - 8.0, intx.name,
                    color='#79c0ff', fontsize=7.5, va='top')

    # Highlight Ground GPS Tie Anchor
    anchor = engine.intersections["INT_STARFISH_MANGROVE"]
    ax.plot(anchor.point.e, anchor.point.n, marker='*', color='#f85149', markersize=18, zorder=10,
            label='Ground-Truthed GPS Anchor')
    ax.text(anchor.point.e - 35.0, anchor.point.n - 15.0,
            f"★ GROUND-TRUTHED GPS ANCHOR (F.A.C. Rule 1)\n{anchor.name}\n"
            f"WGS84: {anchor.gps_lat:.6f}° N, {anchor.gps_lon:.6f}° W (NO FUDGING)",
            color='#f85149', fontsize=9.5, weight='bold', ha='right', va='top',
            bbox={"boxstyle": "round,pad=0.4", "facecolor": "#2b1010", "edgecolor": "#f85149", "alpha": 0.9})

    # Add Legend & Title
    ax.set_title("BEACHWOOD UNIT TWO -- COMPLETE ROAD CENTERLINE NETWORK & RED-LINED ASSUMPTIONS\n"
                 "Plat Book 30, Pages 82 & 82A, Duval County, FL (Duval_Plat_Book_30_Page_82-2.pdf) | Scale 1\"=100'",
                 color='#ffffff', fontsize=14, weight='bold', pad=20)
    ax.set_xlabel("Easting (ft, Local Survey Grid)", color='#8b949e', fontsize=11)
    ax.set_ylabel("Northing (ft, Local Survey Grid)", color='#8b949e', fontsize=11)
    ax.tick_params(colors='#8b949e')
    ax.grid(True, color='#30363d', linestyle=':', alpha=0.6)
    ax.axis('equal')
    ax.legend(loc='upper right', facecolor='#161b22', edgecolor='#30363d', labelcolor='#ffffff', fontsize=9)

    plt.tight_layout()
    plt.savefig(plot_file, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"Visual plot generated: {plot_file}")

    # Copy to artifacts directory
    art_dir = '/home/artwalk/.gemini/antigravity-ide/brain/eec2adec-7072-4297-86b9-e81f005f55cf'
    os.system(f"cp {plot_file} {art_dir}/beachwood_road_centerlines_drawing.png")
    print(f"Copied plot to artifact directory: {art_dir}/beachwood_road_centerlines_drawing.png")

    print("=" * 80)
    print("ROAD CENTERLINE NETWORK PIPELINE COMPLETE.")
    print("=" * 80)


if __name__ == '__main__':
    main()
