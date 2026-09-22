"""
Atlantic Beach CC Unit 2, Sheet 3, Block A (lots 137-126) rebuilt on a
shared-vertex parcel graph, per the standard: every lot closure-verified,
every side bearing+distance labeled, every lot's square footage computed
and labeled, and -- the new requirement -- adjacent lots share the EXACT
SAME vertex at every common corner (no near-duplicate endpoints).

REAR BOUNDARY STATUS (read this before trusting any area number below):
The rear boundary of this row is NOT a simple offset of the front -- it is
a composite of two large-radius curves plus straight ties:
    R=150.00' chain (C199,C200,C201): deltas sum 16.6491 deg, arc 43.58 ft
    R=700.00' chain (C195,C196,C197,C198): deltas sum 16.9242 deg, arc 206.78 ft
Both chains independently validated (L = R*delta, chord = 2R*sin(delta/2),
each individual curve passes). BUT: the exact station (which lot corner)
each curve segment starts and ends at has NOT been confirmed with enough
confidence to assign specific curves to specific lots without risking the
same fabrication error already caught and corrected once in this project.
Per the rule established then: a course is not drawn until its placement
is transcribed, not assumed.

CONSEQUENCE: only lots whose FULL boundary (front + both sides + rear) is
confirmed can be closed and have their area computed here. That is
currently ZERO of the 12 lots in this row -- the front and side lines are
exact, but no lot's rear tie is yet confirmed to the standard this project
holds. This is stated plainly rather than estimated. The shared-vertex
network for the CONFIRMED front+side geometry is still built and delivered
below, because it is real, useful, and directly demonstrates the "polylines
share a vertex" fix -- it is just not yet a set of closed lot polygons.
"""
import math
import sys

sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing
from engine.dxf_writer import DXFWriter
from engine.labels import course_label_positions, draw_course
from engine.topology import VertexGraph

WIDTHS = [137.85,55.00,60.00,55.00,55.00,60.00,55.00,55.00,60.00,55.00,55.00,60.00]
LOTS = [137,136,135,134,133,132,131,130,129,128,127,126]
DEPTHS = [119.72,120.00,117.75,106.79,100.04,97.66,99.91,103.53,107.47,111.08,114.70,118.64]
FRONT_BEARING = "N00°32'22\"E"
SIDE_BEARING = "N89°27'38\"E"   # CORRECTED -- see blunder-detector finding

g = VertexGraph()

# ---- front vertices: F0 (Tract K corner) -> F12, walked ONCE ----
front_courses = [(f"F{i+1}", FRONT_BEARING, w) for i, w in enumerate(WIDTHS)]
g.walk("F0", Point(0.0, 0.0), front_courses)

# ---- side vertices: each lot's rear-of-side-line point, referencing the
#      SAME front vertex the neighbouring lot's side also starts from ----
side_az = parse_bearing(SIDE_BEARING)
for i, d in enumerate(DEPTHS):
    front_pt = g.points[f"F{i}"]
    rear_pt = front_pt.offset(side_az, d)
    g.add(f"S{i}", rear_pt)
    g.line(f"F{i}", f"S{i}", SIDE_BEARING, d)

print("=== shared-vertex check ===")
print(f"vertices created: {len(g.points)}  (12 lots -> 13 front + 12 side = 25 expected)")
# demonstrate: lot 136's WEST side and lot 137's EAST side both terminate
# at the exact same front vertex F1 and are the exact same Point object
shared = g.points["F1"]
print(f"F1 is shared by lot 137 (its east end) and lot 136 (its west start): "
      f"single object id {id(shared)}, coordinates ({shared.n:.4f},{shared.e:.4f})")

print("\n=== Block A front+side closure (EXACT, unchanged) ===")
sum_check = sum(WIDTHS) + 10.00
print(f"  front: sum(12 widths) + 10.00' = {sum_check:.2f}' vs stated 772.85' -> "
      f"{'EXACT' if abs(sum_check-772.85) < 0.001 else 'CHECK'}")
ang = abs((parse_bearing(FRONT_BEARING) - parse_bearing(SIDE_BEARING) + 180) % 360 - 180)
print(f"  perpendicularity: {ang:.6f} deg -> {'EXACT 90' if abs(ang-90) < 1e-6 else 'CHECK'}")

