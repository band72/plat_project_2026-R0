"""Beachwood Unit Two -- Sheet 2 (Line & Curve Tables) and Sheet 3 (Map Checks) for every lot on the full plat.

Every course of every placed lot comes from its block solver (engine/cogo_block.py) via the full-plat composer, so the tables
describe exactly the geometry drawn on the combined sheet. A line or curve shared by two lots appears once, tagged L# / C#,
with the lots it bounds. `course_tags()` returns the tag labels for the plan sheet (layer COURSE-TAG).
"""
import math
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine import dxf_writer
from engine.dxf_writer import writer_suffix  # noqa: E402
from engine.tables import draw_split_table  # noqa: E402
from scripts.plat_folder.common import out_dir  # noqa: E402

PLAT_ID = "PB30_P82_Beachwood"


def _brg(s):
    return re.sub(r"(\d+)\.\d+\"", r'\1"', s)            # N87°35'30.00"E -> N87°35'30"E


def _block_order(b):
    return int(b.split("_")[1])


def collect():
    """Placed lots -> (lines, curves, results) with plat-wide tags."""
    import scripts.plat_folder.build_beachwood_full as full
    placed, solvers = _quiet(full.main)
    lines, curves, results = {}, {}, []
    for bname in sorted(placed, key=_block_order):
        dn, de = placed[bname]["shift"]
        blk = bname.split("_")[1]
        res = solvers[bname].solve_all()
        for num in sorted(res, key=lambda n: (not n.isdigit(), int(n) if n.isdigit() else 0, n)):
            r = res[num]
            results.append((blk, num, r))
            for c in r.courses:
                a = (round(c.start_pt.n + dn, 2), round(c.start_pt.e + de, 2))
                b = (round(c.end_pt.n + dn, 2), round(c.end_pt.e + de, 2))
                key = (blk, tuple(sorted((a, b))))
                store = curves if c.is_curve else lines
                if key not in store:
                    mid = c.arc_points[len(c.arc_points) // 2] if c.is_curve and c.arc_points else None
                    store[key] = {"course": c, "block": blk, "lots": [], "a": a, "b": b,
                                  "mid": (mid.n + dn, mid.e + de) if mid else ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)}
                if num not in store[key]["lots"]:
                    store[key]["lots"].append(num)
    for i, v in enumerate(lines.values(), 1):
        v["tag"] = f"L{i}"
    for i, v in enumerate(curves.values(), 1):
        v["tag"] = f"C{i}"
    return lines, curves, results


def _quiet(fn):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn()


def course_tags():
    """(n, e, tag) for every tagged course, for the plan sheet."""
    lines, curves, _ = collect()
    return [(v["mid"][0], v["mid"][1], v["tag"]) for v in list(lines.values()) + list(curves.values())]


