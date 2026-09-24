"""ATLANTIC BEACH COUNTRY CLUB UNIT 2 -- Sheet 5 of 6 (PB 67 Pg 136). Plat/67-132.pdf page 5, read at 300 dpi.

Atlantic Beach Drive (50' R/W) runs N14°27'25"W from Lot 9 to Lot 16 (labelled S14°27'25"E; the north arrow points right). Built so far (tick 51):
  Lots 9-16, east side of Atlantic Beach Dr: rectangles 120.00' deep (side lines N75°32'35"E, square to the road),
  frontages 60 / 55 / 55 / 55 / 60 / 80 / 80 / 60 from the monument at Lot 9's NW corner.
  Checks: rear line S14°27'25"E 505.00' = the frontages; front R/W S14°27'25"E 526.22' = 505.00 + the 20.00' drainage gap + 1.22' to Lot 17;
  the west-end crossing S89°59'56"W 51.63' (25.82 + 25.82) = 50' R/W / cos(14°27'25").
Tick 52: Lots 17-21 (see the block comment below). Todo: Lots 22-34 (Atlantic Beach Ct bulb), 72-90, Tract F.
"""
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine.cogo import parse_bearing  # noqa: E402
from engine.dxf_writer import writer_suffix  # noqa: E402
from scripts.plat_folder.common import out_dir, render_png, save_metrics, shoelace, write_dxf  # noqa: E402

PLAT_ID = "PB67_P132_AtlanticBeach_S5"


def move(p, brg, d):
    a = math.radians(parse_bearing(brg) if isinstance(brg, str) else brg)
    return (p[0] + d * math.sin(a), p[1] + d * math.cos(a))


ROAD, SIDE = "N14°27'25\"W", "N75°32'35\"E"   # north arrow points RIGHT on this sheet: Lot 9 -> 16 heads N14°W, lots on the east (right) side
lots, checks = {}, {}

widths = [("9", 60.0), ("10", 55.0), ("11", 55.0), ("12", 55.0), ("13", 60.0), ("14", 80.0), ("15", 80.0), ("16", 60.0)]
f = [(0.0, 0.0)]
for _, w in widths:
    f.append(move(f[-1], ROAD, w))
r = [move(p, SIDE, 120.0) for p in f]
for i, (n, _) in enumerate(widths):
    lots[n] = {"ring": [f[i], f[i + 1], r[i + 1], r[i]]}
checks["Rear line S14°27'25\"E 505.00 = frontages of Lots 9-16"] = (math.dist(r[0], r[-1]), 505.00)
checks["Front R/W 526.22 = 505.00 + 20.00 (drainage gap) + 1.22"] = (505.00 + 20.00 + 1.22, 526.22)
checks["West crossing 51.63 = 50 / cos(14°27'25\")"] = (50.0 / math.cos(math.radians(90.0 - parse_bearing(SIDE))), 51.63)

# ---- Lots 17-21 (tick 52) ----
# 20.00' drainage gap, then Lot 17 starts: 1.22' straight to the P.C. of C84 (R=320, Δ 18°13'51", left) = C108 (Lot 17) + C109 (Lot 18); rear concentric
# R=440 = C110 + C111 (radial 17/18 side N66°30'03"E). Past the P.T. the drive runs N32°41'16"W: 4.87' (Lot 18) + 50.00' (Lot 19) + C83 (R=25, 90°) into
# Atlantic Beach Court (N57°18'44"E): 95.00 (Lot 19) + 70.00 (Lot 20) + 60.22 (Lot 21) = 225.22 printed, then C82 (R=25) / C113 (R=50) into the bulb.
# C112 is the last 46.26' of C111, so the monument splitting it is 24.30' along; the plat-boundary curve R=440, L=93.74 (CA 12°12'23") = C110 + 24.30.
def _pt(c_, r_, az):
    return (c_[0] + r_ * math.sin(math.radians(az)), c_[1] + r_ * math.cos(math.radians(az)))


def _arc(c_, r_, az_a, az_b, n=12):
    return [_pt(c_, r_, az_a + (az_b - az_a) * k / n) for k in range(n + 1)]


