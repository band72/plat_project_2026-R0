"""JOHN M. STEVENS SUBDIVISION of part of the Chas. F. Sibbald Grant, Sec 55, and Lot 4 Sec 5, T2S R26E, Duval County
(Ellis, Curtis & Kooker, surveyed 1908, dedicated Dec 1910). Right panel of Plat/Plat_Book_4_Page_85.pdf.

No bearings on the plat. Frame assumption: the Section Line (west side of Lots 36-45) runs due South, and the lot lines
are square to it. Built so far (from the scan, 300 dpi):
    Lots 26-45 south of the Sibbald Grant south line, either side of 50' Stevens Ave.
    todo: Lots 1-25 and 46+ north of it (A.C.L. R.R., Kings Road, Belle St, Park Ave).
"""
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine.dxf_writer import writer_suffix  # noqa: E402
from scripts.plat_folder.common import SQFT_PER_ACRE, out_dir, render_png, save_metrics, shoelace, write_dxf  # noqa: E402

PLAT_ID = "PB4_P85_Stevens"
W, ST, D = 621.50, 50.0, 175.2          # lot width, Stevens Ave width, standard depth
lots, checks = {}, {}

# x: east from the Section Line; y: north, 0 on the Sibbald Grant south line (tops of Lots 45 and 26)
xw0, xw1, xe0, xe1 = 0.0, W, W + ST, W + ST + W
# South end: west column 146.75' per lot (Lots 37, 36), east column 156.75' (Lots 34, 35) -> the two lower lines are
# skewed. Side length varies linearly across the full 1293' width between the printed values.
k = (156.75 - 146.75) / xe1


def side(x):
    return 146.75 + k * x


y8 = -8 * D                               # bottom of Lots 38 / 33
for i, (lw, le) in enumerate(zip(range(45, 37, -1), range(26, 34))):
    y0, y1 = -i * D, -(i + 1) * D
    lots[str(lw)] = {"ring": [(xw0, y0), (xw1, y0), (xw1, y1), (xw0, y1)], "stated": 2.5}
    lots[str(le)] = {"ring": [(xe0, y0), (xe1, y0), (xe1, y1), (xe0, y1)], "stated": 2.5}
for n, (lw, le) in enumerate(((37, 34), (36, 35))):
    top = lambda x: y8 - n * side(x)          # noqa: E731
    bot = lambda x: y8 - (n + 1) * side(x)    # noqa: E731
    lots[str(lw)] = {"ring": [(xw0, top(xw0)), (xw1, top(xw1)), (xw1, bot(xw1)), (xw0, bot(xw0))], "stated": 2.16}
    lots[str(le)] = {"ring": [(xe0, top(xe0)), (xe1, top(xe1)), (xe1, bot(xe1)), (xe0, bot(xe0))], "stated": 2.16}

# ---- north of the Sibbald Grant south line (y = 0), east of Stevens Ave (read at 300 dpi, tick 18) ----
# Belle St south row: Lot 20 (234', railroad-bounded, todo), Lot 19 120' (west 391', east 405'), Lots 18-9 105' x 405'.
x = xe0 + 234.0                        # Lot 20 / 19 line
lots["19"] = {"ring": [(x, 0.0), (x + 120.0, 0.0), (x + 120.0, 405.0), (x, 391.0)], "stated": 1.02}
x += 120.0
for n in range(18, 8, -1):
    lots[str(n)] = {"ring": [(x, 0.0), (x + 105.0, 0.0), (x + 105.0, 405.0), (x, 405.0)], "stated": 1.0}
    x += 105.0
x9e = x                                  # east line of Lot 9 = west line of Lots 2-7 and of Block 8
# Block 8 (Lots 1-4, 105' x 105' under the 420' line) and Lots 7, 6, 5 (105/105/90) up to Belle St's south line (y 405),
# Belle St 30', then Lots 4, 3, 2 (90/105/105). All 420' wide. Lot 1 (117.8' east side, under the railroad) is todo.
for i, n in enumerate(("4", "3", "2", "1")):
    lots[f"B8-{n}"] = {"ring": [(x9e + 105.0 * i, 0.0), (x9e + 105.0 * (i + 1), 0.0), (x9e + 105.0 * (i + 1), 105.0),
                                (x9e + 105.0 * i, 105.0)], "stated": None}
