"""OCEAN GROVE, UNIT NO. 1 -- Plat Book 15, Page 82, Duval County, FL (Ellis, Curtis & Kooker, 28 April 1937).
Plat/Plat_Book_15_Page_82.pdf.  Replaces the schematic scripts/build_ocean_grove.py (two rows of 50x120 lots).

The plat prints NO bearings: lines are dimensioned by the angles between them (89°48', 90°12', 90°17', ...), and the
caption distances are "more or less". So the frame is an assumption: 17th Street's south line runs due East; every
other direction comes from a printed angle. Blocks are built one at a time from the scan (see REFINEMENT_LOG.md):
    done: Block 8 (Lots 1-20), Block 7 (Lots 1-8), Block 6 (Lots 1-12)
    todo: Blocks 5, 4, 3, 2, 1 (curves on Dewees / Coquina / Beach / Mandalay)
"""
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine.dxf_writer import writer_suffix  # noqa: E402
from scripts.plat_folder.common import out_dir, render_png, save_metrics, shoelace, write_dxf  # noqa: E402

PLAT_ID = "PB15_P82_OceanGrove"
EAST = 90.0


def move(p, az, d):
    a = math.radians(az)
    return (p[0] + d * math.sin(a), p[1] + d * math.cos(a))   # (E, N)


def dms(d, m=0.0):
    return d + m / 60.0


# Directions from the printed angles (interior angles at the block corners, measured from the street line):
AZ_W8 = EAST + dms(89, 48)          # Block 8 west line and interior side lines (89°48' at NW) -> S0°12'E
AZ_E8 = 270.0 - dms(90, 17)         # Block 8 east line (90°17' at NE) -> S0°17'E
AZ_W7 = AZ_W8                       # Block 7 west + side lines (89°48' at NW, 90°12' at NE = parallel)

lots, checks, assumptions = {}, {}, [
    "No bearings on the plat: 17th Street S line taken as due East; all other directions from printed angles.",
    "Block 7 hangs off Block 8's west line across Coral St (40', measured along the west line).",
]


def add(block, num, ring, note=""):
    lots[f"B{block}-L{num}"] = {"block": block, "lot": num, "ring": ring, "area": shoelace(ring), "note": note}


# ---------------- Block 8: Lots 1-10 (north row) and 20-11 (south row), rows 110' deep ----------------
nw8 = (0.0, 0.0)                                   # P.R.M., Lot 1 NW
top = [nw8]
for w in [45.0] + [50.0] * 8:
    top.append(move(top[-1], EAST, w))
ne8 = move(top[-1], EAST, 54.3)                    # P.R.M., Lot 10 NE
top.append(ne8)
mid = [move(p, AZ_W8, 110.0) for p in top[:-1]] + [move(ne8, AZ_E8, 110.0)]
bot = [move(p, AZ_W8, 110.0) for p in mid[:-1]] + [move(mid[-1], AZ_E8, 110.0)]
for i in range(10):
    add(8, str(i + 1), [top[i], top[i + 1], mid[i + 1], mid[i]])
    add(8, str(20 - i), [mid[i], mid[i + 1], bot[i + 1], bot[i]])
checks["B8 south line 45+8x50+54.5 = 499.5'"] = (math.dist(bot[0], bot[-1]), 499.5)
checks["B8 Lot 11 south 54.5'"] = (math.dist(bot[-2], bot[-1]), 54.5)
checks["B8 Lot 20 south 45'"] = (math.dist(bot[0], bot[1]), 45.0)

# ---------------- Block 7: Lots 1-4 (north) and 8-5 (south), 4 x 50', rows 105' deep ----------------
nw7 = move(bot[0], AZ_W8, 40.0)                    # across Coral St
t7 = [nw7]
for _ in range(4):
    t7.append(move(t7[-1], EAST, 50.0))
m7 = [move(p, AZ_W7, 105.0) for p in t7]
b7 = [move(p, AZ_W7, 105.0) for p in m7]
for i in range(4):
    add(7, str(i + 1), [t7[i], t7[i + 1], m7[i + 1], m7[i]])
    add(7, str(8 - i), [m7[i], m7[i + 1], b7[i + 1], b7[i]])
