"""
scripts/compute_block13_mapcheck.py -- Survey MapCheck Audit for Block 13.

Plat: Beachwood Unit Two, Plat Book 30, Pages 82 & 82A, Duval County, FL
Target: Block 13, Lots 1 through 11.

Features:
  - Mangrove Avenue (60' R/W): East frontage (Lots 1-11).
  - 50' Right-of-way for drainage and utilities: West rear boundary (Lots 1-11).
  - North Cross Street (60' R/W): North boundary (Lot 1).
  - Surfwood Avenue (60' R/W): South boundary (Lot 11) with 20' skew.
  - Corner return curves (R=25.0') with P.I. angle bar glyphs (Lot 1 NE '┘', Lot 11 SE '└').
  - Control Monuments: P.R.M. at Lot 1/2 and Lot 10/11 on Mangrove Ave.
"""

from __future__ import annotations

import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.cogo_block import BeachwoodBlock13Solver


def run_block13_mapcheck() -> str:
    print("=" * 80)
    print("  COMPUTING SURVEY MAPCHECKS: BLOCK 13 (LOTS 1 - 11)")
    print("  Beachwood Unit Two -- Plat Book 30, Pages 82 & 82A, Duval County, FL")
    print("=" * 80)

    solver = BeachwoodBlock13Solver()
    results = solver.solve_all()

    print(f"\n{'Lot #':<6} | {'Perimeter (ft)':<16} | {'Misclose (ft)':<14} | {'Precision':<16} | {'Net Area (SF)':<14} | {'F.A.C. 5J-17'}")
    print("-" * 86)
    all_passed = True
    for lot_num in [str(k) for k in range(1, 12)]:
        res = results[lot_num]
        status = "PASS" if res.fac_5j17_passed else "FAIL"
        if not res.fac_5j17_passed:
            all_passed = False
        print(f"{lot_num:<6} | {res.perimeter_ft:<16.2f} | {res.misclose_dist_ft:<14.5f} | {res.precision_str:<16} | {res.computed_area_sqft:<14.1f} | {status}")

    print("-" * 86)
    print(f"Traverse Audit Result: {'11/11 LOTS PASSED (100% Certified)' if all_passed else 'SOME LOTS FAILED'}")

    report_path = solver.generate_report("data/block13_mapcheck_report.txt")
    print(f"\nDetailed Surveyor Audit Report saved to: {report_path}")
    return report_path


if __name__ == "__main__":
    run_block13_mapcheck()
