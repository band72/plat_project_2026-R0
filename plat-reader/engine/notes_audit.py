"""
engine/notes_audit.py -- geometric/notes consistency audit for cadastral
block solvers and their drawing scripts.

Exists because two real bugs shipped in the same session, both invisible to
closure checks (misclosure only depends on the vertex chain, not on which
side is flagged as a curve or which sign a segment-area adjustment uses):

  1. A curve table's hand-typed chord_bearing drifting from what
     solve_corner_return() already computed for that same curve (Block 13's
     C1, Block 16's C1/C2/C6 -- wrong by hemisphere/45deg/90deg).
  2. A curve_specs={"side_N": ...} entry pointing at the wrong edge
     (off-by-one), so the curve gets computed/drawn on an adjacent STRAIGHT
     run instead of the real P.C.-to-P.T. edge (Block 13 Lots 1 and 11, in
     a second, duplicated BeachwoodLotAgent construction used only for
     drawing -- the correct DeterministicLotSolver-based geometry never had
     this bug, only its independent redraw copy did).

Every function here returns a plain list of human-readable problem strings
(empty = clean) rather than raising, matching this codebase's established
"isolate the remainder, never let one bad lot halt the batch" philosophy
(see engine/blocks.py's docstring). Call audit_lot_curves() per lot right
after building it, print/collect whatever it returns, and keep going.
"""
from __future__ import annotations

from engine.cogo import parse_bearing

# This plat's corner-return curves are always one of these two radii, and
# the radius is always called out explicitly in the plat's notes/legend --
# never inferred. A declared radius outside this set is a red flag on its
# own, independent of any other check. Override per-plat if a specific
# block's notes state something else (pass typical_radii= explicitly).
DEFAULT_TYPICAL_RADII = (25.0, 30.0)


def _side_endpoints(vertices: list, side_key: str) -> tuple[int, int] | None:
    """side_N -> (i, i+1) 0-based vertex indices, matching the side_key =
    f"side_{i+1}" convention used throughout engine/cogo_block.py and
    engine/lot_agent.py. Returns None if side_key isn't a valid "side_N"
    or N is out of range for `vertices`."""
    if not side_key.startswith("side_"):
        return None
    try:
        n = int(side_key.split("_", 1)[1])
    except ValueError:
        return None
    n_pts = len(vertices)
    if n < 1 or n > n_pts:
        return None
    i = n - 1
    return i, (i + 1) % n_pts


def audit_curve_chord_feasibility(vertices: list, curve_specs: dict,
                                  corner_names: list[str] | None = None,
                                  label: str = "", tol_ft: float = 0.01) -> list[str]:
    """A circle's chord can never exceed its diameter (2*radius) -- this is
    pure geometry, true regardless of what the plat's notes say. Checking
    it catches a curve_specs side_N pointing at the wrong edge immediately
    and unambiguously: the wrong-edge version of Block 13 Lot 11 declared
    radius=25.0 against an actual chord of 74.86 ft, 50% past the 50 ft
    maximum -- an impossible curve that nonetheless rendered *something*,
    silently, instead of erroring.

    Pass `corner_names` (the same list given to DeterministicLotSolver /
    BeachwoodLotAgent) to get the actual endpoint names in the message --
    genuine corner-return curves in this codebase are consistently named
    with a "PC"/"PT" prefix on at least one end, so an edge with neither
    is worth a second look even when the chord itself is feasible."""
    problems = []
    n_pts = len(vertices)
    for side_key, spec in curve_specs.items():
        endpoints = _side_endpoints(vertices, side_key)
        prefix = f"{label}: " if label else ""
        if endpoints is None:
            problems.append(f"{prefix}curve_specs key {side_key!r} is not a valid side "
                            f"reference for a {n_pts}-vertex polygon")
            continue
        i, j = endpoints
        p1, p2 = vertices[i], vertices[j]
        chord = p1.dist_to(p2)
        radius = spec.get("radius")
        names = ""
        if corner_names and len(corner_names) == n_pts:
            names = f" ({corner_names[i]} -> {corner_names[j]})"
            if "PC" not in corner_names[i].upper() and "PT" not in corner_names[i].upper() \
                    and "PC" not in corner_names[j].upper() and "PT" not in corner_names[j].upper():
                problems.append(
                    f"{prefix}{side_key}{names} is marked as a curve but neither endpoint "
                    f"name looks like a curve tangent point (no 'PC'/'PT') -- double-check "
                    f"this is really the P.C.-to-P.T. edge, not an off-by-one onto a "
                    f"neighboring straight run"
                )
        if radius is None:
            problems.append(f"{prefix}{side_key}{names} has no radius in its curve_specs")
            continue
        max_chord = 2.0 * float(radius)
        if chord > max_chord + tol_ft:
            problems.append(
                f"{prefix}{side_key}{names}: chord {chord:.2f}' exceeds the maximum "
                f"possible chord (2*R={max_chord:.2f}') for a R={radius:.2f}' curve -- "
                f"geometrically impossible, this is very likely the wrong edge "
                f"(check for an off-by-one in the side_N index)"
            )
    return problems


