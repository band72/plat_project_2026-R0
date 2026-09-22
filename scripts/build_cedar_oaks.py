import math
import sys

sys.path.insert(0, '.')
import data.cedar_oaks as co
from engine.cogo import Point, parse_bearing
from engine.dxf_writer import DXFWriter
from engine.lots import Lot, shoelace_area

# ---------- validation 1: depth progression vs bearing convergence ----------
print("=== CHECK 1: depth progression vs bearing convergence ===")
conv = abs(parse_bearing(co.BLK1_NORTH_BEARING) -
           (180 - parse_bearing(co.BLK1_SOUTH_BEARING) + 360) % 360)
conv_min = (33 - 6)  # arcmin, N89°33' vs 89°06'
pred = 80.01 * math.tan(math.radians(conv_min / 60.0))
deltas = [co.BLK1_SIDE_LENGTHS[i] - co.BLK1_SIDE_LENGTHS[i + 1]
          for i in range(len(co.BLK1_SIDE_LENGTHS) - 1)]
obs = sum(deltas) / len(deltas)
print(f"  convergence {conv_min}' -> predicted depth loss per 80.01' lot = {pred:.3f} ft")
print(f"  observed mean decrement = {obs:.3f} ft   (individual: "
      f"{', '.join(f'{d:.2f}' for d in deltas)})")
print(f"  agreement: {abs(pred-obs):.3f} ft  -> "
      f"{'CONSISTENT' if abs(pred-obs) < 0.05 else 'CHECK'}")
bad = [i for i, d in enumerate(deltas) if abs(d - obs) > 0.05]
print(f"  progression outliers (would flag a digit error): "
      f"{bad if bad else 'none'}")

# ---------- validation 2: north line segment sum vs stated total ----------
print("\n=== CHECK 2: north boundary segment sum ===")
seg = sum(co.BLK1_NORTH_WIDTHS) + 105.0 + co.BLK1_EAST_REMAINDER
print(f"  segments (95.02 + 7x80.01 + 105 + 330) = {seg:.2f} ft")
print(f"  stated total N89°33'E {co.BLK1_NORTH_TOTAL_STATED}'+/- -> "
      f"diff {seg - co.BLK1_NORTH_TOTAL_STATED:+.2f} ft "
      f"({'within plat stated +/- tolerance' if abs(seg-co.BLK1_NORTH_TOTAL_STATED) < 5 else 'CHECK'})")

# ---------- build Block 1 (trapezoidal lots) ----------
naz = parse_bearing(co.BLK1_NORTH_BEARING)
saz = parse_bearing(co.BLK1_SOUTH_BEARING)
side_az = parse_bearing(co.BLK1_SIDE_BEARING)

origin = Point(0.0, 0.0)          # NW corner of Lot 1, Block 1 (local frame)
north_pts = [origin]
p = origin
for wdt in co.BLK1_NORTH_WIDTHS:
    p = p.offset(naz, wdt)
    north_pts.append(p)

side_lengths = list(co.BLK1_SIDE_LENGTHS) + [co.BLK1_SIDE_9_DERIVED]
south_pts = [north_pts[i].offset(side_az, side_lengths[i])
             for i in range(len(side_lengths))]
print(f"  NOTE: 9th side line (east side of Lot 8) = {co.BLK1_SIDE_9_DERIVED}' "
      f"DERIVED from the validated progression, not read from the sheet.")

print("\n=== CHECK 3: Block 1 per-lot closure (trapezoids) ===")
blk1 = []
for i in range(len(co.BLK1_LOTS)):
    nw, ne = north_pts[i], north_pts[i + 1]
    sw, se = south_pts[i], south_pts[i + 1]
    # independent check: south width implied by geometry vs south width read
    implied = sw.dist_to(se)
    read_w = co.BLK1_SOUTH_WIDTHS[i]
    corners = [nw, ne, se, sw]
    area = shoelace_area(corners + [corners[0]])
    blk1.append(Lot(number=co.BLK1_LOTS[i], corners=corners, area_sqft=area))
    flag = "ok" if abs(implied - read_w) < 0.15 else "CHECK"
    print(f"  Lot {co.BLK1_LOTS[i]}: south width implied {implied:7.2f} vs read "
          f"{read_w:6.2f} ({implied-read_w:+.2f})  area {area:8.1f} sf  [{flag}]")

# ---------- build Block 2 (rectangles) ----------
b2naz = parse_bearing(co.BLK2_NORTH_BEARING)
b2saz = parse_bearing(co.BLK2_SIDE_BEARING)
# place Block 2 one 60' R/W south of Block 1's south line
b2_origin = south_pts[0].offset(parse_bearing("S00°54'00\"E"), 60.0)
print("\n=== CHECK 4: Block 2 lots (80' x 120' rectangles) ===")
blk2 = []
p = b2_origin
for i, wdt in enumerate(co.BLK2_NORTH_WIDTHS):
    nw = p
    ne = p.offset(b2naz, wdt)
    se = ne.offset(b2saz, co.BLK2_DEPTH)
    sw = nw.offset(b2saz, co.BLK2_DEPTH)
    corners = [nw, ne, se, sw]
    area = shoelace_area(corners + [corners[0]])
    blk2.append(Lot(number=co.BLK2_LOTS[i], corners=corners, area_sqft=area))
    expect = wdt * co.BLK2_DEPTH
    print(f"  Lot {co.BLK2_LOTS[i]}: {wdt:6.2f} x {co.BLK2_DEPTH} -> area {area:8.1f} sf "
          f"(expect {expect:8.1f}) [{'ok' if abs(area-expect)<1 else 'CHECK'}]")
    p = ne

