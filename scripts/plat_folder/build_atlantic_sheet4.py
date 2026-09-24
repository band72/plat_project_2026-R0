"""ATLANTIC BEACH COUNTRY CLUB UNIT 2 -- Sheet 4 of 6 (PB 67 Pg 135). Plat/67-132.pdf page 4, read at 300 dpi.

Maritime Oak Drive runs N38°23'04"W (50' R/W). Built so far:
  SE row, Lots 95-100: rectangles 120.00' deep (side lines N51°36'56"E, square to the road), frontages 55 / 60 / 60 / 80 / 70 / 60.
  Check: the printed rear line S38°23'04"E 502.15' = 2.15 + 55 (94) + 55 + 60 + 60 + 80 + 70 + 60 + 60 (101) exactly.
Todo: Lots 94, 101 (curve / irregular ends), the NW row 108-118, the cul-de-sac lots 102-107, and 88-93 / 119-124 at the south end.
"""
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine.cogo import parse_bearing  # noqa: E402
from engine.dxf_writer import writer_suffix  # noqa: E402
from scripts.plat_folder.common import out_dir, render_png, save_metrics, shoelace, write_dxf  # noqa: E402

PLAT_ID = "PB67_P132_AtlanticBeach_S4"


def move(p, brg, d):
    a = math.radians(parse_bearing(brg) if isinstance(brg, str) else brg)
    return (p[0] + d * math.sin(a), p[1] + d * math.cos(a))


ROAD_NW, SIDE_SE = "N38°23'04\"W", "N51°36'56\"E"
lots, checks = {}, {}

# SE row: front corners along the SE R/W going NW from the Lot 94/95 corner; rear corners 120' out along N51°36'56"E
widths = [("95", 55.0), ("96", 60.0), ("97", 60.0), ("98", 80.0), ("99", 70.0), ("100", 60.0)]
f = [(0.0, 0.0)]
for _, w in widths:
    f.append(move(f[-1], ROAD_NW, w))
r = [move(p, SIDE_SE, 120.0) for p in f]
for i, (n, _) in enumerate(widths):
    lots[n] = {"ring": [f[i], f[i + 1], r[i + 1], r[i]]}
checks["Rear line S38°23'04\"E 502.15' = 2.15 + 55 + 55 + 60 + 60 + 80 + 70 + 60 + 60"] = (2.15 + 55 + 55 + 60 + 60 + 80 + 70 + 60 + 60, 502.15)
# NW row (tick 42): 50' across the road (S51°36'56"W from the SE R/W), rectangles 120' deep to the N38°23'04"W 534.60' boundary.
# 115/114 and 112/113 are 90' lots split 60' / 60' (front lot on the road, rear lot behind). Shapes are fully printed; the row's
# position ALONG the road is not tied on this sheet -> placed with its 116 south corner opposite the SE row's Lot 95 south corner, FLAGGED.
SIDE_NW = "S51°36'56\"W"
# Tie (tick 43): both R/W straights are 557.72', so their ends are opposite (radial). SE straight starts 2.15' before Lot 94 (55');
# NW straight starts at the end of C181 and runs 80.49' (Lot 118) + 55' (Lot 117) to Lot 116. So Lot 116's south corner is 50' across
# and (80.49 + 55) - (2.15 + 55) = 78.34' along the road from Lot 95's south corner.
pt_se = move(f[0], (parse_bearing(ROAD_NW) + 180.0) % 360.0, 57.15)
pt_nw = move(pt_se, SIDE_NW, 50.0)
g0 = move(pt_nw, ROAD_NW, 80.49 + 55.0)
checks["NW straight 557.72' = 80.49 + 55 + 55 + 90 + 90 + 55 + 55 + 60 + 17.23 (Lot 108)"] = (80.49 + 55 + 55 + 90 + 90 + 55 + 55 + 60 + 17.23, 557.72)
p117 = move(g0, (parse_bearing(ROAD_NW) + 180.0) % 360.0, 55.0)
lots["117"] = {"ring": [p117, g0, move(g0, "S51°36'56\"W", 120.0), move(p117, "S51°36'56\"W", 120.0)]}
# Lot 118 (tick 44): front = C181 (R=150, chord 6.37' S37°13'36"E going SW) + 80.49' straight; SW side S64°14'39"W 122.84';
# rear 60.00' along the N38°23'04"W boundary from Lot 117's rear corner. Check: the SW side must end on that 60.00' point.
w118 = move(pt_nw, "S37°13'36\"E", 6.37)
x118 = move(w118, "S64°14'39\"W", 122.84)
r117 = move(p117, "S51°36'56\"W", 120.0)
rb118 = move(r117, "S38°23'04\"E", 60.0)
checks["Lot 118 SW side end vs 60.00' along the rear boundary (ft)"] = (math.dist(x118, rb118), 0.0)
lots["118"] = {"ring": [w118, pt_nw, p117, r117, rb118, x118]}
# Lot 119 (tick 45): C182 (R=150, chord 93.92' S17°42'20"E going SW), west side S86°26'04"W 123.84', boundary N07°48'24"W 45.00' + 14.60'
# back to Lot 118's corner. The loop misses by ~5' in every orientation / with or without L7 (4.44') -> BEST FIT, flagged.
y119 = move(w118, "S17°42'20\"E", 93.92)
t119 = move(y119, "S86°26'04\"W", 123.84)
m119 = move(t119, "N07°48'24\"W", 45.00)
checks["Lot 119 boundary monument -> Lot 118 corner, printed 14.60' (ft)"] = (math.dist(m119, x118), 14.60)
lots["119"] = {"ring": [y119, w118, x118, m119, t119]}
FLAGGED_119 = {"119"}
p94 = move(f[0], (parse_bearing(ROAD_NW) + 180.0) % 360.0, 55.0)
lots["94"] = {"ring": [p94, f[0], r[0], move(p94, SIDE_SE, 120.0)]}
row = [("116", 55.0, None), ("115", 90.0, "114"), ("112", 90.0, "113"), ("111", 55.0, None), ("110", 55.0, None), ("109", 60.0, None)]
g = [g0]
for _, w, _b in row:
    g.append(move(g[-1], ROAD_NW, w))
