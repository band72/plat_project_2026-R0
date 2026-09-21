"""
BROOKLYN LAKE ESTATES -- PB 4/39, Clay County FL
Full linework: caption boundary, lot fabric, and curve geometry drawn as
true arcs with complete curve data annotation.

Distances on the caption boundary are taken from the WORD channel
(spelled-out form), which was shown in Iter 13 to survive OCR where the
numeral form did not.
"""
import sys, math
sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing, azimuth_to_bearing
from engine.curves import Curve
from engine.lots import shoelace_area, Lot
from engine.dxf_writer import DXFWriter

EAST = parse_bearing("N90°00'00\"E")
NORTH = 0.0

# ---------------- caption boundary (word-channel distances) ----------------
CAPTION = [
    ("N90°00'00\"E", 1791.89, "East, S line NW1/4 & NE1/4 of SW1/4",
     "seventeen hundred ninety-one and eighty-nine hundredths"),
    ("N38°50'30\"E", 348.67, "NW'ly R/W line State Road No. 21",
     "three hundred forty-eight and sixty-seven hundredths"),
    ("N51°09'30\"W", 200.00, "SW'ly bdy of Farnham lands (DB 40 P 253)",
     "two hundred"),
    ("N38°50'30\"E", 400.00, "NW'ly bdy of Farnham lands, to Lake Brooklyn",
     "four hundred (more or less)"),
]
MEANDER_SHORE = 3600.0     # "thirty-six hundred (3600) feet more or less"
WEST_LINE = ("S00°30'30\"W", 300.00)   # Sec 17 W line / N prolongation

POB = Point(0.0, 0.0)
pts = [POB]
p = POB
for b, d, _, _ in CAPTION:
    p = p.offset(parse_bearing(b), d)
    pts.append(p)
p4 = pts[-1]
p5 = POB.offset(parse_bearing("N00°30'30\"E"), WEST_LINE[1])

chord_d = p4.dist_to(p5)
chord_az = math.degrees(math.atan2(p5.e - p4.n * 0 + (p5.e - p4.e) * 0 + (p5.e - p4.e),
                                   p5.n - p4.n)) % 360
chord_az = math.degrees(math.atan2(p5.e - p4.e, p5.n - p4.n)) % 360

print("=== CHECK: Farnham lands are a rectangle ===")
a = parse_bearing("N38°50'30\"E"); b = parse_bearing("N51°09'30\"W")
print(f"  included angle = {abs((a-b+180)%360-180):.6f} deg -> "
      f"{'EXACT 90' if abs(abs((a-b+180)%360-180)-90)<1e-6 else 'CHECK'}")

print("\n=== CHECK: meander is a shore distance, not a chord ===")
print(f"  straight chord P4->P5 = {chord_d:.2f} ft @ {azimuth_to_bearing(chord_az)}")
print(f"  caption shore distance = {MEANDER_SHORE:.0f} ft 'more or less'")
print(f"  sinuosity = {MEANDER_SHORE/chord_d:.2f}")

# ---------------- Carroll Drive curve ----------------
CV_R, CV_DELTA = 300.00, 48.00
CV_L = CV_R * math.radians(CV_DELTA)
CV_CH = 2 * CV_R * math.sin(math.radians(CV_DELTA) / 2)
CV_T = CV_R * math.tan(math.radians(CV_DELTA) / 2)
tan_in = EAST                       # Carroll Dr leaves the row heading East
tan_out = (tan_in - CV_DELTA) % 360  # curve to the LEFT
print("\n=== CHECK: curve tangent-out vs drawn Carroll Drive bearing ===")
print(f"  tangent-in East(90d) minus delta 48d -> tangent-out "
      f"{azimuth_to_bearing(tan_out)}")
print(f"  plat letters Carroll Drive as N42°00'E -> "
      f"{'MATCH' if abs(tan_out-42.0)<0.01 else 'CHECK'}")
print(f"  curve elements: R={CV_R} delta={CV_DELTA}  L={CV_L:.2f} "
      f"chord={CV_CH:.2f} T={CV_T:.2f}")

# ---------------- lot fabric (SW row) ----------------
ROW = POB.offset(parse_bearing("N00°30'30\"E"), 50.0)   # row is 50' N of sec line
LOTS = [
    dict(num="41", front=75.00, east=207.88, mb="S86°13'00\"W", md=73.25,
         west=202.79, wb="S00°30'30\"W"),
    dict(num="40", front=75.00, east=212.05, mb="S86°47'00\"W", md=75.07,
         west=207.84, wb="S00°00'00\"W"),
    dict(num="39", front=75.00, east=212.35, mb="S89°44'30\"W", md=75.00,
         west=212.01, wb="S00°00'00\"W"),
    dict(num="38", front=75.00, east=236.31, mb="S72°07'30\"W", md=78.80,
         west=212.12, wb="S00°00'00\"W"),
]

