---
name: review-plat-notes
description: Audits a Beachwood block cadastral solver (engine/cogo_block.py) and its matching scripts/compute_blockN_mapcheck.py / scripts/draw_blockN_mapcheck.py for a specific class of bug that closure checks cannot catch -- hardcoded curve bearings that drift from the solver's own analytically-computed value, curve_specs pointing at the wrong polygon edge (off-by-one), area-sign errors in curve segment adjustments, and corner-return radii that don't match the plat's stated typical radii (25' or 30'). Use this any time a new BeachwoodBlockNSolver is added, an existing one is modified, or a lot's curve geometry changes -- BEFORE considering the work done, even if `python3 -m pytest` is green and the script prints "100% Certified". Also use it whenever the user asks to "review the notes", "check the curve table", "verify the radii", or reports that a drawn curve or corner return looks visually wrong (too big, in the wrong spot, wrong shape) compared to what R=25'/30' should look like.
---

# Review Plat Notes

## Why this exists

Twice in one session, a new Beachwood block solver shipped with real
geometry bugs while every test passed and every script printed "100%
Certified" / "11/11 LOTS PASSED". Both bugs were invisible to closure
checks for the same underlying reason: **a traverse's misclosure only
depends on the straight-line distance between its actual vertex points.**
It does not care whether a given edge is flagged as a curve, which
direction a curve's segment-area adjustment is added or subtracted, or
whether a curve table's printed bearing matches the geometry at all. A
lot can close to 0.000 ft and still have its curve table lying about the
curve, or be treating one of its curve's own segment-area contribution
with the wrong sign, or (worst case) have the wrong edge marked as curved
entirely.

Concretely, what shipped and had to be found by hand:

1. **Hardcoded chord bearings drifting from the solve.** `get_curve_table_data()`
   typed a curve's `chord_bearing` as a literal string instead of reading
   `self.solN.chord_bearing` -- the value `solve_corner_return()` had
   already computed correctly. Wrong by hemisphere and ~2 deg in one case,
   by ~90 deg in another.
2. **Area sign errors.** A lot's precomputed "stated" area subtracted a
   curve's segment area where `DeterministicLotSolver.compute_mapcheck()`
   actually *adds* it for that same `curve_specs` `rot="CW"` -- a
   systematic ~2x-segment-area mismatch, invisible to closure, silently
   printed as "Area Discrepancy" while the script still reported PASS.
3. **Wrong-edge curves (off-by-one).** `curve_specs={"side_N": {...}}`
   pointed at the wrong `N`, so the curve got computed/drawn on an
   adjacent *straight* run instead of the real P.C.-to-P.T. edge. This
   happened in a **second, independent construction of the same lot** --
   the drawing script built its own `BeachwoodLotAgent` for CAD/PNG
   rendering, separate from the solver's own (already-correct)
   `DeterministicLotSolver`, and the two drifted out of sync.

None of these needed a human to eyeball a plat scan to catch -- they were
all internal inconsistencies inside the code itself, catchable by
checking one piece of already-computed truth against another. That's what
`engine/notes_audit.py` automates.

## When to run this

Run it whenever any of the following is true:

- You just added a new `BeachwoodBlockNSolver` class or a new lot within
  an existing one.
- You modified a `curve_specs`, `get_curve_table_data()`, or a lot's
  `stated_area_sqft` computation.
