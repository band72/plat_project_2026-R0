"""
BEACHWOOD UNIT TWO -- interior worked from the known corner (P.O.B.) inward.
PB 30, Pages 82 & 82A, Duval County, FL (1960).

Method: the P.O.B. on the N'ly line of Section 32 anchors the north edge.
Everything below is chained southward using transcribed row depths and
street widths, and westward using the transcribed west offsets. Nothing is
positioned by eye.

All values visually transcribed at 3x from a 200 DPI scan.
"""
import sys, math
sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing
from engine.lots import shoelace_area, Lot
from engine.dxf_writer import DXFWriter
from engine.verify import verify_ring
from engine.lotsheets import plot_all

STREET_BEARING = "S87°35'30\"W"     # every E-W line on this sheet
SIDE_BEARING = "N02°24'30\"W"       # every N-S lot line
NORTH_DISTANCE = 1626.37
WEST_RW = 50.0                       # 50' R/W for drainage & utilities (west)
NORTH_RW = 50.0                      # 50' R/W for drainage & utilities (north)
MANGROVE_RW = 60.0
STREET_RW = 60.0                     # Starfish, Sail (60' R/W)
ROW_DEPTH = 100.0
WEST_BLOCK_WIDTH = 100.0             # lot row west of Mangrove Ave

# west offset from the west boundary to each block's west line
OFF_BLK18 = WEST_RW                                         # Mangrove ends at Starfish
OFF_BLK17 = WEST_RW + WEST_BLOCK_WIDTH + MANGROVE_RW        # = 210.0
OFF_BLK16 = OFF_BLK17

BLOCKS = [
    dict(block="18", off=OFF_BLK18, first=103.50, n=19,
         lots=[str(i) for i in range(1, 20)], row="single",
         depth_top=NORTH_RW),                       # top of row below north R/W
    dict(block="17N", off=OFF_BLK17, first=93.50, n=17,
         lots=[str(i) for i in range(1, 18)], row="north"),
    dict(block="17S", off=OFF_BLK17, first=93.50, n=17,
         lots=[str(i) for i in range(34, 17, -1)], row="south"),
    dict(block="16N", off=OFF_BLK16, first=93.50, n=17,
         lots=[str(i) for i in range(1, 18)], row="north"),
]

# ---------------- CHECK A: every row must end on the same east line ----------
print("=== CHECK A: common east line across rows (independent of each other) ===")
ends = {}
for b in BLOCKS:
    width = b["first"] + 75.0 * (b["n"] - 1)
    end = b["off"] + width
    ends[b["block"]] = end
    print(f"  Blk {b['block']:>3}: offset {b['off']:6.2f} + ({b['first']:6.2f} + "
          f"{b['n']-1} x 75.00) = {width:7.2f} -> east line at {end:8.2f} ft")
spread = max(ends.values()) - min(ends.values())
print(f"  spread across rows = {spread:.2f} ft -> "
      f"{'ALL ROWS AGREE' if spread < 0.05 else 'CHECK'}")
print(f"  remainder to the {NORTH_DISTANCE} ft north line = "
      f"{NORTH_DISTANCE - max(ends.values()):.2f} ft (Beachwood Blvd tie, unresolved)")

# ---------------- CHECK B: perpendicularity -----------------
ang = abs((parse_bearing(STREET_BEARING) - parse_bearing(SIDE_BEARING) + 180) % 360 - 180)
print(f"\n=== CHECK B: side vs street bearing = {ang:.6f} deg -> "
      f"{'EXACT' if abs(ang-90) < 0.0005 else 'CHECK'} ===")

# ---------------- build ----------------
eaz = (parse_bearing(STREET_BEARING) + 180) % 360     # east
saz = (parse_bearing(SIDE_BEARING) + 180) % 360       # south

POB = Point(0.0, 0.0)

def at(south_ft, east_ft):
    return POB.offset(saz, south_ft).offset(eaz, east_ft)

# running southward station from the POB
station = NORTH_RW          # top of Block 18 row
layout = []
for b in BLOCKS:
    layout.append((b, station))
    station += ROW_DEPTH
    if b["block"] == "18":
        station += STREET_RW          # Starfish Avenue
    elif b["block"] == "17S":
        station += STREET_RW          # Sail Avenue