y = 105.0
for n, dpt in (("7", 105.0), ("6", 105.0), ("5", 90.0)):
    lots[n] = {"ring": [(x9e, y), (x9e + 420.0, y), (x9e + 420.0, y + dpt), (x9e, y + dpt)], "stated": 1.0}
    y += dpt
K405 = "Lots 5-7 + Block 8 = Lot 9's 405'"
checks[K405] = (y, 405.0)
y += 30.0                                # Belle St
for n, dpt in (("4", 90.0), ("3", 105.0), ("2", 105.0)):
    lots[n] = {"ring": [(x9e, y), (x9e + 420.0, y), (x9e + 420.0, y + dpt), (x9e, y + dpt)], "stated": 1.0}
    y += dpt

# ---- railroad-bounded lots (tick 29, best fit per user decision) ----
# A.C.L. R.R. south R/W line: circle least-squares fitted to the 4 printed ties that end on it (Lot 20/19 391', Lot 23/22 185.6',
# Lot 22/21 249.5', Lot 1 east 117.8'); R ~ 26,500', ties within 1.7'. Belle St taken as 30' (north line y = 435), like the east column.
import numpy as np  # noqa: E402
from scipy.optimize import least_squares  # noqa: E402
_T = np.array([(xe0 + 234.0, 391.0), (xe0 + 984.0, 435.0 + 185.6), (xe0 + 1194.0, 435.0 + 249.5), (xe0 + 1824.0, 735.0 + 117.8)])
_f = least_squares(lambda q: np.hypot(_T[:, 0] - q[0], _T[:, 1] - q[1]) - q[2], [xe0 + 900.0, -26000.0, 26500.0])
RCX, RCY, RR = _f.x
for (tx, ty), r_ in zip(_T, _f.fun):
    checks[f"R.R. tie at x={tx - xe0:.0f}"] = (ty - r_, ty)


def rr_y(x_):
    return RCY + math.sqrt(RR * RR - (x_ - RCX) ** 2)


def rr_x_at(y_, x_guess):
    lo, hi = x_guess - 800.0, x_guess + 800.0
    for _ in range(80):
        mid_ = (lo + hi) / 2
        if rr_y(mid_) < y_:
            lo = mid_
        else:
            hi = mid_
    return (lo + hi) / 2


def rr_edge(x0_, x1_, n=12):
    return [(x0_ + (x1_ - x0_) * k / n, rr_y(x0_ + (x1_ - x0_) * k / n)) for k in range(n + 1)]


x1312, x1110, x9e_ = xe0 + 984.0, xe0 + 1194.0, xe0 + 1404.0
apex23 = rr_x_at(435.0, x1312)
lots["20"] = {"ring": [(xe0, 0.0), (xe0 + 234.0, 0.0)] + rr_edge(xe0 + 234.0, xe0, 16), "stated": 1.82}
lots["23"] = {"ring": [(apex23, 435.0), (x1312, 435.0)] + rr_edge(x1312, apex23, 16)[:-1], "stated": 1.59}
lots["22"] = {"ring": [(x1312, 435.0), (x1110, 435.0)] + rr_edge(x1110, x1312), "stated": 1.10}
lots["21"] = {"ring": [(x1110, 435.0), (x9e_, 435.0)] + rr_edge(x9e_, x1110), "stated": 1.38}
lots["1"] = {"ring": [(x9e_, 735.0), (x9e_ + 420.0, 735.0)] + rr_edge(x9e_ + 420.0, x9e_), "stated": 0.57}
RR_LOTS = {"20", "23", "22", "21", "1"}

# ---- north of the railroad (tick 31): INSET in its own frame. The plat prints no angle between Kings Road and the lot lines,
# but the acreages fix it at 90° (Lots 55-57: 420 x 105 = 1.01A vs "1.A"; Lot 49: 105 x 412 = 0.99A vs "1.A"), and no printed
# dimension ties this tier to the lots south of the railroad -- so it is drawn as an inset, NOT in position.
IX, IY = xe1 + 400.0, 900.0                               # inset origin (clear of the main drawing)
for k, n in enumerate(("55", "56", "57")):
    y0 = IY - 105.0 * k
    lots[n] = {"ring": [(IX, y0), (IX + 420.0, y0), (IX + 420.0, y0 - 105.0), (IX, y0 - 105.0)], "stated": 1.0}
