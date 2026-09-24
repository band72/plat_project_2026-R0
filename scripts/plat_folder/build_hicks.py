"""HICKS SUBDIVISION of the N.W.1/4 of the N.E.1/4 of Sec 12, T2S, R25E
(Ellis, Curtis & Kooker, March 30 1912; filed Plat Book 4, folio 85, 19 Apr 1912).
Left panel of Plat/Plat_Book_4_Page_85.pdf.

Every distance below is read off the scan.  The plat prints NO bearings, so the
orientation (north line due East, west line due South) is an assumption; the
south-east corner is then fixed by the printed 1333' east and 1309' south lines.
The A.C.L. R.R. right-of-way is curved on the plat and carries no curve data:
its two lines are fitted as circles through the printed side-line ties to it.
Stated acreages are checked against computed areas -- they are the only
independent redundancy this 1912 plat offers.
"""
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from scripts.plat_folder.common import (SQFT_PER_ACRE, arc_points, fit_circle, out_dir, render_png,  # noqa: E402
                                        save_metrics, shoelace, write_dxf)

PLAT_ID = "PB4_P85_Hicks"

# ---- exterior (as printed) -------------------------------------------------
NORTH, WEST, EAST, SOUTH = 1320.0, 1335.0, 1333.0, 1309.0
NW = (0.0, 0.0)
NE = (NORTH, 0.0)
SW = (0.0, -WEST)


def circle_intersect(c0, r0, c1, r1, near):
    dx, dy = c1[0] - c0[0], c1[1] - c0[1]
    d = math.hypot(dx, dy)
    a = (r0 * r0 - r1 * r1 + d * d) / (2 * d)
    h = math.sqrt(r0 * r0 - a * a)
    mx, my = c0[0] + a * dx / d, c0[1] + a * dy / d
    cands = [(mx + h * dy / d, my - h * dx / d), (mx - h * dy / d, my + h * dx / d)]
    return min(cands, key=lambda p: math.dist(p, near))


SE = circle_intersect(NE, EAST, SW, SOUTH, near=(SOUTH, -WEST))


def along(p0, p1, d):
    L = math.dist(p0, p1)
    return (p0[0] + (p1[0] - p0[0]) * d / L, p0[1] + (p1[1] - p0[1]) * d / L)


def east_at(d):
    return along(NE, SE, d)


def south_at(d):
    return along(SW, SE, d)


# ---- interior grid (as printed) ---------------------------------------------
X1 = 451.3            # Newman | William (451.3 + 451.3 + 417.4 = 1320.0)
X2 = X1 + 451.3       # William | Roberson, and Levi | Roberson
XE = 570.0            # Edward | Levi / Wilson (Edward's 570 north line)
Y1 = -321.0           # south line of Newman & William
Y2 = Y1 - 408.0       # south line of Levi (408 sides)
S1 = 558.8            # Frank | Richard (W) along south line
S2 = S1 + 408.1       # Richard (W) | Richard (E); 341.1 remains to SE (sum 1308.0 vs 1309 printed)

# ---- A.C.L. R.R. right-of-way: fit both lines through the printed ties -----
rr_n_pts = [(0.0, Y1 - 719.7),          # west line: 321 + 719.7 to R/W
            (XE, Y1 - 658.7),           # Edward east side 658.7 to R/W
            east_at(417.4 + 313.0 + 74.5)]  # east line: Roberson 417.4, 313, Wilson 74.5
b1, b2 = south_at(S1), south_at(S2)
rr_s_pts = [(0.0, -WEST + 202.0),       # Frank west side 202
            (b1[0], b1[1] + 266.0),     # Frank / Richard side 266
            (b2[0], b2[1] + 382.0),     # Richard / Richard side 382
            east_at(EAST - 432.0)]      # Richard (E) east side 432 (digit "4" faint)
cn = fit_circle(rr_n_pts)
cs = fit_circle(rr_s_pts)


def on_circle_vertical(c, x, near_y):
    cx, cy, r = c
    dy = math.sqrt(r * r - (x - cx) ** 2)
    return min([(x, cy + dy), (x, cy - dy)], key=lambda p: abs(p[1] - near_y))


def project(c, p):
    cx, cy, r = c
    a = math.atan2(p[1] - cy, p[0] - cx)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


