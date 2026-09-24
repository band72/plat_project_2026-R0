"""ATLANTIC BEACH COUNTRY CLUB UNIT 2 -- Sheet 3 of 6 (PB 67 Pg 134), Lots 136-126 along Maritime Oak Drive.
Plat/67-132.pdf page 3, read at 300 dpi.

Replaces scripts/build_forceclosed.py for this row. That script shifted every printed side line one lot west (it treated the
137/136 line's 119.72' as Lot 137's own side) and then invented an "assumed" 13th depth; it also drew the Maritime Oak Dr
frontage as straight chords, saying the plat doesn't say which curve belongs to which lot. It does: each lot's frontage is
labelled on the plat (curve tags / straight distances), and the curve table gives every chord bearing and length.

Two independent constructions meet at every front corner:
  (a) rear line N00°32'22"E with the printed lot widths, then each printed side line N89°27'38"W and depth;
  (b) the frontage chain along Maritime Oak Dr from the 137/136 corner, built only from the curve table chords and the
      printed straight distances (80.00' tangent N00°32'22"E = 45.89 + 34.12; 307.87' tangent N04°17'54"E).
The residual at each corner is reported; nothing is forced.
"""
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine.cogo import parse_bearing  # noqa: E402
from engine.dxf_writer import writer_suffix  # noqa: E402
from scripts.plat_folder.common import out_dir, render_png, save_metrics, shoelace, write_dxf  # noqa: E402

PLAT_ID = "PB67_P132_AtlanticBeach_S3"


def move(p, brg, d):
    a = math.radians(parse_bearing(brg) if isinstance(brg, str) else brg)
    return (p[0] + d * math.sin(a), p[1] + d * math.cos(a))   # (E, N)


def rev(brg):
    return (parse_bearing(brg) + 180.0) % 360.0


LOTS = [136, 135, 134, 133, 132, 131, 130, 129, 128, 127, 126]
WIDTHS = [55.00, 60.00, 55.00, 55.00, 60.00, 55.00, 55.00, 60.00, 55.00, 55.00, 60.00]      # rear line, per lot
SIDES = [119.72, 120.00, 117.75, 106.79, 100.04, 97.66, 99.91, 103.53, 107.47, 111.08, 114.70, 118.64]  # 137/136 .. 126/125
# Sheet 3 is drawn with north to the LEFT: Lot 137 is the north end, so walking 137 -> 126 is southward.
REAR, SIDE = "S00°32'22\"W", "N89°27'38\"W"

# Curve table (sheet 3): tag -> (length, radius, chord bearing as printed, chord). Direction of travel here is northward.
CT = {"C201": (9.12, 150.0, "N02°16'52\"E", 9.12), "C200": (26.01, 150.0, "N04°25'43\"W", 25.98),
      "C199": (8.45, 150.0, "N11°00'41\"W", 8.45), "C198": (47.64, 700.0, "S10°40'35\"E", 47.63),
      "C197": (55.43, 700.0, "S06°27'31\"E", 55.41), "C196": (60.07, 700.0, "S01°43'55\"E", 60.05),
      "C195": (43.64, 700.0, "S02°30'44\"W", 43.63),
      "C194": (45.14, 100.0, "N08°38'04\"W", 44.76), "C190": (15.13, 100.0, "N25°54'01\"W", 15.11),
      "C189": (45.90, 235.0, "S24°38'19\"E", 45.82), "C202": (196.30, 150.0, "N41°30'46\"E", 182.59)}


def south(brg):
    """Chord bearing pointing south (direction of travel; the table prints some chords northward)."""
    az = parse_bearing(brg)
    return az if 90.0 < az < 270.0 else (az + 180.0) % 360.0


# Frontage of each lot, southward (137 -> 126), as labelled on the plat: ("C", tag) or ("L", bearing, distance)
T1, T2 = REAR, "S04°17'54\"W"
FRONT = {136: [("C", "C201"), ("L", T1, 45.89)], 135: [("L", T1, 34.12), ("C", "C200")],
         134: [("C", "C199"), ("C", "C198")], 133: [("C", "C197")], 132: [("C", "C196")],
         131: [("C", "C195"), ("L", T2, 11.42)], 130: [("L", T2, 55.12)], 129: [("L", T2, 60.13)],
         128: [("L", T2, 55.12)], 127: [("L", T2, 55.12)], 126: [("L", T2, 60.13)]}