- You modified or added a `scripts/draw_blockN_mapcheck.py` or
  `scripts/compute_blockN_mapcheck.py` -- especially if it builds its own
  `BeachwoodLotAgent` list rather than drawing straight from the solver's
  `.lots` (check for this explicitly: `grep -n "BeachwoodLotAgent(" scripts/draw_blockN_mapcheck.py`
  -- if that construction exists, it is a second, independent copy of the
  geometry and needs its own audit pass, not just the solver's).
- The user reports a drawn curve or corner return looks visually wrong,
  or asks you to check radii/notes/curve tables.
- Before telling the user a block is done, even if tests pass. This is
  the equivalent, for curve geometry, of this repo's own
  `MASTER_PROMPT.md` "Rule 3: No Stale Geometry" -- treat it as a
  precondition for "done", not an optional extra pass.

## How to run it

`engine/notes_audit.py` has no CLI of its own -- it's a small library of
plain functions returning lists of problem strings (empty = clean),
meant to be called from a short Python snippet or wired directly into a
`scripts/draw_blockN_mapcheck.py`/`compute_blockN_mapcheck.py` (see
`scripts/draw_block13_mapcheck.py` and `scripts/draw_block16_mapcheck.py`
for the pattern already wired in -- copy it for a new block rather than
reinventing it).

**Step 1 -- audit every lot's curve geometry (always do this first):**

```python
from engine.cogo_block import BeachwoodBlockNSolver  # the block under review
from engine.notes_audit import audit_solver_curves, print_audit_report

solver = BeachwoodBlockNSolver()
print_audit_report(audit_solver_curves(solver), header="BLOCK N SOLVER CURVE AUDIT")
```

This runs `audit_curve_chord_feasibility()` (a curve's chord can never
exceed 2*radius -- this alone would have caught the off-by-one bug, since
a 74.86 ft chord against a declared 25 ft radius is mathematically
impossible) and `audit_typical_radius()` (flags any curve radius that
isn't 25' or 30', this plat's stated typical corner-return radii) against
every lot in the solver's `.lots` dict.

**Step 2 -- if the drawing script has its OWN agent construction, audit
that too, separately:**

```python
from engine.notes_audit import audit_lot_curves, print_audit_report

problems = {
    ag.lot_number: audit_lot_curves(ag.corners, ag.curve_specs, ag.corner_names, label=f"Lot {ag.lot_number}")
    for ag in agents if ag.curve_specs
}
print_audit_report({k: v for k, v in problems.items() if v}, header="BLOCK N DRAWING-AGENT CURVE AUDIT")
```

Do not skip this because Step 1 came back clean -- Step 1 only covers the
solver's own construction. The bug that actually shipped was a drift
*between* two independent constructions of the same lot; auditing only
one of them would have missed it, same as it did the first time.

**Step 3 -- audit the curve table's published bearings against the solve,
for every curve that has a corresponding `solve_corner_return()` result:**

```python
from engine.notes_audit import audit_curve_bearing_consistency

for tag, sol in (("C1", solver.sol1), ("C2", solver.sol11)):  # map tags to their solveN objects
    row = next(r for r in solver.get_curve_table_data() if r["tag"] == tag)
    for p in audit_curve_bearing_consistency(row["chord_bearing"], sol.chord_bearing, tag=tag):
        print(p)
```

This only applies to curves built via `solve_corner_return()` (corner
returns). Curves with no `solveN` counterpart (e.g. a street-frontage
curve subdivided by hand, like Block 16's Marina Avenue curves) can't be
checked this way -- verify those against the plat's actual stated curve
data instead (see Step 4).

**Step 4 -- read the actual notes, don't stop at internal consistency.**

Everything above only proves the code agrees with *itself*. It cannot
tell you the code agrees with the *real, recorded plat* -- that still
needs a human (or you, reading the source) to check the stated radius,
bearing, and dimension notes against what got coded. In particular:

- A `audit_typical_radius()` flag on a large, non-25'/30' radius (like a
  389.27 ft street-centerline curve) is *not* automatically a bug --
  it's a prompt to go confirm that value against the plat's own curve
  table/legend, which is exactly what already happened for Block 16's
  Marina Avenue and Keel Drive curves (see `MASTER_PROMPT.md`'s Iter 44
  entry -- those radii are correct and documented, just not
  corner-return-typical). Don't "fix" a large curve's radius down to 25'
  or 30' just because the audit flagged it; read the notes first.
- If the plat sheet or its transcribed notes are available, cross-check
  every stated radius/bearing/dimension the code claims to derive from
  it. The audit module only ever compares code against code.

## Fixing what you find

- **Chord-infeasibility or "neither endpoint" flags**: almost always an
  off-by-one in a `curve_specs={"side_N": ...}` key. Recount from the
  `corner_names`/`node_names` list -- `side_N` connects index `N-1` to
  index `N` (`engine/lot_agent.py`'s `side_key = f"side_{i+1}"`
  convention). Find the two names that actually contain "PC"/"PT" and use
  the side number between them.
- **Bearing-drift flags**: replace the hardcoded literal with the actual
  `self.solN.chord_bearing` attribute (wrap in
  `engine.cogo_block.whole_second_bearing()` if you need it formatted
  without the `.00` seconds `azimuth_to_bearing()` always emits, to match
  this file's existing whole-second table convention).
- **Area-sign issues** (not directly caught by this audit yet, but caused
  the same class of silent-certification problem): if a lot has a curve
  side, its `stated_area_sqft` precompute must add the curve's segment
  area when `curve_specs[...]["rot"] == "CW"` and subtract it for
  `"CCW"` -- the same sign `DeterministicLotSolver.compute_mapcheck()`
  itself applies (see `engine/cogo_block.py` around the `curve_adj +=`
  line). If you add a new curved lot, sanity-check by comparing
  `res.computed_area_sqft` against `res.stated_area_sqft` once solved --
  `abs(res.area_diff_pct) < 0.01` should hold if both formulas agree, and
  they must (see `test_block16_cogo.py::test_block16_curvilinear_lot_areas_match_stated`
  for the pattern).

After fixing anything, re-run the affected `compute_blockN_mapcheck.py`
and `draw_blockN_mapcheck.py` so the report/DXF/PNG artifacts stay in
sync with the corrected engine code (`MASTER_PROMPT.md`'s "Rule 3"), and
re-run the audit one more time to confirm it's clean before calling the
block done.

## Extending the audit

If you find a new class of bug this session's checks wouldn't have
caught, add a function to `engine/notes_audit.py` alongside the existing
ones (same style: take plain data, return a list of strings, never
raise) and a red/green test pair in `test_notes_audit.py` that reproduces
the actual bug, not a synthetic stand-in -- that's the bar the existing
tests were held to (see `test_wrong_edge_curve_is_flagged_by_chord_feasibility`
and its sibling for the pattern). A check that can't demonstrably catch a
real bug that actually shipped isn't worth adding.