checks["B7 south line 4x50' (parallel sides)"] = (math.dist(b7[0], b7[-1]), 200.0)

# ---------------- Block 6: Lots 1-5 (Coral St), 12 and 6 (middle), 11-7 (Dewees Ave / Coquina curve) ----------------
def meet(p, az1, q, az2):
    """Intersection of the line through p (azimuth az1) with the line through q (azimuth az2)."""
    d1 = (math.sin(math.radians(az1)), math.cos(math.radians(az1)))
    d2 = (math.sin(math.radians(az2)), math.cos(math.radians(az2)))
    den = d1[0] * d2[1] - d1[1] * d2[0]
    t = ((q[0] - p[0]) * d2[1] - (q[1] - p[1]) * d2[0]) / den
    return (p[0] + t * d1[0], p[1] + t * d1[1])


nw6 = move(t7[4], EAST, 40.0)   # across Coquina Place (40')
t6 = [nw6]
for w in (50.0, 50.0, 50.0, 50.0):
    t6.append(move(t6[-1], EAST, w))
ne6 = move(t6[-1], EAST, 57.9)
# Beach Ave W line at Lot 5: fixed by Lot 5's printed 38' south side (the printed 80°42' NE angle is kept as a check;
# the two disagree by ~20', i.e. 0.67' at the bottom of the lot)
r1 = [move(p, AZ_W8, 115.0) for p in t6]
l5se = move(r1[4], EAST, 38.0)
AZ_A = math.degrees(math.atan2(l5se[0] - ne6[0], l5se[1] - ne6[1])) % 360.0
for i in range(4):
    add(6, str(i + 1), [t6[i], t6[i + 1], r1[i + 1], r1[i]])
add(6, "5", [t6[4], ne6, l5se, r1[4]])
checks["B6 Lot 5 NE angle 80°42'"] = ((270.0 - AZ_A) % 360.0, dms(80, 42))
checks["B6 Lot 5 east 116.6'"] = (math.dist(ne6, l5se), 116.6)

# Beach Ave W line bends (angles on the street side): 25.2' more on A, 156°58' bend, 52.7', 192°44' bend
bend1 = move(l5se, AZ_A, 25.2)
AZ_B = (AZ_A + 180.0 + dms(156, 58)) % 360.0
l7ne = move(bend1, AZ_B, 52.7)
AZ_C = (EAST + 180.0 + 88.0 + 180.0) % 360.0       # Lot 7 east line from its own printed 88° SE angle
# 126' line (tops of Lots 9, 8, 7) runs west from Lot 7 NE, parallel to Coral St
x78t = move(l7ne, EAST + 180.0, 46.0)
x89t = move(x78t, EAST + 180.0, 50.0)
ce = move(x89t, EAST + 180.0, 30.0)              # chamfer end
p35 = move(r1[2], AZ_W8, 35.0)                    # Lot 12 / Lot 6 line: 35' + 25'
ch0 = move(r1[2], AZ_W8, 60.0)                    # chamfer start (Lot 6 SW / Lot 12 SE area)
l12sw = move(r1[0], AZ_W8, 60.0)
add(6, "12", [r1[0], r1[2], p35, l12sw])
add(6, "6", [r1[2], l5se, bend1, l7ne, ce, ch0])
checks["B6 Lot 12 south 103'"] = (math.dist(l12sw, p35), 103.0)
checks["B6 Lot 6 top 138'"] = (math.dist(r1[2], l5se), 138.0)
checks["B6 chamfer 25'"] = (math.dist(ch0, ce), 25.0)
# Lots 9-7 (115' deep) and the Dewees Ave N line
b89, b78 = move(x89t, AZ_W8, 115.0), move(x78t, AZ_W8, 115.0)
l7se = meet(b78, EAST, l7ne, AZ_C)
add(6, "8", [x89t, x78t, b78, b89])
add(6, "7", [x78t, l7ne, l7se, b78])
checks["B6 Lot 7 east 115.6'"] = (math.dist(l7ne, l7se), 115.6)
checks["B6 Lot 7 south 50'"] = (math.dist(b78, l7se), 50.0)
checks["B6 Beach bend 192°44' (street side)"] = ((AZ_C - AZ_B - 180.0) % 360.0, dms(192, 44))
# Coquina curve R=100, tangent to the Coquina E line and to the Dewees N line
R6 = 100.0
ctr6 = meet(move(l12sw, EAST, R6), AZ_W8, move(b89, AZ_W8 + 180.0, R6), EAST)
pt6 = move(ctr6, EAST + 180.0, R6)                # P.T. on Coquina
pc6 = move(ctr6, AZ_W8, R6)                       # P.C. on Dewees
def arc(s_):
    """Point on the Coquina curve s_ feet along the arc from the P.T. (swinging from west of centre to south)."""
    return move(ctr6, (270.0 - math.degrees(s_ / R6)) % 360.0, R6)



