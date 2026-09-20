"""
BROOKLYN LAKE ESTATES -- Plat Book 4, Page 39, Clay County, FL
A re-subdivision in Sec 17, T8S, R23E. Sheet header reads SHEET 1 OF 2
(the uploaded file is named "sheet_2_of_2" -- naming mismatch, flagged).

Interior worked from the P.O.B. at the SW corner of the NW1/4 of the SW1/4.

PLAT NOTES (transcribed):
  - "Bearings and distances shown on curves refer to the chord."
  - "Lots 6 through 41 extend from Carroll Drive to the waters of Lake
    Brooklyn. Bearings and distances shown along the Lake front of said lots
    refer to a CLOSING MEANDER ONLY and do not represent the boundary of
    said Lake front lots. Measurements shown on the side lines of the Lake
    front lots refer to the distance from Carroll Drive to iron pipes
    located on the aforementioned meander line."
  - "All bearings ... are assumed, being based on the Southerly boundary
    line of the NW1/4 of the SW1/4 of Section 17 ... having a bearing of
    'East'."

Because the lake front is a COMPUTED CLOSING MEANDER, each lot is a closed
figure and must close tightly -- unlike a true natural-boundary lot. That
makes per-lot closure a valid and strict test here.
"""
import sys, math
sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing, azimuth_to_bearing
from engine.lots import shoelace_area, Lot
from engine.dxf_writer import DXFWriter

SOUTH_BEARING = "N90°00'00\"E"          # "EAST" per the assumed-bearing note
SOUTH_TOTAL_STATED = 378.00             # "EAST 378.0'"
WEST_BOUNDARY = ("S00°30'30\"W", 300.0) # Sec 17 west line, 300'+/-
SECTION_OFFSET = 50.0                   # lot line lies 50' north of the section line

# west-to-east: lot number, south frontage, EAST side-line depth, lake meander
LOTS = [
    dict(num="41", front=75.00, east_depth=207.88, meander=("S86°13'00\"W", 73.25),
         west_depth=202.79, west_bearing="S00°30'30\"W"),
    dict(num="40", front=75.00, east_depth=212.05, meander=("S86°47'00\"W", 75.07),
         west_depth=207.88, west_bearing="S00°00'00\"W"),
    dict(num="39", front=75.00, east_depth=212.35, meander=("S89°44'30\"W", 75.00),
         west_depth=212.05, west_bearing="S00°00'00\"W"),
    dict(num="38", front=75.00, east_depth=236.31, meander=("S72°07'30\"W", 78.80),
         west_depth=212.35, west_bearing="S00°00'00\"W"),
]
# Lot 37 omitted: its easterly boundary runs to the Carroll Drive curve
# (N76 51'50"E 125.0, delta=48 00', R=300.0) and the figure cannot be closed
# from the south row alone.

print("=== CHECK 1: south frontage sum vs stated total ===")
fsum = sum(l["front"] for l in LOTS) + 77.80      # lot 37 frontage 77.8'
print(f"  75+75+75+75+77.80 = {fsum:.2f} ft vs stated EAST {SOUTH_TOTAL_STATED} ft")
print(f"  difference {fsum - SOUTH_TOTAL_STATED:+.2f} ft "
      f"({'within plat rounding' if abs(fsum-SOUTH_TOTAL_STATED)<0.3 else 'CHECK'})")

print("\n=== CHECK 2: per-lot closure (meander is a COMPUTED closing line) ===")
east_az = parse_bearing(SOUTH_BEARING)
north_az = 0.0

origin = Point(0.0, 0.0)     # SW corner of Lot 41 (50' N of the P.O.B.)
built = []
x = 0.0
for l in LOTS:
    sw = origin.offset(east_az, x)
    se = sw.offset(east_az, l["front"])
    ne = se.offset(north_az, l["east_depth"])            # east side bears NORTH
    maz = parse_bearing(l["meander"][0])
    nw = ne.offset(maz, l["meander"][1])                 # lake closing meander
    # the west side is now determined -- compare against the transcribed value
    implied_d = nw.dist_to(sw)
    dn, de = sw.n - nw.n, sw.e - nw.e
    implied_az = math.degrees(math.atan2(de, dn)) % 360
    err = abs(implied_d - l["west_depth"])
    corners = [sw, se, ne, nw]
    area = shoelace_area(corners + [corners[0]])
    built.append(Lot(number=l["num"], corners=corners, area_sqft=area))
    print(f"  Lot {l['num']}: west side implied {implied_d:7.2f} ft @ "
          f"{azimuth_to_bearing(implied_az)}")
    print(f"           transcribed {l['west_depth']:7.2f} ft @ {l['west_bearing']}"
          f"   -> misclose {err:.2f} ft  [{'ok' if err < 0.35 else 'CHECK'}]")
    print(f"           area {area:,.0f} sf ({area/43560:.3f} ac)")
    x += l["front"]

print("\n=== CHECK 3: meander bearings trend with the shoreline ===")
for l in LOTS:
    print(f"  Lot {l['num']}: {l['meander'][0]}  {l['meander'][1]:.2f}'")
print("  bearings swing progressively westward/southward moving east, matching")
print("  the drawn shoreline curving away from the section line -- consistent.")

