"""
scripts/compute_block16_mapcheck.py -- Survey MapCheck Audit for Block 16.

Plat: Beachwood Unit Two, Plat Book 30, Pages 82 & 82A, Duval County, FL
Target: Block 16, Lots 1 through 8 (North Row) and Lots 33 through 28 (South Row).

Features:
  - Sail Avenue (60' R/W): North frontage (Lots 1-8).
  - South Street, Marina Avenue, Keel Drive: South frontage (Lots 33-28).
  - West Cross Street (60' R/W): West boundary (Lots 1 & 33).
  - Centerline Axis (618.50'): Dividing line between North and South rows.
  - Corner return curves (R=25.0') with P.I. angle bar glyphs (Lot 1 NW '┌', Lot 33 SW '└', Lot 29 SE '┘').
  - Control Monument: P.R.M. at Lot 33/32 on South Street.
  - Marina Avenue North R/W Curve: R=389.27', Delta=37°42'50" across Lots 31, 30, 29.
  - Keel Drive North R/W Curve: R=167.95' across Lot 28.
  - Wedge Lot 29: Centerline apex convergence at x=403.26'.
"""

from __future__ import annotations

import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.cogo_block import BeachwoodBlock16Solver


def run_block16_mapcheck() -> str:
    print("=" * 80)
    print("  COMPUTING SURVEY MAPCHECKS: BLOCK 16 (14 LOTS)")
    print("  Beachwood Unit Two -- Plat Book 30, Pages 82 & 82A, Duval County, FL")
    print("=" * 80)

    solver = BeachwoodBlock16Solver()
    results = solver.solve_all()

    lot_order = ["1", "2", "3", "4", "5", "6", "7", "8", "33", "32", "31", "30", "29", "28"]

    print(f"\n{'Lot #':<6} | {'Perimeter (ft)':<16} | {'Misclose (ft)':<14} | {'Precision':<16} | {'Net Area (SF)':<14} | {'F.A.C. 5J-17'}")
    print("-" * 86)
    all_passed = True
    for lot_num in lot_order:
        res = results[lot_num]
        status = "PASS" if res.fac_5j17_passed else "FAIL"
        if not res.fac_5j17_passed:
            all_passed = False
        print(f"{lot_num:<6} | {res.perimeter_ft:<16.2f} | {res.misclose_dist_ft:<14.5f} | {res.precision_str:<16} | {res.computed_area_sqft:<14.1f} | {status}")

    print("-" * 86)
    print(f"Traverse Audit Result: {'14/14 LOTS PASSED (100% Certified)' if all_passed else 'SOME LOTS FAILED'}")

    report_path = solver.generate_report("data/block16_mapcheck_report.txt")
    print(f"\nDetailed Surveyor Audit Report saved to: {report_path}")
    return report_path


if __name__ == "__main__":
    run_block16_mapcheck()