def _chord_arc(p0_, brg_, chord_, r_, turn, n=12):
    """Arc from p0_ along a printed chord; turn=+1 curves right (clockwise), -1 left."""
    p1_ = move(p0_, brg_, chord_)
    mx, my = (p0_[0] + p1_[0]) / 2, (p0_[1] + p1_[1]) / 2
    h = math.sqrt(max(r_ ** 2 - (chord_ / 2) ** 2, 0.0))
    ux, uy = (p1_[0] - p0_[0]) / chord_, (p1_[1] - p0_[1]) / chord_
    c_ = (mx + turn * h * uy, my - turn * h * ux)
    a0_ = math.degrees(math.atan2(p0_[0] - c_[0], p0_[1] - c_[1]))
    a1_ = math.degrees(math.atan2(p1_[0] - c_[0], p1_[1] - c_[1]))
    return _arc(c_, r_, a0_, a0_ + (a1_ - a0_ + 180.0) % 360.0 - 180.0, n)


def _brg(a_, b_):
    return math.degrees(math.atan2(b_[0] - a_[0], b_[1] - a_[1])) % 360.0


DRV2, CT = "N32°41'16\"W", "N57°18'44\"E"
p17 = move(f[-1], ROAD, 20.0)
pc84 = move(p17, ROAD, 1.22)
C84c = move(pc84, "S75°32'35\"W", 320.0)
az_pc = parse_bearing(SIDE)
d108, d109 = math.degrees(50.50 / 320.0), math.degrees(51.32 / 320.0)
d24 = math.degrees(24.30 / 440.0)
fr17 = _arc(C84c, 320.0, az_pc, az_pc - d108)
fr18 = _arc(C84c, 320.0, az_pc - d108, az_pc - d108 - d109)
rr17 = _arc(C84c, 440.0, az_pc, az_pc - d108)
rr18 = _arc(C84c, 440.0, az_pc - d108, az_pc - d108 - d109)
mon1 = _pt(C84c, 440.0, az_pc - d108 - d24)
rr20 = _arc(C84c, 440.0, az_pc - d108 - d24, az_pc - d108 - d109, 8)
q18 = move(fr18[-1], DRV2, 4.87)
rq18 = move(rr18[-1], DRV2, 4.87)
pc83 = move(q18, DRV2, 50.0)
pi83 = move(pc83, DRV2, 25.0)
pt83 = move(pi83, CT, 25.0)
fil83 = _chord_arc(pc83, "N12°18'44\"E", 35.36, 25.0, +1, 8)
c19 = move(pt83, CT, 95.0)
c20 = move(c19, CT, 70.0)
c21 = move(c20, CT, 60.22)
mon2 = move(mon1, "N63°20'12\"E", 72.83)
mon3 = move(mon2, "N69°02'55\"E", 78.97)
a82 = _chord_arc(c21, "N81°24'26\"E", 20.41, 25.0, +1, 8)
a113 = _chord_arc(a82[-1], "S75°31'05\"E", 1.78, 50.0, -1, 2)
q234 = move(mon3, "N68°37'15\"E", 2.73)   # C234 (R=183, 2.73') on the plat-boundary curve before the 21/22 corner
p21 = move(q234, DRV2, 140.58)
checks["C108 chord N18°58'41\"W 50.45 (computed length)"] = (math.dist(pc84, fr17[-1]), 50.45)
checks["C108 chord bearing error (deg)"] = ((_brg(pc84, fr17[-1]) - parse_bearing("N18°58'41\"W") + 180) % 360 - 180, 0.0)
checks["17/18 side radial vs N66°30'03\"E (deg)"] = ((_brg(fr17[-1], rr17[-1]) - parse_bearing("N66°30'03\"E") + 180) % 360 - 180, 0.0)
checks["C84 P.T. tangent = N32°41'16\"W: 18/19 side square to it (deg)"] = ((az_pc - d108 - d109) - parse_bearing(CT), 0.0)
checks["C83 chord N12°18'44\"E 35.36 (P.C. -> P.T.)"] = (math.dist(pc83, pt83), 35.36)
checks["Court R/W 225.22 = 95.00 + 70.00 + 60.22"] = (95.0 + 70.0 + 60.22, 225.22)
checks["Lot 19 rear corner on the court: 4.87 + 75.00 = 79.87 rear line (ft off)"] = (math.dist(move(rq18, DRV2, 75.0), c19), 0.0)
checks["Plat-boundary curve R=440 L=93.74 = C110 + 24.30"] = (69.44 + 24.30, 93.74)
checks["72.83' line radial at the C111/C112 monument (deg)"] = ((_brg(mon1, mon2) - (az_pc - d108 - d24) + 180) % 360 - 180, 0.0)
checks["Lot 20 closure: 72.83' line end vs court corner + 133.69' S32°41'16\"E (ft)"] = (math.dist(mon2, move(c20, "S32°41'16\"E", 133.69)), 0.0)
checks["Lot 21 closure via C234: 140.58' line end vs C82 + C113 end (ft; 1:4000, at the 0.10' tolerance)"] = (math.dist(p21, a113[-1]), 0.0)
lots["17"] = {"ring": [p17] + fr17 + rr17[::-1] + [move(p17, SIDE, 120.0)]}
lots["18"] = {"ring": fr18 + [q18, rq18] + rr18[::-1]}
lots["19"] = {"ring": [q18] + fil83 + [c19, rq18]}
lots["20"] = {"ring": rr20 + [rq18, c19, c20, mon2]}
lots["21"] = {"ring": [mon2, c20, c21] + a82[1:] + a113[1:] + [q234, mon3]}

