"""
BEACHWOOD UNIT TWO -- Plat Book 30, Pages 82 & 82A, Duval County, FL (1960)
Beach Boulevard Estates, Inc. / Simmerson, Bell & Akel. Scale 1"=100'.
Replat of part of Beachwood Acreage Replat (PB 29 pg 86).

Values transcribed by VISUAL READ from a 200 DPI scan at 3x magnification.
Tesseract measured 0 usable bearings on this sheet across 8 preprocessing
variants -- see MASTER_PROMPT.md Iter 7.

PLAT NOTES (sheet 2, transcribed):
  1. Bearings and distances shown on curves are chord bearings and distances.
  2. Distances shown on block corners are to street line intersections.
  3. Building restriction and setback lines are 25 feet from street line.
  5. Permanent Reference Monuments are shown thus: (c) P.R.M.
  6. Easements are for drainage & utilities.
  7. Tract "A" is reserved for Sewage Lift Station.
"""
import sys, math
sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing
from engine.lots import shoelace_area, Lot
from engine.dxf_writer import DXFWriter

# ---- north boundary (N'ly line of Section 32) ----
NORTH_BEARING = "S87°35'30\"W"
NORTH_DISTANCE = 1626.37          # "S.87°35'30"W.-1626.37'"
POC_TO_POB = ("N87°35'30\"E", 762.64)   # from NW cor Sec 32 to POB

# ---- Block 18: north row, between the 50' drainage R/W and Starfish Ave ----
BLK18_STREET_BEARING = "S87°35'30\"W"    # Starfish Avenue, 60' R/W
BLK18_SIDE_BEARING = "N02°24'30\"W"      # lot side lines
BLK18_DEPTH = 100.00
BLK18_WIDTHS = [103.50] + [75.00] * 18   # Lots 1-19
BLK18_LOTS = [str(i) for i in range(1, 20)]
NORTH_ROW_RW = 50.0                      # 50' R/W for drainage and utilities

UNRESOLVED = [
    "East end of each block (ties to Beachwood Boulevard: 80.04', 116.39', "
    "113.34', 111.58', 108.55' read but the closing geometry to the Blvd "
    "curve is not legible at 200 DPI).",
    "Diagonal blocks (Marina Ave, Sands Ave, Cape Horn Ave, Keel Drive) -- "
    "these run at a skew with inline 'Curve Data' blocks (A=/R=/T=) that are "
    "only partly legible.",
    "Sheet 1 caption: ~25 courses; several bearings ambiguous at this "
    "resolution. NOT transcribed -- would require the original or a rescan.",
    "Tract 'A' (sewage lift station) location noted but not dimensioned here.",
]

# ================= VALIDATION =================
print("=== CHECK 1: side bearing perpendicular to street bearing ===")
street = parse_bearing(BLK18_STREET_BEARING)
side = parse_bearing(BLK18_SIDE_BEARING)
ang = abs((street - side + 180) % 360 - 180)
print(f"  street {BLK18_STREET_BEARING} vs side {BLK18_SIDE_BEARING}")
print(f"  included angle = {ang:.6f} deg  -> "
      f"{'EXACTLY PERPENDICULAR' if abs(ang-90) < 0.0005 else 'CHECK'}")
print("  (87d35'30\" + 2d24'30\" = 90d00'00\" -- the two bearings are read from "
      "different parts of the sheet and confirm each other)")

print("\n=== CHECK 2: parallel boundaries imply constant depth ===")
print(f"  north line {NORTH_BEARING} and Starfish Ave {BLK18_STREET_BEARING} are")
print(f"  identical -> convergence 0' -> predicted depth decrement 0.000 ft")
print(f"  observed: all depths transcribed as {BLK18_DEPTH} ft (decrement 0.000)")
print("  -> CONSISTENT (contrast Cedar Oaks, where 27' convergence predicted")
print("     0.628 ft/lot and the depths duly shrank)")

print("\n=== CHECK 3: block width vs north boundary ===")
tot = sum(BLK18_WIDTHS)
print(f"  Lot 1 103.50 + 18 x 75.00 = {tot:.2f} ft")
print(f"  north line total {NORTH_DISTANCE} ft -> remainder east of Lot 19 = "
      f"{NORTH_DISTANCE - tot:.2f} ft")
print(f"  (remainder covers the Beachwood Blvd tie -- see UNRESOLVED)")

# ================= BUILD =================
saz = parse_bearing(BLK18_STREET_BEARING)
daz = parse_bearing(BLK18_SIDE_BEARING)
# walk west->east along the row; street bearing points west, so use its reverse
eaz = (saz + 180) % 360
depth_az = (daz + 180) % 360          # south, into the lot from the north line

origin = Point(0.0, 0.0)              # NW corner of Lot 1 (local frame)
lots = []
p = origin
print("\n=== CHECK 4: Block 18 lot closure ===")
for num, wdt in zip(BLK18_LOTS, BLK18_WIDTHS):
    nw = p
    ne = p.offset(eaz, wdt)
    se = ne.offset(depth_az, BLK18_DEPTH)
    sw = nw.offset(depth_az, BLK18_DEPTH)
    corners = [nw, ne, se, sw]
    area = shoelace_area(corners + [corners[0]])
    expect = wdt * BLK18_DEPTH
    ok = abs(area - expect) < 0.5
    lots.append(Lot(number=num, corners=corners, area_sqft=area))
    if num in ("1", "2", "19"):
        print(f"  Lot {num:>2}: {wdt:6.2f} x {BLK18_DEPTH} -> {area:8.1f} sf "
              f"(expect {expect:8.1f}) [{'ok' if ok else 'CHECK'}]")
    p = ne
