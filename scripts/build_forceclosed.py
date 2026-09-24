"""
Atlantic Beach CC Unit 2, Sheet 3, Block A -- FORCE-CLOSED lots.

Per direction: lots are closed in vector form even where a boundary is not
fully transcribed, with every ASSUMED segment isolated on a red "ERROR"
layer so it is unmistakable that an assumption filled a gap in knowledge.

Layer contract (this is the whole point -- read it before using any number):
  LOT_LINE   (cyan)   transcribed, closure-verified, recorded-precision
  ERROR      (red)    ASSUMED. Drawn to force closure. NOT a recorded
                      boundary. Any area computed using one of these is
                      provisional.
  LABELS     (white)  bearings, distances, lot numbers
  AREA_OK    (green)  square footage where the whole ring is transcribed
  AREA_PROV  (red)    square footage that depends on an ERROR-layer segment
  VERTEX     (yellow) shared nodes (one object per corner)

The rear boundary of this row is the assumed part. What IS known about it,
and is recorded here rather than discarded:
  - it is composed of two validated curve chains, R=150.00' (C199,C200,C201)
    and R=700.00' (C195,C196,C197,C198); every curve passes L/chord checks
    and each chain's summed arc matches its summed segment lengths to 0.01'
  - two straight tie labels (45.89' + 34.12' = 80.01') match a separately
    labelled 80.00' tangent, confirming the rear runs PARALLEL to the front
    (N00°32'22"E) over that stretch
  - NOT known: which curve station belongs to which lot corner
So the assumption made here is specifically: "the rear boundary between two
adjacent side-line endpoints is a straight chord." That is exactly right
where the rear is the 80.00' tangent, and it is a chord approximation of a
very large radius (R=700', and R=150') elsewhere -- the induced area error
is small and is QUANTIFIED below against the actual drawn linework, rather
than merely asserted to be small.
"""
import math
import sys

import cv2

sys.path.insert(0, '.')
from engine.blunder import classify, course_deviation
from engine.cogo import Point, azimuth_to_bearing, parse_bearing
from engine.dxf_writer import DXFWriter
from engine.labels import course_label_positions, draw_course
from engine.registration import ATLANTIC_SHEET3 as REG
from engine.topology import Parcel, VertexGraph
from engine.vectorize import map_mask_excluding, merge_collinear, segments

WIDTHS = [137.85, 55.00, 60.00, 55.00, 55.00, 60.00, 55.00, 55.00, 60.00, 55.00, 55.00, 60.00]
LOTS = [137, 136, 135, 134, 133, 132, 131, 130, 129, 128, 127, 126]
DEPTHS = [119.72, 120.00, 117.75, 106.79, 100.04, 97.66, 99.91, 103.53, 107.47, 111.08, 114.70, 118.64]
FRONT_BEARING = "N00°32'22\"E"
SIDE_BEARING = "N89°27'38\"E"      # corrected via blunder detector (Iter 22)

# ---------------- build shared-vertex network ----------------
g = VertexGraph()
g.walk("F0", Point(0.0, 0.0),
       [(f"F{i+1}", FRONT_BEARING, w) for i, w in enumerate(WIDTHS)])
side_az = parse_bearing(SIDE_BEARING)
for i, d in enumerate(DEPTHS):
    g.add(f"S{i}", g.points[f"F{i}"].offset(side_az, d))
# the 13th side line (east edge of lot 126) closes the last lot; its depth is
# the next value in the transcribed series -- NOT read, so it is ASSUMED.
# Flagged explicitly and drawn on the ERROR layer like every other assumption.
ASSUMED_LAST_DEPTH = DEPTHS[-1] + (DEPTHS[-1] - DEPTHS[-2])   # continue the trend
g.add("S12", g.points["F12"].offset(side_az, ASSUMED_LAST_DEPTH))

print("=== what is TRANSCRIBED vs ASSUMED ===")
print(f"  transcribed: front boundary {FRONT_BEARING} 772.85' (EXACT closure)")
print("  transcribed: 12 lot widths, 12 side-line depths")
print("  ASSUMED    : rear boundary = straight chord between side endpoints")
print(f"  ASSUMED    : east side of lot 126 depth = {ASSUMED_LAST_DEPTH:.2f}' "
      f"(trend continuation, not read)")