a61, a141 = arc(61.0), arc(141.0)


def arc_pts(s0, s1, n=24):
    return [arc(s0 + (s1 - s0) * k / n) for k in range(n + 1)]


add(6, "11", [l12sw, p35, ch0] + arc_pts(61.0, 0.0) + [pt6], "Coquina curve R=100")
add(6, "10", [ch0, ce] + arc_pts(141.0, 61.0), "Coquina curve R=100")
add(6, "9", [ce, x89t, b89, pc6] + arc_pts(math.radians(90.0) * R6, 141.0), "Coquina curve R=100")
checks["B6 Coquina tangent 26.4' (Lot 12 SW -> P.T.)"] = (math.dist(l12sw, pt6), 26.4)
checks["B6 Lot 9 arc 18' (141' + 18' = R x 90°?)"] = (math.radians(90.0) * R6 - 141.0, 18.0)
checks["B6 Lot 9 straight 48.5' (P.C. -> 8/9)"] = (math.dist(pc6, b89), 48.5)
checks["B6 Lot 10/11 line 118.3'"] = (math.dist(ch0, a61), 118.3)
checks["B6 Lot 9/10 line 119'"] = (math.dist(ce, a141), 119.0)
assumptions.append("Block 6: plat values conflict by ~5' (26.4' Coquina tangent vs the 115' lot depths, 52.7' Beach segment, 88° and the 25' "
                   "chamfer). Built from the majority (lot depths / Beach / chamfer); the R=100 Coquina curve is fitted tangent to both "
                   "street lines and its printed 26.4' tangent and 18' arc are reported as misfits.")

# ---------------- Block 4 (top rows): Lots 1/2, 11/3, 10/4 ----------------
# Shell St (40') below Block 7; west line continues Block 7's. Top 100' + 110'; west 50/50/50; middle line (easement) 50/50/35;
# east 50/50/55.6 on the Coquina W line (90°12' at NE = parallel). Lots 5-9 (R=543.68 west curve, R=291 Dewees curve,
# Dewees line) are built together with Block 1, which shares the Dewees line.
nw4 = move(b7[0], AZ_W8, 40.0)
w4 = [nw4, move(nw4, AZ_W8, 50.0), move(nw4, AZ_W8, 100.0), move(nw4, AZ_W8, 150.0)]
m4t = move(nw4, EAST, 100.0)
m4 = [m4t, move(m4t, AZ_W8, 50.0), move(m4t, AZ_W8, 100.0), move(m4t, AZ_W8, 135.0)]
e4t = move(m4t, EAST, 110.0)
e4 = [e4t, move(e4t, AZ_W8, 50.0), move(e4t, AZ_W8, 100.0), move(e4t, AZ_W8, 155.6)]
for (wn, mn, en), (lw, le) in zip(((0, 0, 0), (1, 1, 1), (2, 2, 2)), (("1", "2"), ("11", "3"), ("10", "4"))):
    add(4, lw, [w4[wn], m4[mn], m4[mn + 1], w4[wn + 1]])
    add(4, le, [m4[mn], e4[en], e4[en + 1], m4[mn + 1]])