# (a) rear + side lines
rear = [(0.0, 0.0)]
for w in WIDTHS:
    rear.append(move(rear[-1], REAR, w))
front_a = [move(t, SIDE, d) for t, d in zip(rear, SIDES)]

# (b) frontage chain from the 137/136 front corner (shared start)
def arc_pts(p0, p1, R, left, n=16):
    c = math.dist(p0, p1)
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    h = math.sqrt(max(R * R - c * c / 4, 0.0))
    ux, uy = (p1[0] - p0[0]) / c, (p1[1] - p0[1]) / c
    sgn = 1.0 if left else -1.0                   # centre on the left of travel for a left-turning curve
    cx, cy = mx - sgn * uy * h, my + sgn * ux * h
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    return [(cx + R * math.cos(a0 + da * k / n), cy + R * math.sin(a0 + da * k / n)) for k in range(n + 1)], (c, R)


LEFT_TURN = {"C202", "C201", "C200", "C199", "C194", "C190"}   # going south: R=150 and R=100 turn left; R=700, R=235 turn right
cur = front_a[0]
front_b = [cur]
segs = {}                                          # lot -> list of front polylines (for drawing and areas)
seg_area = {}
for lot in LOTS:
    pts = [cur]
    adj = 0.0
    for el in FRONT[lot]:
        if el[0] == "L":
            nxt = move(cur, el[1], el[2])
            pts.append(nxt)
        else:
            L, R, brg, ch = CT[el[1]]
            nxt = move(cur, south(brg), ch)
            ap, _ = arc_pts(cur, nxt, R, el[1] in LEFT_TURN)
            pts += ap[1:]
            d = L / R
            seg = 0.5 * R * R * (d - math.sin(d))
            # lots lie east of the frontage (on the left going south): a left-turning arc (centre east) bulges west,
            # away from the lot -> plus; a right-turning arc bulges into the lot -> minus
            adj += seg if el[1] in LEFT_TURN else -seg
        cur = nxt
    segs[lot] = pts
    seg_area[lot] = adj
    front_b.append(cur)

# rings (rear corners, side lines, frontage from construction (a) corners) and checks
lots, checks = {}, {}
for i, lot in enumerate(LOTS):
    miss = math.dist(front_a[i + 1], front_b[i + 1])
    checks[f"Lot {lot}/{LOTS[i + 1] if i + 1 < len(LOTS) else 125} front corner: side-line vs frontage chain (ft)"] = (miss, 0.0)
    ring = [rear[i], rear[i + 1], front_a[i + 1]] + list(reversed(segs[lot]))[1:-1] + [front_a[i]]
    lots[str(lot)] = {"ring": ring, "area": shoelace(ring)}

# ---- Lot 137 (north end): rear 137.85' north of the 137/136 rear corner, frontage = curve C202 (R=150) ----
t_n = move(rear[0], (parse_bearing(REAR) + 180.0) % 360.0, 137.85)    # north corner (monument)
c202, _ = arc_pts(t_n, front_a[0], 150.0, True, n=32)
lots["137"] = {"ring": [t_n, rear[0], front_a[0]] + list(reversed(c202))[1:-1], "area": 0.0}
lots["137"]["area"] = shoelace(lots["137"]["ring"])
checks["Lot 137 C202 chord 182.59' (north corner -> 137/136 front)"] = (math.dist(t_n, front_a[0]), 182.59)
az202 = math.degrees(math.atan2(t_n[0] - front_a[0][0], t_n[1] - front_a[0][1])) % 360.0
checks["Lot 137 C202 chord bearing N41°30'46\"E (deg)"] = (az202, parse_bearing("N41°30'46\"E"))

# ---- Lots 125, 124 (south end): rear 10.00' + 45.78' / 55.95' on the N10°02'38"W course; sides 120.62', 104.67' ----
bend = move(rear[-1], REAR, 10.00)
t125 = move(bend, "S10°02'38\"E", 45.78)
t124 = move(t125, "S10°02'38\"E", 55.95)
fa125, fa124 = move(t125, SIDE, 120.62), move(t124, SIDE, 104.67)


