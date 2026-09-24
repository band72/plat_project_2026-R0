"""
mapcheck_block15.py -- MapCheck audit for all 18 lots of Block 15, Beachwood Unit Two
(Plat Book 30, Pages 82 & 82A, Duval County, FL).

Draws straight from engine.cogo_block.BeachwoodBlock15Solver -- this script used to
build its own second copy of the lot geometry, which drifted from the solver and kept
the pre-2026-09-24 (wrong) west end alive in the report and DXF.  Single source now.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.audit import dxf_audit  # noqa: E402
from engine.cogo_block import BeachwoodBlock15Solver  # noqa: E402
from engine.dxf_writer import DXFWriter  # noqa: E402

LOT_ORDER = [str(i) for i in range(1, 19)]


def run_block15_mapcheck():
    print("=" * 80)
    print("  BEACHWOOD UNIT TWO: BLOCK 15 FULL MAPCHECK AUDIT (ALL 18 LOTS)")
    print("  Plat Book 30, Pages 82 & 82A, Duval County, FL (1960)")
    print("=" * 80)

    solver = BeachwoodBlock15Solver()
    results = solver.solve_all()
    passed = sum(1 for r in results.values() if r.passed)
    for num in LOT_ORDER:
        r = results[num]
        print(f"  [{'PASS' if r.passed else 'FAIL'}] Lot {num:>2} | Perimeter {r.perimeter_ft:7.2f} ft | "
              f"Misclose {r.misclose_dist_ft:.4f} ft | Area {r.computed_area_sqft:9.1f} SF")

    print("\n  Printed-dimension redundancy checks (computed vs plat):")
    for key, (calc, printed) in solver.checks.items():
        flag = "" if abs(calc - printed) < 0.05 else "   <-- FLAG: plat value inconsistent with the rest of the block"
        print(f"    {key:<36} {calc:9.3f}  vs {printed:8.2f}  ({calc - printed:+.3f}){flag}")

    report_file = solver.generate_report("data/beachwood_block15_mapcheck_report.txt")
    with open(report_file, "a", encoding="utf-8") as f:
        f.write("PRINTED-DIMENSION REDUNDANCY CHECKS (computed vs plat)\n")
        for key, (calc, printed) in solver.checks.items():
            f.write(f"  {key:<36} {calc:9.3f}  vs {printed:8.2f}  ({calc - printed:+.3f})\n")
    print(f"\nBLOCK 15 AUDIT RESULT: {passed} / {len(results)} LOTS CLOSED")
    print(f"Detailed Report Written to: {report_file}")

    dxf_path = "dxf/PB0030_P0082_Block15_MapCheck.dxf"
    dxf_path_claude = "dxf/PB0030_P0082_Block15_MapCheck_claude.dxf"
    dxf = DXFWriter()
    dxf.add_layer("LOT_LINE", "cyan", "CONTINUOUS")
    dxf.add_layer("CURVE", "magenta", "CONTINUOUS")
    dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
    dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")
    for num in LOT_ORDER:
        r = results[num]
        for c in r.courses:
            if c.is_curve:
                dxf.polyline([(p.n, p.e) for p in c.arc_points], "CURVE")
            else:
                dxf.line((c.start_pt.n, c.start_pt.e), (c.end_pt.n, c.end_pt.e), "LOT_LINE")
        verts = solver.lots[num].vertices
        cn = sum(p.n for p in verts) / len(verts)
        ce = sum(p.e for p in verts) / len(verts)
        dxf.text((cn, ce), num, height=8.0, layer="TEXT-LABELS", halign=1, valign=2)
        dxf.text((cn - 12.0, ce), f"{r.computed_area_sqft:,.0f} SF", height=4.0, layer="TEXT-LABELS", halign=1, valign=2)
    dxf.text((180.0, -650.0), "BEACHWOOD UNIT TWO -- BLOCK 15 (LOTS 1-18)  PB 30 PG 82A", height=12.0, layer="TITLEBLOCK")
    dxf.save(dxf_path)
    dxf.save(dxf_path_claude)
    audit = dxf_audit(dxf_path)
    print(f"DXF Saved -> {dxf_path} & {dxf_path_claude} | Status: {audit['status']}")

    return {"status": "PASS" if passed == len(results) else "FAIL", "passed": passed, "total": len(results),
            "report_file": report_file, "dxf_path": dxf_path, "results": results}


if __name__ == "__main__":
    res = run_block15_mapcheck()
    sys.exit(0 if res["status"] == "PASS" else 1)
