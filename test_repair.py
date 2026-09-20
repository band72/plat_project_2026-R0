"""
Does inverse-solving actually recover the corrupted OCR fields?
Tested against the real failing rows from benchmark_cells.py, scored on the
hand-transcribed ground truth.
"""
import sys
sys.path.insert(0, '.')
from engine.repair import inverse_solve_curve, radius_consensus, apply_corrections
from engine.ocr import validate_curve
import data.trail_ridge_estates as trd

# Actual OCR output rows that failed (verbatim from the benchmark run)
OCR_ROWS = {
    "C3":  dict(length=172.69, radius=119.0, delta=89.9517, chord_bearing="N44°25'14\"E", chord=155.50),
    "C45": dict(length=13.06,  radius=20.0,  delta=14.9672, chord_bearing="N87°55'49\"W", chord=13.02),
    "C46": dict(length=44.76,  radius=29.0,  delta=102.58,  chord_bearing="N51°17'24\"W", chord=39.02),
    "C21": dict(length=74.22,  radius=140.0, delta=3.3767,  chord_bearing="N66°47'15\"E", chord=73.36),
    "C15": dict(length=0.59,   radius=140.0, delta=2.7053,  chord_bearing="N08°15'04\"W", chord=90.32),
    "C28": dict(length=30.27,  radius=26.0,  delta=9.0,     chord_bearing="S44°23'47\"W", chord=35.36),
    "C49": dict(length=168.28, radius=274.0, delta=68.1672, chord_bearing="S68°10'02\"E", chord=165.65),
    "C35": dict(length=15.86,  radius=274.0, delta=77.83,   chord_bearing="S77°49'48\"E", chord=76.62),
    "C6":  dict(length=26.34,  radius=82.0,  delta=8.2483,  chord_bearing="S08°14'54\"W", chord=20.24),
    "C25": dict(length=19.95,  radius=1148.0, delta=12.5572, chord_bearing="N12°33'26\"W", chord=19.93),
    "C37": dict(length=20.38,  radius=1000.0, delta=87.5533, chord_bearing="S87°33'12\"E", chord=20.88),
}

gt = {k: v for k, v in trd.CURVE_TABLE.items() if isinstance(v, dict) and "radius" in v}

print("=== TIER 1: INTRA-ROW INVERSE SOLVE ===\n")
corrections = {}
for cid, rec in OCR_ROWS.items():
    good, msg = validate_curve(rec)
    cands = inverse_solve_curve(rec)
    g = gt.get(cid)
    print(f"{cid}: validate={'OK' if good else 'FAIL'}")
    if not cands:
        print("   no single-field inverse explains it -> leave for higher-tier context\n")
        continue
    best = cands[0]
    corrections[cid] = best
    print(f"   -> {best['field']}: read {best['read']} | solved {best['solved']}")
    print(f"      {best['why']}; {best['corroboration']}")
    if g:
        truth = g[best["field"] if best["field"] != "delta" else "delta"]
        hit = abs(truth - best["solved"]) < 0.02
        print(f"      GROUND TRUTH {best['field']}={truth}  -> {'CORRECT' if hit else 'WRONG'}")
    print()

print("\n=== TIER 2: RADIUS CONSENSUS ACROSS TABLE ===\n")
cons = radius_consensus({**OCR_ROWS})
for cid, c in cons.items():
    g = gt.get(cid)
    print(f"{cid}: R read {c['read']} -> solved {c['solved']}  ({c['why']}; {c['corroboration']})")
    if g:
        print(f"    GROUND TRUTH radius={g['radius']} -> "
              f"{'CORRECT' if abs(g['radius']-c['solved'])<0.02 else 'WRONG'}")
for cid, c in cons.items():
    corrections.setdefault(cid, c)

print("\n=== APPLY + RE-VERIFY ===\n")
fixed, applied, review = apply_corrections(OCR_ROWS, corrections)
print("AUTO-APPLIED (single-digit edit, high confidence):")
for e in applied:
    print(f"  {e['curve']}.{e['field']}: {e['read']} -> {e['solved']}   [{e['why']}]")
print("\nFLAGGED FOR REVIEW (redundancy-only / implausible radius):")
for e in review:
    print(f"  {e['curve']}.{e['field']}: read {e['read']} -> proposed {e['solved']}")
    print(f"      {e['why']}")
    print(f"      {e['corroboration']}; radius in family: {e['radius_in_family']}")

print("\n=== FINAL SCORE vs GROUND TRUTH ===\n")
n = ex = 0
for cid, rec in sorted(fixed.items()):
    g = gt.get(cid)
    if not g:
        continue
    n += 1
    same = (abs(rec["radius"] - g["radius"]) < 0.02 and
            abs(rec["length"] - g["length"]) < 0.02 and
            abs(rec["chord"] - g["chord"]) < 0.02 and
            abs(rec["delta"] - g["delta"]) < 0.01)
    ok, _ = validate_curve(rec)
    if same:
        ex += 1
    status = "EXACT" if same else ("closes-but-differs" if ok else "still bad")
    print(f"  {cid}: {status}")
    if not same:
        print(f"      got L={rec['length']} R={rec['radius']} d={rec['delta']:.4f} c={rec['chord']}")
        print(f"      gt  L={g['length']} R={g['radius']} d={g['delta']:.4f} c={g['chord']}")
print(f"\nrecovered exactly: {ex}/{n}  ({100*ex/n:.0f}%)" if n else "")
print(f"(before repair: 0/{n} of these rows were correct)")