def chain(start, elements):
    cur, pts = start, [start]
    for el in elements:
        if el[0] == "L":
            nxt = move(cur, el[1], el[2])
            pts.append(nxt)
        else:
            _, R, brg, ch = CT[el[1]]
            nxt = move(cur, south(brg), ch)
            pts += arc_pts(cur, nxt, R, el[1] in LEFT_TURN)[0][1:]
        cur = nxt
    return cur, pts


fb125, seg125 = chain(front_a[-1], [("L", T2, 10.83), ("C", "C194")])
fb124, seg124 = chain(fa125, [("C", "C190"), ("C", "C189")])
checks["Lot 125/124 front corner: side-line vs frontage chain (ft)"] = (math.dist(fa125, fb125), 0.0)
checks["Lot 124/123 front corner: side-line vs frontage chain (ft)"] = (math.dist(fa124, fb124), 0.0)
lots["125"] = {"ring": [rear[-1], bend, t125, fa125] + list(reversed(seg125))[1:-1] + [front_a[-1]]}
lots["124"] = {"ring": [t125, t124, fa124] + list(reversed(seg124))[1:-1] + [fa125]}
for n in ("125", "124"):
    lots[n]["area"] = shoelace(lots[n]["ring"])
checks["80.00' tangent = 45.89 + 34.12"] = (45.89 + 34.12, 80.00)
checks["307.87' tangent = 11.42+55.12+60.13+55.12+55.12+60.13+10.83"] = (11.42 + 55.12 + 60.13 + 55.12 + 55.12 + 60.13 + 10.83, 307.87)

# ---- South of Maritime Oak Dr, west of Timber Bridge Lane: Lots 167-176 (tick 21) ----
# Tie across the 50' street: C41 (R=200, S R/W) is concentric with C45 (R=150, N R/W) and C41 = C206 + C207 (17.01 + 28.95),
# C45 = C200 + C199 (26.01 + 8.45), so the S R/W P.C. lies 50' west of the N R/W P.C. (start of C200).
def chord_pt(p0, brg_south_or_as_is, ch):
    return move(p0, brg_south_or_as_is, ch)


def arc_ring(p0, p1, R, left):
    return arc_pts(p0, p1, R, left, n=16)[0]


npc = move(front_a[1], T1, 34.12)                          # N R/W: end of the 80' tangent = start of C200
spc = move(npc, SIDE, 50.0)                                # S R/W P.C.
q0 = move(spc, "S01°53'50\"E", 17.00)                     # end of C206 = Lot 167 N corner (C41 / C207)
q1 = move(q0, SIDE, 75.72)                                 # 167/168 on the north line N89°27'38"W 126.00
q2 = move(q1, SIDE, 50.28)
q3 = move(q2, "N80°24'17\"W", 2.30)                        # 168/169
REAR2, SIDE2, FRONT2 = "N80°24'17\"W", "S09°35'43\"W", "S80°24'17\"E"
# Lots 169-175: rear corners along N80°24'17"W (55, then N75°38'28"W 60.21, N65°08'58"W 57.01, then 225 = 55/60/55/55)
rr = [q3, move(q3, REAR2, 55.00)]
rr.append(move(rr[-1], "N75°38'28\"W", 60.21))
rr.append(move(rr[-1], "N65°08'58\"W", 57.01))
for w in (55.0, 60.0, 55.0, 55.0):
    rr.append(move(rr[-1], REAR2, w))
depths = [130.00, 130.00, 135.00, 150.00, 150.00, 150.00, 150.00, 154.78]   # 168/169 .. 175/176
ff = [move(t, SIDE2, dd) for t, dd in zip(rr, depths)]
names = [169, 170, 171, 172, 173, 174]
fronts = [55.0, 60.0, 55.0, 55.0, 60.0, 55.0]
for i, (n, fw) in enumerate(zip(names, fronts)):
    lots[str(n)] = {"ring": [rr[i], rr[i + 1], ff[i + 1], ff[i]]}
    checks[f"Lot {n} front {fw}' (Timber Bridge W R/W)"] = (math.dist(ff[i], ff[i + 1]), fw)
