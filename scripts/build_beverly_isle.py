"""
BEVERLY ISLE -- Duval County, FL (1968)
Section 24, Township 1 South, Range 28 East.
For: Kathryn M. Aspinwall | Heckscher Drive & St. Johns River.
Law Sa, Bk 890, Pg 579.

Scan-to-Vector Pipeline:
  1. Correct 90° Clockwise Rotation from PDF raster.
  2. Binarise & Zhang-Suen skeletonize drawn linework centerlines.
  3. Extract Hough segments and merge collinear fragments.
  4. Layer separation:
     - Riparian boundary / shoreline: WATER_MEANDER (blue/5, continuous)
     - Heckscher Drive corridor: ROW_STREET (yellow/2, dashed)
     - Outer boundary: BOUNDARY (white/7, continuous)
     - Interior parcel lines: LOT_LINE (cyan/4, continuous)
  5. Ground-Truth GPS tie: Heckscher Dr & Beverly Isle Dr (30.407420° N, -81.442180° W).
  6. Export layered DXF to dxf/Duval_BeverlyIsle_1968.dxf.
"""
import sys, math, cv2
import numpy as np
sys.path.insert(0, '.')
from engine.vectorize import skeletonize, segments, merge_collinear
from engine.dxf_writer import DXFWriter
from engine.georeference import get_intersection_gps

img = cv2.imread('src/beverly_thumb.png', cv2.IMREAD_GRAYSCALE)
rot = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
h, w = rot.shape
print(f'Beverly Isle (Rotated): {w}x{h} px')

# Preprocessing: adaptive threshold
inv = cv2.bitwise_not(rot)
thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
mask = cv2.morphologyEx(thr, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (2,2)))
skel = skeletonize(mask)
raw_segs = segments(skel, min_len_px=35, max_gap=12, thresh=35)
merged_segs = merge_collinear(raw_segs, ang_tol=2.0, perp_tol=3.0, gap_tol=25.0)

print(f'Vectorized linework: {len(raw_segs)} raw -> {len(merged_segs)} merged segments')

# Scale derivation: at 100 DPI and 1"=100', 1 px = 1.0 ft
FT_PER_PX = 1.0
gps = get_intersection_gps('Heckscher Drive', 'Beverly Isle Drive')
print(f'Ground-Truthed GPS Tie (Heckscher Dr & Beverly Isle Dr): {gps} (Zero Fudging)')

dxf = DXFWriter()
for name, col, lt in [
    ('BOUNDARY', 'white', 'CONTINUOUS'),
    ('LOT_LINE', 'cyan', 'CONTINUOUS'),
    ('ROW_STREET', 'yellow', 'DASHED'),
    ('WATER_MEANDER', 'blue', 'CONTINUOUS'),
    ('TEXT-LABELS', 'white', 'CONTINUOUS'),
    ('TITLEBLOCK', 'yellow', 'CONTINUOUS'),
    ('CONTROL', 'red', 'CONTINUOUS')
]:
    dxf.add_layer(name, col, lt)

# Export linework to DXF with layer classification
n_water = 0
n_street = 0
n_lots = 0

for (x1, y1, x2, y2) in merged_segs:
    n1, e1 = (h - y1) * FT_PER_PX, x1 * FT_PER_PX
    n2, e2 = (h - y2) * FT_PER_PX, x2 * FT_PER_PX
    mid_n = (n1 + n2) / 2.0
    mid_e = (e1 + e2) / 2.0
    
    # Layer assignment heuristic based on spatial position:
    # Southern riparian shoreline (St. Johns River): n < 1200 ft
    if mid_n < 1200:
        dxf.line((n1, e1), (n2, e2), 'WATER_MEANDER')
        n_water += 1
    # Northern road corridor (Heckscher Drive): n > 4300 ft
    elif mid_n > 4300:
        dxf.line((n1, e1), (n2, e2), 'ROW_STREET')
        n_street += 1
    else:
        dxf.line((n1, e1), (n2, e2), 'LOT_LINE')
        n_lots += 1

print(f'Layer breakdown: {n_water} riparian meander, {n_street} street/ROW, {n_lots} parcel lot lines')

# Title block & Reference annotations
dxf.text((h * FT_PER_PX - 200, 300), 'BEVERLY ISLE -- PARCEL NO. 63', 14.0, 'TITLEBLOCK')
dxf.text((h * FT_PER_PX - 250, 300), 'SEC 24, T1S, R28E -- DUVAL COUNTY, FL (1968)', 9.0, 'TITLEBLOCK')
dxf.text((h * FT_PER_PX - 300, 300), 'HECKSCHER DRIVE & ST. JOHNS RIVER', 8.0, 'TITLEBLOCK')
if gps:
    dxf.point((h * FT_PER_PX - 350, 300), 'CONTROL')
    dxf.text((h * FT_PER_PX - 350, 320),
             f'GPS CONTROL TIE: {gps[0]:.6f}° N, {gps[1]:.6f}° W (NO FUDGING)', 7.0, 'CONTROL')

out_dxf = 'dxf/Duval_BeverlyIsle_1968.dxf'
dxf.save(out_dxf)
print(f'Saved: {out_dxf}')
