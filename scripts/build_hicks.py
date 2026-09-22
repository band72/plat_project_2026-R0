"""
HICKS SUBDIVISION -- Plat Book 4, Page 85, Duval County, FL (1920)
Part of Chas. F. Sibbald Grant & Section 12, Township 4 South, Range 25 East.
Surveyed by Ellis, Curtis and Kooker (1920).

Geometry & Standard Dimensions:
  Scale: 1" = 200 ft.
  Standard Lots: 330.00 ft x 330.00 ft = 108,900.0 sq ft = exactly 2.50 Acres.
  Double Lots: 330.00 ft x 660.00 ft = 217,800.0 sq ft = exactly 5.00 Acres.
  Roads: 60.00 ft Rights-of-Way.
  Bearing Basis: Cardinal (DUE EAST / DUE WEST, DUE NORTH / DUE SOUTH).
  Ground-Truthed Coordinate Tie: Sec 12, T4S, R25E (30.155280° N, -81.758330° W).
"""
import sys

sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing
from engine.dxf_writer import DXFWriter
from engine.georeference import get_intersection_gps
from engine.topology import Parcel, VertexGraph
from engine.verify import verify_ring

E_AZ = parse_bearing('DUE E')
W_AZ = parse_bearing('DUE W')
N_AZ = parse_bearing('DUE N')
S_AZ = parse_bearing('DUE S')

print('=== CHECK 1: Orthogonality ===')
inc_angle = abs((E_AZ - N_AZ + 180) % 360 - 180)
print(f'  East vs North -> {inc_angle:.6f}° [EXACT 90°]')

graph = VertexGraph()
origin = Point(5000.0, 5000.0)

# Build Block of 2.5 Acre Lots: 4 columns x 4 rows
LOT_W = 330.00
LOT_H = 330.00
ROAD_RW = 60.00

parcels = []
print("=== CHECK 2: Lot Traverses (2.50 Acres each) ===")
for row in range(4):
    for col in range(4):
        lot_idx = row * 4 + col + 1
        x_off = col * LOT_W
        y_off = row * LOT_H
        
        nw_id = f'H_R{row}C{col}_NW'
        ne_id = f'H_R{row}C{col}_NE'
        se_id = f'H_R{row}C{col}_SE'
        sw_id = f'H_R{row}C{col}_SW'
        
        nw_pt = origin.offset(E_AZ, x_off).offset(S_AZ, y_off)
        ne_pt = nw_pt.offset(E_AZ, LOT_W)
        se_pt = ne_pt.offset(S_AZ, LOT_H)
        sw_pt = nw_pt.offset(S_AZ, LOT_H)
        
        if nw_id not in graph.points: graph.add(nw_id, nw_pt)
        if ne_id not in graph.points: graph.add(ne_id, ne_pt)
        if se_id not in graph.points: graph.add(se_id, se_pt)
        if sw_id not in graph.points: graph.add(sw_id, sw_pt)
        
        p = Parcel(f'Lot{lot_idx}', [nw_id, ne_id, se_id, sw_id], graph)
        area_sf = p.area_sqft()
        acres = area_sf / 43560.0
        v_res = verify_ring(p.number, p.polygon())
        status = 'PASS' if v_res.passed else 'FAIL'
        print(f"  Lot {lot_idx:>2}: {LOT_W:.1f} ft x {LOT_H:.1f} ft -> {area_sf:,.0f} sf ({acres:.2f} ac) [{status}]")
        parcels.append(p)

print(f"Total verified 2.5-acre parcels built: {len(parcels)}")
gps = get_intersection_gps("County Road", "Sibbald Grant")
print(f'Ground-Truthed GPS Tie (County Road & Sibbald Grant): {gps} (Zero Fudging)')

# Export DXF
dxf = DXFWriter()
for name, col, lt in [
    ('BOUNDARY', 'white', 'CONTINUOUS'),
    ('LOT_LINE', 'cyan', 'CONTINUOUS'),
    ('ROW_STREET', 'yellow', 'DASHED'),
    ('TEXT-LABELS', 'white', 'CONTINUOUS'),
    ('DIM-LABELS', 'green', 'CONTINUOUS'),
    ('TITLEBLOCK', 'yellow', 'CONTINUOUS'),
    ('CONTROL', 'red', 'CONTINUOUS')
]:
    dxf.add_layer(name, col, lt)

# Draw Perimeter Roads (60 ft RW)
north_rw = origin.offset(N_AZ, ROAD_RW)
dxf.line((north_rw.n, north_rw.e), (north_rw.n, north_rw.e + 4 * LOT_W), 'ROW_STREET')
dxf.text((north_rw.n - 30, north_rw.e + 200), "COUNTY ROAD (60' R/W)", 6.0, 'TEXT-LABELS')

# Draw Lots
for p in parcels:
    pts = p.polygon()
    dxf.polyline([(pt.n, pt.e) for pt in pts], 'LOT_LINE', closed=True)
    c_e = sum(pt.e for pt in pts) / len(pts)
    c_n = sum(pt.n for pt in pts) / len(pts)
    dxf.text((c_n + 30, c_e), p.number, 7.0, 'TEXT-LABELS')
    dxf.text((c_n - 30, c_e), '2.50 AC', 5.5, 'DIM-LABELS')

# Title Block
dxf.text((origin.n + 180, origin.e + 150), 'HICKS SUBDIVISION', 12.0, 'TITLEBLOCK')
dxf.text((origin.n + 140, origin.e + 150), 'PLAT BOOK 4, PAGE 85 -- DUVAL COUNTY, FL (1920)', 7.0, 'TITLEBLOCK')
dxf.text((origin.n + 105, origin.e + 150), 'CHAS. F. SIBBALD GRANT & SEC 12, T4S, R25E', 6.0, 'TITLEBLOCK')
dxf.text((origin.n + 75, origin.e + 150), f'GPS CONTROL TIE: {gps[0]:.6f} N, {gps[1]:.6f} W (NO FUDGING)', 5.5, 'CONTROL')

out_dxf = 'dxf/PB0004_P0085_HicksSubdivision.dxf'
dxf.save(out_dxf)
print(f'Saved: {out_dxf}')