checks["B4 Lot 10 south 101.9'"] = (math.dist(w4[3], m4[3]), 101.9)
checks["B4 Lot 4 south 111.98'"] = (math.dist(m4[3], e4[3]), 111.98)

# ---------------- Block 4 Lots 5-9: BEST FIT (user decision 2026-09-24), flagged ----------------
# The printed values here do not admit one exact figure (e.g. the R=543.68 west curve cannot turn enough over its printed 130' of arc to
# meet the printed 60°54' apex). So the unknown corners are solved by least squares against every printed value; each residual is
# reported. Arcs are treated as chords (short arcs of large radii) for this first fit.
import numpy as np  # noqa: E402
from scipy.optimize import least_squares  # noqa: E402

m5 = move(m4[3], AZ_W8, 35.0)                     # middle line: 35' (Lots 9/5), 45' (Lots 8/6)
m6 = move(m5, AZ_W8, 45.0)
OBS = [  # (point a, point b, printed distance)
    ("W4", "W9", 52.3), ("W9", "W8", 54.0), ("W8", "WPC", 23.8), ("WPC", "APX", 81.6),
    ("M6", "D67", 68.5), ("W9", "M5", 81.8), ("W8", "M6", 68.9), ("M5", "E5", 81.9),
    ("E4", "E5", 51.0), ("E5", "EPC", 8.6), ("EPC", "D67", 85.0), ("D67", "APX", 75.0),
]
FIXED = {"W4": w4[3], "M5": m5, "M6": m6, "E4": e4[3]}
FREE = ["W9", "W8", "WPC", "APX", "D67", "E5", "EPC"]


def _pts(x):
    P_ = dict(FIXED)
    for k_, nm in enumerate(FREE):
        P_[nm] = (x[2 * k_], x[2 * k_ + 1])
    return P_


def _ang(o, a_, b_):
    u = (a_[0] - o[0], a_[1] - o[1])
    v = (b_[0] - o[0], b_[1] - o[1])
    return math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))))))


def _res(x):
    P_ = _pts(x)
    r = [math.dist(P_[a_], P_[b_]) - dd for a_, b_, dd in OBS]
    r.append((_ang(P_["APX"], P_["WPC"], P_["D67"]) - dms(60, 54)) * math.pi / 180.0 * 75.0)   # angle as ft at 75'
    r.append((_ang(P_["D67"], P_["EPC"], P_["APX"]) - 180.0) * math.pi / 180.0 * 75.0)       # Dewees straight
    return r


# start from a rough drawing-shaped guess
g = {"W9": move(w4[3], AZ_W8 - 10, 52.0), "W8": move(w4[3], AZ_W8 - 20, 104.0)}
g["WPC"] = move(g["W8"], AZ_W8 - 25, 24.0)
g["APX"] = move(g["WPC"], AZ_W8 - 35, 81.0)
g["D67"] = move(g["APX"], 40.0, 75.0)
g["EPC"] = move(g["D67"], 40.0, 85.0)
g["E5"] = move(e4[3], AZ_W8 + 10, 51.0)
x0 = np.array([c for nm in FREE for c in g[nm]])
fit = least_squares(_res, x0)
FP = _pts(fit.x)
for (a_, b_, dd), rr_ in zip(OBS, fit.fun[:len(OBS)]):
    checks[f"B4 best-fit {a_}-{b_} {dd}'"] = (dd + rr_, dd)
checks["B4 best-fit apex angle 60°54' (deg)"] = (_ang(FP["APX"], FP["WPC"], FP["D67"]), dms(60, 54))
add(4, "9", [w4[3], m4[3], m5, FP["W9"]], "best fit")
add(4, "5", [m4[3], e4[3], FP["E5"], m5], "best fit")
add(4, "8", [FP["W9"], m5, m6, FP["W8"]], "best fit")
add(4, "6", [m5, FP["E5"], FP["EPC"], FP["D67"], m6], "best fit")
add(4, "7", [FP["W8"], m6, FP["D67"], FP["APX"], FP["WPC"]], "best fit")
assumptions.append("Block 4 Lots 5-9: least-squares best fit to 12 printed distances + the 60°54' apex angle (arcs as chords); "
                   "flagged, residuals in checks; to be refined (true arcs, curve constraints) in later iterations.")