for i, (n, w, back) in enumerate(row):
    a0, a1 = g[i], g[i + 1]
    if back is None:
        lots[n] = {"ring": [a0, a1, move(a1, SIDE_NW, 120.0), move(a0, SIDE_NW, 120.0)]}
    else:
        m0, m1 = move(a0, SIDE_NW, 60.0), move(a1, SIDE_NW, 60.0)
        lots[n] = {"ring": [a0, a1, m1, m0]}
        lots[back] = {"ring": [m0, m1, move(a1, SIDE_NW, 120.0), move(a0, SIDE_NW, 120.0)]}
FLAGGED = set() | FLAGGED_119   # NW row tied by the opposite straights (tick 43); 119 is a best fit

# ---- Cul-de-sac bulb + Lot 108 (tick 46) ----
# NW R/W straight ends 17.23' past the 109/108 corner; C51 (R=25) reverses into the R=50 bulb, tangent externally, so the bulb's R.P. is
# on the road centreline sqrt(75^2 - 50^2) past the fillet centre. Checks: C51 = 25 x acos(50/75) = 21.027 (printed 21.03); the 108/107 line
# (57.45' along N55°10'28"W from Lot 109's rear corner, then 115.00' N51°36'56"E) ends 49.998' from the R.P.; C180 (23.49') ends 0.009' from it.
def _arc(c_, r_, p0_, a_len, sg, n=12):
    a0_ = math.atan2(p0_[1] - c_[1], p0_[0] - c_[0])
    return [(c_[0] + r_ * math.cos(a0_ + sg * a_len / r_ * k / n), c_[1] + r_ * math.sin(a0_ + sg * a_len / r_ * k / n)) for k in range(n + 1)]


e_nw = move(g[6], ROAD_NW, 17.23)
fc51 = move(e_nw, SIDE_NW, 25.0)
RP = move(move(fc51, SIDE_SE, 50.0), ROAD_NW, math.sqrt(75.0 ** 2 - 50.0 ** 2))
t51 = (fc51[0] + (RP[0] - fc51[0]) / 3.0, fc51[1] + (RP[1] - fc51[1]) / 3.0)
c51 = _arc(fc51, 25.0, e_nw, 25.0 * math.acos(50.0 / 75.0), 1)
if math.dist(c51[-1], t51) > 0.01:
    c51 = _arc(fc51, 25.0, e_nw, 25.0 * math.acos(50.0 / 75.0), -1)
