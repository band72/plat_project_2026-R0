"""
Benchmark the OCR pipeline against the hand-transcribed ground truth for
Trail Ridge Estates. This is how we learn whether the algorithm is good
enough to trust on plats where no human transcription exists.
"""
import sys
sys.path.insert(0, '.')
from engine.ocr import (load_gray, ocr_best, parse_curve_rows, parse_line_rows,
                        validate_curve, repair_curve)
import data.trail_ridge_estates as trd

FILES = {
    # file name -> actual sheet number (naming is offset: file_1/file_2 are dupes of sheet 1)
    "PB0082_P0035_4216027_sheet_4_of_6.png": 3,
    "PB0082_P0035_4216027_sheet_5_of_6.png": 4,
    "PB0082_P0035_4216027_sheet_6_of_6.png": 5,
}

all_curves, all_lines = {}, {}
for fn, sheet in FILES.items():
    img = load_gray(f"/mnt/user-data/uploads/{fn}")
    h, w = img.shape
    # Clay County sheets put line/curve tables in the right margin
    strip = (int(w * 0.69), int(h * 0.18), int(w * 0.31), int(h * 0.60))
    txt = ocr_best(img, strip)
    c = parse_curve_rows(txt)
    l = parse_line_rows(txt)
    print(f"sheet {sheet}: OCR parsed {len(c)} curve rows, {len(l)} line rows")
    all_curves.update(c)
    all_lines.update(l)

print(f"\nTOTAL parsed: {len(all_curves)} curves, {len(all_lines)} lines")

# ---- self-validation (no ground truth needed -- works on any plat) ----
print("\n=== SELF-VALIDATION (geometry consistency, needs no ground truth) ===")
ok, repaired, failed = [], [], []
for cid, rec in sorted(all_curves.items()):
    good, msg = validate_curve(rec)
    if good:
        ok.append(cid)
    else:
        fix = repair_curve(rec)
        if fix and validate_curve(fix)[0]:
            all_curves[cid] = fix
            repaired.append((cid, msg))
        else:
            failed.append((cid, msg))
print(f"passed clean: {len(ok)}")
print(f"auto-repaired: {len(repaired)}")
for cid, m in repaired:
    print(f"   {cid}: {m}")
print(f"unrecoverable: {len(failed)}")
for cid, m in failed:
    print(f"   {cid}: {m}")

# ---- score against hand-transcribed ground truth ----
print("\n=== SCORED vs HAND-TRANSCRIBED GROUND TRUTH ===")
gt = {k: v for k, v in trd.CURVE_TABLE.items() if isinstance(v, dict) and "radius" in v}
matched = exact = 0
mismatches = []
for cid, g in sorted(gt.items()):
    if cid not in all_curves:
        continue
    matched += 1
    o = all_curves[cid]
    same = (abs(o["radius"] - g["radius"]) < 0.02 and
            abs(o["length"] - g["length"]) < 0.02 and
            abs(o["chord"] - g["chord"]) < 0.02 and
            abs(o["delta"] - g["delta"]) < 0.01 and
            o["chord_bearing"].replace(" ", "") == g["chord_bearing"].replace(" ", ""))
    if same:
        exact += 1
    else:
        mismatches.append((cid, o, g))

print(f"ground-truth curves: {len(gt)}")
print(f"found by OCR:        {matched}")
print(f"exact field match:   {exact}")
if matched:
    print(f"accuracy on found rows: {100*exact/matched:.1f}%")
for cid, o, g in mismatches[:12]:
    print(f"\n  {cid} MISMATCH")
    print(f"    OCR: L={o['length']} R={o['radius']} d={o['delta']:.4f} cb={o['chord_bearing']} c={o['chord']}"
          + (" [repaired]" if o.get("repaired") else ""))
    print(f"    GT : L={g['length']} R={g['radius']} d={g['delta']:.4f} cb={g['chord_bearing']} c={g['chord']}")

missing = sorted(set(gt) - set(all_curves))
print(f"\nGround-truth curves NOT found by OCR ({len(missing)}): {missing}")

print("\n=== LINE TABLE vs GROUND TRUTH ===")
gtl = trd.LINE_TABLE
lmatch = lexact = 0
for lid, g in sorted(gtl.items()):
    if lid not in all_lines:
        continue
    lmatch += 1
    o = all_lines[lid]
    if (abs(o["length"] - g["length"]) < 0.02 and
            o["bearing"].replace(" ", "") == g["bearing"].replace(" ", "")):
        lexact += 1
    else:
        print(f"  {lid}: OCR {o['length']} {o['bearing']}  |  GT {g['length']} {g['bearing']}")
print(f"ground-truth lines: {len(gtl)}, found: {lmatch}, exact: {lexact}")