# ---- Lots 22-27 around the Atlantic Beach Ct bulb (tick 53) ----
# R.P. on the court centreline, sqrt(75^2 - 50^2) past the C82 fillet (R=25, reversing into the R=50 bulb C81). Radials are true bearings OUTWARD
# from the R.P.: 22/23 S67°49'37"E (50 + 128.47), 23/24 N53°29'23"E (50 + 131.66; labelled inward S53°29'23"W), 24/25 N01°38'09"E (50 + 128.79).
# Bulb pieces by DELTA (C114 / C115 print R=50.10 but every delta sums to C81's 276°22'46" on R=50): C113 2°02'24", C114 81°17'19", C115 58°41'01",
# C116 51°51'14", C117 80°35'13", C118 1°55'34". Outer boundary: R=183 (C234 + 145.73 + 184.17 + C235 = L 340.08), R=165 (156.87 + 97.75 = 254.62),
# then S54°09'28"W 43.47 + 80.12 + 70.11 (= 193.70). Side lines S32°41'16"E 133.70 / 138.86 / 135.00 land on the bulb / court R/W.
BULB = math.sqrt(75.0 ** 2 - 50.0 ** 2)
RPc = move(move(c21, CT, BULB), "N32°41'16\"W", 25.0)
fc82 = move(c21, "S32°41'16\"E", 25.0)
checks["C82 end on the bulb (distance from R.P. - 50, ft)"] = (math.dist(RPc, a82[-1]) - 50.0, 0.0)


def _dms(d_, m_, s_):
    return d_ + m_ / 60.0 + s_ / 3600.0


az21 = _az0 = math.degrees(math.atan2(a82[-1][0] - RPc[0], a82[-1][1] - RPc[1])) % 360.0 - _dms(2, 2, 24)
az2223 = az21 - _dms(81, 17, 19)
az2324 = az2223 - _dms(58, 41, 1)
az2425 = az2324 - _dms(51, 51, 14)
az80 = az2425 - _dms(80, 35, 13) - _dms(1, 55, 34)
checks["C114 end vs printed radial S67°49'37\"E (deg)"] = ((az2223 - parse_bearing("S67°49'37\"E") + 180) % 360 - 180, 0.0)
checks["C115 end vs printed radial N53°29'23\"E (deg)"] = ((az2324 - parse_bearing("N53°29'23\"E") + 180) % 360 - 180, 0.0)
checks["C116 end vs printed radial N01°38'09\"E (deg)"] = ((az2425 - parse_bearing("N01°38'09\"E") + 180) % 360 - 180, 0.0)
checks["C118 end = C80 contact, mirror of C82 about the court CL (deg)"] = (
    ((az80 - parse_bearing(CT) + 180.0) % 360 - 180) + ((az21 + _dms(2, 2, 24) - parse_bearing(CT) + 180.0) % 360 - 180) , 0.0)