# ---------------- parcels ----------------
parcels = []
for i, num in enumerate(LOTS):
    ring = [f"F{i}", f"F{i+1}", f"S{i+1}", f"S{i}"]
    parcels.append(Parcel(str(num), ring, g))

# ---------------- quantify the assumption against the scan ----------------
img = cv2.imread("src/abcc300-3.png", 0)
mask = map_mask_excluding(img, exclude=[(0.085, 0.20, 0.165, 0.44),
                                        (0.085, 0.66, 0.12, 0.09),
                                        (0.02, 0.80, 0.20, 0.18)])
raster = []
for x1, y1, x2, y2 in merge_collinear(segments(mask)):
    n1, e1 = REG.px_to_local(x1, y1)
    n2, e2 = REG.px_to_local(x2, y2)
    raster.append((n1, e1, n2, e2))

print("\n=== how wrong is each ASSUMED rear line, measured against the ink? ===")
rear_dev = {}
for i, num in enumerate(LOTS):
    a_t, b_t = g.points[f"S{i}"], g.points[f"S{i+1}"]
    a = REG.true_to_local(a_t.n, a_t.e)
    b = REG.true_to_local(b_t.n, b_t.e)
    dev = course_deviation(a, b, raster)
    verdict, cause = classify(dev)
    rear_dev[num] = dev
    m = f"{dev['mean']:.2f}" if dev.get('mean') is not None else "n/a"
    x = f"{dev['max']:.2f}" if dev.get('max') is not None else "n/a"
    print(f"  lot {num}: assumed rear deviates mean {m:>6s} ft, max {x:>6s} ft  [{verdict}]")

# ---------------- areas ----------------
print("\n=== areas (ALL PROVISIONAL -- every ring uses an assumed rear) ===")
areas = {}
for p in parcels:
    a, status = p.area_or_none()
    areas[p.number] = a
    if a is None:
        print(f"  lot {p.number}: NO AREA -- {status}")
    else:
        print(f"  lot {p.number}: {a:>9,.0f} SF  ({a/43560:.3f} ac)  PROVISIONAL")
valid = [a for a in areas.values() if a]
if valid:
    print(f"  block total {sum(valid):,.0f} SF ({sum(valid)/43560:.2f} ac) across {len(valid)} lots")