def audit_curve_bearing_consistency(published_bearing: str, solved_bearing: str,
                                    tag: str = "", tol_deg: float = 0.05) -> list[str]:
    """Compare a curve table's published chord_bearing (often hand-typed as
    a literal string) against the value solve_corner_return() actually
    computed for that curve. Any real divergence here is a copy/paste or
    typo drift, not a rounding artifact -- tol_deg defaults to 0.05 deg
    (3 arcsec) to allow for the display formatting's own rounding while
    still catching the wrong-hemisphere/wrong-quadrant class of error that
    slipped through twice (both were off by tens of degrees, not seconds)."""
    published_az = parse_bearing(published_bearing)
    solved_az = parse_bearing(solved_bearing)
    diff = abs(published_az - solved_az) % 360.0
    diff = min(diff, 360.0 - diff)
    if diff > tol_deg:
        prefix = f"{tag}: " if tag else ""
        return [
            f"{prefix}published chord_bearing {published_bearing!r} differs from "
            f"solve_corner_return()'s own computed {solved_bearing!r} by {diff:.2f} deg -- "
            f"the table is very likely hand-typed instead of reading .chord_bearing "
            f"off the solve"
        ]
    return []


def audit_typical_radius(radius: float, tag: str = "",
                         typical_radii: tuple[float, ...] = DEFAULT_TYPICAL_RADII,
                         tol_ft: float = 0.01) -> list[str]:
    """Flag a curve radius that isn't one of the plat's stated typical
    values. This is a weaker signal than chord feasibility (a genuinely new
    radius IS possible on a real plat -- verify against the plat's actual
    notes/legend before treating this as a bug, not just against this
    default set), so treat it as a prompt to go read the notes, not as
    proof of an error on its own."""
    if any(abs(radius - r) <= tol_ft for r in typical_radii):
        return []
    prefix = f"{tag}: " if tag else ""
    allowed = ", ".join(f"{r:g}'" for r in typical_radii)
    return [
        f"{prefix}radius {radius:g}' is not one of this plat's typical corner-return "
        f"radii ({allowed}) -- confirm against the plat's own stated notes/legend "
        f"before assuming this is intentional"
    ]


def audit_lot_curves(vertices: list, curve_specs: dict,
                     corner_names: list[str] | None = None, label: str = "",
                     typical_radii: tuple[float, ...] = DEFAULT_TYPICAL_RADII) -> list[str]:
    """Convenience wrapper: run every geometry-only check (chord feasibility
    + typical radius) against one lot's curve_specs. Does NOT check bearing
    consistency -- that needs the corresponding CornerReturnSolve object,
    which isn't available from vertices/curve_specs alone; call
    audit_curve_bearing_consistency() separately per curve table row."""
    problems = list(audit_curve_chord_feasibility(vertices, curve_specs, corner_names, label))
    for side_key, spec in curve_specs.items():
        radius = spec.get("radius")
        if radius is not None:
            problems.extend(audit_typical_radius(float(radius), tag=f"{label} {side_key}".strip(),
                                                  typical_radii=typical_radii))
    return problems


def audit_solver_curves(solver, typical_radii: tuple[float, ...] = DEFAULT_TYPICAL_RADII) -> dict[str, list[str]]:
    """Run audit_lot_curves() over every lot in a Beachwood-style block
    solver (anything exposing a `.lots` dict of DeterministicLotSolver
    instances, e.g. BeachwoodBlock13Solver/BeachwoodBlock16Solver). Returns
    {lot_number: [problems]} for lots that have any -- clean lots are
    omitted, so `if audit_solver_curves(solver):` alone tells you whether
    anything needs attention."""
    out: dict[str, list[str]] = {}
    for lot_num, lot in solver.lots.items():
        problems = audit_lot_curves(
            lot.vertices, lot.curve_specs,
            corner_names=getattr(lot, "node_names", None),
            label=f"Lot {lot_num}",
            typical_radii=typical_radii,
        )
        if problems:
            out[lot_num] = problems
    return out


def print_audit_report(problems_by_lot: dict[str, list[str]], header: str = "NOTES AUDIT") -> bool:
    """Print a problems-by-lot dict in the same plain style this codebase's
    compute_blockN_mapcheck.py scripts already use for their summary
    tables. Returns True if anything was printed (i.e. there were
    problems), so callers can use it directly as a "did this pass" check."""
    if not problems_by_lot:
        print(f"[OK] {header}: clean -- no curve/radius inconsistencies found.")
        return False
    print(f"[!!] {header}: {sum(len(p) for p in problems_by_lot.values())} issue(s) found:")
    for lot_num, problems in problems_by_lot.items():
        for p in problems:
            print(f"  Lot {lot_num}: {p}")
    return True