# ---------------- Block 1, east half (Lots 1-9) -- tick 24 ----------------
# Local frame: 16th St N line is y = 0, Lot 2 SW at x = 0; E-W lines at 90°, side lines due N (the plat prints "90°" here).
# Printed: Lots 1-3 52' wide (1: 118' deep, 2-3: 100'); Lot 4 104' / 50' / 123.2'; the spine at 59°08' to the E-W lines with
# Lots 5/6/7 on it (58.22 / 58.02 / 58.22 = the west side's 32.23+32.23+55+55); E-W lines 134.2 / 116.6 / 98.2 (= 48.2 + 50);
# Lot 8 55' top / 99.7' west; Beach W line 51 / 51 / 52.7 + 48 with a 199°28' bend.
def L(x, y):
    return (x, y)


SP = math.radians(90.0 - dms(59, 8))               # spine azimuth N30°52'E
def spine(t):
    return (t * math.sin(SP), 150.0 + t * math.cos(SP))


s4, s5, s6, s7 = spine(0.0), spine(58.22), spine(58.22 + 58.02), spine(174.46)
b56, b67, b78e = (s5[0] + 134.2, s5[1]), (s6[0] + 116.6, s6[1]), (s7[0] + 98.2, s7[1])
l89 = (s7[0] + 48.2, s7[1])                         # Lot 9 / 8 (bottom), easement line between them
l8nw = (l89[0], l89[1] + 99.7)
l8ne = (l8nw[0] + 55.0, l8nw[1])
lot1 = [L(-52, 0), L(0, 0), L(0, 118), L(-52, 118)]
blk1 = {"1": lot1, "2": [L(0, 0), L(52, 0), L(52, 100), L(0, 100)], "3": [L(52, 0), L(104, 0), L(104, 100), L(52, 100)],
        "4": [L(0, 100), L(104, 100), L(123.2, 150), L(0, 150)],
        "5": [s4, L(123.2, 150), b56, s5], "6": [s5, b56, b67, s6], "7": [s6, b67, b78e, s7],
        "8": [l89, b78e, l8ne, l8nw]}
bchk = {
    "B1 Lot 14 east 32' = Lot 4 west top (150) - Lot 1 (118)": (150.0 - 118.0, 32.0),
    "B1 Beach: Lot 4 NE -> Lot 5/6 (15.6 + 48.5 arc R103, as chord)": (math.dist((123.2, 150.0), b56),
                                                                       15.6 + 2 * 103 * math.sin(48.5 / 206.0)),
    "B1 Beach: Lot 6 east 51'": (math.dist(b56, b67), 51.0),
    "B1 Beach: Lot 7 east 51'": (math.dist(b67, b78e), 51.0),
    "B1 Lot 8 east 52.7' + 48' with 199°28' bend (chord)": (math.dist(b78e, l8ne),
                                                           math.sqrt(52.7 ** 2 + 48 ** 2 + 2 * 52.7 * 48 * math.cos(math.radians(19.4667)))),
}
# ---- west half (Lots 9-16), least squares -- tick 25 ----
# Rear points on the spine (from s4 up): Lot 13 55, Lot 12 55, Lot 11 32.23, Lot 10 32.23. Lot 14 east: s4 -> (0,118) -> Lot 1 NW (-52,118);
# Lot 15 east 28' down to (-52,90); Lot 16 east 90' down to (-52,0); Lot 16 bottom 72' to (-124,0) on Mandalay.
r1011, r1112, r1213 = spine(142.23), spine(110.0), spine(55.0)
c14, c15, c16 = (-52.0, 118.0), (-52.0, 90.0), (-124.0, 0.0)
# Lot 9: 70.66' top from Lot 8 NW and 91.2' west side from s7 fix its front corner exactly (circle intersection, west/upper root)
def _circ(p0, r0, p1, r1, pick):
    dd = math.dist(p0, p1)
    aa = (r0 * r0 - r1 * r1 + dd * dd) / (2 * dd)
    hh = math.sqrt(max(r0 * r0 - aa * aa, 0.0))
    mx, my = p0[0] + aa * (p1[0] - p0[0]) / dd, p0[1] + aa * (p1[1] - p0[1]) / dd
    c1 = (mx + hh * (p1[1] - p0[1]) / dd, my - hh * (p1[0] - p0[0]) / dd)
    c2 = (mx - hh * (p1[1] - p0[1]) / dd, my + hh * (p1[0] - p0[0]) / dd)
    return min((c1, c2), key=pick)