def on_circle_line(c, p0, p1, near):
    """Intersection of circle c with the line p0->p1 closest to `near`."""
    cx, cy, r = c
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    fx, fy = p0[0] - cx, p0[1] - cy
    A, B, C = dx * dx + dy * dy, 2 * (fx * dx + fy * dy), fx * fx + fy * fy - r * r
    disc = math.sqrt(B * B - 4 * A * C)
    ts = [(-B + disc) / (2 * A), (-B - disc) / (2 * A)]
    return min(((p0[0] + t * dx, p0[1] + t * dy) for t in ts), key=lambda p: math.dist(p, near))


# R/W corners snapped onto the fitted circles (so adjoining parcels share them)
n_w = on_circle_line(cn, NW, SW, rr_n_pts[0])
n_e5 = on_circle_vertical(cn, XE, rr_n_pts[1][1])
n_e = on_circle_line(cn, NE, SE, rr_n_pts[2])
s_w = on_circle_line(cs, NW, SW, rr_s_pts[0])
s_1 = on_circle_line(cs, b1, (b1[0], b1[1] + 1), rr_s_pts[1])
s_2 = on_circle_line(cs, b2, (b2[0], b2[1] + 1), rr_s_pts[2])
s_e = on_circle_line(cs, NE, SE, rr_s_pts[3])

rn = lambda a, b: arc_points(*cn, a, b)[1:-1]  # noqa: E731
rs = lambda a, b: arc_points(*cs, a, b)[1:-1]  # noqa: E731

E4174, E7304 = east_at(417.4), east_at(417.4 + 313.0)

PARCELS = [  # (name, stated acres, ring)
    ("LOUISA NEWMAN", 3.32, [NW, (X1, 0), (X1, Y1), (0, Y1)]),
    ("WILLIAM HICKS", 3.32, [(X1, 0), (X2, 0), (X2, Y1), (X1, Y1)]),
    ("MARGENA ROBERSON (N)", 4.00, [(X2, 0), NE, E4174, (X2, -417.4)]),
    ("MARGENA ROBERSON (S)", 3.00, [(X2, -417.4), E4174, E7304, (X2, Y2)]),
    ("LEVI HICKS", 3.07, [(XE, Y1), (X2, Y1), (X2, Y2), (XE, Y2)]),
    ("EDWARD HICKS", 9.00, [(0, Y1), (XE, Y1), n_e5] + rn(n_e5, n_w) + [n_w]),
    ("WILSON HICKS", 2.97, [(XE, Y2), (X2, Y2), E7304, n_e] + rn(n_e, n_e5) + [n_e5]),
    ("FRANK HICKS", 3.00, [s_w] + rs(s_w, s_1) + [s_1, b1, SW]),
    ("RICHARD HICKS (W)", 2.80, [s_1] + rs(s_1, s_2) + [s_2, b2, b1]),
    ("RICHARD HICKS (E)", 3.00, [s_2] + rs(s_2, s_e) + [s_e, SE, b2]),
]

# ---- redundancy checks -----------------------------------------------------
checks = []
for name, stated, ring in PARCELS:
    ac = shoelace(ring) / SQFT_PER_ACRE
    checks.append({"parcel": name, "stated_ac": stated, "computed_ac": round(ac, 3),
                   "diff_pct": round(100 * (ac - stated) / stated, 2)})

dim_resid = {
    "Levi north line 330 vs model": round((X2 - XE) - 330.0, 2),
    "Wilson north line 743.4 vs model": round(math.dist((XE, Y2), E7304) - 743.4, 2),
    "Wilson west side 247.7 vs model": round((Y2 - n_e5[1]) - 247.7, 2),
    "south line parts 1308.0 vs 1309": round(S1 + 408.1 + 341.1 - SOUTH, 2),
    "R/W north tie residuals (ft)": [round(math.dist(p, project(cn, p)), 2) for p in rr_n_pts],
    "R/W south tie residuals (ft)": [round(math.dist(p, project(cs, p)), 2) for p in rr_s_pts],
}
row_width = [round(cs[2] - cn[2], 1), round(math.dist(n_w, s_w), 1), round(math.dist(n_e, s_e), 1)]
boundary_area = shoelace([NW, NE, SE, SW]) / SQFT_PER_ACRE
parcel_sum = sum(c["computed_ac"] for c in checks)
row_area = boundary_area - parcel_sum