# Lot 175: front 11.56' straight + C212 (part of C37, R=200); Lot 176: C213 + C214, rear S73°01'49"W 67.08', south S09°35'43"W 138.57'
r176 = move(rr[-1], "S73°01'49\"W", 67.08)
f176 = move(r176, SIDE2, 138.57)
pc37 = move(ff[6], REAR2, 11.56)                           # 11.56' past the 174/175 corner along the straight
lots["175"] = {"ring": [rr[6], rr[7], ff[7]] + list(reversed(arc_ring(pc37, ff[7], 200.0, False)))[1:-1] + [pc37, ff[6]]}
lots["176"] = {"ring": [rr[7], r176, f176] + list(reversed(arc_ring(ff[7], f176, 200.0, False)))[1:-1] + [ff[7]]}
d37 = sum(2 * math.degrees(math.asin(math.dist(a_, b_) / 400.0)) for a_, b_ in ((pc37, ff[7]), (ff[7], f176)))
checks["C37 (R=200) Δ 19°53'40\" = C212 + C213 + C214 (deg)"] = (d37, 19 + 53 / 60 + 40 / 3600)
checks["Straight 362.66' = 11.10 + 55+60+55+55+60+55 + 11.56"] = (11.10 + 340.0 + 11.56, 362.66)
# Lot 168: north line q1-q2-q3, side 130 to its front corner, front 11.10' + C209 + C208 back to the 167/168 line (135.00')
p168 = move(q1, "S00°32'22\"W", 135.00)
pc209 = move(ff[0], FRONT2, 11.10)
e209 = move(pc209, "S84°39'22\"E", 62.27)
checks["Lot 168 front chain (11.10 + C209) end vs 167/168 line (135.00') end (ft)"] = (math.dist(e209, p168), 0.0)
e208 = move(p168, "S89°11'03\"E", 4.05)                  # C208 (R=420.02, 4.05') is Lot 167's, east of the 167/168 corner
lots["168"] = {"ring": [q1, q2, q3, ff[0], pc209] + arc_ring(pc209, e209, 420.0, True)[1:] + [p168]}
# Lot 167: q0 -> q1 (75.72) -> p168 (135.00) -> east 64.73' -> C39 (R=25) -> C40 (R=650) -> C207 (R=200) back to q0
e167 = move(e208, "S89°27'38\"E", 64.73)
c207s = move(q0, "S08°28'47\"E", 28.92)
c40e = move(c207s, "S09°06'08\"E", 79.90)
checks["Lot 167 closure via C207 + C40 + C39 (ft)"] = (math.dist(move(c40e, "S42°28'49\"W", 37.19), e167), 0.0)
lots["167"] = {"ring": [q0, q1, p168, e208, e167, c40e, c207s]}
# ---- Lots 164-160, east of Timber Bridge Lane (tick 32) ----
# E R/W straight = W R/W straight (362.66') moved 50' across the street; pieces 47.30 (Lot 165) + 60 + 55 + 60 + 70 + 55 + 15.36 = 362.66.
# Side lines N09°35'43"E (square to the street), printed lengths 241.55 / 255.58 / 268.43 / 282.46 / 298.83; their far ends must fall
# on the rear line with the printed pieces 61.62 / 56.48 / 61.62 / 71.89 (independent check).
e_top = move(pc209, "N09°35'43\"E", 50.0)
FE = [move(e_top, REAR2, 47.30)]
for w_ in (60.0, 55.0, 60.0, 70.0, 55.0):
    FE.append(move(FE[-1], REAR2, w_))
LEN = [241.55, 255.58, 268.43, 282.46, 298.83, 230.97]
RE = [move(f_, "N09°35'43\"E", l_) for f_, l_ in zip(FE, LEN)]
for i_, (n_, rear_) in enumerate(zip(("164", "163", "162", "161"), (61.62, 56.48, 61.62, 71.89))):
    checks[f"Lot {n_} rear piece {rear_}' on the S03°33'50\"E line"] = (math.dist(RE[i_], RE[i_ + 1]), rear_)
for i_, n_ in enumerate(("164", "163", "162", "161", "160")):
    lots[n_] = {"ring": [FE[i_], RE[i_], RE[i_ + 1], FE[i_ + 1]]}

