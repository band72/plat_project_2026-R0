"""
Cell-accurate OCR benchmark vs hand-transcribed ground truth.
This is the real accuracy number for the pipeline.
"""
import sys
sys.path.insert(0, '.')
from engine.ocr import (load_gray, find_table_regions_inside_border,
                        parse_table_by_cells, validate_curve, repair_curve)
import data.trail_ridge_estates as trd

import os

FILES = {
    "PB0082_P0035_4216027_sheet_4_of_6.png": 3,
    "PB0082_P0035_4216027_sheet_5_of_6.png": 4,
    "PB0082_P0035_4216027_sheet_6_of_6.png": 5,
}

found_files = {}
for fn, sheet in FILES.items():
    for p in [f"/mnt/user-data/uploads/{fn}", f"temp_images/{fn}", f"data/{fn}", fn]:
        if os.path.exists(p):
            found_files[p] = sheet
            break

if not found_files:
    print(f"Benchmark skipped: local source images not found ({list(FILES.keys())})")
    sys.exit(0)

all_curves, all_lines = {}, {}
for path, sheet in found_files.items():
    img = load_gray(path)
    h, w = img.shape
    regs = [r for r in find_table_regions_inside_border(img) if r[0] > w * 0.65]
    sc, sl = {}, {}
    for r in regs:
        c, l = parse_table_by_cells(img, r)
        sc.update(c)
        sl.update(l)
    print(f"sheet {sheet}: {len(regs)} table regions -> {len(sc)} curves, {len(sl)} lines")
    all_curves.update(sc)
    all_lines.update(sl)

print(f"\nTOTAL: {len(all_curves)} curves, {len(all_lines)} lines")

print("\n=== SELF-VALIDATION ===")
ok, rep, bad = [], [], []
for cid, rec in sorted(all_curves.items()):
    good, msg = validate_curve(rec)
    if good:
        ok.append(cid)
        continue
    fix = repair_curve(rec)
    if fix and validate_curve(fix)[0]:
        all_curves[cid] = fix
        rep.append((cid, msg))
    else:
        bad.append((cid, msg))
print(f"clean: {len(ok)}   repaired: {len(rep)}   rejected: {len(bad)}")
for cid, m in rep:
    print(f"   repaired {cid}: {m}")
for cid, m in bad:
    print(f"   REJECTED {cid}: {m}")

gt = {k: v for k, v in trd.CURVE_TABLE.items() if isinstance(v, dict) and "radius" in v}
print("\n=== CURVES vs GROUND TRUTH ===")
found = exact = 0
diffs = []
for cid, g in sorted(gt.items()):
    if cid not in all_curves:
        continue
    found += 1
    o = all_curves[cid]
    if (abs(o["radius"] - g["radius"]) < 0.02 and abs(o["length"] - g["length"]) < 0.02
            and abs(o["chord"] - g["chord"]) < 0.02 and abs(o["delta"] - g["delta"]) < 0.01
            and o["chord_bearing"].replace(" ", "") == g["chord_bearing"].replace(" ", "")):
        exact += 1
    else:
        diffs.append((cid, o, g))
print(f"ground truth: {len(gt)}   found: {found}   exact: {exact}"
      + (f"   ({100*exact/found:.1f}% of found)" if found else ""))
for cid, o, g in diffs:
    print(f"  {cid}: OCR L={o['length']} R={o['radius']} d={o['delta']:.4f} "
          f"cb={o['chord_bearing']} c={o['chord']}")
    print(f"       GT  L={g['length']} R={g['radius']} d={g['delta']:.4f} "
          f"cb={g['chord_bearing']} c={g['chord']}")
miss = sorted(set(gt) - set(all_curves))
print(f"missing ({len(miss)}): {miss}")

print("\n=== LINES vs GROUND TRUTH ===")
gtl = trd.LINE_TABLE
lf = le = 0
for lid, g in sorted(gtl.items()):
    if lid not in all_lines:
        continue
    lf += 1
    o = all_lines[lid]
    if (abs(o["length"] - g["length"]) < 0.02
            and o["bearing"].replace(" ", "") == g["bearing"].replace(" ", "")):
        le += 1
    else:
        print(f"  {lid}: OCR {o['length']} {o['bearing']}  |  GT {g['length']} {g['bearing']}")
print(f"ground truth: {len(gtl)}   found: {lf}   exact: {le}")
print(f"missing: {sorted(set(gtl) - set(all_lines))}")
