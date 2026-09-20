"""
Lincoln Place -- PB 11 Pg 50, Duval County, FL (1926), Lincoln Development Co.
B.G. Moore & Marcel Mazeau, Engineers. Scale 1"=100'.

Values transcribed by VISION from the scanned sheet (Tesseract cannot read
this hand-lettered 200 DPI scan -- measured: 0 bearings parsed, and no
preprocessing variant rescued it). Every value below is flagged with its
confidence so a surveyor can check the originals.

The caption traverse does NOT close cleanly, and two independent checks
disagree about why. Rather than pick one, this DXF draws BOTH hypotheses on
separate layers so the discrepancy is visible and can be adjudicated against
the original document.
"""
import sys, math
sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing
from engine.dxf_writer import DXFWriter

# Caption as read off the sheet. Historic hyphenated format on the original:
#   "S-83°58'-W", "S-2°13'-W", "N-88°05'-E", "N-1°0'-E"
AS_READ = [
    ("S83°58'00\"W", 1368.12, "read: S-83°58'-W  1368.12"),
    ("S02°13'00\"W", 1323.00, "read: S-2°13'-W  1323.00"),
    ("N88°05'00\"E", 1395.44, "read: N-88°05'-E  1395.44"),
    ("N01°00'00\"E", 1320.00, "read: N-1°0'-E  1320.00"),
]

# Hypothesis A: bearings on courses 1 and 3 are transposed. Evidence: holding
# three courses and inversing the fourth, course 1 wants ~S88°08'W and course
# 3 wants ~N83°59'E -- i.e. each wants the other's value. Corrected area lands
# at 39.98 ac against a 40.00 ac nominal quarter-quarter (NE1/4 of NW1/4).
HYP_A = [
    ("S88°05'00\"W", 1368.12, "swapped bearing"),
    ("S02°13'00\"W", 1323.00, "as read"),
    ("N83°58'00\"E", 1395.44, "swapped bearing"),
    ("N01°00'00\"E", 1320.00, "as read"),
]

# Hypothesis B: A, plus course 2 distance 1323.00 -> 1423.00 (single-digit
# edit, 3->4). Closure improves 99.0 -> 11.7 ft, but area moves to 43.10 ac,
# AWAY from the 40 ac expectation. Closure and area disagree.
HYP_B = [
    ("S88°05'00\"W", 1368.12, "swapped bearing"),
    ("S02°13'00\"W", 1423.00, "distance 1323->1423 (UNVERIFIED)"),
    ("N83°58'00\"E", 1395.44, "swapped bearing"),
    ("N01°00'00\"E", 1320.00, "as read"),
]


def traverse(courses, origin=Point(0.0, 0.0)):
    p = origin
    pts = [p]
    for b, d, _ in courses:
        p = p.offset(parse_bearing(b), d)
        pts.append(p)
    return pts


def report(pts, courses):
    err = math.hypot(pts[-1].n - pts[0].n, pts[-1].e - pts[0].e)
    per = sum(d for _, d, _ in courses)
    a = 0.0
    for i in range(len(pts) - 1):
        a += pts[i].e * pts[i + 1].n - pts[i + 1].e * pts[i].n
    return err, per, abs(a) / 2 / 43560.0


dxf = DXFWriter()
dxf.add_layer("BOUNDARY_AS_READ", "white", "CONTINUOUS")
dxf.add_layer("HYP_A_SWAPPED", "cyan", "CONTINUOUS")
dxf.add_layer("HYP_B_SWAP_PLUS_DIST", "magenta", "DASHED")
dxf.add_layer("CLOSURE_GAP", "red", "DASHED")
dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")

sets = [
    ("BOUNDARY_AS_READ", AS_READ, "AS READ"),
    ("HYP_A_SWAPPED", HYP_A, "HYP A: bearings 1<->3 swapped"),
    ("HYP_B_SWAP_PLUS_DIST", HYP_B, "HYP B: A + course2 dist 1423"),
]

summary = []
for layer, courses, label in sets:
    pts = traverse(courses)
    err, per, ac = report(pts, courses)
    summary.append((label, err, per / err, ac))
    for i in range(len(pts) - 1):
        dxf.line((pts[i].n, pts[i].e), (pts[i + 1].n, pts[i + 1].e), layer=layer)
        mn = (pts[i].n + pts[i + 1].n) / 2
        me = (pts[i].e + pts[i + 1].e) / 2
        b, d, note = courses[i]
        dxf.text((mn, me), f"{b} {d:.2f}'", height=12, layer="TEXT-LABELS")
    # closure gap
    dxf.line((pts[-1].n, pts[-1].e), (pts[0].n, pts[0].e), layer="CLOSURE_GAP")
    dxf.text((pts[-1].n, pts[-1].e), f"{label}: misclose {err:.2f}'",
             height=14, layer="CLOSURE_GAP")

base = traverse(AS_READ)
top = max(p.n for p in base) + 150
left = min(p.e for p in base)
L = [
    "LINCOLN PLACE -- PLAT BOOK 11, PAGE 50, DUVAL COUNTY, FL (1926)",
    "NE 1/4 of NW 1/4, Section 10, Township 2 South, Range 26 East",
    "Lincoln Development Co.  |  B.G. Moore & Marcel Mazeau, Engineers",
    "",
    "SOURCE: 200 DPI scan, hand-lettered. Tesseract OCR parsed 0 bearings;",
    "no preprocessing variant succeeded. Values transcribed by visual read",
    "and MUST be verified against the original document.",
    "",
    "CLOSURE ANALYSIS -- TWO CHECKS DISAGREE:",
]
for label, err, prec, ac in summary:
    L.append(f"  {label}: misclose {err:.2f} ft (1:{prec:.0f}), area {ac:.2f} ac")
L += [
    "",
    "  Nominal quarter-quarter section area = 40.00 ac.",
    "  HYP A matches AREA (39.98 ac) but not closure (99.0 ft).",
    "  HYP B matches CLOSURE (11.7 ft) but not area (43.10 ac).",
    "  -> UNRESOLVED. Do not treat either as authoritative.",
    "  -> 1926 plats frequently do not close; a misclose is NOT by itself",
    "     proof of a transcription error.",
]
for i, line in enumerate(L):
    dxf.text((top - i * 45, left), line, height=16 if i == 0 else 12,
             layer="TITLEBLOCK")

out = "dxf/PB0011_P0050_LincolnPlace_closure_hypotheses.dxf"
dxf.save(out)
print("saved", out)
for label, err, prec, ac in summary:
    print(f"  {label:32s} misclose {err:7.2f} ft  1:{prec:<7.0f} area {ac:6.2f} ac")