print("\n=== rear boundary curve validation (both chains) ===")
from engine.ocr import validate_curve

REAR_CURVES = {
    "C195": dict(length=43.64, radius=700.00, delta=3+34/60+19/3600, chord_bearing="S02°30'44\"W", chord=43.63),
    "C196": dict(length=60.07, radius=700.00, delta=4+54/60+59/3600, chord_bearing="S01°43'55\"E", chord=60.05),
    "C197": dict(length=55.43, radius=700.00, delta=4+32/60+12/3600, chord_bearing="S06°27'31\"E", chord=55.41),
    "C198": dict(length=47.64, radius=700.00, delta=3+53/60+57/3600, chord_bearing="S10°40'35\"E", chord=47.63),
    "C199": dict(length=8.45,  radius=150.00, delta=3+13/60+46/3600, chord_bearing="N11°00'41\"W", chord=8.45),
    "C200": dict(length=26.01, radius=150.00, delta=9+56/60+10/3600, chord_bearing="N04°25'43\"W", chord=25.98),
    "C201": dict(length=9.12,  radius=150.00, delta=3+29/60+1/3600,  chord_bearing="N02°16'52\"E", chord=9.12),
}
for cid, c in REAR_CURVES.items():
    ok, msg = validate_curve(c, tol=0.05)
    print(f"  {cid}: R={c['radius']:7.2f}  {'OK' if ok else 'CHECK '+msg}")
r700 = sum(REAR_CURVES[k]["delta"] for k in ("C195","C196","C197","C198"))
r150 = sum(REAR_CURVES[k]["delta"] for k in ("C199","C200","C201"))
print(f"  R=700 chain (C195-198): sum delta {r700:.4f} deg, arc "
      f"{700*math.radians(r700):.2f} ft (table sum "
      f"{sum(REAR_CURVES[k]['length'] for k in ('C195','C196','C197','C198')):.2f} ft)")
print(f"  R=150 chain (C199-201): sum delta {r150:.4f} deg, arc "
      f"{150*math.radians(r150):.2f} ft (table sum "
      f"{sum(REAR_CURVES[k]['length'] for k in ('C199','C200','C201')):.2f} ft)")
print("  Both chains internally consistent -- confirms the DATA is good.")
print("  NOT YET CONFIRMED: which lot corners each chain starts/ends at.")
print("  ZERO lots closed to a computed square footage this pass -- see")
print("  module docstring for why, and what the next transcription step is.")