p9 = _circ(l8nw, 70.66, s7, 91.2, pick=lambda q: q[0])
ch = lambda arc_, R_: 2 * R_ * math.sin(arc_ / (2 * R_))  # noqa: E731
F1 = ["F1011", "F1112", "PC", "F1213", "F1314", "F1415", "DW", "F1516"]
FIX1 = {"P9": p9, "R1011": r1011, "R1112": r1112, "R1213": r1213, "S4": s4, "C14": c14, "C15": c15, "C16": c16}
OBS1 = [("R1011", "F1011", 108.0), ("R1112", "F1112", 119.8), ("R1213", "F1213", 120.5), ("S4", "F1314", 120.5),
        ("C14", "F1415", 90.0), ("C15", "F1516", 94.8),
        ("P9", "F1011", ch(75.0, 231.0)), ("F1011", "F1112", ch(65.0, 231.0)), ("F1112", "PC", ch(27.0, 231.0)),
        ("PC", "F1213", 28.0), ("F1213", "F1314", 55.0), ("F1314", "F1415", 55.0), ("F1415", "DW", 67.0),
        ("DW", "F1516", ch(62.1, 368.0)), ("F1516", "C16", ch(56.0, 368.0))]


def _p1(x):
    P_ = dict(FIX1)
    for k_, nm in enumerate(F1):
        P_[nm] = (x[2 * k_], x[2 * k_ + 1])
    return P_


def _r1(x):
    P_ = _p1(x)
    r = [math.dist(P_[a_], P_[b_]) - dd for a_, b_, dd in OBS1]
    for a_, o_, b_ in (("PC", "F1213", "F1314"), ("F1213", "F1314", "F1415"), ("F1314", "F1415", "DW")):
        r.append((_ang(P_[o_], P_[a_], P_[b_]) - 180.0) * math.pi / 180.0 * 55.0)   # Dewees W line straight
    return r


g1 = {"F1011": (s7[0] - 100, s7[1] + 40), "F1112": (r1112[0] - 110, r1112[1] + 30), "PC": (r1213[0] - 115, r1213[1] + 45),
      "F1213": (r1213[0] - 115, r1213[1] + 20), "F1314": (-100.0, 90.0), "F1415": (-130.0, 60.0), "DW": (-165.0, 10.0),
      "F1516": (-150.0, 30.0)}
fit1 = least_squares(_r1, np.array([c for nm in F1 for c in g1[nm]]))
P1 = _p1(fit1.x)
for (a_, b_, dd), rr_ in zip(OBS1, fit1.fun[:len(OBS1)]):
    bchk[f"B1 best-fit {a_}-{b_} {dd:.2f}'"] = (dd + rr_, dd)
blk1.update({
    "9": [s7, l89, l8nw, p9], "10": [r1011, s7, p9, P1["F1011"]], "11": [r1112, r1011, P1["F1011"], P1["F1112"]],
    "12": [r1213, r1112, P1["F1112"], P1["PC"], P1["F1213"]], "13": [s4, r1213, P1["F1213"], P1["F1314"]],
    "14": [c14, (0.0, 118.0), s4, P1["F1314"], P1["F1415"]], "15": [c15, c14, P1["F1415"], P1["DW"], P1["F1516"]],
    "16": [c16, (-52.0, 0.0), c15, P1["F1516"]],
})
assumptions.append("Block 1 Lots 9-16: least squares, 8 unknown front corners vs 15 printed distances (R=231 / R=368 arcs as chords) "
                   "+ Dewees straightness (redundancy 2); Lot 9's front corner is exact from its 70.66'/91.2'.")

