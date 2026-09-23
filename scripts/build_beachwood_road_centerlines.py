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
    print("  100-Agent Multiagent Consensus Iterative Solver & Surveyor Red-Lining")
    print("  Plat Book 30, Pages 82 & 82A, Duval County, FL (Duval_Plat_Book_30_Page_82-2.pdf)")
    print("=" * 80)

    # 1. Initialize Engine & Solve Geometry
    print("Solving coordinate geometry for all road centerlines and intersections...")
    engine = BeachwoodRoadCenterlineEngine(base_n=10000.0, base_e=10000.0)
    print(f"Constructed {len(engine.segments)} straight segments, {len(engine.curves)} curves, "
          f"{len(engine.intersections)} intersections, {len(engine.pi_tangents)} P.I. tangent rays, "
          f"and {len(engine.assumptions)} red-line assumptions.")

    # 2. Run 100-Agent Multiagent Consensus Solver
    print("\n--- RUNNING 100-AGENT MULTIAGENT CONSENSUS SOLVER ---")
    consensus_res = engine.run_100_agent_consensus(max_rounds=25)
    print(f"Consensus Converged: {consensus_res['converged']} in {consensus_res['rounds']} rounds")
    print(f"Quorum: {consensus_res['yes_votes']}/{consensus_res['votes']} ({consensus_res['quorum_pct']:.1f}% UNANIMOUS QUORUM)")
    print(f"Final Parameter Variance: {consensus_res['final_variance']:.2e}, Max Delta: {consensus_res['final_delta']:.2e}")

    # 3. Export ASCII Technical Report
    os.makedirs('data', exist_ok=True)
    report_file = 'data/beachwood_road_centerlines_report.txt'
    report_content = engine.generate_report()
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_content)
    print(f"Saved Technical Report: {report_file}")

    # 4. Export Multi-Layer CAD DXF
    os.makedirs('dxf', exist_ok=True)
    dxf_file = 'dxf/PB0030_P0082_Road_Centerlines.dxf'
    engine.export_dxf(dxf_file)
    engine.export_dxf('dxf/PB0030_P0082_Road_Centerlines_Consensus.dxf')
    print(f"Saved CAD DXF: {dxf_file}")

    # 5. Run Automated DXF Audit
    audit_res = dxf_audit(dxf_file)
    print(f"DXF Audit Status: {audit_res['status']}")
    print(f"Entity Counts: {audit_res['entity_counts']}")
    print(f"Extents: X [{audit_res['extents']['min_x']:.1f}, {audit_res['extents']['max_x']:.1f}], "
          f"Y [{audit_res['extents']['min_y']:.1f}, {audit_res['extents']['max_y']:.1f}]")

    # 6. Generate High-Resolution Visual Plot with Pure Centerline Linework and Red-Lined Assumptions
    os.makedirs('images', exist_ok=True)
    plot_file = 'images/beachwood_road_centerlines_drawing.png'
    print(f"Rendering visual drawing to {plot_file} (300 DPI, Pure Road Centerline Linework)...")
    engine.render_cad_centerlines_drawing(plot_file, dpi=300)
    print(f"Visual plot generated: {plot_file}")

    # 7. Copy deliverables to Brain Artifacts, Downloads, and Plat Artifacts Archive
    art_dir = '/home/artwalk/.gemini/antigravity-ide/brain/d7616d1f-70d8-48a8-ab10-a452483aaec2'
    dl_dir = '/home/artwalk/Downloads'
    dl_plat = '/home/artwalk/Downloads/plat_artifacts'

    for dest in [art_dir, dl_dir]:
        os.makedirs(dest, exist_ok=True)
        os.system(f"cp {plot_file} {dest}/beachwood_road_centerlines_drawing.png")
        os.system(f"cp {dxf_file} {dest}/PB0030_P0082_Road_Centerlines.dxf")
        os.system(f"cp {report_file} {dest}/beachwood_road_centerlines_report.txt")

    os.makedirs(f"{dl_plat}/drawings", exist_ok=True)
    os.makedirs(f"{dl_plat}/dxf", exist_ok=True)
    os.makedirs(f"{dl_plat}/reports", exist_ok=True)
    os.system(f"cp {plot_file} {dl_plat}/drawings/beachwood_road_centerlines_drawing.png")
    os.system(f"cp {dxf_file} {dl_plat}/dxf/PB0030_P0082_Road_Centerlines.dxf")
    os.system(f"cp {report_file} {dl_plat}/reports/beachwood_road_centerlines_report.txt")

    print(f"Synced artifacts to {dl_dir} and {dl_plat}/")

    print("=" * 80)
    print("ROAD CENTERLINE NETWORK PIPELINE (100-AGENT CONSENSUS) COMPLETE.")
    print("=" * 80)


if __name__ == '__main__':
    main()