o2223 = _pt(RPc, 178.47, az2223)
o2324 = _pt(RPc, 181.66, az2324)
o2425 = _pt(RPc, 178.79, az2425)
checks["Lot 22 outer chord N45°22'44\"E 141.91 from C234 end -> 22/23 radial end (ft)"] = (math.dist(move(q234, "N45°22'44\"E", 141.91), o2223), 0.0)
checks["Lot 23 outer chord N06°15'56\"W 176.49 -> 23/24 radial end (ft)"] = (math.dist(move(o2223, "N06°15'56\"W", 176.49), o2324), 0.0)
m235 = move(o2324, "N36°15'41\"W", 7.44)
checks["Lot 24 outer chord N64°39'49\"W 151.03 -> 24/25 radial end (ft)"] = (math.dist(move(m235, "N64°39'49\"W", 151.03), o2425), 0.0)
mon25 = move(o2425, "S71°07'44\"W", 96.32)
o2526 = move(mon25, "S54°09'28\"W", 43.47)
o2627 = move(o2526, "S54°09'28\"W", 80.12)
o2728 = move(o2627, "S54°09'28\"W", 70.11)
p80 = _pt(RPc, 50.0, az80)
az2526 = az80 + _dms(1, 55, 34)                    # C118 (1.68') belongs to Lot 26: the 25/26 line ends at the C117/C118 point
p2526 = _pt(RPc, 50.0, az2526)
checks["25/26 line (133.70 S32°41'16\"E) end vs C117/C118 point on the bulb (ft)"] = (math.dist(move(o2526, "S32°41'16\"E", 133.70), p2526), 0.0)
fc80 = _pt(RPc, 75.0, az80)
e_row = move(c21, "N32°41'16\"W", 50.0)            # a point on the court's east R/W (50' across from the west R/W)
t80 = move(fc80, "S32°41'16\"E", 25.0)              # C80 tangent point on the east R/W (fillet centre lies outside the R/W)
c26 = move(t80, "S57°18'44\"W", 60.22)
c27 = move(c26, "S57°18'44\"W", 70.00)
checks["C80 tangent point on the east court R/W (ft off the line)"] = (
    abs((t80[0] - e_row[0]) * math.cos(math.radians(parse_bearing(CT))) - (t80[1] - e_row[1]) * math.sin(math.radians(parse_bearing(CT)))), 0.0)
checks["26/27 line (138.86) end vs court R/W + 60.22 (ft)"] = (math.dist(move(o2627, "S32°41'16\"E", 138.86), c26), 0.0)
checks["27/28 line (135.00) end vs court R/W + 70.00 (ft)"] = (math.dist(move(o2728, "S32°41'16\"E", 135.00), c27), 0.0)
bulb_ = lambda a_, b_, n_=12: _arc(RPc, 50.0, a_, b_, n_)  # noqa: E731
_ob = lambda c_, r_, p_, q_, n_=16: _arc(c_, r_, math.degrees(math.atan2(p_[0] - c_[0], p_[1] - c_[1])),  # noqa: E731
                                          math.degrees(math.atan2(p_[0] - c_[0], p_[1] - c_[1])) + ((math.degrees(math.atan2(q_[0] - c_[0], q_[1] - c_[1])) - math.degrees(math.atan2(p_[0] - c_[0], p_[1] - c_[1])) + 180) % 360 - 180), n_)


def _centre(p_, q_, r_, turn):
    ch = math.dist(p_, q_)
    h = math.sqrt(max(r_ ** 2 - (ch / 2) ** 2, 0.0))
    ux, uy = (q_[0] - p_[0]) / ch, (q_[1] - p_[1]) / ch
    return ((p_[0] + q_[0]) / 2 + turn * h * uy, (p_[1] + q_[1]) / 2 - turn * h * ux)