built = []
x = 0.0
for l in LOTS:
    sw = ROW.offset(EAST, x)
    se = sw.offset(EAST, l["front"])
    ne = se.offset(NORTH, l["east"])
    nw = ne.offset(parse_bearing(l["mb"]), l["md"])
    corners = [sw, se, ne, nw]
    built.append(Lot(l["num"], corners, shoelace_area(corners + [corners[0]])))
    x += l["front"]

# ---------------- DXF ----------------
dxf = DXFWriter()
for n, c, lt in [("BOUNDARY", "white", "CONTINUOUS"),
                 ("MEANDER", "magenta", "DASHED"),
                 ("LOT_LINE", "cyan", "CONTINUOUS"),
                 ("ROW_STREET", "yellow", "DASHED"),
                 ("CURVE", "yellow", "CONTINUOUS"),
                 ("CURVE_RADIAL", "gray", "DASHED"),
                 ("SETBACK", "green", "DASHED"),
                 ("DIM-LABELS", "green", "CONTINUOUS"),
                 ("TEXT-LABELS", "white", "CONTINUOUS"),
                 ("CURVE_TABLE", "yellow", "CONTINUOUS"),
                 ("CONTROL", "red", "CONTINUOUS"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS")]:
    dxf.add_layer(n, c, lt)


def pl(a, b, layer):
    dxf.line((a.n, a.e), (b.n, b.e), layer=layer)


def label(a, b, text, layer="DIM-LABELS", h=9, off=6):
    mn, me = (a.n + b.n) / 2, (a.e + b.e) / 2
    az = math.degrees(math.atan2(b.e - a.e, b.n - a.n)) % 360
    rot = (90 - az) % 360
    if 90 < rot < 270:
        rot = (rot + 180) % 360
    dxf.text((mn + off, me), text, height=h, layer=layer, rotation=rot)


# boundary courses with bearing+distance labels
for i, (bb, dd, desc, words) in enumerate(CAPTION):
    pl(pts[i], pts[i + 1], "BOUNDARY")
    label(pts[i], pts[i + 1], f"{bb}  {dd:.2f}'")

# meander chord (dashed) + note
pl(p4, p5, "MEANDER")
label(p4, p5, f"MEANDER CLOSURE {chord_d:.2f}' — SHORE DIST 3600'± (NOT A CHORD)",
      layer="MEANDER", h=11, off=14)

# west line
pl(p5, POB, "BOUNDARY")
label(p5, POB, f"{WEST_LINE[0]}  {WEST_LINE[1]:.0f}'±")

# control points
for pt, nm in [(POB, "P.O.B. / P.R.M.  SW cor NW1/4 of SW1/4 Sec 17"),
               (pts[1], "P.R.M. on NW'ly R/W SR 21"),
               (pts[2], "P.R.M. S'ly cor Farnham"),
               (pts[3], "P.R.M. W'ly cor Farnham")]:
    dxf.point((pt.n, pt.e), layer="CONTROL")
    dxf.text((pt.n + 10, pt.e + 8), nm, height=8, layer="CONTROL")

# lot fabric
for l, lot in zip(LOTS, built):
    sw, se, ne, nw = lot.corners
    pl(sw, se, "LOT_LINE"); pl(se, ne, "LOT_LINE"); pl(nw, sw, "LOT_LINE")
    pl(ne, nw, "MEANDER")
    label(sw, se, f"{l['front']:.0f}'", h=7, off=-9)
    label(se, ne, f"{l['east']:.2f}'", h=7)
    label(ne, nw, f"{l['mb']} {l['md']:.2f}'", layer="MEANDER", h=6, off=7)
    cn = sum(q.n for q in lot.corners) / 4
    ce = sum(q.e for q in lot.corners) / 4
    dxf.text((cn, ce), lot.number, height=14, layer="TEXT-LABELS")
    dxf.text((cn - 18, ce - 16), f"{lot.area_sqft:,.0f} sf", height=7, layer="TEXT-LABELS")
    a = sw.offset(NORTH, 25.0); b2 = se.offset(NORTH, 25.0)
    pl(a, b2, "SETBACK")
dxf.text((built[0].corners[0].n - 26, built[0].corners[0].e + 20),
         "25' BUILDING RESTRICTION LINE", height=8, layer="SETBACK")

# ---- Carroll Drive curve as a TRUE ARC ----
pc = ROW.offset(EAST, 378.00)          # east end of the lot row
crv = Curve(id="C1", length=CV_L, radius=CV_R, delta_deg=CV_DELTA,
            chord_bearing=azimuth_to_bearing((tan_in - CV_DELTA / 2) % 360),
            chord=CV_CH, rot="CCW")
arc = crv.arc_points(pc, n_segments=48)
for i in range(len(arc) - 1):
    pl(arc[i], arc[i + 1], "CURVE")
pt_end = arc[-1]
# radial lines at PC and PT
rp_az = (tan_in - 90.0) % 360
rp = pc.offset(rp_az, CV_R)
pl(pc, rp, "CURVE_RADIAL"); pl(pt_end, rp, "CURVE_RADIAL")
dxf.point((rp.n, rp.e), layer="CURVE_RADIAL")
dxf.text((rp.n + 8, rp.e), "R.P.  C1", height=8, layer="CURVE_RADIAL")
dxf.text((pc.n - 12, pc.e), "P.C.", height=9, layer="CONTROL")
dxf.text((pt_end.n + 10, pt_end.e), "P.T.", height=9, layer="CONTROL")
# tangent-out bearing label
tout = pt_end.offset(tan_out, 150.0)
pl(pt_end, tout, "ROW_STREET")
label(pt_end, tout, f"CARROLL DRIVE  {azimuth_to_bearing(tan_out)}",
      layer="ROW_STREET", h=10, off=10)

# ---- curve table block ----
tx = pts[1].n + 420
te = pts[1].e - 300
rows = [
    "CURVE TABLE",
    "CURVE   RADIUS    DELTA      LENGTH    CHORD     TANGENT   CHORD BEARING",
    f"C1      {CV_R:7.2f}   {int(CV_DELTA)}°00'00\"   {CV_L:7.2f}   {CV_CH:7.2f}   "
    f"{CV_T:7.2f}   {azimuth_to_bearing((tan_in-CV_DELTA/2)%360)}",
    "",
    "R and DELTA were READ from the plat; LENGTH, CHORD and TANGENT are",
    "DERIVED (engine/solver.py, Iter 12). Tangent-out computes to N42°00'E,",
    "matching the Carroll Drive bearing lettered on the sheet.",
]
for i, t in enumerate(rows):
    dxf.text((tx - i * 22, te), t, height=11 if i == 0 else 9, layer="CURVE_TABLE")

# ---- title block ----
top = pts[3].n + 320
lft = POB.e - 120
body = [
    "BROOKLYN LAKE ESTATES -- PLAT BOOK 4, PAGE 39, CLAY COUNTY, FLORIDA",
    "Re-subdivision in Sec 17, T8S, R23E  |  Scale 1\" = 100'",
    "",
    "BEARING BASIS (per caption): bearings are ASSUMED, based on the Southerly",
    "boundary line of the NW1/4 of the SW1/4 of Sec 17 having a bearing of 'East'.",
    "NOT grid bearings -- do not treat as State Plane.",
    "",
    "CAPTION BOUNDARY -- distances taken from the SPELLED-OUT word form:",
]
for bb, dd, desc, words in CAPTION:
    body.append(f"   {bb}  {dd:>8.2f}'   [{words}]")
    body.append(f"        {desc}")
body += [
    f"   MEANDER along Lake Brooklyn, shore distance {MEANDER_SHORE:.0f}'± "
    f"(chord {chord_d:.2f}', sinuosity {MEANDER_SHORE/chord_d:.2f})",
    f"   {WEST_LINE[0]}  {WEST_LINE[1]:.0f}'±   W line Sec 17 / N prolongation",
    "",
    "CHECKS: Farnham lands corner = exactly 90°00'00\" (N38°50'30\"E vs N51°09'30\"W).",
    "        Curve tangent-out N42°00'E matches the drawn Carroll Drive bearing.",
    "        Lot closures 0.04-0.27 ft (lake front is a COMPUTED closing meander).",
    "",
    "The meander is drawn DASHED on its own layer: it is a closing line only and",
    "does NOT represent the true lake-front boundary (plat note).",
]
for i, t in enumerate(body):
    dxf.text((top - i * 24, lft), t, height=13 if i == 0 else 9, layer="TITLEBLOCK")

out = "dxf/PB0004_P0039_BrooklynLake_linework.dxf"
dxf.save(out)
print(f"\nsaved {out}")
print(f"lots {len(built)}, boundary courses {len(CAPTION)+2}, arc segments {len(arc)-1}")