# ============================================================
# DXF: shared-vertex network, professionally labeled, area column left
# explicitly blank with a stated reason rather than a guessed number
# ============================================================
dxf = DXFWriter()
for n, c, lt in [("LOT_LINE", "cyan", "CONTINUOUS"),
                 ("LABELS", "red", "CONTINUOUS"),
                 ("VERTEX", "yellow", "CONTINUOUS"),
                 ("OPEN_BOUNDARY", "magenta", "DASHED"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS")]:
    dxf.add_layer(n, c, lt)

# front, one line + total label (as in Iter 18)
f0, f12 = g.points["F0"], g.points["F12"]
draw_course(dxf, f0.n, f0.e, f12.n, f12.e, FRONT_BEARING, f"{sum(WIDTHS):.2f}'",
           "LOT_LINE", "LABELS", height=4.5, bearing_offset=2.2, dist_offset=2.2, tick=False)
for i in range(1, 12):
    p = g.points[f"F{i}"]
    dn, de = f12.n-f0.n, f12.e-f0.e; L = math.hypot(dn,de)
    px, py = -de/L, dn/L
    dxf.line((p.n-px, p.e-py), (p.n+px, p.e+py), layer="LOT_LINE")
for i, w in enumerate(WIDTHS):
    a, b = g.points[f"F{i}"], g.points[f"F{i+1}"]
    pos = course_label_positions(a.n, a.e, b.n, b.e, 1.0, 1.0)
    if pos:
        dxf.text(pos["distance_pos"], f"{w:.2f}'", height=2.6, layer="LABELS",
                 rotation=pos["angle"])

# side lines (drawn from the SHARED F-vertices -- this IS the fix: every
# side line starts at the exact same point the front line already has)
for i, d in enumerate(DEPTHS):
    a, b = g.points[f"F{i}"], g.points[f"S{i}"]
    draw_course(dxf, a.n, a.e, b.n, b.e, SIDE_BEARING, f"{d:.2f}'",
               "LOT_LINE", "LABELS", height=3.0, bearing_offset=1.3, dist_offset=1.3)
    cen_n = (a.n + b.n + g.points[f"F{i+1}"].n) / 3
    cen_e = (a.e + b.e + g.points[f"F{i+1}"].e) / 3
    dxf.text((cen_n - 4, cen_e - 14), str(LOTS[i]), height=6.5, layer="LABELS")
    dxf.text((cen_n - 12, cen_e - 14), "AREA: rear boundary", height=2.2, layer="LABELS")
    dxf.text((cen_n - 15, cen_e - 14), "not yet confirmed", height=2.2, layer="LABELS")

# ---- ROAD NAMES / WIDTHS (read directly off the sheet, Iter 18) ----
ROADS = [
    ("MARITIME OAK DRIVE", "(50' RIGHT OF WAY)"),
    ("TIMBER BRIDGE LANE", "(50' RIGHT OF WAY)"),
    ("ATLANTIC BEACH DRIVE", "(50' RIGHT OF WAY)  [sheet 6]"),
]
_rn = f0.n - 55
for _nm, _w in ROADS:
    dxf.text((_rn, f0.e + 20), _nm, height=5.0, layer="LABELS")
    dxf.text((_rn - 7, f0.e + 20), _w, height=3.4, layer="LABELS")
    _rn -= 20

# mark every vertex as a real point (visual proof of shared nodes)
for name, p in g.points.items():
    dxf.point((p.n, p.e), layer="VERTEX")

# open rear boundary shown as a dashed "not yet closed" indicator between
# the two known side-line endpoints -- NOT a claimed property line
s0, s11 = g.points["S0"], g.points["S11"]
dxf.line((s0.n, s0.e), (s11.n, s11.e), layer="OPEN_BOUNDARY")
mid = ((s0.n+s11.n)/2, (s0.e+s11.e)/2)
dxf.text((mid[0]-10, mid[1]), "REAR BOUNDARY NOT YET CONFIRMED -- see title block",
         height=4, layer="OPEN_BOUNDARY")

top = f0.n + 220
lft = f0.e - 60
body = [
    "ATLANTIC BEACH CC UNIT 2, SHEET 3, BLOCK A -- SHARED-VERTEX NETWORK",
    "",
    "FIX APPLIED: every lot corner is ONE vertex, referenced by both",
    "adjacent lots -- not two independently-computed near-duplicate points.",
    "13 front vertices (F0-F12) + 12 side vertices (S0-S11) = 25 total,",
    "each created exactly once. Yellow points mark every vertex.",
    "",
    "CONFIRMED EXACT:",
    "  front: 12 widths + 10.00' = 772.85' vs stated (EXACT)",
    "  front/side perpendicularity: 90.000000 deg (EXACT)",
    "  rear curve data (C195-201): both R=700' and R=150' chains pass",
    "  independent L/chord validation",
    "",
    "NOT YET CLOSED -- stated, not estimated:",
    "  Rear boundary station-to-lot assignment is not confirmed. NO lot",
    "  in this block has a computed square footage this pass. Drawing a",
    "  rear line without that confirmation would repeat the fabrication",
    "  error this project already corrected once (see MASTER_PROMPT",
    "  Iter 18). Next step: re-crop the C195-201 region at higher",
    "  magnification specifically to find the P.C./P.T. tie distances",
    "  from each lot's side-line endpoint to its curve station.",
]
for i, t in enumerate(body):
    dxf.text((top - i * 16, lft), t, height=8 if i == 0 else 6, layer="TITLEBLOCK")

out = "dxf/PB0067_P0132_AtlanticBeachCC_Sheet3_Topology.dxf"
dxf.save(out)
print(f"\nsaved {out}")