c180 = _arc(RP, 50.0, t51, 23.49, -1)
a108 = move(g[6], SIDE_NW, 120.0)
b108 = move(a108, "N55°10'28\"W", 57.45)
p108 = move(b108, SIDE_SE, 115.0)
checks["C51 arc = 25 x acos(50/75) vs printed 21.03"] = (25.0 * math.acos(50.0 / 75.0), 21.03)
checks["Lot 108/107 line end -> R.P. (bulb R = 50)"] = (math.dist(p108, RP), 50.0)
checks["C180 (23.49') end vs 108/107 line end (ft)"] = (math.dist(c180[-1], p108), 0.0)
lots["108"] = {"ring": [g[6], e_nw] + c51[1:] + c180[1:-1] + [p108, b108, a108]}

# ---- Lots 107-104 around the bulb (tick 47) ----
# Radial lines are printed as true bearings outward from the R.P.; each outer end is checked against its printed station on the
# boundary chain (128.87 / 77.21 / 63.03 / 80.74 / 37.77 / 149.49 / 108.87 from the Lot 108 monument): all within 0.01'.
M2 = move(b108, "N34°18'28\"W", 128.87)
M3 = move(M2, "N02°13'42\"E", 77.21)
M4 = move(M3, "N37°55'35\"E", 63.03)
M5 = move(M4, "N51°55'28\"E", 80.74)
M6 = move(M5, "N58°54'55\"E", 37.77)   # seconds digit faint ("5?"); +/-5" moves nothing by 0.01'
M7 = move(M6, "N89°58'05\"E", 149.49)
radial = {"107/106": ("S84°20'26\"W", 132.20, move(b108, "N34°18'28\"W", 116.93)),
          "106/105": ("N46°59'39\"W", 135.96, move(M4, "N51°55'28\"E", 13.09)),
          "105/104": ("N04°30'05\"W", 138.66, move(M6, "N89°58'05\"E", 35.59)),
          "104/103": ("N38°01'49\"E", 142.95, move(M7, "S28°40'49\"E", 41.21))}
R_in, R_out = {}, {}
for k_, (brg_, len_, onb_) in radial.items():
    R_in[k_] = move(RP, brg_, 50.0)
    R_out[k_] = move(RP, brg_, 50.0 + len_)
    checks[f"Radial {k_} outer end vs boundary station (ft)"] = (math.dist(R_out[k_], onb_), 0.0)


def bulb(p0_, p1_, n=16):
    a0_ = math.atan2(p0_[1] - RP[1], p0_[0] - RP[0])
    a1_ = math.atan2(p1_[1] - RP[1], p1_[0] - RP[0])
    da_ = (a1_ - a0_ + math.pi) % (2 * math.pi) - math.pi
    return [(RP[0] + 50.0 * math.cos(a0_ + da_ * k / n), RP[1] + 50.0 * math.sin(a0_ + da_ * k / n)) for k in range(n + 1)]


lots["107"] = {"ring": [p108, b108, R_out["107/106"]] + bulb(R_in["107/106"], p108)[:-1]}
lots["106"] = {"ring": [R_out["107/106"], M2, M3, M4, R_out["106/105"]] + bulb(R_in["106/105"], R_in["107/106"])}
lots["105"] = {"ring": [R_out["106/105"], M5, M6, R_out["105/104"]] + bulb(R_in["105/104"], R_in["106/105"])}
lots["104"] = {"ring": [R_out["105/104"], M7, R_out["104/103"]] + bulb(R_in["104/103"], R_in["105/104"])}

# ---- Lots 103-101 (tick 48) ----
# SE R/W straight = 2.15 + 55 + 55 + 60 + 60 + 80 + 70 + 60 + 70 (101) + 45.57 (102) = 557.72 exactly. Boundary S28°40'49"E 108.87 then
# S19°18'48"E 95.34 = 21.28 + 63.48 + 10.58. Checks: 102/101 line (123.46') lands 0.007' from its boundary station; 103/102 line (139.62')
# lands 0.010' from the end of C174 (R=25, chord 15.14'); Lot 101's rear from the boundary corner to Lot 100's rear corner = 60.001 (60.00).
M8 = move(M7, "S28°40'49\"E", 108.87)
M9 = move(M8, "S19°18'48\"E", 95.34)
c101 = move(f[6], ROAD_NW, 70.0)
pc_se = move(c101, ROAD_NW, 45.57)
o103, o102 = move(M8, "S19°18'48\"E", 21.28), move(M8, "S19°18'48\"E", 84.76)
in103 = move(pc_se, "N20°45'32\"W", 15.14)
checks["SE straight 557.72' = lots 94-101 + 45.57"] = (2.15 + 55 + 55 + 60 + 60 + 80 + 70 + 60 + 70 + 45.57, 557.72)
checks["102/101 line end vs boundary station 84.76' (ft)"] = (math.dist(move(c101, SIDE_SE, 123.46), o102), 0.0)
checks["103/102 line end vs C174 end (ft)"] = (math.dist(move(o103, "S51°36'56\"W", 139.62), in103), 0.0)
checks["Lot 101 rear (boundary corner -> Lot 100 rear) vs 60.00'"] = (math.dist(M9, r[6]), 60.0)
f53 = move(pc_se, SIDE_SE, 25.0)
t53 = (f53[0] + (RP[0] - f53[0]) / 3.0, f53[1] + (RP[1] - f53[1]) / 3.0)
lots["101"] = {"ring": [f[6], c101, o102, M9, r[6]]}
lots["102"] = {"ring": [c101, pc_se, in103, o103, o102]}
lots["103"] = {"ring": [in103, t53] + bulb(t53, R_in["104/103"])[1:] + [R_out["104/103"], M8, o103]}

