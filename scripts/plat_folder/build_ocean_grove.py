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

# ---------------- outputs ----------------
d = out_dir(PLAT_ID)
FLAGGED = {"B6-L9", "B6-L10", "B6-L11"}   # Coquina curve corner: plat values conflict by up to 4.7' (see checks/assumptions)
rings = [("LOT-FLAGGED" if k in FLAGGED else "LOT", v["ring"]) for k, v in lots.items()]
texts = []
for k, v in lots.items():
    cx = sum(p[0] for p in v["ring"]) / len(v["ring"])
    cy = sum(p[1] for p in v["ring"]) / len(v["ring"])
    texts.append(("TEXT-LABELS", (cx, cy), v["lot"], 8))
for blk, ref in ((8, mid[4]), (7, m7[2]), (6, r1[2]), (4, m4[2])):
    texts.append(("BLOCK-TEXT", (ref[0] + 8, ref[1]), f"({blk})", 14))
texts.append(("TITLEBLOCK", (250.0, 60.0), "OCEAN GROVE UNIT NO. 1  PB 15 PG 82 (1937)  -  claude reconstruction, in progress", 14))
texts.append(("TITLEBLOCK", (250.0, 35.0), "NO BEARINGS ON PLAT - 17TH ST TAKEN DUE EAST; BLOCK 4 LOTS 5-9 AND BLOCKS 5,3,2,1 NOT YET BUILT", 9))
layers = [("LOT", "cyan", "CONTINUOUS"), ("LOT-FLAGGED", "red", "CONTINUOUS"), ("TEXT-LABELS", "white", "CONTINUOUS"),
          ("BLOCK-TEXT", "yellow", "CONTINUOUS"), ("TITLEBLOCK", "yellow", "CONTINUOUS")]
write_dxf(os.path.join(d, "PB0015_P0082_OceanGrove_claude.dxf"), layers, rings, [], texts)
render_png(os.path.join(d, "PB0015_P0082_OceanGrove.png"), "Ocean Grove Unit No. 1 (PB 15 Pg 82) - claude reconstruction (in progress)",
           rings, [], texts, flagged={"LOT-FLAGGED"})

worst = max(abs(c - p) for k, (c, p) in checks.items() if "°" not in k.split("'")[-1] and "angle" not in k and "bend" not in k)
save_metrics(PLAT_ID, {
    "plat_id": PLAT_ID, "source": "Plat/Plat_Book_15_Page_82.pdf",
    "blocks_built": [8, 7, 6, "4 (Lots 1-4, 10, 11)"], "blocks_todo": ["4 (Lots 5-9)", 5, 3, 2, 1],
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