# ---- Lot 165 (tick 33): front 47.30' straight + C218 (R=470, chord 22.70' S81°47'19"E going north) to the 165/166 corner;
# north side N09°35'43"E 225.73'; rear piece 71.89' on the rear line is the independent check.
f166 = move(e_top, "S81°47'19\"E", 22.70)
r166 = move(f166, "N09°35'43\"E", 225.73)
checks["Lot 165 rear piece 71.89' (165/166 line end -> 165/164 line end)"] = (math.dist(r166, RE[0]), 71.89)
lots["165"] = {"ring": [f166, r166, RE[0], FE[0], e_top]}

# ---- Lot 166 (ticks 34-35). 400 dpi re-read: C220/C221 inside Lot 165 is the dashed EASEMENT line ("120.11' TO EASEMENT"), not a lot
# line. Lot 166 wraps: front C219 (R=470, chord 51.55'), north 121.42' to the curve, down the curve to Lot 140's SW corner, along
# Lot 140's south line (99.41 + 20) to the rear line, 38.05' down the rear line, then back along the full 225.73' line (Lot 165's north).
# Printed curve lengths C222/C223 (60.27/49.11) do not fit this corner at drawing scale -> curve drawn as a chord, FLAGGED.
f138 = move(f166, "S86°19'00\"E", 51.55)
r138 = move(f138, "N09°35'43\"E", 121.42)
_d = math.atan2(r166[0] - RE[0][0], r166[1] - RE[0][1])
q140 = (r166[0] + 38.05 * math.sin(_d), r166[1] + 38.05 * math.cos(_d))
k140 = move(q140, "S00°32'22\"W", 119.41)
checks["Lot 166 curve chord (Lot 140 SW -> 121.42' corner) vs C222+C223 (109.22')"] = (math.dist(k140, r138), 109.22)
lots["166"] = {"ring": [f166, f138, r138, k140, q140, r166]}

# ---- Lots 145-147, east of the rear line (tick 37) ----
# The east lots have their OWN vertices on the rear line (printed east-side pieces 70.01 / 60.01 / 55.01, vs the west side's 71.89 / 61.62 /
# 56.48), starting at the 225.73'/220.60' vertex. East lines are 220.60 / 221.64 / 222.52 / 223.33 long; their direction is the one value
# not usable as printed on this sheet (rotated label basis), so it is solved from the three printed Coastal Oak frontages 70.00 / 60.00 /
# 55.00 -- one unknown, three observations: the fit is exact to 0.001', which confirms the reading.
from scipy.optimize import minimize_scalar  # noqa: E402
_u = ((RE[0][0] - r166[0]) / math.dist(r166, RE[0]), (RE[0][1] - r166[1]) / math.dist(r166, RE[0]))
VE = [r166]
for _p in (70.01, 60.01, 55.01):
    VE.append((VE[-1][0] + _p * _u[0], VE[-1][1] + _p * _u[1]))
LE = [220.60, 221.64, 222.52, 223.33]


def _east_ends(az):
    a_ = math.radians(az)
    return [(v_[0] + l_ * math.sin(a_), v_[1] + l_ * math.cos(a_)) for v_, l_ in zip(VE, LE)]


def _east_err(az):
    e_ = _east_ends(az)
    return sum((math.dist(e_[i_], e_[i_ + 1]) - t_) ** 2 for i_, t_ in enumerate((70.0, 60.0, 55.0)))


_fit = min((minimize_scalar(_east_err, bounds=(a0_, a0_ + 30.0), method="bounded") for a0_ in range(0, 360, 30)), key=lambda r_: r_.fun)
EE = _east_ends(_fit.x)
for i_, (n_, fw_) in enumerate(zip(("145", "146", "147"), (70.0, 60.0, 55.0))):
    checks[f"Lot {n_} Coastal Oak frontage {fw_}' (east-line direction solved once for all three)"] = (math.dist(EE[i_], EE[i_ + 1]), fw_)
    lots[n_] = {"ring": [VE[i_], EE[i_], EE[i_ + 1], VE[i_ + 1]]}