# ---- Lots 93, 92, 91 (tick 49) ----
# SE R/W curve C54 (R=200, Δ 38°55'25") = C173 (59.41, Lot 93) + C172 (76.46, Lot 92), starting at the P.C. 2.15' SE of Lot 94; the rear curve
# (R=320 = 200 + 120, concentric) = C171 (95.05) + C170 (90.92), starting 2.15' past Lot 94's rear. Checks: C173/C172 chord bearings; the 93/92
# side is radial S68°38'03"W 120.00; the 92/91 line (N75°42'15"E 122.54, not radial) joins the two curve ends; Lot 91 (L8 4.44, C55, C56, C57,
# 23.49', match line S35°41'54"W 120.00', 23.49', S56°04'58"E 16.78') closes on Lot 92's rear corner.
def _around(c_, r_, az_a, az_b, n=16):
    return [(c_[0] + r_ * math.sin(math.radians(az_a + (az_b - az_a) * k / n)), c_[1] + r_ * math.cos(math.radians(az_a + (az_b - az_a) * k / n)))
            for k in range(n + 1)]


def _chord_arc(p0_, brg_, chord_, r_, turn, n=12):
    """Arc from p0_ along a printed chord; turn=+1 curves right (clockwise), -1 left."""
    p1_ = move(p0_, brg_, chord_)
    mx, my = (p0_[0] + p1_[0]) / 2, (p0_[1] + p1_[1]) / 2
    h = math.sqrt(max(r_ ** 2 - (chord_ / 2) ** 2, 0.0))
    ux, uy = (p1_[0] - p0_[0]) / chord_, (p1_[1] - p0_[1]) / chord_
    c_ = (mx + turn * h * uy, my - turn * h * ux)   # centre on the right of travel for a right turn
    a0_ = math.degrees(math.atan2(p0_[0] - c_[0], p0_[1] - c_[1]))
    a1_ = math.degrees(math.atan2(p1_[0] - c_[0], p1_[1] - c_[1]))
    da_ = (a1_ - a0_ + 180.0) % 360.0 - 180.0
    return _around(c_, r_, a0_, a0_ + da_, n)


C54c = move(pt_se, "S51°36'56\"W", 200.0)
az0 = parse_bearing("N51°36'56\"E")
d173, d172 = math.degrees(59.41 / 200.0), math.degrees(76.46 / 200.0)
d171, d170 = math.degrees(95.05 / 320.0), math.degrees(90.92 / 320.0)
front93 = _around(C54c, 200.0, az0, az0 + d173)
front92 = _around(C54c, 200.0, az0 + d173, az0 + d173 + d172)
rear93 = _around(C54c, 320.0, az0, az0 + d171)
rear92 = _around(C54c, 320.0, az0 + d171, az0 + d171 + d170)
F93, F92, B93, B92 = front93[-1], front92[-1], rear93[-1], rear92[-1]
rpc = move(pt_se, SIDE_SE, 120.0)


def _brg(a_, b_):
    return math.degrees(math.atan2(b_[0] - a_[0], b_[1] - a_[1])) % 360.0


