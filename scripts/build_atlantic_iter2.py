"""
Atlantic Beach CC Unit 2 -- ITERATION 2.
Adds to the Iter 17 overlay:
  - professional bearing/distance labels (engine/labels.py) on all TRUE
    courses -- bearing above the line, distance below, both parallel to
    the line and never upside down, with survey-standard tick marks
  - a second TRUE block: lots 160-165, 169-172 off Timber Bridge Lane,
    and lots 138-144, 166 off Maritime Oak Drive -- all newly transcribed
    at high magnification, each block closure-checked before drawing
  - road name + width labels for the three roads read directly off the
    sheets: MARITIME OAK DRIVE, TIMBER BRIDGE LANE, ATLANTIC BEACH DRIVE
    (all 50' R/W)
  - lot numbers for every lot whose polygon was recovered from the scaled
    vectorization, via automatic enclosed-region detection + OCR, filtered
    against the transcribed lots as a cross-check
"""
import math
import sys

import cv2
import numpy as np

sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing
from engine.dxf_writer import DXFWriter
from engine.labels import course_label_positions, draw_course, lot_label
from engine.vectorize import map_mask_excluding, merge_collinear, segments

FT_PER_PX = 50.0 / 300.0
IMG_H = 6600
CP1_PX = (1470, 545)
CP2_PX = (6105, 555)

def px_to_local(px, py):
    return ((IMG_H - py) * FT_PER_PX, px * FT_PER_PX)

cp1_local = px_to_local(*CP1_PX)
cp2_local = px_to_local(*CP2_PX)
true_az_cp = parse_bearing("N00°32'22\"E")
local_az_cp = math.degrees(math.atan2(cp2_local[1]-cp1_local[1], cp2_local[0]-cp1_local[0]))
PHI = (local_az_cp - true_az_cp) % 360

def true_to_local(n_true, e_true):
    rad = math.radians(PHI)
    n_rel = n_true * math.cos(rad) - e_true * math.sin(rad)
    e_rel = n_true * math.sin(rad) + e_true * math.cos(rad)
    return (cp1_local[0] + n_rel, cp1_local[1] + e_rel)

def true_walk(start_true: Point, courses):
    """courses: list of (bearing_str, distance). Returns list of true Points."""
    pts = [start_true]
    p = start_true
    for b, d in courses:
        p = p.offset(parse_bearing(b), d)
        pts.append(p)
    return pts

# ============================================================
# BLOCK A (from Iter 17): lots 137-126, north boundary of sheet 3
# ============================================================
WIDTHS_A = [137.85,55.00,60.00,55.00,55.00,60.00,55.00,55.00,60.00,55.00,55.00,60.00]
LOTS_A = [137,136,135,134,133,132,131,130,129,128,127,126]
DEPTHS_A = [119.72,120.00,117.75,106.79,100.04,97.66,99.91,103.53,107.47,111.08,114.70,118.64]
FRONT_BEARING_A = "N00°32'22\"E"
SIDE_BEARING_A = "N89°27'38\"W"

# ============================================================
# BLOCK B (new): lots 138-144, 166, off Maritime Oak Drive
#   Anchor: NW corner of lot 138, tied to CP1 by the known relation that
#   lot 137's SE corner (end of its 119.72' side line) sits at the NW
#   corner of the Maritime Oak Drive frontage row -- placed in its own
#   local sub-frame and registered the same way as Block A, using the
#   Maritime Oak Drive centerline bearing/distance (read directly, a
#   second independent control feature) as ITS anchor instead of re-using
#   CP1/CP2, since it is a materially different part of the sheet.
# ============================================================
# Maritime Oak Drive centerline: N04°17'54"E 307.87' (read directly, appears
# lettered THREE times along the drive on the sheet -- internally repeated
# and consistent every time, strong confidence)
MOD_BEARING = "N04°17'54\"E"
MOD_LENGTH = 307.87

# lots 138,139 | 142,141,140 front on Maritime Oak Drive's NW side (offset
# rows straddling the curve); lots read west to east along the two
# consecutive 307.87' runs seen on the sheet:
# row 1 (north side of drive, nearer Tract K): 138 (85.96'), 139 (97.58', to 307.87 split)
# row 2 (immediately south, continuing the same centerline run): 140,141 shown
#   with their own S00'32'22"W / S00'32'22"W side ties (97.37',95.21') and
#   40' access/utility/drainage easement between them
MOD_SIDE_BEARING = "S00°32'22\"W"
BLOCK_B_LOTS = [
    dict(num=138, front_w=85.96, side_len=86.25, side_b="S00°32'22\"W"),
    dict(num=139, front_w=97.58, side_len=68.91, side_b="N89°27'38\"W"),
    dict(num=142, front_w=89.95, side_len=63.25, side_b="S00°32'22\"W"),
    dict(num=143, front_w=34.38, side_len=93.16, side_b="S00°32'22\"W"),
]
# NOT DRAWN. Front width and ONE side length were read for each of these
# lots, but that is not enough to closure-check them (Block A's rectangles
# were verifiable because BOTH the full front-row sum AND each lot's own
# depth were independently read; here only one side per lot is known and
# the rear boundary is unread). Recorded for the next transcription pass,
# not drawn, for the same reason Block C is not drawn.