# outer curves turn LEFT walking C234 -> 22 -> 23 -> 24 (convex outward, counter-clockwise about the bulb)
C183 = _centre(q234, o2223, 183.0, -1)
C165 = _centre(m235, o2425, 165.0, -1)
checks["R=183 centre consistency: 23/24 radial end on the same circle (ft)"] = (abs(math.dist(C183, o2324) - 183.0), 0.0)
p2122 = _pt(RPc, 50.0, az21)
fil80 = _arc(fc80, 25.0, math.degrees(math.atan2(p80[0] - fc80[0], p80[1] - fc80[1])), math.degrees(math.atan2(t80[0] - fc80[0], t80[1] - fc80[1])), 8)
lots["22"] = {"ring": [q234] + _ob(C183, 183.0, q234, o2223)[1:] + bulb_(az2223, az21)[1:] + [q234]}
lots["22"]["ring"] = lots["22"]["ring"][:-1]
lots["23"] = {"ring": _ob(C183, 183.0, o2223, o2324) + bulb_(az2324, az2223)}
lots["24"] = {"ring": [o2324] + _ob(C183, 183.0, o2324, m235)[1:] + _ob(C165, 165.0, m235, o2425)[1:] + bulb_(az2425, az2324)}
lots["25"] = {"ring": [o2425] + _ob(C165, 165.0, o2425, mon25)[1:] + [o2526] + bulb_(az2526, az2425)}
lots["26"] = {"ring": [o2526, o2627, c26] + fil80[::-1] + bulb_(az80, az2526, 2)[1:]}
lots["27"] = {"ring": [o2627, o2728, c27, c26]}

# ---- Lots 28-33, east side of Atlantic Beach Dr north of the court (tick 54) ----
# Lot 28 = 75 x 120 with the C79 fillet (mirror of Lot 19): 95.00 on the court from the 27/28 corner, C79 (R=25, 90°), 50.00 on the drive.
# Then 60 / 60 / 55 / 60 and Lot 33 (37.22 + C123, R=400 curving toward the lots); side lines N57°18'44"E 120.00 (Lot 33's match-line side 119.60).
# Rear line N32°41'16"W from the court: 75 + 60 (= the 135.00 line to the bulb-traverse monument) + 60 + 55 + 60 + 55 (part of S32°41'16"E 1225.00).
# Checks: east R/W 322.22 = 50 + 60 + 60 + 55 + 60 + 37.22; Lot 28's front is collinear with Lot 19's (same east R/W across the court mouth); the monument from the bulb
# traverse is 120' deep and 135' from the court; Lot 33's 119.60 = 120 - the C123 offset.
DRV_E = "N32°41'16\"W"
pc79 = move(c27, "S57°18'44\"W", 95.0)
pi79 = move(pc79, "S57°18'44\"W", 25.0)
pt79 = move(pi79, DRV_E, 25.0)
fil79 = _chord_arc(pc79, "N77°41'16\"W", 35.36, 25.0, +1, 8)
checks["C79 chord N77°41'16\"W 35.36 end vs P.T. (ft)"] = (math.dist(fil79[-1], pt79), 0.0)
_nx, _ny = math.cos(math.radians(parse_bearing(DRV_E))), -math.sin(math.radians(parse_bearing(DRV_E)))   # unit normal to the drive
checks["Lot 28 front collinear with Lot 19 front (same east R/W across the court mouth, ft)"] = (abs((pt79[0] - q18[0]) * _nx + (pt79[1] - q18[1]) * _ny), 0.0)
fe = [pt79, move(pt79, DRV_E, 50.0)]
for w in (60.0, 60.0, 55.0, 60.0, 37.22):
    fe.append(move(fe[-1], DRV_E, w))
checks["East R/W S32°41'16\"E 322.22 = 50 + 60 + 60 + 55 + 60 + 37.22"] = (math.dist(pt79, fe[-1]), 322.22)
re_ = [c27]
for w in (75.0, 60.0, 60.0, 55.0, 60.0, 55.0):
    re_.append(move(re_[-1], DRV_E, w))