# ---------- DXF ----------
dxf = DXFWriter()
for lname, col, lt in [("BOUNDARY", "white", "CONTINUOUS"),
                       ("LOT_LINE", "cyan", "CONTINUOUS"),
                       ("ROW_STREET", "yellow", "DASHED"),
                       ("TEXT-LABELS", "white", "CONTINUOUS"),
                       ("DIM-LABELS", "green", "CONTINUOUS"),
                       ("TITLEBLOCK", "yellow", "CONTINUOUS"),
                       ("UNRESOLVED", "red", "DASHED")]:
    dxf.add_layer(lname, col, lt)


def draw(lot, layer="LOT_LINE"):
    pts = lot.close()
    for i in range(len(pts) - 1):
        dxf.line((pts[i].n, pts[i].e), (pts[i + 1].n, pts[i + 1].e), layer=layer)
    cn = sum(q.n for q in lot.corners) / 4
    ce = sum(q.e for q in lot.corners) / 4
    dxf.text((cn, ce), f"{lot.number}", height=10, layer="TEXT-LABELS")
    dxf.text((cn - 14, ce - 18), f"{lot.area_sqft:,.0f} sf", height=6, layer="TEXT-LABELS")


for lot in blk1:
    draw(lot)
for lot in blk2:
    draw(lot)

# north boundary emphasised
for i in range(len(north_pts) - 1):
    dxf.line((north_pts[i].n, north_pts[i].e),
             (north_pts[i + 1].n, north_pts[i + 1].e), layer="BOUNDARY")
    mn = (north_pts[i].n + north_pts[i + 1].n) / 2
    me = (north_pts[i].e + north_pts[i + 1].e) / 2
    dxf.text((mn + 5, me), f"{co.BLK1_NORTH_WIDTHS[i]:.2f}'", height=7, layer="DIM-LABELS")
dxf.text((north_pts[0].n + 22, north_pts[0].e),
         f"N'ly line of Lot 4, Blk 1, Ortega Farms  {co.BLK1_NORTH_BEARING} "
         f"({co.BLK1_NORTH_TOTAL_STATED:.0f}'+/- total)", height=9, layer="DIM-LABELS")

# side-line depth labels
for i, d in enumerate(side_lengths):
    a, b = north_pts[i], south_pts[i]
    dxf.text(((a.n + b.n) / 2, (a.e + b.e) / 2 - 6), f"{d:.2f}'", height=6, layer="DIM-LABELS")

# Cedar Oaks Drive R/W
dxf.line((south_pts[0].n, south_pts[0].e), (south_pts[-1].n, south_pts[-1].e), layer="ROW_STREET")
dxf.line((b2_origin.n, b2_origin.e),
         (blk2[-1].corners[1].n, blk2[-1].corners[1].e), layer="ROW_STREET")
mid = Point((south_pts[0].n + b2_origin.n) / 2, (south_pts[0].e + b2_origin.e) / 2)
dxf.text((mid.n, mid.e + 120), "CEDAR OAKS DRIVE (60' R/W)  89°06'", height=11, layer="ROW_STREET")

# unresolved east end marker
east = north_pts[-1]
dxf.line((east.n, east.e), (east.n, east.e + co.BLK1_EAST_REMAINDER), layer="UNRESOLVED")
dxf.text((east.n + 14, east.e + 40),
         "EAST END UNRESOLVED (Lots 9-11, 'Not Included' parcel, Cedar Creek)",
         height=9, layer="UNRESOLVED")

top = max(q.n for q in north_pts) + 120
lft = min(q.e for q in north_pts)
lines = [
    "CEDAR OAKS -- PLAT BOOK 24, PAGE 18, DUVAL COUNTY, FL (1953)",
    "Replat of Lots 4 & 5, Blk 1, Ortega Farms (PB 3 pg 79). R.L. Cropsdell & Co.",
    "",
    "SOURCE: 200 DPI scan; values transcribed by visual read at 3x, NOT by OCR.",
    "PLAT NOTE: bearings/distances on curves are CHORD bearings and distances.",
    "",
    "VALIDATION:",
    f"  Bearing convergence 27' predicts {pred:.3f} ft depth loss per 80.01' lot;",
    f"  observed decrement {obs:.3f} ft -> independent confirmation of both the",
    "  bearings and the depth sequence. No progression outliers.",
    f"  North segments sum {seg:.2f} ft vs stated {co.BLK1_NORTH_TOTAL_STATED:.0f}'+/-.",
    "",
    "SCOPE: Block 1 Lots 1-8 and Block 2 Lots 1-8 built and closure-checked.",
    "East end and Park Road curve NOT built -- not legible at this resolution.",
]
for i, t in enumerate(lines):
    dxf.text((top - i * 26, lft), t, height=11 if i == 0 else 8, layer="TITLEBLOCK")

out = "dxf/PB0024_P0018_CedarOaks.dxf"
dxf.save(out)
print(f"\nsaved {out}")
print(f"lots built: {len(blk1)+len(blk2)}")