def write_sheets():
    lines, curves, results = collect()
    d = out_dir(PLAT_ID)

    # ---------------- Sheet 2: line and curve tables ----------------
    dxf = dxf_writer.DXFWriter()
    for name, col in (("TABLE_BORDER", "white"), ("TABLE_TEXT", "white"), ("TABLE_HEADER", "yellow"), ("TITLEBLOCK", "yellow")):
        dxf.add_layer(name, col)
    dxf.text((80.0, 0.0), "BEACHWOOD UNIT TWO -- PLAT BOOK 30, PAGES 82 & 82A -- SHEET 2: LINE AND CURVE TABLES (ALL LOTS)",
             18.0, "TITLEBLOCK")
    dxf.text((55.0, 0.0), f"{len(lines)} lines and {len(curves)} curves bounding {len(results)} lots. Tags L#/C# are shown on the "
             "plan sheet (layer COURSE-TAG). Curve bearings are chord bearings; distances on curves are arc lengths.", 8.0, "TITLEBLOCK")
    lrows = [[v["tag"], v["block"], ", ".join(v["lots"]), _brg(v["course"].bearing_str), f"{v['course'].distance:.2f}'"]
             for v in lines.values()]
    boxes = draw_split_table(dxf, 0.0, 0.0, "LINE TABLE", ["LINE", "BLK", "LOT(S)", "BEARING", "DISTANCE"], lrows,
                             [34.0, 26.0, 46.0, 88.0, 56.0], max_rows_per_col=60)
    right = max(b[1] for b in boxes) if boxes else 0.0     # (bottom_n, right_e, w, h)
    crows = []
    for v in curves.values():
        cd = v["course"].curve_data
        crows.append([v["tag"], v["block"], ", ".join(v["lots"]), f"{cd.get('radius', 0.0):.2f}'", f"{cd.get('length', 0.0):.2f}'",
                      str(cd.get("delta_dms", "")), _brg(v["course"].bearing_str), f"{cd.get('chord', 0.0):.2f}'",
                      f"{cd.get('tangent', 0.0):.2f}'"])
    draw_split_table(dxf, 0.0, right + 60.0, "CURVE TABLE",
                     ["CURVE", "BLK", "LOT(S)", "RADIUS", "LENGTH", "DELTA", "CHORD BEARING", "CHORD", "TANGENT"], crows,
                     [36.0, 26.0, 46.0, 50.0, 50.0, 66.0, 88.0, 50.0, 50.0], max_rows_per_col=60)
    p2 = os.path.join(d, f"PB0030_P0082_Beachwood_Sheet2_LineCurveTables{writer_suffix()}.dxf")
    dxf.save(p2)

    # ---------------- Sheet 3: map checks ----------------
    dxf = dxf_writer.DXFWriter()
    for name, col in (("TABLE_BORDER", "white"), ("TABLE_TEXT", "white"), ("TABLE_HEADER", "yellow"), ("TITLEBLOCK", "yellow")):
        dxf.add_layer(name, col)
    n_pass = sum(1 for _, _, r in results if r.passed)
    worst = max(r.misclose_dist_ft for _, _, r in results)
    dxf.text((80.0, 0.0), "BEACHWOOD UNIT TWO -- PLAT BOOK 30, PAGES 82 & 82A -- SHEET 3: LOT MAP CHECKS (ALL LOTS)", 18.0, "TITLEBLOCK")
    dxf.text((55.0, 0.0), f"{n_pass} of {len(results)} lots close (F.A.C. 5J-17, 1:10,000). Worst misclosure {worst:.4f}'. Record area = "
             "closed-form area from the printed dimensions (the plat prints no lot areas); DIFF = computed - record.", 8.0, "TITLEBLOCK")
    mrows = []
    for blk, num, r in results:
        mrows.append([blk, num, str(len(r.courses)), f"{r.perimeter_ft:.2f}'", f"{r.misclose_dist_ft:.4f}'",
                      "EXACT" if r.misclose_dist_ft < 1e-6 else r.precision_str, f"{r.computed_area_sqft:,.1f}",
                      f"{r.computed_acres:.4f}", f"{r.stated_area_sqft:,.1f}", f"{r.area_diff_sqft:+.1f}",
                      "PASS" if r.passed else "FAIL"])
    draw_split_table(dxf, 0.0, 0.0, "MAP CHECK SUMMARY",
                     ["BLK", "LOT", "CRS", "PERIMETER", "MISCLOSE", "PRECISION", "AREA SF", "ACRES", "RECORD SF", "DIFF", "CHECK"],
                     mrows, [26.0, 30.0, 26.0, 60.0, 56.0, 64.0, 62.0, 50.0, 62.0, 44.0, 40.0], max_rows_per_col=55)
    p3 = os.path.join(d, f"PB0030_P0082_Beachwood_Sheet3_MapChecks{writer_suffix()}.dxf")
    dxf.save(p3)

    # full course-by-course report
    p3t = os.path.join(d, "PB0030_P0082_Beachwood_MapCheck_Report.txt")
    with open(p3t, "w") as f:
        f.write(f"BEACHWOOD UNIT TWO -- MAP CHECKS, ALL LOTS ({len(results)})\n\n")
        for _, _, r in results:
            f.write(r.format_surveyor_sheet() + "\n\n")
    print(f"lines {len(lines)}  curves {len(curves)}  lots {len(results)}  pass {n_pass}  worst misclose {worst:.4f}'")
    for pth in (p2, p3, p3t):
        print(f"-> {pth}")


if __name__ == "__main__":
    write_sheets()