kx = IX + 600.0                                           # Kings Road row: Lot 49 (105 x 412), Lot 48 (105, 412 / 390)
lots["49"] = {"ring": [(kx, IY), (kx + 105.0, IY), (kx + 105.0, IY - 412.0), (kx, IY - 412.0)], "stated": 1.0}
lots["48"] = {"ring": [(kx + 105.0, IY), (kx + 210.0, IY), (kx + 210.0, IY - 390.0), (kx + 105.0, IY - 412.0)], "stated": 0.99}
INSET = {"55", "56", "57", "49", "48"}

area_checks = []
for num, v in lots.items():
    ac = shoelace(v["ring"]) / SQFT_PER_ACRE
    v["acres"] = ac
    if v["stated"] is None:
        continue
    area_checks.append({"lot": num, "stated_ac": v["stated"], "computed_ac": round(ac, 3),
                        "diff_pct": round(100 * (ac - v["stated"]) / v["stated"], 2)})
FLAGGED = {c["lot"] for c in area_checks if abs(c["diff_pct"]) > 5.0} | RR_LOTS | INSET
checks["Lots 36+37 average vs 2.16A"] = ((lots["36"]["acres"] + lots["34"]["acres"]) / 2.0, 2.16)
worst = max(abs(c["diff_pct"]) for c in area_checks)

d = out_dir(PLAT_ID)
rings = [("LOT-FLAGGED" if n in FLAGGED else "LOT", v["ring"]) for n, v in lots.items()]
texts = [("TEXT-LABELS", (sum(p[0] for p in v["ring"]) / 4, sum(p[1] for p in v["ring"]) / 4),
          f"{n}  {v['stated']}A" if v["stated"] else n, 14) for n, v in lots.items()]
texts.append(("TITLEBLOCK", (xe1 / 2, 60.0), "JOHN M. STEVENS SUBDIVISION  PB 4 FOLIO 85 (1910)  -  ag reconstruction (in progress)", 18))
texts.append(("TITLEBLOCK", (IX + 300.0, IY + 60.0), "INSET - LOTS 55-57, 49, 48 (NORTH OF A.C.L. R.R.) - NOT IN POSITION: NO PRINTED TIE", 12))
texts.append(("TITLEBLOCK", (xe1 / 2, 30.0), "NO BEARINGS ON PLAT - SECTION LINE TAKEN DUE SOUTH; LOTS NORTH OF THE SIBBALD GRANT LINE NOT YET BUILT", 10))
layers = [("LOT", "cyan", "CONTINUOUS"), ("LOT-FLAGGED", "red", "CONTINUOUS"), ("TEXT-LABELS", "white", "CONTINUOUS"), ("TITLEBLOCK", "yellow", "CONTINUOUS")]
write_dxf(os.path.join(d, f"PB0004_P0085_Stevens{writer_suffix()}.dxf"), layers, rings, [], texts)
render_png(os.path.join(d, "PB0004_P0085_Stevens.png"), "John M. Stevens Subdivision (PB 4 folio 85) - ag reconstruction (Lots 26-45)",
           rings, [], texts, flagged={"LOT-FLAGGED"})
save_metrics(PLAT_ID, {
    "plat_id": PLAT_ID, "source": "Plat/Plat_Book_4_Page_85.pdf (right panel)",
    "lots_built": len(lots), "lots_todo": "1-25 and 46+ (north of the Sibbald Grant south line)",
    "area_checks": sorted(area_checks, key=lambda c: c["lot"]),
    "flagged": sorted(FLAGGED),
    "checks": {k: {"computed": round(c, 3), "printed": p_} for k, (c, p_) in checks.items()},
    "worst_area_diff_pct": worst,
    "assumptions": [
        "No bearings on the plat: Section Line taken due South, lot lines square to it.",
        "Lots 34-37: printed depths 146.75' (west column) and 156.75' (east column) interpreted as a south line skewed across the "
        "full width; the plat's single 2.16A for all four is their average (2.13A / 2.20A computed).",
    ],
})
for c in sorted(area_checks, key=lambda c: c["lot"]):
    print(f"  Lot {c['lot']:>2}: stated {c['stated_ac']}A  calc {c['computed_ac']}A  ({c['diff_pct']:+.2f}%)")
print(f"lots {len(lots)}  worst {worst:.2f}%  flagged {sorted(FLAGGED)} | avg 34-37: {checks['Lots 36+37 average vs 2.16A'][0]:.3f}A vs 2.16"
      f" | 5-7 + B8 = {checks[K405][0]:.1f} vs 405")
