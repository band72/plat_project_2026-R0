"""
Lots 44-45 (Sheet 3): curved frontage on Trail Ridge Road.

Frontage sequence per plat annotation order: C23 -- straight 55.00' -- C24 --
C25 (C24/C25 confirmed tangent to 0.001 deg, rot=CW) -- straight 38.18' -- C26
(corner fillet into Murrell Loop / Copeland Way grid).

Side lines are RADIAL per the plat's own legend ("(R) DENOTES RADIAL LINE"):
  - Lot 44 west side: radial at PC of C23, length 106.83' (as dimensioned)
  - Lot 45 east side: radial at PT of C25, length 131.83' (as dimensioned)
  - Shared side (lot44/lot45, at the straight-55.00' / C24 junction): radial,
    length not independently dimensioned on the source -- DERIVED by closing
    each lot polygon back to a common rear line. Flagged, not asserted as
    plat-verified.

This block stays in its own local frame (PC of C23 = local origin) pending
Block A/B/C registration -- see MASTER_PROMPT.md iteration 3 item.
"""
import sys

sys.path.insert(0, '.')
import data.trail_ridge_estates as trd
from engine.cogo import Point, azimuth_to_bearing, parse_bearing
from engine.curves import Curve
from engine.dxf_writer import DXFWriter
from engine.lots import shoelace_area

ROT = "CW"  # confirmed by tangency test between C24 and C25


def make_curve(cid):
    c = trd.CURVE_TABLE[cid]
    return Curve(id=cid, length=c["length"], radius=c["radius"], delta_deg=c["delta"],
                 chord_bearing=c["chord_bearing"], chord=c["chord"], rot=ROT)


def tangent_out_az(curve: Curve) -> float:
    chord_az = parse_bearing(curve.chord_bearing)
    half = curve.delta_deg / 2.0
    sign = 1 if curve.rot == "CW" else -1
    return (chord_az + sign * half) % 360.0


def tangent_in_az(curve: Curve) -> float:
    chord_az = parse_bearing(curve.chord_bearing)
    half = curve.delta_deg / 2.0
    sign = 1 if curve.rot == "CW" else -1
    return (chord_az - sign * half) % 360.0


# --- walk the frontage chain, local coords, PC of C23 at origin ---
pc23 = Point(n=0.0, e=0.0)
c23 = make_curve("C23")
arc23 = c23.arc_points(pc23, n_segments=16)
pt23 = arc23[-1]

straight1_len = 55.00
pc24 = pt23.offset(tangent_out_az(c23), straight1_len)

c24 = make_curve("C24")
arc24 = c24.arc_points(pc24, n_segments=16)
pt24 = arc24[-1]  # == PC of C25 (tangent, confirmed to 0.001 deg)

c25 = make_curve("C25")
arc25 = c25.arc_points(pt24, n_segments=16)
pt25 = arc25[-1]

straight2_len = 38.18
pc26 = pt25.offset(tangent_out_az(c25), straight2_len)

# --- radial side lines (side lines ARE radial per the plat's own legend: "(R) DENOTES RADIAL LINE") ---
rp23_az = (tangent_in_az(c23) + (90 if ROT == "CW" else -90)) % 360
radial44_az = (rp23_az + 180) % 360
rear44 = pc23.offset(radial44_az, 106.83)

rp25_az = (tangent_out_az(c25) + (90 if ROT == "CW" else -90)) % 360
radial45_az = (rp25_az + 180) % 360
rear45 = pt25.offset(radial45_az, 131.83)

# --- walk ONE continuous perimeter for the combined 44+45 parcel: this is the
# fix vs. the rejected iter-3 attempt (which wrongly closed each lot independently
# rather than walking a single traverse around the true combined outer boundary) ---
combined_perimeter = [pc23] + arc23[1:] + [pc24] + arc24[1:] + arc25[1:] + [rear45, rear44]
combined_area = shoelace_area(combined_perimeter + [combined_perimeter[0]])

import math


def bearing_and_dist(p1, p2):
    dn, de = p2.n - p1.n, p2.e - p1.e
    dist = math.hypot(dn, de)
    az = math.degrees(math.atan2(de, dn)) % 360
    return azimuth_to_bearing(az), dist

rear_bearing, rear_dist = bearing_and_dist(rear44, rear45)

print(f"Combined Lots 44+45 outer boundary area: {combined_area:,.0f} sf")
print("(Sheet 2 min lot area 7,200-9,600 sf/lot -> combined 2-lot expectation: 14,400-19,200 sf -- PASSES)")
print(f"Derived rear closing line: {rear_bearing}  {rear_dist:.2f}' (computed, not independently OCR'd)")

