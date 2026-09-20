"""
Brooklyn Lake Estates through the known/unknown solver.

Only quantities actually READ off the sheet are declared as such. Everything
else starts UNKNOWN and is either derived by constraint propagation or is
reported on the frontier as something still to be read or rescanned.
"""
import sys, math
sys.path.insert(0, '.')
from engine.solver import (Model, SumEquals, TraverseClosure, CurveRelation,
                           Complementary, TangentRelation)
from engine.cogo import parse_bearing

m = Model("BROOKLYN LAKE ESTATES -- PB 4/39, Clay County FL")

# ---------------- KNOWN: read off the sheet ----------------
# south row frontages (lots 41,40,39,38,37 west->east)
for n, v in [("f41", 75.00), ("f40", 75.00), ("f39", 75.00),
             ("f38", 75.00), ("f37", 77.80)]:
    m.read(n, v)
m.read("south_total", 378.00, source="EAST 378.0' dimension")

# east side-line depths (bearing NORTH)
for n, v in [("d41e", 207.88), ("d40e", 212.05), ("d39e", 212.35), ("d38e", 236.31)]:
    m.read(n, v)
m.read("d41w", 202.79, source="west line = Sec 17 line")

# lake closing-meander courses
MEANDER = {"41": ("S86°13'00\"W", 73.25), "40": ("S86°47'00\"W", 75.07),
           "39": ("S89°44'30\"W", 75.00), "38": ("S72°07'30\"W", 78.80)}
for k, (b, d) in MEANDER.items():
    m.read(f"mn{k}", d, source=f"meander {b}")

# Carroll Drive curve at the SE of the row
m.read("cv1_R", 300.00, source="R=300.0 on sheet")
m.read("cv1_delta", 48.00, source="delta=48 00'")
m.unknown("cv1_L")
m.unknown("cv1_chord")
m.read("cv1_T", 133.0, confidence="M", source="T=133.? partly legible")

# lot 37 east boundary pieces
m.read("l37_ne", 125.00, source="N76 51'50\"E 125.0")
m.unknown("l37_east_depth")          # not legible
m.read("d37w", 236.31, source="shared with lot 38 east line")

# section geometry
m.read("sec_south_1320", 1320.00, source="EAST 1320.0' -- quarter-quarter")
m.read("west_bdy", 300.00, confidence="M", source="S0 30'30\"W 300'+/-")

# ---------------- CONSTRAINTS ----------------
m.add(SumEquals("south frontages sum to EAST 378.0'",
                ["f41", "f40", "f39", "f38", "f37"], "south_total"))

# per-lot closure: frontage E, east side N, meander, west side back S.
# west side distance is the single unknown in lots 40/39/38.
NORTH, EAST = 0.0, 90.0
SOUTH = 180.0
WEST_BEARING = {"41": parse_bearing("S00°30'30\"W"),   # Sec 17 line, NOT due south
                "40": SOUTH, "39": SOUTH, "38": SOUTH}
for lot, (fr, de, mk, dw) in {
        "41": ("f41", "d41e", "mn41", "d41w"),
        "40": ("f40", "d40e", "mn40", "d40w"),
        "39": ("f39", "d39e", "mn39", "d39w"),
        "38": ("f38", "d38e", "mn38", "d38w")}.items():
    maz = parse_bearing(MEANDER[lot][0])
    m.add(TraverseClosure(f"lot {lot} closes (frontage/east/meander/west)",
                          [(EAST, fr), (NORTH, de), (maz, mk),
                           (WEST_BEARING[lot], dw)]))

# the west side of one lot IS the east side of its western neighbour
m.add(SumEquals("lot40 west == lot41 east", ["d41e"], "d40w"))
m.add(SumEquals("lot39 west == lot40 east", ["d40e"], "d39w"))
m.add(SumEquals("lot38 west == lot39 east", ["d39e"], "d38w"))
m.add(SumEquals("lot37 west == lot38 east", ["d38e"], "d37w"))

# Carroll Drive curve
m.add(CurveRelation("Carroll Dr curve C1", "cv1_R", "cv1_L", "cv1_delta", "cv1_chord"))
m.add(TangentRelation("Carroll Dr C1 tangent T=R*tan(d/2)", "cv1_R", "cv1_delta", "cv1_T"))

m.solve().report()

# ---------------- summary of what got computed ----------------
print("\n=== DERIVED VALUES (computed, not read) ===")
for n, q in m.q.items():
    if q.status == "DERIVED":
        print(f"  {n:16s} = {q.value:10.3f}   via {q.source}")

print("\n=== CROSS-CHECK: derived west depths vs independently read east depths ===")
pairs = [("d40w", "d41e"), ("d39w", "d40e"), ("d38w", "d39e")]
for a, b in pairs:
    qa, qb = m.get(a), m.get(b)
    if qa.known and qb.known:
        print(f"  {a} {qa.value:8.2f} ({qa.status})  vs  {b} {qb.value:8.2f} "
              f"({qb.status})  -> {abs(qa.value-qb.value):.2f} ft")