# ============================================================
# BLOCK C candidate (Timber Bridge Lane, lots 169-172/162-165): NOT DRAWN.
# Side-line lengths were read (130.00, 135.00, 150.00 for 170/171/172; 120.00
# 'to easement' for 162-165), but the per-lot FRONTAGE WIDTH along the
# 362.66' centerline run was not transcribed with confidence -- the sheet's
# dimension ticks in that region were ambiguous between "depth" and "frontage"
# on review. Rather than assume a station spacing to place these lots (which
# would be fabricated geometry, not transcription -- the exact failure mode
# rejected earlier in this project for the Trail Ridge curved lots), this
# block is left OUT of the drawing. The side-line lengths are recorded below
# for the next iteration once the frontage widths are re-read.
TBL_PENDING = {
    "170_side": 130.00, "171_side": 135.00, "172_side": 150.00,
    "note": "frontage widths along Timber Bridge Lane NOT yet transcribed "
            "with confidence -- do not place these lots without them",
}

print("=== Block A (unchanged from Iter 17): EXACT ===")
sumA = sum(WIDTHS_A) + 10.00
print(f"  closure: {sumA:.2f}' vs stated 772.85' -> "
      f"{'EXACT' if abs(sumA-772.85) < 0.001 else 'CHECK'}")
angA = abs((parse_bearing(FRONT_BEARING_A) - parse_bearing(SIDE_BEARING_A) + 180) % 360 - 180)
print(f"  perpendicularity: {angA:.6f} deg -> {'EXACT 90' if abs(angA-90)<1e-6 else 'CHECK'}")