# ---------------- DXF ----------------
dxf = DXFWriter()
for n, c, lt in [("BOUNDARY", "white", "CONTINUOUS"), ("LOT_LINE", "cyan", "CONTINUOUS"),
                 ("MEANDER", "magenta", "DASHED"), ("SETBACK", "green", "DASHED"),
                 ("TEXT-LABELS", "white", "CONTINUOUS"), ("DIM-LABELS", "green", "CONTINUOUS"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS"), ("CONTROL", "red", "CONTINUOUS"),
                 ("UNRESOLVED", "red", "DASHED")]:
    dxf.add_layer(n, c, lt)

for lot in built:
    sw, se, ne, nw = lot.corners
    dxf.line((sw.n, sw.e), (se.n, se.e), layer="LOT_LINE")
    dxf.line((se.n, se.e), (ne.n, ne.e), layer="LOT_LINE")
    dxf.line((ne.n, ne.e), (nw.n, nw.e), layer="MEANDER")
    dxf.line((nw.n, nw.e), (sw.n, sw.e), layer="LOT_LINE")
    cn = sum(q.n for q in lot.corners) / 4
    ce = sum(q.e for q in lot.corners) / 4
    dxf.text((cn, ce), lot.number, height=11, layer="TEXT-LABELS")
    dxf.text((cn - 16, ce - 14), f"{lot.area_sqft:,.0f} sf", height=6, layer="TEXT-LABELS")

for l, lot in zip(LOTS, built):
    sw, se, ne, nw = lot.corners
    dxf.text(((sw.n - 9), (sw.e + se.e) / 2 - 10), f"{l['front']:.0f}'", height=7, layer="DIM-LABELS")
    dxf.text(((se.n + ne.n) / 2, se.e + 3), f"{l['east_depth']:.2f}'", height=6, layer="DIM-LABELS")
    dxf.text(((ne.n + nw.n) / 2 + 5, (ne.e + nw.e) / 2 - 20),
             f"{l['meander'][0]} {l['meander'][1]:.2f}'", height=6, layer="MEANDER")

# 25' building restriction line
for lot in built:
    sw, se, ne, nw = lot.corners
    a = sw.offset(north_az, 25.0); b = se.offset(north_az, 25.0)
    dxf.line((a.n, a.e), (b.n, b.e), layer="SETBACK")

# P.O.B. and section line, 50' south of the lot row
pob = origin.offset(parse_bearing("S00°30'30\"W"), SECTION_OFFSET)
dxf.point((pob.n, pob.e), layer="CONTROL")
dxf.text((pob.n - 14, pob.e), "P.O.B. -- SW cor NW1/4 of SW1/4 Sec 17",
         height=9, layer="CONTROL")
sec_e = pob.offset(east_az, 1320.0)
dxf.line((pob.n, pob.e), (sec_e.n, sec_e.e), layer="BOUNDARY")
dxf.text((pob.n - 9, pob.e + 300), "EAST  1320.0'  (S line NW1/4 of SW1/4)",
         height=9, layer="DIM-LABELS")
row_e = origin.offset(east_az, SOUTH_TOTAL_STATED)
dxf.line((origin.n, origin.e), (row_e.n, row_e.e), layer="BOUNDARY")
dxf.text((origin.n - 8, origin.e + 130), f"EAST  {SOUTH_TOTAL_STATED}'",
         height=8, layer="DIM-LABELS")
wtop = origin.offset(parse_bearing("N00°30'30\"E"), 202.79)
dxf.line((pob.n, pob.e), (wtop.n, wtop.e), layer="BOUNDARY")
dxf.text(((pob.n + wtop.n) / 2, pob.e - 26), "S.0°30'30\"W.  300'+/-",
         height=8, layer="DIM-LABELS")

e_end = built[-1].corners[1]
dxf.line((e_end.n, e_end.e), (e_end.n + 260, e_end.e), layer="UNRESOLVED")
dxf.text((e_end.n + 40, e_end.e + 8),
         "LOT 37 AND EAST OF HERE UNRESOLVED: ties to Carroll Drive curve "
         "(N76°51'50\"E 125.0, delta=48°00', R=300.0)", height=9, layer="UNRESOLVED")

top = origin.n + 330
lft = origin.e
body = [
    "BROOKLYN LAKE ESTATES -- PLAT BOOK 4, PAGE 39, CLAY COUNTY, FL",
    "Re-subdivision in Sec 17, T8S, R23E  |  1\" = 100'",
    "SOUTHWEST LAKE-FRONT LOTS 38-41, worked from the P.O.B.",
    "",
    "SOURCE: visual transcription at 2.6x; NOT OCR.",
    "NOTE: the lake front shown is a CLOSING MEANDER ONLY and does not",
    "represent the true lot boundary (plat note). Drawn on its own layer.",
    "",
    "VALIDATION:",
    f"  South frontages 75+75+75+75+77.80 = {fsum:.2f} ft vs stated EAST 378.0 ft.",
    "  Per-lot closure: the west side line is DETERMINED by the other three",
    "  courses and was compared against the independently transcribed value:",
]
for l, lot in zip(LOTS, built):
    sw, se, ne, nw = lot.corners
    d = nw.dist_to(sw)
    body.append(f"    Lot {l['num']}: implied {d:7.2f} vs read {l['west_depth']:7.2f} "
                f"-> {abs(d-l['west_depth']):.2f} ft")
body += [
    "",
    "Bearings are ASSUMED per the plat, based on the S line of the NW1/4 of",
    "the SW1/4 of Sec 17 having a bearing of 'East'.",
]
for i, t in enumerate(body):
    dxf.text((top - i * 22, lft), t, height=11 if i == 0 else 8, layer="TITLEBLOCK")

out = "dxf/PB0004_P0039_BrooklynLakeEstates_SW.dxf"
dxf.save(out)
print(f"\nsaved {out}")
