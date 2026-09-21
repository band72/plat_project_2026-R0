"""
Atlantic Beach CC Unit 2, Sheet 3, Block A -- with the VERIFICATION ENGINE.

Two outputs:
  1. the plan drawing (as before: transcribed cyan, assumed red ERROR)
  2. a per-lot CHECK SHEET set -- one page per lot, each lot drawn as a
     single closed polyline, every side labeled, verdict printed, and any
     offending geometry redrawn in red

The verification engine (engine/verify.py) runs INDEPENDENTLY of the
construction code. It does not trust the builder's belief that a ring is
valid; it re-derives closure, self-intersection, collinear overlap, spike
vertices, vertex degree and area from the finished coordinates.
"""
import sys, math
sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing, azimuth_to_bearing
from engine.topology import VertexGraph
from engine.dxf_writer import DXFWriter
from engine.verify import verify_ring, verify_network
from engine.lotsheets import plot_all

WIDTHS = [137.85, 55.00, 60.00, 55.00, 55.00, 60.00, 55.00, 55.00, 60.00, 55.00, 55.00, 60.00]
LOTS = [137, 136, 135, 134, 133, 132, 131, 130, 129, 128, 127, 126]
DEPTHS = [119.72, 120.00, 117.75, 106.79, 100.04, 97.66, 99.91, 103.53, 107.47, 111.08, 114.70, 118.64]
FRONT_BEARING = "N00°32'22\"E"
SIDE_BEARING = "N89°27'38\"E"

g = VertexGraph()
g.walk("F0", Point(0.0, 0.0),
       [(f"F{i+1}", FRONT_BEARING, w) for i, w in enumerate(WIDTHS)])
side_az = parse_bearing(SIDE_BEARING)
for i, d in enumerate(DEPTHS):
    g.add(f"S{i}", g.points[f"F{i}"].offset(side_az, d))
ASSUMED_LAST = DEPTHS[-1] + (DEPTHS[-1] - DEPTHS[-2])
g.add("S12", g.points["F12"].offset(side_az, ASSUMED_LAST))

# rings share vertex OBJECTS -- adjacent lots reference the same corner
parcels = {}
for i, num in enumerate(LOTS):
    parcels[str(num)] = [g.points[f"F{i}"], g.points[f"F{i+1}"],
                         g.points[f"S{i+1}"], g.points[f"S{i}"]]

print("=== VERIFICATION ENGINE ===")
net = verify_network(parcels)
res = net["lots"]
npass = sum(1 for v in res.values() if v.passed)
print(f"lots verified: {len(res)}   PASS: {npass}   FAIL: {len(res)-npass}")
print()
print(f"{'lot':>5s} {'verdict':>7s} {'area SF':>10s} {'perim':>9s} {'verts':>6s}  findings")
print("-" * 78)
for lot in [str(l) for l in LOTS]:
    v = res[lot]
    codes = ",".join(sorted({f.code for f in v.findings})) or "-"
    print(f"{lot:>5s} {'PASS' if v.passed else 'FAIL':>7s} "
          f"{v.area:>10,.0f} {v.perimeter:>9.2f} {v.n_vertices:>6d}  {codes}")

print("\n=== cross-lot shared-vertex check ===")
nd = net["near_duplicate_vertices"]
if nd:
    print(f"  {len(nd)} near-duplicate-but-distinct vertices found:")
    for la, ia, lb, ib, d in nd[:8]:
        print(f"    lot {la}[{ia}] vs lot {lb}[{ib}] : {d:.4f} ft apart")
else:
    print("  none -- every shared corner is a single shared vertex object")

print("\n=== warnings (non-blocking) ===")
warns = [(lot, f) for lot, v in res.items() for f in v.warnings]
if warns:
    for lot, f in warns[:10]:
        print(f"  lot {lot}: {f.code} -- {f.message}")
else:
    print("  none")

# ---- deliberate negative test: prove the engine actually catches faults ----
print("\n=== NEGATIVE CONTROL (engine must FAIL these) ===")
bow = [Point(0, 0), Point(100, 100), Point(0, 100), Point(100, 0)]
vb = verify_ring("BOWTIE-TEST", bow)
print(f"  bowtie      -> {'FAIL' if not vb.passed else 'PASS'} "
      f"({', '.join(sorted({f.code for f in vb.errors}))})")
spike = [Point(0, 0), Point(100, 0), Point(100, 50), Point(100.0, 0.02), Point(0, 50)]
vs = verify_ring("SPIKE-TEST", spike)
print(f"  spike/sliver-> {'FAIL' if not vs.passed else 'PASS'} "
      f"({', '.join(sorted({f.code for f in vs.errors})) or 'no errors'})")
dup = [Point(0, 0), Point(0, 0.001), Point(100, 0), Point(100, 50)]
vd = verify_ring("DUPVERT-TEST", dup)
print(f"  dup vertex  -> {'FAIL' if not vd.passed else 'PASS'} "
      f"({', '.join(sorted({f.code for f in vd.errors}))})")

# ---- DXF: check sheets ----
dxf = DXFWriter()
for n, c, lt in [("LOT_POLYLINE", "cyan", "CONTINUOUS"),
                 ("ERROR", "red", "CONTINUOUS"),
                 ("SHEET_LABELS", "white", "CONTINUOUS"),
                 ("SHEET_FRAME", "gray", "CONTINUOUS"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS")]:
    dxf.add_layer(n, c, lt)

count = plot_all(dxf, res, parcels, cols=4, origin_n=0.0, origin_e=0.0)

hdr = [
    "ATLANTIC BEACH CC UNIT 2 -- SHEET 3 BLOCK A -- LOT CLOSURE CHECK SHEETS",
    f"{count} lots, one page each. Each lot drawn as a SINGLE CLOSED POLYLINE.",
    "Checks per lot: ring closed / no zero-length side / no duplicate vertex /",
    "single continuous loop (every vertex degree 2) / no self-intersection /",
    "no collinear overlapping sides / no spike vertices / positive area /",
    "arc endpoints meet their vertices.",
    "RED = geometry that failed a check, drawn on top of the offending side.",
    f"RESULT: {npass} of {count} lots pass all geometric checks.",
    "",
    "NOTE ON AREAS: these rings use an ASSUMED rear boundary (see the plan",
    "drawing's ERROR layer). The geometry is verified sound; the AREAS remain",
    "PROVISIONAL until the rear curve stations are transcribed.",
]
for i, t in enumerate(hdr):
    dxf.text((120 - i * 11, 0), t, height=7 if i == 0 else 5, layer="TITLEBLOCK")

out = "dxf/PB0067_P0132_AtlanticBeachCC_Sheet3_CheckSheets.dxf"
dxf.save(out)
print(f"\nsaved {out}")