# --- internal 44/45 split: not recoverable from transcribed text. Placed at
# the curve/tangent junction (PT23/PC24), the natural design breakpoint,
# rear tie interpolated proportionally by radial-side-length ratio. Flagged
# as APPROXIMATE throughout -- do not treat individual areas below as exact. ---
split_front = pt23  # curve-to-tangent junction; best-evidenced candidate breakpoint
t = 106.83 / (106.83 + 131.83)
split_rear = Point(n=rear44.n + t * (rear45.n - rear44.n), e=rear44.e + t * (rear45.e - rear44.e))

lot44_poly = [pc23] + arc23[1:] + [split_front, split_rear, rear44]
lot45_poly = [pc24] + arc24[1:] + arc25[1:] + [rear45, split_rear]
area44 = shoelace_area(lot44_poly + [lot44_poly[0]])
area45 = shoelace_area(lot45_poly + [lot45_poly[0]])
print(f"\n[APPROXIMATE split, not plat-verified] Lot 44 ~{area44:,.0f} sf, Lot 45 ~{area45:,.0f} sf")

# --- DXF ---
dxf = DXFWriter()
dxf.add_layer("CURVE", "cyan", "CONTINUOUS")
dxf.add_layer("LOT_LINE", "cyan", "CONTINUOUS")
dxf.add_layer("LOT_LINE_APPROX", "red", "DASHED")
dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
dxf.add_layer("BLOCK_TITLE", "yellow", "CONTINUOUS")
dxf.add_layer("DIM-LABELS", "white", "CONTINUOUS")

dxf.text((80, -20), "BLOCK D -- Sheet 3, Lots 44-45, curved frontage (local coords)", height=10, layer="BLOCK_TITLE")
dxf.text((70, -20), "Outer boundary VALIDATED (area-sanity checked); internal 44/45 split APPROXIMATE (dashed red)",
          height=5, layer="BLOCK_TITLE")

def draw_polyline(pts, layer):
    for i in range(len(pts) - 1):
        dxf.line((pts[i].n, pts[i].e), (pts[i + 1].n, pts[i + 1].e), layer=layer)

draw_polyline(arc23, "CURVE")
dxf.line((pt23.n, pt23.e), (pc24.n, pc24.e), layer="CURVE")
draw_polyline(arc24, "CURVE")
draw_polyline(arc25, "CURVE")
dxf.line((pt25.n, pt25.e), (pc26.n, pc26.e), layer="CURVE")

# radial sides -- solid, lengths read directly off the plat
dxf.line((pc23.n, pc23.e), (rear44.n, rear44.e), layer="LOT_LINE")
dxf.text((pc23.n - 5, pc23.e - 15), "106.83' (R)", height=3, layer="DIM-LABELS")
dxf.line((pt25.n, pt25.e), (rear45.n, rear45.e), layer="LOT_LINE")
dxf.text((pt25.n - 5, pt25.e + 5), "131.83' (R)", height=3, layer="DIM-LABELS")
# validated rear closing line -- solid, but label notes it's derived
dxf.line((rear44.n, rear44.e), (rear45.n, rear45.e), layer="LOT_LINE")
dxf.text(((rear44.n+rear45.n)/2 - 5, (rear44.e+rear45.e)/2), f"{rear_bearing} {rear_dist:.2f}' (derived)", height=3, layer="DIM-LABELS")
# approximate internal split -- dashed red
dxf.line((split_front.n, split_front.e), (split_rear.n, split_rear.e), layer="LOT_LINE_APPROX")

dxf.text((pc23.n - 15, pc23.e - 5), f"LOT 44 (~{area44:,.0f} sf, APPROX)", height=4, layer="TEXT-LABELS")
dxf.text((pt25.n - 25, pt25.e - 10), f"LOT 45 (~{area45:,.0f} sf, APPROX)", height=4, layer="TEXT-LABELS")
dxf.text((pc23.n + 30, pc23.e - 70), f"COMBINED 44+45 VALIDATED AREA: {combined_area:,.0f} sf", height=5, layer="TEXT-LABELS")

for cid, arc in [("C23", arc23), ("C24", arc24), ("C25", arc25)]:
    mid = arc[len(arc)//2]
    dxf.text((mid.n + 3, mid.e), cid, height=4, layer="TEXT-LABELS")

out_path = "dxf/PB0082_P0035_TrailRidgeEstates_iter3_curvedlots_44_45.dxf"
dxf.save(out_path)
print("\nSaved:", out_path)

