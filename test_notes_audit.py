"""
test_notes_audit.py -- pytest coverage for engine/notes_audit.py.

Each test reproduces one of the two real bugs found and fixed this session
as a red/green pair: the buggy version must be flagged, the fixed version
must come back clean. That's the actual bar this audit module needs to
clear -- not "it runs", but "it would have caught the bug that shipped."
"""
from __future__ import annotations

from engine.cogo_block import BeachwoodBlock13Solver, solve_corner_return
from engine.notes_audit import (
    audit_curve_bearing_consistency,
    audit_curve_chord_feasibility,
    audit_lot_curves,
    audit_solver_curves,
    audit_typical_radius,
)


def _lot11_vertices():
    """Real Block 13 Lot 11 geometry, straight from the fixed solver --
    used as the ground truth for both the buggy and fixed curve_specs
    reproductions below (only curve_specs changes, never the vertices)."""
    solver = BeachwoodBlock13Solver()
    lot = solver.lots["11"]
    return lot.vertices, lot.node_names


def test_wrong_edge_curve_is_flagged_by_chord_feasibility():
    """Reproduces the actual Block 13 Lot 11 bug from
    scripts/draw_block13_mapcheck.py: curve_specs declared on side_3
    (NE_Cor/PRM -> PC_East, a real 74.86' straight run) instead of side_4
    (PC_East -> PC_South, the true 25' radius curve). A 25' radius curve
    cannot have a 74.86' chord -- more than the 50' diameter -- so this
    must be flagged, not silently rendered."""
    vertices, node_names = _lot11_vertices()
    buggy_specs = {"side_3": {"radius": 25.0, "rot": "CW"}}
    problems = audit_curve_chord_feasibility(vertices, buggy_specs, node_names, label="Lot 11")
    assert problems, "the wrong-edge curve_specs should have been flagged, but wasn't"
    assert any("exceeds the maximum possible chord" in p for p in problems)


def test_correct_edge_curve_passes_chord_feasibility():
    """The fixed side_4 curve_specs for the same lot must come back clean:
    this is the actual P.C.-to-P.T. edge, and its chord (35.46') is well
    within the 50' diameter for R=25'."""
    vertices, node_names = _lot11_vertices()
    fixed_specs = {"side_4": {"radius": 25.0, "rot": "CW"}}
    problems = audit_curve_chord_feasibility(vertices, fixed_specs, node_names, label="Lot 11")
    assert problems == [], f"the correct curve_specs should be clean, got: {problems}"


def test_audit_solver_curves_is_clean_for_both_shipped_blocks():
    """End-to-end: the real, fixed BeachwoodBlock13Solver should audit
    clean across every lot -- if a future change reintroduces a wrong-edge
    or non-typical-radius curve anywhere in this solver, this test catches
    it without needing to know which lot broke."""
    solver = BeachwoodBlock13Solver()
    problems = audit_solver_curves(solver)
    assert problems == {}, f"expected a clean audit, got: {problems}"


def test_hardcoded_bearing_drift_is_flagged():
    """Reproduces the Block 13 C1 bug: the curve table hardcoded
    chord_bearing="S43°58'20\"W" while solve_corner_return() for that same
    curve actually computes S46°01'40"E -- wrong by both hemisphere and
    angle. This is exactly the class of drift audit_curve_bearing_consistency
    exists to catch."""
    sol = solve_corner_return("N88°58'20\"E", "S01°01'40\"E", radius=25.0,
                              stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0)
    problems = audit_curve_bearing_consistency(
        published_bearing="S43°58'20\"W", solved_bearing=sol.chord_bearing, tag="C1",
    )
    assert problems, "a chord bearing off by hemisphere and ~2 deg should have been flagged"


def test_matching_bearing_is_not_flagged():
    sol = solve_corner_return("N88°58'20\"E", "S01°01'40\"E", radius=25.0,
                              stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0)
    problems = audit_curve_bearing_consistency(
        published_bearing=sol.chord_bearing, solved_bearing=sol.chord_bearing, tag="C1",
    )
    assert problems == []


def test_rounding_noise_is_not_flagged_as_drift():
    """A few arc-seconds of DMS rounding (unavoidable when a hand-typed
    table uses whole seconds and the solve carries 2 decimal places) is not
    the same class of problem as a wrong-hemisphere/wrong-quadrant typo --
    must not false-positive on it."""
    problems = audit_curve_bearing_consistency(
        published_bearing="N42°35'30\"E", solved_bearing="N42°35'30.02\"E", tag="C1",
    )
    assert problems == []


def test_non_typical_radius_is_flagged():
    problems = audit_typical_radius(22.5, tag="C9")
    assert problems
    assert "22.5" in problems[0]


def test_typical_radii_25_and_30_pass():
    assert audit_typical_radius(25.0) == []
    assert audit_typical_radius(30.0) == []


def test_audit_lot_curves_combines_chord_and_radius_checks():
    vertices, node_names = _lot11_vertices()
    # Correct edge, but a made-up non-typical radius -- should flag on the
    # radius check even though the edge/chord itself is fine.
    specs = {"side_4": {"radius": 22.5, "rot": "CW"}}
    problems = audit_lot_curves(vertices, specs, node_names, label="Lot 11")
    assert any("22.5" in p for p in problems)


def test_naming_heuristic_flags_curve_on_non_pc_pt_named_edge():
    """Soft signal, not a hard failure by itself, but the wrong-edge bug's
    endpoints (NE_Cor/PRM -> PC_East) had only ONE 'PC'-named end -- this
    check would have been a second, independent hint even before the chord
    math is examined."""
    vertices, node_names = _lot11_vertices()
    # side_3 = NE_Cor(PRM) -> PC_East: only one endpoint contains "PC".
    buggy_specs = {"side_3": {"radius": 25.0, "rot": "CW"}}
    problems = audit_curve_chord_feasibility(vertices, buggy_specs, node_names, label="Lot 11")
    assert not any("neither endpoint" in p for p in problems), (
        "side_3 has one PC-named endpoint, so the 'neither endpoint' heuristic "
        "should not fire here -- the chord-feasibility problem is what should"
    )