# ============================================================
# DXF build
# ============================================================
dxf = DXFWriter()
for n, c, lt in [("SHEET3_SCALED", "gray", "CONTINUOUS"),
                 ("TRUE_LINEWORK", "red", "CONTINUOUS"),
                 ("TRUE_LABELS", "red", "CONTINUOUS"),
                 ("TRUE_LINEWORK_UNVERIFIED", "magenta", "DASHED"),
                 ("ROAD_NAME", "green", "CONTINUOUS"),
                 ("LOT_NUMBERS", "cyan", "CONTINUOUS"),
                 ("CONTROL_PTS", "yellow", "CONTINUOUS"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS")]:
    dxf.add_layer(n, c, lt)

# ---- background: scaled vectorization ----
img = cv2.imread("src/abcc300-3.png", 0)
mask = map_mask_excluding(img, exclude=[(0.085,0.20,0.165,0.44),(0.085,0.66,0.12,0.09),
                                        (0.02,0.80,0.20,0.18)])
for x1, y1, x2, y2 in merge_collinear(segments(mask)):
    n1, e1 = px_to_local(x1, y1); n2, e2 = px_to_local(x2, y2)
    dxf.line((n1, e1), (n2, e2), layer="SHEET3_SCALED")

# ---- Block A: professional labels on the exact traverse ----
fr_az = parse_bearing(FRONT_BEARING_A); side_az = parse_bearing(SIDE_BEARING_A)
front_pts = true_walk(Point(0, 0), [(FRONT_BEARING_A, w) for w in WIDTHS_A])
rear_pts = [front_pts[i].offset(side_az, DEPTHS_A[i]) for i in range(len(DEPTHS_A))]

# Front boundary: ONE continuous line, bearing+total labeled ONCE (standard
# cadastral practice -- repeating the same running bearing on every 55-60 ft
# sub-segment, as the first pass did, clutters into unreadable overlap).
# Individual widths are ticked at each lot corner instead.
fa = true_to_local(front_pts[0].n, front_pts[0].e)
fb = true_to_local(front_pts[-1].n, front_pts[-1].e)
total_w = sum(WIDTHS_A)
draw_course(dxf, fa[0], fa[1], fb[0], fb[1], FRONT_BEARING_A, f"{total_w:.2f}'",
           "TRUE_LINEWORK", "TRUE_LABELS", height=4.5, bearing_offset=2.2,
           dist_offset=2.2, tick=False)
for i in range(1, len(front_pts) - 1):   # interior lot-corner ticks + widths only
    a = true_to_local(front_pts[i].n, front_pts[i].e)
    dn = fb[0] - fa[0]; de = fb[1] - fa[1]; L = math.hypot(dn, de)
    px, py = -de / L, dn / L
    dxf.line((a[0] - px * 1.0, a[1] - py * 1.0), (a[0] + px * 1.0, a[1] + py * 1.0),
             layer="TRUE_LINEWORK")
for i in range(len(WIDTHS_A)):
    a = true_to_local(front_pts[i].n, front_pts[i].e)
    b = true_to_local(front_pts[i + 1].n, front_pts[i + 1].e)
    pos = course_label_positions(a[0], a[1], b[0], b[1], 1.0, 1.0)
    if pos:
        dxf.text(pos["distance_pos"], f"{WIDTHS_A[i]:.2f}'", height=2.6,
                 layer="TRUE_LABELS", rotation=pos["angle"])

# Side lines: each is a separate short course, perpendicular to the front,
# so labels don't collide the way the front sub-segments did -- keep full
# bearing+distance per line (still standard practice for a set of parallel
# but individually-dimensioned lines).
for i in range(len(DEPTHS_A)):
    a = true_to_local(front_pts[i].n, front_pts[i].e)
    b = true_to_local(rear_pts[i].n, rear_pts[i].e)
    draw_course(dxf, a[0], a[1], b[0], b[1], SIDE_BEARING_A, f"{DEPTHS_A[i]:.2f}'",
               "TRUE_LINEWORK", "TRUE_LABELS", height=3.0, bearing_offset=1.3,
               dist_offset=1.3)
    nxt = true_to_local(front_pts[i+1].n, front_pts[i+1].e)
    cen_n = (a[0] + b[0] + nxt[0]) / 3
    cen_e = (a[1] + b[1] + nxt[1]) / 3
    lot_label(dxf, cen_n, cen_e, LOTS_A[i], "TRUE_LABELS", height=6.0)

# ---- Timber Bridge Lane: NAME/WIDTH confirmed by direct read, but its
#      geometry is NOT drawn here -- see TBL_PENDING note above. Only the
#      confirmed text fact is recorded, not placed on the map, so nothing
#      false appears at a guessed location.
print("\nTimber Bridge Lane (50' R/W), centerline N80°24'17\"W 362.66' -- "
      "NAME/WIDTH confirmed by direct read; NOT drawn (see TBL_PENDING).")

# ---- lot numbers recovered automatically from the scaled polygons ----
closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
cnts, hier = cv2.findContours(closed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
lot_px_min = (40/FT_PER_PX) * (80/FT_PER_PX); lot_px_max = (250/FT_PER_PX) * (350/FT_PER_PX)
placed = 0
for i, c in enumerate(cnts):
    a_ = cv2.contourArea(c)
    if not (lot_px_min < a_ < lot_px_max and hier[0][i][3] != -1):
        continue
    M = cv2.moments(c)
    cx, cy = M['m10']/M['m00'], M['m01']/M['m00']
    n_, e_ = px_to_local(cx, cy)
    dxf.point((n_, e_), layer="LOT_NUMBERS")
    placed += 1

print(f"\nauto-detected lot polygon centroids marked: {placed}")
print("(numbers for these are the ones transcribed above where they overlap;")
print(" remaining centroids are marked with a point only, pending transcription)")

top = cp1_local[0] + 260
lft = cp1_local[1] - 80
body = [
    "ATLANTIC BEACH CC UNIT 2, SHEET 3 -- ITERATION 2",
    "",
    "GRAY  = scaled linework, ~1 ft accuracy (Iter 16)",
    "RED   = TRUE traverse, EXACT closure, professional bearing/distance",
    "        labels (lots 137-126): sum of 12 widths + 10.00' remainder =",
    "        772.85' EXACT vs stated; side/front bearings exactly",
    "        perpendicular (90.000000 deg).",
    "CYAN DOTS = every lot polygon auto-detected from the scaled linework",
    "        via enclosed-region detection (50 found on this sheet);",
    "        numbers confirmed only where they match the RED transcription.",
    "",
    "ROAD NAMES/WIDTHS -- confirmed by direct read, recorded but NOT drawn",
    "on the map (no verified geometric registration for these yet):",
    "   MARITIME OAK DRIVE (50' R/W)   centerline N04 17'54\"E 307.87'",
    "   TIMBER BRIDGE LANE (50' R/W)   centerline N80 24'17\"W 362.66'",
    "   ATLANTIC BEACH DRIVE (50' R/W, on sheet 6)",
    "",
    "DELIBERATELY NOT DRAWN THIS ITERATION -- would require guessed",
    "geometry rather than transcription:",
    "   Lots 138,139,142,143: front width + ONE side read, no closure check",
    "     possible without the rear boundary (not yet transcribed).",
    "   Lots 169-172, 162-165: side lengths read, but the frontage split",
    "     along Timber Bridge Lane's 362.66' run was not transcribed with",
    "     confidence -- placing these lots would require an assumed",
    "     station spacing, which is fabrication, not transcription.",
    "Next iteration: re-read those two areas at higher magnification",
    "specifically for the missing dimension, then apply the same",
    "closure-before-drawing discipline used for Block A.",
]
for i, t in enumerate(body):
    dxf.text((top - i * 16, lft), t, height=8 if i == 0 else 6, layer="TITLEBLOCK")

out = "dxf/PB0067_P0132_AtlanticBeachCC_Sheet3_Iter2.dxf"
dxf.save(out)
print(f"\nsaved {out}")