checks["135.00 line: court corner + 75 + 60 vs bulb-traverse monument (ft)"] = (math.dist(re_[2], o2728), 0.0)
checks["Lot 29/30 side: front corner + 120.00 N57°18'44\"E vs monument (ft)"] = (math.dist(move(fe[2], CT, 120.0), o2728), 0.0)
a123 = _chord_arc(fe[-1], "N31°24'51\"W", 17.78, 400.0, +1, 6)
checks["Lot 33 match-line side 119.60 (end of C123 -> rear corner)"] = (math.dist(a123[-1], re_[-1]), 119.60)
lots["28"] = {"ring": fil79 + [fe[1], re_[1], c27]}
for i, n in enumerate(("29", "30", "31", "32"), start=1):
    lots[n] = {"ring": [fe[i], fe[i + 1], re_[i + 1], re_[i]]}
lots["33"] = {"ring": [fe[5]] + a123 + [re_[6], re_[5]]}

# ---- Lots 81-86 + Tract F, west side of Atlantic Beach Dr (tick 55) ----
# West R/W = 50' west of the east R/W; C61 (R=270, Δ 18°13'51") is concentric with C84 (R=320) about the CL curve (R=295), so its P.C. is opposite C84's.
# Going south from that P.C.: 37.76 (Lot 82), 20.00 drainage gap, 70 (83), 55 (84), 55 (85), 50 (86) + C60 (R=25, 90°) = 287.76 printed.
# North: C161 (Lot 82) + C160 (Lot 81) + 21.30; rear concentric R=150 (C163 + C162) + 21.30. Rear line N14°27'25"W 194.92 = 14.92 + 55 + 55 + 70.
# Tract F (lift station): 60.08 on Lot 86's rear from the cross-street R/W, N75°32'35"E 40.00, S14°27'25"E 60.00, closed by 33.25 + C164 (R=300)
# on the cross-street R/W (95.00 + 33.25 = 128.25 printed).
SOUTH, WEST = "S14°27'25\"E", "S75°32'35\"W"
pcW = move(pc84, WEST, 50.0)
fw = [pcW]
for w in (37.76, 20.0, 70.0, 55.0, 55.0, 50.0):
    fw.append(move(fw[-1], SOUTH, w))
checks["West R/W S14°27'25\"E 287.76 = 37.76 + 20 + 70 + 55 + 55 + 50"] = (math.dist(fw[0], fw[-1]), 287.76)
fil60 = _chord_arc(fw[-1], "S30°32'35\"W", 35.36, 25.0, +1, 8)
pt60 = move(move(fw[-1], SOUTH, 25.0), WEST, 25.0)
checks["C60 chord S30°32'35\"W 35.36 end vs P.T. (ft)"] = (math.dist(fil60[-1], pt60), 0.0)
rw = [move(p, WEST, 120.0) for p in fw]
r86s = move(pt60, WEST, 95.0)
checks["Lot 86 rear: 120' deep corner vs 95.00 along the cross-street (ft)"] = (math.dist(move(rw[-1], SOUTH, 25.0), r86s), 0.0)
checks["Rear line N14°27'25\"W 194.92 = 14.92 + 55 + 55 + 70 (gap-edge rear -> Tract F monument)"] = (math.dist(rw[2], move(r86s, ROAD, 60.08)), 194.92)
lots["83"] = {"ring": [fw[2], fw[3], rw[3], rw[2]]}
lots["84"] = {"ring": [fw[3], fw[4], rw[4], rw[3]]}
lots["85"] = {"ring": [fw[4], fw[5], rw[5], rw[4]]}
lots["86"] = {"ring": [fw[5]] + fil60 + [r86s, rw[5]]}
mTF = move(r86s, ROAD, 60.08)
tTF = move(mTF, WEST, 40.0)
wTF = move(tTF, SOUTH, 60.0)
x33 = move(r86s, WEST, 33.25)
a164 = _chord_arc(x33, "S76°11'15\"W", 6.75, 300.0, +1, 4)
checks["Tract F closure: S14°27'25\"E 60.00 end vs C164 end (ft)"] = (math.dist(wTF, a164[-1]), 0.0)
tract_f = [r86s, mTF, tTF, wTF] + a164[::-1][1:-1] + [x33]
# Lots 82 / 81 on C61
C61c = move(pcW, WEST, 270.0)
d161, d160 = math.degrees(28.86 / 270.0), math.degrees(57.05 / 270.0)
fr82 = _arc(C61c, 270.0, az_pc, az_pc - d161)
fr81 = _arc(C61c, 270.0, az_pc - d161, az_pc - d161 - d160)
rr82 = _arc(C61c, 150.0, az_pc, az_pc - d161, 6)
rr81 = _arc(C61c, 150.0, az_pc - d161, az_pc - d161 - d160, 8)
checks["C161 chord N17°31'08\"W 28.84 (computed length)"] = (math.dist(fr82[0], fr82[-1]), 28.84)
checks["C160 chord N26°38'04\"W 56.95 (computed length)"] = (math.dist(fr81[0], fr81[-1]), 56.95)
checks["C163 chord 16.02 / C162 chord 31.64 (rear R=150), sum of misses (ft)"] = (
    abs(math.dist(rr82[0], rr82[-1]) - 16.02) + abs(math.dist(rr81[0], rr81[-1]) - 31.64), 0.0)