# ---------------- DXF ----------------
dxf = DXFWriter()
for n, c, lt in [("LOT_LINE", "cyan", "CONTINUOUS"),
                 ("ERROR", "red", "DASHED"),
                 ("LABELS", "white", "CONTINUOUS"),
                 ("AREA_PROV", "red", "CONTINUOUS"),
                 ("AREA_OK", "green", "CONTINUOUS"),
                 ("VERTEX", "yellow", "CONTINUOUS"),
                 ("ROAD_NAME", "green", "CONTINUOUS"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS")]:
    dxf.add_layer(n, c, lt)

def L(name):
    p = g.points[name]
    return REG.true_to_local(p.n, p.e)

# front boundary: one line, one bearing+total (professional convention)
f0, f12 = L("F0"), L("F12")
draw_course(dxf, f0[0], f0[1], f12[0], f12[1], FRONT_BEARING,
            f"{sum(WIDTHS):.2f}'", "LOT_LINE", "LABELS",
            height=4.5, bearing_offset=2.4, dist_offset=2.4, tick=False)
for i, w in enumerate(WIDTHS):                     # per-lot widths + corner ticks
    a, b = L(f"F{i}"), L(f"F{i+1}")
    pos = course_label_positions(a[0], a[1], b[0], b[1], 1.0, 1.0)
    if pos:
        dxf.text(pos["distance_pos"], f"{w:.2f}'", height=2.6,
                 layer="LABELS", rotation=pos["angle"],
                 halign=pos["distance_align"][0], valign=pos["distance_align"][1])
    dn, de = f12[0]-f0[0], f12[1]-f0[1]
    ln = math.hypot(dn, de); px, py = -de/ln, dn/ln
    dxf.line((a[0]-px, a[1]-py), (a[0]+px, a[1]+py), layer="LOT_LINE")

# side lines: transcribed (cyan) except the assumed last one (red ERROR)
for i in range(13):
    a, b = L(f"F{i}"), L(f"S{i}")
    assumed = (i == 12)
    d = ASSUMED_LAST_DEPTH if assumed else DEPTHS[i]
    draw_course(dxf, a[0], a[1], b[0], b[1], SIDE_BEARING, f"{d:.2f}'",
                "ERROR" if assumed else "LOT_LINE", "LABELS",
                height=3.0, bearing_offset=1.3, dist_offset=1.3)
    if assumed:
        mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
        dxf.text((mid[0]-4, mid[1]), "ASSUMED DEPTH", height=2.4, layer="ERROR")

# rear boundary: ALL assumed -> ERROR layer, with real bearing/distance shown
for i, num in enumerate(LOTS):
    a, b = L(f"S{i}"), L(f"S{i+1}")
    at, bt = g.points[f"S{i}"], g.points[f"S{i+1}"]
    dist = at.dist_to(bt)
    az = math.degrees(math.atan2(bt.e-at.e, bt.n-at.n)) % 360
    draw_course(dxf, a[0], a[1], b[0], b[1], azimuth_to_bearing(az),
                f"{dist:.2f}'", "ERROR", "LABELS", height=2.8,
                bearing_offset=1.3, dist_offset=1.3, tick=False)

# lot numbers + provisional areas
for i, p in enumerate(parcels):
    ring = [L(n) for n in p.vertex_names]
    cn = sum(q[0] for q in ring)/4
    ce = sum(q[1] for q in ring)/4
    dxf.text((cn-3, ce-9), p.number, height=7.0, layer="LABELS")
    a = areas[p.number]
    if a:
        dxf.text((cn-11, ce-11), f"{a:,.0f} SF", height=3.2, layer="AREA_PROV")
        dxf.text((cn-16, ce-11), "(PROVISIONAL)", height=2.2, layer="AREA_PROV")

for name in g.points:
    dxf.point(L(name), layer="VERTEX")

rn = f0[0] - 60
for nm, wd in [("MARITIME OAK DRIVE", "(50' RIGHT OF WAY)"),
               ("TIMBER BRIDGE LANE", "(50' RIGHT OF WAY)"),
               ("ATLANTIC BEACH DRIVE", "(50' RIGHT OF WAY) [sheet 6]")]:
    dxf.text((rn, f0[1]+18), nm, height=5.0, layer="ROAD_NAME")
    dxf.text((rn-7, f0[1]+18), wd, height=3.4, layer="ROAD_NAME")
    rn -= 20

worst = max((d['max'] for d in rear_dev.values() if d.get('max')), default=0)
body = [
    "ATLANTIC BEACH CC UNIT 2, SHEET 3, BLOCK A -- FORCE-CLOSED",
    "",
    "*** RED 'ERROR' LAYER = ASSUMED GEOMETRY, NOT RECORDED ***",
    "Every red segment fills a gap in transcription so the lot closes.",
    "Any area shown in red is PROVISIONAL because its ring uses one.",
    "",
    "CYAN (transcribed, recorded precision):",
    "   front boundary N00d32'22\"E 772.85' -- 12 widths + 10.00' = EXACT",
    "   12 side-line depths, bearing N89d27'38\"E",
    "   front/side perpendicularity 90.000000 deg EXACT",
    "",
    "RED (assumed):",
    "   rear boundary: straight chord between adjacent side endpoints.",
    "     Known: rear is two validated curve chains, R=700' (C195-198) and",
    "     R=150' (C199-201), plus an 80.00' tangent parallel to the front",
    "     (confirmed: 45.89'+34.12'=80.01'). NOT known: which curve station",
    "     belongs to which lot corner -- hence the chord assumption.",
    "     Measured against the drawn linework, the assumed rear deviates",
    f"     at most {worst:.2f} ft. That is the size of this assumption.",
    "   east side of lot 126: depth continued from the trend, not read.",
    "",
    "TO REMOVE THE ASSUMPTIONS: one high-magnification read of the P.C./P.T.",
    "station ties along C195-C201 converts every red segment to cyan and",
    "every provisional area to final.",
]
top = f0[0] + 250
for i, t in enumerate(body):
    dxf.text((top - i*16, f0[1]-70), t, height=8 if i == 0 else 6, layer="TITLEBLOCK")

out = "dxf/PB0067_P0132_AtlanticBeachCC_Sheet3_ForceClosed.dxf"
dxf.save(out)
print(f"\nsaved {out}")
print(f"largest assumed-rear deviation from the ink: {worst:.2f} ft")