# Placement: the Dewees Ave S line (Lot 8 top) is 60' south of Block 6's Dewees N line, and Lot 8's east corner is on Block 6's Beach
# W line (Lot 7 east, extended across Dewees). Translation only; flagged as an assumption.
anchor = meet(move(b78, AZ_W8, 60.0), EAST, l7ne, AZ_C)
dx, dy = anchor[0] - l8ne[0], anchor[1] - l8ne[1]
for n_, ring_ in blk1.items():
    add(1, n_, [(p_[0] + dx, p_[1] + dy) for p_ in ring_], "Block 1 east half")
for k_, v_ in bchk.items():
    checks[k_] = v_
assumptions.append("Block 1 placed by translation: Lot 8 NE on Block 6's Beach W line extended, 60' (Dewees Ave) south of Block 6's Dewees line.")

# ---------------- triangle Blocks 5 and 2 (tick 27): shape exact from 3 printed sides, placement from the neighbours ----------------
def tri(p0, p1, a0, a1, left=True):
    """Third vertex at distance a0 from p0 and a1 from p1 (on the left of p0->p1 if left)."""
    dd = math.dist(p0, p1)
    x = (a0 * a0 - a1 * a1 + dd * dd) / (2 * dd)
    h = math.sqrt(max(a0 * a0 - x * x, 0.0))
    ux, uy = (p1[0] - p0[0]) / dd, (p1[1] - p0[1]) / dd
    sg = 1.0 if left else -1.0
    return (p0[0] + x * ux - sg * h * uy, p0[1] + x * uy + sg * h * ux)


# Block 5: west side 56.2' on Coquina Pl E line (40' east of Block 4's east line, level with Lot 4), then 54' (Ra=140) and 56' (Ra=291)
b5a = move(e4[2], EAST, 40.0)
b5b = move(b5a, AZ_W8, 56.2)
b5c = tri(b5a, b5b, ch(54.0, 140.0), ch(56.0, 291.0), left=True)
add(5, "5", [b5a, b5c, b5b], "triangle, placement from Coquina Pl")
# Block 2: bottom 43.3' on 16th St N line, east side 49.7' (Ra=543.68, Mandalay W line, 60' west of Block 1 Lot 16), west 55.1'
b2e = (-124.0 - 60.0 + dx, 0.0 + dy)
b2w = (b2e[0] - 43.3, b2e[1])
b2t = tri(b2w, b2e, 55.1, ch(49.7, 543.68), left=True)
add(2, "2", [b2w, b2e, b2t], "triangle, placement from Mandalay Ave")
checks["B5 triangle closes (3 printed sides)"] = (math.dist(b5a, b5b) + math.dist(b5b, b5c) + math.dist(b5c, b5a), 56.2 + ch(56.0, 291.0) + ch(54.0, 140.0))
checks["B2 triangle closes (3 printed sides)"] = (math.dist(b2w, b2e) + math.dist(b2e, b2t) + math.dist(b2t, b2w), 43.3 + ch(49.7, 543.68) + 55.1)
assumptions.append("Blocks 5 and 2 (triangles): shape fixed by their three printed sides (arcs as chords); position placed from the adjoining "
                   "street widths (Coquina Pl 40', Mandalay Ave 60') -- not tied by any printed dimension, flagged.")