# ---- Lot 148 (tick 39): BEST FIT, flagged. Rear piece 76.96' (east set), south line 226.68' at the printed N08°41'54"W (4°17'19" off the
# solved N04°24'35"W family), front 25.35' + C227 (R=470, chord 43.66'). The two ways to its SE corner miss by ~9' (no reading tried closes:
# best 4.0'), so the ring is drawn through both and the misfit is reported.
_cst = math.degrees(math.atan2(EE[3][0] - EE[2][0], EE[3][1] - EE[2][1])) % 360.0
p148 = move(EE[3], _cst, 25.35)
q148 = move(p148, _cst + (5 + 19 / 60 + 26 / 3600) / 2.0, 43.66)
v148 = (VE[3][0] + 76.96 * _u[0], VE[3][1] + 76.96 * _u[1])
e148 = move(v148, _fit.x + 4 + 17 / 60 + 19 / 3600, 226.68)
checks["Lot 148 SE corner: 226.68' line end vs Coastal Oak 25.35' + C227 (ft)"] = (math.dist(e148, q148), 0.0)
lots["148"] = {"ring": [VE[3], EE[3], p148, q148, e148, v148]}

for n in ("167", "168", "169", "170", "171", "172", "173", "174", "175", "176", "166", "165", "164", "163", "162", "161", "160",
          "145", "146", "147", "148"):
    lots[n]["area"] = shoelace(lots[n]["ring"])

worst = max(c for k, (c, p) in checks.items() if "front corner" in k)

d = out_dir(PLAT_ID)
# Lots 175/176 corners are fixed by printed side lines, but their frontage curves C212-C214 are not in this sheet's curve table:
# modelled as R=200 (C37) arcs from the printed 11.56' tangent, which does not reproduce C37's 19°53'40" -> flagged, not certified.
FLAGGED = {"175", "176", "165", "166", "148"}   # 165: rear piece misses the printed 71.89 by 0.25
rings = [("LOT-FLAGGED" if n in FLAGGED else "LOT", v["ring"]) for n, v in lots.items()]
texts = [("TEXT-LABELS", (sum(p[0] for p in v["ring"]) / len(v["ring"]), sum(p[1] for p in v["ring"]) / len(v["ring"])),
          f"{n}  {v['area']:,.0f} SF", 6) for n, v in lots.items()]
texts.append(("TITLEBLOCK", (-60.0, 160.0), "ATLANTIC BEACH CC UNIT 2  PB 67 PG 134 (SHEET 3)  LOTS 124-137, 167-176  -  ag", 8))
layers = [("LOT", "cyan", "CONTINUOUS"), ("LOT-FLAGGED", "red", "CONTINUOUS"), ("TEXT-LABELS", "white", "CONTINUOUS"), ("TITLEBLOCK", "yellow", "CONTINUOUS")]
write_dxf(os.path.join(d, f"PB0067_P0134_AtlanticBeachCC_Sheet3{writer_suffix()}.dxf"), layers, rings, [], texts)
render_png(os.path.join(d, "PB0067_P0134_AtlanticBeachCC_Sheet3.png"),
           f"Atlantic Beach CC Unit 2, Sheet 3 - Lots 124-137, 167-176 ({writer_suffix().strip('_')})", rings, [], texts, flagged={"LOT-FLAGGED"})
save_metrics(PLAT_ID, {
    "plat_id": PLAT_ID, "source": "Plat/67-132.pdf page 3",
    "lots_built": len(lots), "lots": {k: {"area_sqft": round(v["area"], 1)} for k, v in lots.items()},
    "checks": {k: {"computed": round(c, 3), "printed": p} for k, (c, p) in checks.items()},
    "worst_front_corner_misfit_ft": round(worst, 3),
    "flagged_lots": sorted(FLAGGED),
    "supersedes": "scripts/build_forceclosed.py (off-by-one side lines, assumed chord frontage, assumed 13th depth)",
    "todo": "Sheet 3 Lots 138-166 (east of Timber Bridge Lane), C212-C214 data for Lots 175/176, Sheets 1, 2, 4, 5, 6",
})
for k, (c, p) in checks.items():
    print(f"  {k:<72} {c:8.3f} (plat {p})")
print(f"lots {len(lots)}  worst front-corner misfit {worst:.3f}'")