checks["C173 chord S29°52'30\"E 59.19 (computed length)"] = (math.dist(pt_se, F93), 59.19)
checks["C172 chord S10°24'48\"E 76.00 (computed length)"] = (math.dist(F93, F92), 76.00)
checks["C173 chord bearing error (deg)"] = (_brg(pt_se, F93) - parse_bearing("S29°52'30\"E"), 0.0)
checks["93/92 radial side bearing error vs N68°38'03\"E (deg)"] = (_brg(F93, B93) - parse_bearing("N68°38'03\"E"), 0.0)
checks["92/91 line length (curve end to curve end) vs 122.54"] = (math.dist(F92, B92), 122.54)
checks["92/91 line bearing error vs N75°42'15\"E (deg)"] = (_brg(F92, B92) - parse_bearing("N75°42'15\"E"), 0.0)
lots["93"] = {"ring": [p94, pt_se] + front93[1:] + rear93[::-1] + [move(p94, SIDE_SE, 120.0)]}
lots["92"] = {"ring": front92 + rear92[::-1]}
l8e = move(F92, "S00°32'22\"W", 4.44)
a55 = _chord_arc(l8e, "S05°05'23\"W", 21.42, 135.0, +1)
a56 = _chord_arc(a55[-1], "S32°17'31\"E", 33.41, 25.0, -1)
a57 = _chord_arc(a56[-1], "S64°15'46\"E", 51.89, 150.0, +1)
m1 = move(a57[-1], "S54°18'06\"E", 23.49)       # along the C57 tangent, square to the match line
m2 = move(m1, "N35°41'54\"E", 120.0)
x91 = move(B92, "S56°04'58\"E", 16.78)
checks["Lot 91 closing course (match-line corner -> end of 16.78') vs 23.49"] = (math.dist(m2, x91), 23.49)
lots["91"] = {"ring": [F92] + a55 + a56[1:] + a57[1:] + [m1, m2, x91, B92]}

# ---- Lots 120-124 + Lot 119 re-solved (tick 50) ----
# SW R/W from the NW straight's P.T.: C181 + C182 (= C50, R=150), L7 4.44', C183 + C184 (= C49, R=85), C185-C189 (= C48, R=235), C190 (R=100),
# walked by the curve table's chords. Side lines N89°27'38"W (120/119: S86°26'04"W 123.84 from the END OF C183). Independent checks on the rear
# boundary: Lot 120 rear 61.20 on N11°55'06"E; the R=335 curve (CA 21°57'44", chord 127.62) holds the 122/121 and 123/122 rear corners; C191 chord
# 30.21; Lot 124 rear 55.95 and the match-line corner (17.54 + 55.95 past the P.T.). Lot 119 (flagged in tick 45 because its side line was started
# at the end of C182) now closes: its N07°48'24"W 45.00' boundary course ends 14.59' from Lot 118's corner (printed 14.60).
a182 = _chord_arc(w118, "S17°42'20\"E", 93.92, 150.0, +1)
l7e = move(a182[-1], "S00°32'22\"W", 4.44)
a183 = _chord_arc(l7e, "S03°10'55\"W", 7.84, 85.0, +1, n=4)
a184 = _chord_arc(a183[-1], "S19°00'31\"W", 38.77, 85.0, +1)
a185 = _chord_arc(a184[-1], "S27°47'18\"W", 36.09, 235.0, -1)
a186 = _chord_arc(a185[-1], "S16°23'47\"W", 57.18, 235.0, -1)
a187 = _chord_arc(a186[-1], "S02°41'03\"W", 55.04, 235.0, -1)
a188 = _chord_arc(a187[-1], "S11°32'32\"E", 61.36, 235.0, -1)
a189 = _chord_arc(a188[-1], "S24°38'19\"E", 45.82, 235.0, -1)
a190 = _chord_arc(a189[-1], "S25°54'01\"E", 15.11, 100.0, +1, n=4)
SIDE_SW = "N89°27'38\"W"
r120 = move(a183[-1], "S86°26'04\"W", 123.84)
r121, r122, r123, r124 = (move(a185[-1], SIDE_SW, 106.79), move(a186[-1], SIDE_SW, 100.84),
                          move(a187[-1], SIDE_SW, 100.22), move(a188[-1], SIDE_SW, 104.67))
rml = move(a190[-1], SIDE_SW, 120.62)
PC335 = move(r120, "S11°55'06\"W", 86.85)
PT335 = move(PC335, "S00°56'14\"W", 127.62)
arc335 = _chord_arc(PC335, "S00°56'14\"W", 127.62, 335.0, -1, n=48)
_ux, _uy = (PT335[0] - PC335[0]) / 127.62, (PT335[1] - PC335[1]) / 127.62
_h = math.sqrt(335.0 ** 2 - 63.81 ** 2)
C335 = ((PC335[0] + PT335[0]) / 2 - _h * _uy, (PC335[1] + PT335[1]) / 2 + _h * _ux)