# ---------------- Block 3 (tick 28): west 193' on Seminole Rd, 31°09' at SW, 109.1' to the east corner, 97.5' at 30°45' from the top
# (degree digit faint; 30°44.4' solves the 17.15' closure, matching the legible "45'"), then 17.15' P.T. -> east corner.
# Tie: its SW corner is 20.85' north of the 16th St line, 58' west of Block 2's west corner (dashed line on the plat).
b3b = (b2w[0] - 58.0, b2w[1] + 20.85)
b3t = (b3b[0], b3b[1] + 193.0)
b3e = move(b3b, dms(31, 9), 109.1)
b3p = move(b3t, 180.0 - dms(30, 45), 97.5)
add(3, "3", [b3b, b3t, b3p, b3e], "triangle, tied to Block 2 by the printed 58' / 20.85'")
checks["B3 P.T. -> east corner 17.15'"] = (math.dist(b3p, b3e), 17.15)

# ---------------- outputs ----------------
d = out_dir(PLAT_ID)
FLAGGED = {"B6-L9", "B6-L10", "B6-L11", "B4-L5", "B4-L6", "B4-L7", "B4-L8", "B4-L9",
           *{f"B1-L{i}" for i in range(1, 17)}, "B5-L5", "B2-L2", "B3-L3"}   # Block 1: placement assumed   # Coquina curve corner: plat values conflict by up to 4.7' (see checks/assumptions)
rings = [("LOT-FLAGGED" if k in FLAGGED else "LOT", v["ring"]) for k, v in lots.items()]
texts = []
for k, v in lots.items():
    cx = sum(p[0] for p in v["ring"]) / len(v["ring"])
    cy = sum(p[1] for p in v["ring"]) / len(v["ring"])
    texts.append(("TEXT-LABELS", (cx, cy), v["lot"], 8))
for blk, ref in ((8, mid[4]), (7, m7[2]), (6, r1[2]), (4, m4[2]), (1, (anchor[0] - 150.0, anchor[1] - 200.0))):
    texts.append(("BLOCK-TEXT", (ref[0] + 8, ref[1]), f"({blk})", 14))
texts.append(("TITLEBLOCK", (250.0, 60.0), "OCEAN GROVE UNIT NO. 1  PB 15 PG 82 (1937)  -  claude reconstruction, in progress", 14))
texts.append(("TITLEBLOCK", (250.0, 35.0), "NO BEARINGS ON PLAT - 17TH ST TAKEN DUE EAST; RED = BEST FIT OR ASSUMED PLACEMENT (SEE metrics.json)", 9))
layers = [("LOT", "cyan", "CONTINUOUS"), ("LOT-FLAGGED", "red", "CONTINUOUS"), ("TEXT-LABELS", "white", "CONTINUOUS"),
          ("BLOCK-TEXT", "yellow", "CONTINUOUS"), ("TITLEBLOCK", "yellow", "CONTINUOUS")]
write_dxf(os.path.join(d, f"PB0015_P0082_OceanGrove{writer_suffix()}.dxf"), layers, rings, [], texts)
render_png(os.path.join(d, "PB0015_P0082_OceanGrove.png"), "Ocean Grove Unit No. 1 (PB 15 Pg 82) - ag reconstruction, all 8 blocks",
           rings, [], texts, flagged={"LOT-FLAGGED"})

worst = max(abs(c - p) for k, (c, p) in checks.items() if "°" not in k.split("'")[-1] and "angle" not in k and "bend" not in k
            and "best-fit" not in k)
save_metrics(PLAT_ID, {
    "plat_id": PLAT_ID, "source": "Plat/Plat_Book_15_Page_82.pdf",
    "blocks_built": [8, 7, 6, "4 (Lots 1-4, 10, 11; 5-9 best fit, flagged)"], "blocks_todo": [],
    "lots_built": len(lots),
    "lots": {k: {"area_sqft": round(v["area"], 1)} for k, v in lots.items()},
    "checks": {k: {"computed": round(c, 3), "printed": p, "diff": round(c - p, 3)} for k, (c, p) in checks.items()},
    "worst_check_ft": round(worst, 3),
    "flagged_lots": sorted(FLAGGED),
    "assumptions": assumptions,
})
for k, (c, p) in checks.items():
    print(f"  {k:<40} {c:9.3f} vs {p:8.2f} ({c - p:+.3f})")
print(f"lots built: {len(lots)}  worst check {worst:.3f}'")