print("\n=== row stations (ft south of P.O.B.) ===")
for b, st in layout:
    print(f"  Blk {b['block']:>3}: north line at {st:7.2f}, south line at {st+ROW_DEPTH:7.2f}")

all_lots = []
for b, st in layout:
    widths = [b["first"]] + [75.0] * (b["n"] - 1)
    x = b["off"]
    for num, wdt in zip(b["lots"], widths):
        nw = at(st, x)
        ne = at(st, x + wdt)
        se = at(st + ROW_DEPTH, x + wdt)
        sw = at(st + ROW_DEPTH, x)
        corners = [nw, ne, se, sw]
        area = shoelace_area(corners + [corners[0]])
        all_lots.append((b["block"], Lot(number=num, corners=corners, area_sqft=area)))
        x += wdt

print(f"\n=== CHECK C: lot closure ===")
n75 = sum(1 for _, l in all_lots if abs(l.area_sqft - 7500.0) < 0.5)
odd = [(bk, l.number, round(l.area_sqft, 1)) for bk, l in all_lots
       if abs(l.area_sqft - 7500.0) >= 0.5]
print(f"  total lots built: {len(all_lots)}")
print(f"  at exactly 7,500 sf (75x100): {n75}")
print(f"  wider end lots: {odd}")

# ---------------- DXF ----------------
dxf = DXFWriter()
for n, c, lt in [("BOUNDARY", "white", "CONTINUOUS"), ("LOT_LINE", "cyan", "CONTINUOUS"),
                 ("ROW_STREET", "yellow", "DASHED"), ("EASEMENT", "green", "DASHED"),
                 ("TEXT-LABELS", "white", "CONTINUOUS"), ("DIM-LABELS", "green", "CONTINUOUS"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS"), ("UNRESOLVED", "red", "DASHED"),
                 ("CONTROL", "red", "CONTINUOUS")]:
    dxf.add_layer(n, c, lt)

for bk, lot in all_lots:
    dxf.polyline([(p.n, p.e) for p in lot.corners], layer="LOT_LINE", closed=True)
    cn = sum(q.n for q in lot.corners) / 4
    ce = sum(q.e for q in lot.corners) / 4
    dxf.text((cn, ce), lot.number, height=9, layer="TEXT-LABELS")

# north boundary + POB
n_end = at(0.0, NORTH_DISTANCE)
dxf.line((POB.n, POB.e), (n_end.n, n_end.e), layer="BOUNDARY")
dxf.point((POB.n, POB.e), layer="CONTROL")
dxf.text((POB.n + 16, POB.e), "P.O.B.", height=12, layer="CONTROL")
dxf.text((POB.n + 6, POB.e + 380),
         f"N'ly line Section 32   {STREET_BEARING}  {NORTH_DISTANCE}'",
         height=10, layer="DIM-LABELS")

# R/W strips
nr = at(NORTH_RW, 0.0); nr2 = at(NORTH_RW, NORTH_DISTANCE)
dxf.line((nr.n, nr.e), (nr2.n, nr2.e), layer="EASEMENT")
dxf.text((nr.n + 6, nr.e + 120), "50' R/W FOR DRAINAGE AND UTILITIES",
         height=9, layer="EASEMENT")
w1 = at(0.0, WEST_RW); w2 = at(station, WEST_RW)
dxf.line((w1.n, w1.e), (w2.n, w2.e), layer="EASEMENT")

# streets
for label, st in [("STARFISH AVENUE (60' R/W)", NORTH_RW + ROW_DEPTH),
                  ("SAIL AVENUE (60' R/W)", NORTH_RW + ROW_DEPTH + STREET_RW + 2 * ROW_DEPTH)]:
    a = at(st, OFF_BLK17); b2 = at(st, max(ends.values()))
    dxf.line((a.n, a.e), (b2.n, b2.e), layer="ROW_STREET")
    c = at(st + STREET_RW, OFF_BLK17); d = at(st + STREET_RW, max(ends.values()))
    dxf.line((c.n, c.e), (d.n, d.e), layer="ROW_STREET")
    m = at(st + STREET_RW / 2, OFF_BLK17 + 300)
    dxf.text((m.n, m.e), f"{label}   {STREET_BEARING}", height=11, layer="ROW_STREET")

# block labels
for b, st in layout:
    m = at(st + ROW_DEPTH / 2, b["off"] - 60)
    dxf.text((m.n, m.e), f"BLK {b['block']}", height=12, layer="TEXT-LABELS")

# unresolved east tie
e1 = at(0.0, max(ends.values())); e2 = at(station, max(ends.values()))
dxf.line((e1.n, e1.e), (e2.n, e2.e), layer="UNRESOLVED")
dxf.text((e1.n - 30, e1.e + 12),
         f"EAST TIE TO BEACHWOOD BLVD UNRESOLVED "
         f"({NORTH_DISTANCE - max(ends.values()):.2f}' remainder)",
         height=10, layer="UNRESOLVED")
# unresolved south
s1 = at(station, OFF_BLK16); s2 = at(station, max(ends.values()))
dxf.line((s1.n, s1.e), (s2.n, s2.e), layer="UNRESOLVED")
dxf.text((s1.n - 20, s1.e + 200),
         "SOUTH OF HERE UNRESOLVED: Blk 16 south row transitions to the diagonal "
         "Marina/Sands/Cape Horn fabric (inline curve data, not legible at 200 DPI)",
         height=9, layer="UNRESOLVED")

top = POB.n + 260
lft = POB.e
body = [
    "BEACHWOOD UNIT TWO -- PB 30, PAGES 82 & 82A, DUVAL COUNTY, FL (1960)",
    "Beach Boulevard Estates, Inc.  |  Simmerson, Bell & Akel  |  1\"=100'",
    "INTERIOR WORKED FROM THE P.O.B. INWARD",
    "",
    "SOURCE: 200 DPI scan; visual transcription at 3x, NOT OCR.",
    "",
    "VALIDATION:",
    f"  A. Three independently-transcribed rows (different lot counts, different",
    f"     west offsets) all terminate at {max(ends.values()):.2f} ft east of the west",
    f"     boundary. Spread = {spread:.2f} ft. Blk 18: 50.00+103.50+18(75); ",
    f"     Blk 17/16: 210.00+93.50+16(75). Independent agreement.",
    f"  B. Side bearing N2d24'30\"W + street S87d35'30\"W = 90d00'00\" exactly",
    f"     (computed {ang:.6f} deg).",
    "  C. All rows parallel -> depth must be constant; all transcribed at 100.00 ft.",
    f"  D. {n75} of {len(all_lots)} lots close at exactly 7,500 sf; remainder are the",
    "     wider west end lots (103.50 / 93.50 frontage), as drawn.",
    "",
    "SCOPE: Blocks 18, 17 (both rows) and 16 (north row). South and east edges",
    "flagged UNRESOLVED -- not guessed.",
    "PLAT NOTE: curve bearings/distances are CHORD bearings and distances.",
]
for i, t in enumerate(body):
    dxf.text((top - i * 30, lft), t, height=12 if i == 0 else 9, layer="TITLEBLOCK")

out = "dxf/PB0030_P0082_BeachwoodUnitTwo_interior.dxf"
dxf.save(out)
print(f"\nsaved {out}")

# ---------------- MapCheck & Per-Lot Check Sheets Export ----------------
parcels_dict = {f"Blk{bk}-L{l.number}": l.corners for bk, l in all_lots}
verifs_dict = {f"Blk{bk}-L{l.number}": verify_ring(f"Blk{bk}-L{l.number}", l.corners) for bk, l in all_lots}

dxf_cs = DXFWriter()
for n, c, lt in [("LOT_POLYLINE", "cyan", "CONTINUOUS"),
                 ("ERROR", "red", "CONTINUOUS"),
                 ("SHEET_LABELS", "white", "CONTINUOUS"),
                 ("SHEET_FRAME", "gray", "CONTINUOUS"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS")]:
    dxf_cs.add_layer(n, c, lt)

plot_all(dxf_cs, verifs_dict, parcels_dict, cols=10)
cs_out = "dxf/PB0030_P0082_Beachwood_CheckSheets.dxf"
dxf_cs.save(cs_out)
print(f"saved {cs_out}")