checks["82/81 side radial vs S69°25'09\"W (deg)"] = ((_brg(fr82[-1], rr82[-1]) - parse_bearing("S69°25'09\"W") + 180) % 360 - 180, 0.0)
checks["C61 = C161 + C160 = 85.91 (Δ 18°13'51\")"] = (28.86 + 57.05, 85.91)
f81e, r81e = move(fr81[-1], DRV2, 21.30), move(rr81[-1], DRV2, 21.30)
checks["81/80 side S57°18'44\"W 120.00 (ft)"] = (math.dist(f81e, r81e), 120.0)
checks["Lot 82 rear straight N14°27'25\"W 37.76 (gap-edge rear -> C163 start)"] = (math.dist(rw[1], rr82[0]), 37.76)
lots["82"] = {"ring": [fw[1]] + fr82 + rr82[::-1] + [rw[1]]}
lots["81"] = {"ring": fr81 + [f81e, r81e] + rr81[::-1]}
lots["Tract F"] = {"ring": tract_f}

for v in lots.values():
    v["area"] = shoelace(v["ring"])

d = out_dir(PLAT_ID)
rings = [("LOT", v["ring"]) for v in lots.values()]
texts = [("TEXT-LABELS", (sum(p[0] for p in v["ring"]) / len(v["ring"]), sum(p[1] for p in v["ring"]) / len(v["ring"])), f"{n}  {v['area']:,.0f} SF", 6)
         for n, v in lots.items()]
texts.append(("TITLEBLOCK", (-150.0, -60.0), f"ATLANTIC BEACH CC UNIT 2  PB 67 PG 136 (SHEET 5)  LOTS 9-33, 81-86, TRACT F  ({writer_suffix().strip('_')})", 8))
layers = [("LOT", "cyan", "CONTINUOUS"), ("LOT-FLAGGED", "red", "CONTINUOUS"), ("TEXT-LABELS", "white", "CONTINUOUS"), ("TITLEBLOCK", "yellow", "CONTINUOUS")]
write_dxf(os.path.join(d, f"PB0067_P0136_AtlanticBeachCC_Sheet5{writer_suffix()}.dxf"), layers, rings, [], texts)
render_png(os.path.join(d, "PB0067_P0136_AtlanticBeachCC_Sheet5.png"), "Atlantic Beach CC Unit 2, Sheet 5 - Lots 9-33, 81-86, Tract F", rings, [], texts,
           flagged={"LOT-FLAGGED"})
save_metrics(PLAT_ID, {
    "plat_id": PLAT_ID, "source": "Plat/67-132.pdf page 5", "lots_built": len(lots),
    "lots": {k: {"area_sqft": round(v["area"], 1)} for k, v in lots.items()},
    "flagged": {},
    "checks": {k: {"computed": round(c, 3), "printed": p} for k, (c, p) in checks.items()},
    "todo": "Lots 72-80 and 87-90 (west of the drive); Lot 34 and the 1225.00 line continue on Sheet 6",
})
for k, (c, p) in checks.items():
    print(f"  {k}: {c:.2f} vs {p}")
print(f"lots {len(lots)}")