worst = max(abs(c["diff_pct"]) for c in checks)
flagged = [c["parcel"] for c in checks if abs(c["diff_pct"]) > 5.0]

# ---- outputs -----------------------------------------------------------------
d = out_dir(PLAT_ID)
layers = [("BOUNDARY", "white", "CONTINUOUS"), ("PARCEL", "cyan", "CONTINUOUS"),
          ("PARCEL-FLAGGED", "red", "CONTINUOUS"), ("RR-ROW", "yellow", "DASHDOT"),
          ("TEXT-LABELS", "white", "CONTINUOUS"), ("TITLEBLOCK", "yellow", "CONTINUOUS")]
rings = [("BOUNDARY", [NW, NE, SE, SW])]
texts = []
for (name, stated, ring), c in zip(PARCELS, checks):
    lay = "PARCEL-FLAGGED" if name in flagged else "PARCEL"
    rings.append((lay, ring))
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    texts.append(("TEXT-LABELS", (cx, cy + 15), name, 12))
    texts.append(("TEXT-LABELS", (cx, cy - 15), f"{stated}A stated / {c['computed_ac']:.2f}A calc", 8))
lines = [("RR-ROW", arc_points(*cn, n_w, n_e)), ("RR-ROW", arc_points(*cs, s_w, s_e))]
texts.append(("TEXT-LABELS", ((n_w[0] + n_e[0]) / 2, (n_w[1] + s_w[1]) / 2 + 60), "A.C.L. R.R. (fitted, no curve data on plat)", 9))
texts.append(("TITLEBLOCK", (NORTH / 2, 120), "HICKS SUBDIVISION  NW1/4 NE1/4 SEC 12 T2S R25E  PB 4 FOLIO 85 (1912)", 18))
texts.append(("TITLEBLOCK", (NORTH / 2, 80), "NO BEARINGS ON PLAT - ORIENTATION ASSUMED CARDINAL", 10))

write_dxf(os.path.join(d, "PB0004_P0085_Hicks_claude.dxf"), layers, rings, lines, texts)
render_png(os.path.join(d, "PB0004_P0085_Hicks.png"), "Hicks Subdivision (PB 4 folio 85, 1912) - faithful reconstruction",
           rings, lines, texts, flagged={"PARCEL-FLAGGED"})

metrics = {
    "plat_id": PLAT_ID,
    "source": "Plat/Plat_Book_4_Page_85.pdf (left panel)",
    "parcels_on_plat": 10,
    "parcels_built": len(PARCELS),
    "boundary": {"type": "record dims, 4 sides", "closure": "closed by construction (SE from 1333'/1309' arcs)",
                 "area_ac": round(boundary_area, 3)},
    "area_checks": checks,
    "worst_area_diff_pct": worst,
    "flagged": flagged,
    "dimension_residuals": dim_resid,
    "rr_row_width_ft": {"radius_diff": row_width[0], "on_west_line": row_width[1], "on_east_line": row_width[2]},
    "rr_row_area_ac": round(row_area, 3),
    "assumptions": [
        "No bearings on plat: north line taken due East, west line due South.",
        "A.C.L. R.R. R/W lines fitted as circles through printed side-line ties (no curve data on plat).",
        "Richard Hicks (E) east side read as 432 (first digit faint; 432 is the only value consistent with the R/W width).",
        "Interior division lines taken perpendicular to the north line.",
    ],
}
save_metrics(PLAT_ID, metrics)

print(f"SE corner: E {SE[0]:.2f}  N {SE[1]:.2f}   boundary {boundary_area:.3f} ac")
print(f"R/W circles: north R={cn[2]:.1f}  south R={cs[2]:.1f}  width {row_width}")
for c in checks:
    print(f"  {c['parcel']:<22} stated {c['stated_ac']:>5.2f}A  calc {c['computed_ac']:>6.3f}A  ({c['diff_pct']:+.2f}%)")
for k, v in dim_resid.items():
    print(f"  {k}: {v}")
print(f"worst area diff {worst:.2f}%  flagged: {flagged or 'none'}")