def _az(c_, p_):
    return math.degrees(math.atan2(p_[0] - c_[0], p_[1] - c_[1]))


checks["Lot 120 rear (120/119 -> 121/120 rear corners) vs 61.20"] = (math.dist(r120, r121), 61.20)
checks["Lot 121 rear: 25.64' to the P.C. of R=335 (ft)"] = (math.dist(r121, PC335), 25.64)
checks["C191 chord (P.C. -> 122/121 rear corner) vs 30.21"] = (math.dist(PC335, r122), 30.21)
checks["122/121 rear corner off the R=335 curve (ft)"] = (abs(math.dist(C335, r122) - 335.0), 0.0)
checks["123/122 rear corner off the R=335 curve (ft)"] = (abs(math.dist(C335, r123) - 335.0), 0.0)
checks["124/123 rear corner vs P.T. + 17.54' S10°02'38\"E (ft)"] = (math.dist(move(PT335, "S10°02'38\"E", 17.54), r124), 0.0)
checks["Match-line rear corner vs P.T. + 17.54 + 55.95 (ft)"] = (math.dist(move(PT335, "S10°02'38\"E", 73.49), rml), 0.0)
m119b = move(r120, "N07°48'24\"W", 45.0)
checks["Lot 119 closing course (45.00' monument -> Lot 118 corner) vs 14.60"] = (math.dist(m119b, x118), 14.60)
lots["119"] = {"ring": a182 + [l7e] + a183[1:] + [r120, m119b, x118]}
lots["120"] = {"ring": a183[-1:] + a184[1:] + a185[1:] + [r121, r120]}
lots["121"] = {"ring": a186 + [r122] + _around(C335, 335.0, _az(C335, r122), _az(C335, PC335), 8)[1:] + [r121]}
lots["122"] = {"ring": a187 + [r123] + _around(C335, 335.0, _az(C335, r123), _az(C335, r122), 12)[1:]}
lots["123"] = {"ring": a188 + [r124, PT335] + _around(C335, 335.0, _az(C335, PT335), _az(C335, r123), 12)[1:]}
lots["124"] = {"ring": a189 + a190[1:] + [rml, r124]}
FLAGGED = set()

for v in lots.values():
    v["area"] = shoelace(v["ring"])

d = out_dir(PLAT_ID)
rings = [("LOT-FLAGGED" if n in FLAGGED else "LOT", v["ring"]) for n, v in lots.items()]
texts = [("TEXT-LABELS", (sum(p[0] for p in v["ring"]) / len(v["ring"]), sum(p[1] for p in v["ring"]) / len(v["ring"])), f"{n}  {v['area']:,.0f} SF", 6)
         for n, v in lots.items()]
texts.append(("TITLEBLOCK", (0.0, 200.0), f"ATLANTIC BEACH CC UNIT 2  PB 67 PG 135 (SHEET 4)  LOTS 91-124  ({writer_suffix().strip('_')})", 8))
layers = [("LOT", "cyan", "CONTINUOUS"), ("LOT-FLAGGED", "red", "CONTINUOUS"), ("TEXT-LABELS", "white", "CONTINUOUS"), ("TITLEBLOCK", "yellow", "CONTINUOUS")]
write_dxf(os.path.join(d, f"PB0067_P0135_AtlanticBeachCC_Sheet4{writer_suffix()}.dxf"), layers, rings, [], texts)
render_png(os.path.join(d, "PB0067_P0135_AtlanticBeachCC_Sheet4.png"), "Atlantic Beach CC Unit 2, Sheet 4 - Lots 91-124", rings, [], texts,
           flagged={"LOT-FLAGGED"})
save_metrics(PLAT_ID, {
    "plat_id": PLAT_ID, "source": "Plat/67-132.pdf page 4", "lots_built": len(lots),
    "lots": {k: {"area_sqft": round(v["area"], 1)} for k, v in lots.items()},
    "flagged": {n: "shape printed; position along Maritime Oak Dr not tied on this sheet" for n in sorted(FLAGGED)},
    "checks": {k: {"computed": round(c, 3), "printed": p} for k, (c, p) in checks.items()},
    "todo": "Tract E (closing course is on the Sheet 3 match line) and Lot 90 (mostly Sheet 5)",
})
for k, (c, p) in checks.items():
    print(f"  {k}: {c:.2f} vs {p}")
print(f"lots {len(lots)}")
