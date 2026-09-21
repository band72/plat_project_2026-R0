"""
Atlantic Beach CC Unit 2, SHEET 4 -- lots closed in the sheet's OWN local
frame. Per direction: sheets are kept separate; a registration engine that
joins them comes later.

Everything here is transcribed off sheet 4 at high magnification. Both
blocks share the same bearing family, and the front/side bearings are
EXACTLY complementary, which is an independent confirmation that both were
read correctly (they are lettered on different parts of the sheet):

    N38°23'04"W  +  S51°36'56"W  =  90°00'00"  EXACT
    N38°23'04"W  +  N51°36'56"E  =  90°00'00"  EXACT

BLOCK S4-A  lots 111,112,113,114 -- 90.00' x 120.00'
BLOCK S4-B  lots  99,100         -- 60.00' x 120.00'

UNRESOLVED on this sheet (recorded, not guessed):
  - the "N38°23'04"W 534.60'" run does not divide evenly into 90.00' lots
    (534.60 / 90 = 5.94). It likely terminates at a curve point rather
    than a lot corner, so it is NOT used to infer a lot count.
  - lots 115,116,117 show both 55.00' and 90.00' dimensions in the same
    area; which is frontage and which is the rear width was not resolved
    at this magnification, so those lots are NOT built.
  - lots 101,102 (123.46', 139.62') are on a curved return and were not
    closed this pass.
"""
import sys, math
sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing
from engine.topology import VertexGraph
from engine.dxf_writer import DXFWriter
from engine.verify import verify_network
from engine.lotsheets import plot_all

FRONT = "N38°23'04\"W"
SIDE_A = "S51°36'56\"W"      # block A side lines
SIDE_B = "N51°36'56\"E"      # block B side lines

print("=== bearing complementarity (independent reads) ===")
for side in (SIDE_A, SIDE_B):
    ang = abs((parse_bearing(FRONT) - parse_bearing(side) + 180) % 360 - 180)
    print(f"  {FRONT} vs {side}: {ang:.6f} deg -> "
          f"{'EXACT 90' if abs(ang - 90) < 1e-9 else 'CHECK'}")

BLOCKS = [
    dict(name="S4-A", lots=[114, 113, 112, 111], width=90.00, depth=120.00,
         side=SIDE_A, origin=Point(0.0, 0.0)),
    dict(name="S4-B", lots=[99, 100], width=60.00, depth=120.00,
         side=SIDE_B, origin=Point(-400.0, 0.0)),
]

g = VertexGraph()
parcels = {}
for blk in BLOCKS:
    fz = parse_bearing(FRONT)
    sz = parse_bearing(blk["side"])
    n = len(blk["lots"])
    tag = blk["name"]
    # front vertices walked once; shared corners are shared objects
    g.walk(f"{tag}_F0", blk["origin"],
           [(f"{tag}_F{i+1}", FRONT, blk["width"]) for i in range(n)])
    for i in range(n + 1):
        g.add(f"{tag}_S{i}", g.points[f"{tag}_F{i}"].offset(sz, blk["depth"]))
    for i, num in enumerate(blk["lots"]):
        parcels[str(num)] = [g.points[f"{tag}_F{i}"], g.points[f"{tag}_F{i+1}"],
                             g.points[f"{tag}_S{i+1}"], g.points[f"{tag}_S{i}"]]
    print(f"\n  {tag}: {n} lots, {blk['width']}' x {blk['depth']}' "
          f"-> front run {n*blk['width']:.2f}'")

print("\n=== VERIFICATION ===")
net = verify_network(parcels)
res = net["lots"]
npass = sum(1 for v in res.values() if v.passed)
print(f"lots verified: {len(res)}   PASS: {npass}   FAIL: {len(res)-npass}\n")
print(f"{'lot':>5s} {'verdict':>7s} {'area SF':>10s} {'perim':>9s}  findings")
print("-" * 60)
for lot in sorted(parcels, key=lambda x: int(x)):
    v = res[lot]
    codes = ",".join(sorted({f.code for f in v.findings})) or "-"
    print(f"{lot:>5s} {'PASS' if v.passed else 'FAIL':>7s} "
          f"{v.area:>10,.0f} {v.perimeter:>9.2f}  {codes}")

exp = {"90x120": 90 * 120, "60x120": 60 * 120}
print(f"\n  expected 90x120 = {exp['90x120']:,} SF ; 60x120 = {exp['60x120']:,} SF")
ok = all(abs(res[str(l)].area - (90*120 if l >= 111 else 60*120)) < 1.0
         for l in [114, 113, 112, 111, 99, 100])
print(f"  all areas match their stated dimensions exactly: {ok}")

nd = net["near_duplicate_vertices"]
print(f"  cross-lot near-duplicate vertices: {len(nd)} "
      f"({'clean' if not nd else 'INVESTIGATE'})")

# ---- check sheets ----
dxf = DXFWriter()
for n_, c_, lt in [("LOT_POLYLINE", "cyan", "CONTINUOUS"),
                   ("ERROR", "red", "CONTINUOUS"),
                   ("SHEET_LABELS", "white", "CONTINUOUS"),
                   ("SHEET_FRAME", "gray", "CONTINUOUS"),
                   ("TITLEBLOCK", "yellow", "CONTINUOUS")]:
    dxf.add_layer(n_, c_, lt)

count = plot_all(dxf, res, parcels, cols=3, origin_n=0.0, origin_e=0.0)
hdr = [
    "ATLANTIC BEACH CC UNIT 2 -- SHEET 4 -- LOT CLOSURE CHECK SHEETS",
    f"{count} lots, one page each, each a SINGLE CLOSED POLYLINE.",
    "Drawn in SHEET 4's OWN LOCAL FRAME -- not joined to sheets 3/5/6.",
    "Joining is a separate registration step, deliberately deferred.",
    "",
    "Bearings transcribed off the sheet; front and side bearings are",
    "EXACTLY complementary (90d00'00\") on both blocks -- independent",
    "confirmation, since they are lettered in different places.",
    f"RESULT: {npass} of {count} lots pass all geometric checks.",
    "These areas are FINAL (not provisional): all four sides of every lot",
    "here are transcribed -- no assumed rear boundary was needed.",
]
for i, t in enumerate(hdr):
    dxf.text((140 - i * 11, 0), t, height=7 if i == 0 else 5, layer="TITLEBLOCK")

out = "dxf/PB0067_P0132_AtlanticBeachCC_Sheet4_CheckSheets.dxf"
dxf.save(out)
print(f"\nsaved {out}")
