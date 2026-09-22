"""
Build DXF for Trail Ridge Estates (PB 82, Pg 35-40) from transcribed plat data.
Iteration 1: parent boundary (closed, verified) + curve/line table QA +
State Plane control points + title/annotation block. Lot-by-lot fabric for
Sheets 3-6 is the next iteration once Sheet 6 (Pg 40) is supplied -- see
MASTER_PROMPT.md.
"""
import sys

sys.path.insert(0, '.')
import data.trail_ridge_estates as trd
from engine.cogo import Course, Point, closure_report, run_traverse
from engine.dxf_writer import DXFWriter

dxf = DXFWriter()
dxf.add_layer("BOUNDARY", "white", "CONTINUOUS")
dxf.add_layer("SECTION_LINE", "gray", "DASHED")
dxf.add_layer("CONTROL_POINTS", "red", "CONTINUOUS")
dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")

# --- boundary traverse ---
pob = Point(n=trd.STATE_PLANE_POINTS[1]["n"], e=trd.STATE_PLANE_POINTS[1]["e"])
courses = [Course(label=c["label"], bearing=c["bearing"], distance=c["distance"])
           for c in trd.BOUNDARY_COURSES]
pts = run_traverse(pob, courses)
rpt = closure_report(pts)

for i in range(len(pts) - 1):
    dxf.line((pts[i].n, pts[i].e), (pts[i + 1].n, pts[i + 1].e), layer="BOUNDARY")

# point of commencement, offset back from POB along the ROW course, reversed
comm_az = (270 - (0)) # placeholder, computed properly below
from engine.cogo import parse_bearing

poc_az = (parse_bearing(trd.COMMENCEMENT_TO_POB["bearing"]) + 180) % 360
poc = pob.offset(poc_az, trd.COMMENCEMENT_TO_POB["distance"])
dxf.line((poc.n, poc.e), (pob.n, pob.e), layer="SECTION_LINE")
dxf.point((poc.n, poc.e), layer="CONTROL_POINTS")
dxf.text((poc.n + 5, poc.e), "POC", height=8, layer="TEXT-LABELS")

# control / labeled points
dxf.point((pob.n, pob.e), layer="CONTROL_POINTS")
dxf.text((pob.n + 5, pob.e), "P.O.B. (State Plane Pt 1)", height=8, layer="TEXT-LABELS")
p2 = Point(n=trd.STATE_PLANE_POINTS[2]["n"], e=trd.STATE_PLANE_POINTS[2]["e"])
dxf.point((p2.n, p2.e), layer="CONTROL_POINTS")
dxf.text((p2.n + 5, p2.e), 'SW Corner Tract "H" (State Plane Pt 2)', height=8, layer="TEXT-LABELS")

# course bearing/distance labels at midpoints
for i in range(len(pts) - 1):
    mid_n = (pts[i].n + pts[i + 1].n) / 2
    mid_e = (pts[i].e + pts[i + 1].e) / 2
    c = trd.BOUNDARY_COURSES[i]
    dxf.text((mid_n, mid_e), f"{c['bearing']}  {c['distance']:.2f}'", height=6, layer="TEXT-LABELS")

# road name label -- pt3->POB course runs along the S'ly R/W line of Trail Ridge Road
road_mid_n = (pts[3].n + pts[4].n) / 2
road_mid_e = (pts[3].e + pts[4].e) / 2
dxf.text((road_mid_n + 12, road_mid_e), "TRAIL RIDGE ROAD (60' PUBLIC R/W)", height=7, layer="TEXT-LABELS")

# title block text (upper area, offset above the boundary bounding box)
max_n = max(p.n for p in pts)
min_e = min(p.e for p in pts)
title_n = max_n + 80
dxf.text((title_n, min_e), "TRAIL RIDGE ESTATES -- PB 82 PG 35-40, CLAY COUNTY, FL", height=14, layer="TITLEBLOCK")
dxf.text((title_n - 20, min_e), "SE 1/4 of SW 1/4, Section 19, T4S, R25E", height=8, layer="TITLEBLOCK")
dxf.text((title_n - 32, min_e), f"Boundary closure: {rpt['error_dist']:.3f} ft "
          f"(1 in {rpt['precision_1_in']:.0f})  |  Perimeter: {rpt['perimeter']:.2f} ft", height=6, layer="TITLEBLOCK")
dxf.text((title_n - 44, min_e), "Bearing basis: S89*42'22\"E along S'ly R/W line of Trail Ridge Rd (Sheet 2, Note 3)", height=6, layer="TITLEBLOCK")
dxf.text((title_n - 56, min_e), "ITERATION 1 -- boundary only. Sheet 6/6 (Pg 40) not yet supplied;", height=6, layer="TITLEBLOCK")
dxf.text((title_n - 66, min_e), "lot fabric, Tract A/B, and remaining curve/line rows pending.", height=6, layer="TITLEBLOCK")

out_path = "dxf/PB0082_P0035_TrailRidgeEstates_iter1_boundary.dxf"
dxf.save(out_path)
print("Saved:", out_path)
print("Closure:", rpt)
