"""
audit_codebase_consensus.py -- 100-Agent Multiagent Consensus Codebase Auditor.

Executes automated architectural and cadastral verification of the plat_project_2026-R0
codebase using 100 simulated autonomous agents partitioned into 5 specialized guilds:
  1. Computational Geometry & COGO Reliability (Agents 1-20)
  2. Computer Vision & Raster Vectorization (Agents 21-40)
  3. Planar Graph & Cadastral Topology (Agents 41-60)
  4. CAD Engineering & DXF Standards (Agents 61-80)
  5. Geodesy, GIS & Public Land Records (Agents 81-100)
"""
from __future__ import annotations
import sys
import os

sys.path.insert(0, ".")
from engine.consensus import CodebaseAuditPanel
from engine.georeference import get_intersection_gps, assert_zero_fudging
from engine.audit import audit_dxf_layers


def run_codebase_consensus_audit(root_dir: str = ".") -> dict:
    print("=" * 80)
    print("      100-AGENT MULTIAGENT CONSENSUS: CODEBASE & CADASTRAL AUDIT PANEL")
    print("=" * 80)

    panel = CodebaseAuditPanel()
    print(f"Initialized Codebase Audit Panel with {len(panel.solver.agents)} Agents across {len(panel.solver.guilds)} Guilds.")

    # 1. Zero-Fudging Rule Verification on Shared Intersections
    print("\n[Audit Step 1/4] Verifying Zero Artificial Offset Fudging on Ground-Truth GPS Intersections...")
    intersections_to_check = [
        ("Starfish Avenue", "Mangrove Avenue", (30.292130, -81.530280)),
        ("Dewees Avenue", "Coquina Place", (30.342120, -81.398650)),
        ("Heckscher Drive", "Beverly Isle Drive", (30.407420, -81.442180)),
        ("Maritime Oak Drive", "Coastal Oak Lane", (30.316880, -81.419450)),
        ("County Road", "Sibbald Grant", (30.155280, -81.758330)),
    ]
    fudging_violations = 0
    for s1, s2, expected_gps in intersections_to_check:
        actual_gps = get_intersection_gps(s1, s2)
        try:
            assert_zero_fudging(actual_gps, expected_gps, max_dist_ft=0.01)
            print(f"  [PASS] {s1} & {s2}: {actual_gps} (Zero Fudging verified)")
        except AssertionError as e:
            print(f"  [FAIL] {e}")
            fudging_violations += 1

    # 2. DXF Output Deliveries Audit
    print("\n[Audit Step 2/4] Auditing Exported DXF CAD Layers & Standards Compliance...")
    dxf_paths = [
        "dxf/PB0030_P0082_Beachwood_Vector_Consensus.dxf",
        "dxf/PB0015_P0082_OceanGrove.dxf",
        "dxf/Duval_BeverlyIsle_1968.dxf",
        "dxf/PB0004_P0085_HicksSubdivision.dxf",
    ]
    dxf_issues = 0
    for dp in dxf_paths:
        if os.path.exists(dp):
            rep = audit_dxf_layers(dp)
            status_tag = f"[{rep['status']}]"
            print(f"  {status_tag} {dp}: {rep['entity_counts']['lines']} lines, {rep['entity_counts']['polylines']} polylines, {rep['entity_counts']['circles']} noise circles")
            if rep["status"] == "FAIL" or rep["entity_counts"]["circles"] > 0:
                dxf_issues += 1

    # 3. Codebase Multiagent Consensus Iteration
    print("\n[Audit Step 3/4] Convening 100 Agents for Multiagent Consensus Convergence...")
    audit_report = panel.audit_codebase(root_dir=root_dir)
    panel.solver.print_summary()

    # 4. Final Quorum Scorecard
    print("\n[Audit Step 4/4] Final 100-Agent Consensus Scorecard:")
    cons = audit_report["consensus"]
    print(f"  Codebase Syntax Integrity: {'100% VALID (0 errors)' if audit_report['syntax_errors'] == 0 else 'SYNTAX ERRORS DETECTED'}")
    print(f"  AST Functions Indexed: {audit_report['total_ast_functions']} across {audit_report['engine_files_count']} engine files & {audit_report['build_scripts_count']} plat pipelines")
    print(f"  Consensus Rounds: {cons['rounds']} | Final Delta: {cons['final_delta']:.8f} | Final Variance: {cons['final_variance']:.10e}")
    print(f"  Quorum Voting Approval: {cons['votes']}/100 Agents ({'UNANIMOUS 100%' if cons['unanimous_quorum'] else 'PARTIAL'})")
    print(f"  Zero-Fudging Violations: {fudging_violations}")
    print(f"  Overall Audit Status: {audit_report['status']}")
    print("=" * 80)

    return audit_report


if __name__ == "__main__":
    res = run_codebase_consensus_audit()
    if res["status"] != "PASS":
        sys.exit(1)