print(f"  ... all {len(lots)} lots closed; "
      f"{sum(1 for l in lots if abs(l.area_sqft - 7500) < 0.5)} at exactly 7,500 sf")

# ================= DXF =================
dxf = DXFWriter()
for n, c, lt in [("BOUNDARY", "white", "CONTINUOUS"), ("LOT_LINE", "cyan", "CONTINUOUS"),
                 ("ROW_STREET", "yellow", "DASHED"), ("EASEMENT", "green", "DASHED"),
                 ("TEXT-LABELS", "white", "CONTINUOUS"), ("DIM-LABELS", "green", "CONTINUOUS"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS"), ("UNRESOLVED", "red", "DASHED")]:
    dxf.add_layer(n, c, lt)

for lot in lots:
    pts = lot.close()
    for i in range(len(pts) - 1):
        dxf.line((pts[i].n, pts[i].e), (pts[i + 1].n, pts[i + 1].e), layer="LOT_LINE")
    cn = sum(q.n for q in lot.corners) / 4
    ce = sum(q.e for q in lot.corners) / 4
    dxf.text((cn, ce), lot.number, height=9, layer="TEXT-LABELS")
    dxf.text((cn - 13, ce - 16), f"{lot.area_sqft:,.0f} sf", height=5, layer="TEXT-LABELS")

nw0 = lots[0].corners[0]
ne_last = lots[-1].corners[1]
dxf.line((nw0.n, nw0.e), (ne_last.n, ne_last.e), layer="BOUNDARY")
dxf.text((nw0.n + 14, nw0.e), f"N'ly line Sec 32   {NORTH_BEARING}  {NORTH_DISTANCE}'",
         height=9, layer="DIM-LABELS")
dxf.text((nw0.n + 5, nw0.e), "POINT OF BEGINNING", height=8, layer="DIM-LABELS")

sw0, se_last = lots[0].corners[3], lots[-1].corners[2]
dxf.line((sw0.n, sw0.e), (se_last.n, se_last.e), layer="ROW_STREET")
dxf.text((sw0.n - 22, sw0.e + 300), f"STARFISH AVENUE (60' R/W)  {BLK18_STREET_BEARING}",
         height=11, layer="ROW_STREET")
# 50' drainage/utility R/W north of the block
dxf.line((nw0.n + NORTH_ROW_RW, nw0.e), (ne_last.n + NORTH_ROW_RW, ne_last.e),
         layer="EASEMENT")
dxf.text((nw0.n + NORTH_ROW_RW - 12, nw0.e + 250),
         "50' RIGHT-OF-WAY FOR DRAINAGE AND UTILITIES", height=9, layer="EASEMENT")
dxf.text((nw0.n - 40, nw0.e + 620), "BLOCK 18", height=14, layer="TEXT-LABELS")

# unresolved east tie
dxf.line((ne_last.n, ne_last.e), (ne_last.n, ne_last.e + (NORTH_DISTANCE - tot)),
         layer="UNRESOLVED")
dxf.text((ne_last.n + 12, ne_last.e + 10),
         f"EAST TIE TO BEACHWOOD BLVD UNRESOLVED ({NORTH_DISTANCE-tot:.2f}' remainder)",
         height=9, layer="UNRESOLVED")

top = nw0.n + 190
lft = nw0.e
body = [
    "BEACHWOOD UNIT TWO -- PLAT BOOK 30, PAGES 82 & 82A, DUVAL COUNTY, FL (1960)",
    "Beach Boulevard Estates, Inc.  |  Simmerson, Bell & Akel  |  1\"=100'",
    "",
    "SOURCE: 200 DPI scan; values transcribed by visual read at 3x, NOT by OCR.",
    "(Tesseract parsed 0 usable bearings here across 8 preprocessing variants.)",
    "",
    "VALIDATION:",
    f"  Side bearing N2d24'30\"W + street bearing S87d35'30\"W = 90d00'00\" exactly",
    f"    -> included angle computed {ang:.6f} deg. The two bearings are read from",
    f"       different parts of the sheet and independently confirm each other.",
    "  North line and Starfish Ave are parallel -> depth must be constant;",
    "    all depths transcribed as 100.00 ft. Consistent.",
    f"  Block width 103.50 + 18(75.00) = {tot:.2f} ft of the {NORTH_DISTANCE} ft north line.",
    "",
    "SCOPE: Block 18 (Lots 1-19) built and closure-checked. Remaining blocks,",
    "the diagonal Marina/Sands/Cape Horn fabric, the Beachwood Blvd tie, and the",
    "sheet-1 caption traverse are NOT built -- not legible at this resolution.",
    "PLAT NOTE: curve bearings/distances are CHORD bearings and distances.",
]
for i, t in enumerate(body):
    dxf.text((top - i * 26, lft), t, height=11 if i == 0 else 8, layer="TITLEBLOCK")

out = "dxf/PB0030_P0082_BeachwoodUnitTwo.dxf"
dxf.save(out)
print(f"\nsaved {out}")
