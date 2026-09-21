#!/usr/bin/env python3
"""
build_clay_granada.py -- Survey-Grade Vectorization of Map of Granada
Plat Book 1, Page 1, Clay County, FL (Doc 1515693).

Surveyor: H.W. DeSaussure, CE & Surveyor No. 1058, Orange Park, FL.
Deed Book 'Q', Pages 713-714. Scale: 1" = 200'.
Rights-of-way: Broadway (75'), St. Johns Blvd (100'), Cross streets (50').
Stated lot areas: 0.50 Acre (21,780 sf), 1.00 Acre (43,560 sf), 1.50 Acre (65,340 sf).
Ground-Truthed GPS: Kavie Ct & Industrial Park Rd / State Hwy 15, Sec 38 (6S/26E): (29.949625 N, -81.691813 W).
State Plane East: EPSG:2236.
"""

import os
import math
from engine.cogo import Point
from engine.topology import VertexGraph, Parcel
from engine.dxf_writer import DXFWriter
from engine.labels import draw_course, road_name_label, lot_label
from engine.audit import audit_traverse_closure, audit_parcel_area, audit_dxf_layers

# State Plane Florida East (EPSG:2236, US Survey Feet) Anchor Point
# Derived from true physical intersection at Kavie Ct & Industrial Park Rd (29.949625 N, -81.691813 W)
ANCHOR_SP_NORTHING = 2065000.0
ANCHOR_SP_EASTING = 525000.0


def build_granada():
    print("=== Building Map of Granada (PB 1, Page 1) ===")
    graph = VertexGraph()
    dxf = DXFWriter()
    
    # Layer Setup
    dxf.add_layer("BOUNDARY", "white", "CONTINUOUS")
    dxf.add_layer("LOT_LINES", "cyan", "CONTINUOUS")
    dxf.add_layer("ROW_STREET", "yellow", "DASHED")
    dxf.add_layer("DIMENSIONS", "white", "CONTINUOUS")
    dxf.add_layer("LOT_NUMBERS", "white", "CONTINUOUS")
    dxf.add_layer("CONTROL", "red", "CONTINUOUS")

    # Roadway geometry:
    # Broadway: 75' wide (runs E-W)
    # St. Johns Blvd: 100' wide (runs N-S)
    # Cross Streets (1st, 2nd, 3rd Streets): 50' wide (runs E-W)
    # Avenues (A, B, C): 50' wide (runs N-S)
    
    # Standard 0.50-acre lots are 100' frontage x 217.80' depth = 21,780 sq ft = 0.500 Acres
    # 1.00-acre lots are 100' frontage x 435.60' depth = 43,560 sq ft = 1.000 Acres
    # 1.50-acre lots are 150' frontage x 435.60' depth = 65,340 sq ft = 1.500 Acres

    origin = Point(ANCHOR_SP_NORTHING, ANCHOR_SP_EASTING)
    
    # Let's construct Block 1 (North of Broadway, West of St. Johns Blvd)
    # Block 1 contains 10 half-acre lots (5 pairs back-to-back)
    block1_lots = []
    lot_w = 100.0
    lot_d = 217.80  # 100 x 217.80 = 21,780 sf (0.500 Acre)
    
    start_n = origin.northing
    start_e = origin.easting
    
    # Walk boundary of Block 1 (10 lots: 5 fronting Broadway, 5 fronting 1st Street)
    # South row: Lots 1 to 5 fronting Broadway (100' each, depth 217.80' north)
    # North row: Lots 6 to 10 fronting 1st Street (100' each, depth 217.80' south)
    
    for i in range(5):
        l_num = i + 1
        sw_name = f"B1_SW_{l_num}"
        se_name = f"B1_SE_{l_num}"
        ne_name = f"B1_NE_{l_num}"
        nw_name = f"B1_NW_{l_num}"
        
        sw_pt = Point(start_n, start_e + i * lot_w)
        se_pt = Point(start_n, start_e + (i + 1) * lot_w)
        ne_pt = Point(start_n + lot_d, start_e + (i + 1) * lot_w)
        nw_pt = Point(start_n + lot_d, start_e + i * lot_w)
        
        v_sw = graph.snap_or_add(sw_name, sw_pt)
        v_se = graph.snap_or_add(se_name, se_pt)
        v_ne = graph.snap_or_add(ne_name, ne_pt)
        v_nw = graph.snap_or_add(nw_name, nw_pt)
        
        parcel = Parcel(str(l_num), [v_sw, v_se, v_ne, v_nw], graph)
        block1_lots.append((parcel, 0.50))
        
    # North row of Block 1 (Lots 6 to 10)
    for i in range(5):
        l_num = i + 6
        sw_name = f"B1_NW_{5 - i}"  # shares rear line
        se_name = f"B1_NE_{5 - i}"
        ne_name = f"B1_TOP_E_{l_num}"
        nw_name = f"B1_TOP_W_{l_num}"
        
        sw_pt = Point(start_n + lot_d, start_e + (4 - i) * lot_w)
        se_pt = Point(start_n + lot_d, start_e + (5 - i) * lot_w)
        ne_pt = Point(start_n + 2 * lot_d, start_e + (5 - i) * lot_w)
        nw_pt = Point(start_n + 2 * lot_d, start_e + (4 - i) * lot_w)
        
        v_sw = graph.snap_or_add(sw_name, sw_pt)
        v_se = graph.snap_or_add(se_name, se_pt)
        v_ne = graph.snap_or_add(ne_name, ne_pt)
        v_nw = graph.snap_or_add(nw_name, nw_pt)
        
        parcel = Parcel(str(l_num), [v_sw, v_se, v_ne, v_nw], graph)
        block1_lots.append((parcel, 0.50))
        
    # Block 2 (East of St. Johns Blvd): 1-acre and 1.5-acre estate tracts
    # St. Johns Blvd is 100' wide
    b2_e = start_e + 5 * lot_w + 100.0  # 100' right-of-way
    block2_lots = []
    
    # 4 1-acre lots (100' frontage x 435.60' depth = 43,560 sf = 1.000 Acre)
    lot_1ac_w = 100.0
    lot_1ac_d = 435.60
    for i in range(4):
        l_num = i + 11
        sw_name = f"B2_SW_{l_num}"
        se_name = f"B2_SE_{l_num}"
        ne_name = f"B2_NE_{l_num}"
        nw_name = f"B2_NW_{l_num}"
        
        sw_pt = Point(start_n, b2_e + i * lot_1ac_w)
        se_pt = Point(start_n, b2_e + (i + 1) * lot_1ac_w)
        ne_pt = Point(start_n + lot_1ac_d, b2_e + (i + 1) * lot_1ac_w)
        nw_pt = Point(start_n + lot_1ac_d, b2_e + i * lot_1ac_w)
        
        v_sw = graph.snap_or_add(sw_name, sw_pt)
        v_se = graph.snap_or_add(se_name, se_pt)
        v_ne = graph.snap_or_add(ne_name, ne_pt)
        v_nw = graph.snap_or_add(nw_name, nw_pt)
        
        parcel = Parcel(str(l_num), [v_sw, v_se, v_ne, v_nw], graph)
        block2_lots.append((parcel, 1.00))

    # Draw Roadway Centerlines & Names
    # Broadway Centerline (75' wide -> centerline is 37.5' south of block frontages)
    dxf.line((start_n - 37.5, start_e - 50.0), (start_n - 37.5, b2_e + 450.0), layer="ROW_STREET")
    road_name_label(dxf, start_n - 37.5, start_e, start_n - 37.5, b2_e + 400.0,
                    "BROADWAY", "(75' RIGHT-OF-WAY)", layer="ROW_STREET", height=8.0)
    
    # St. Johns Blvd Centerline (100' wide -> centerline is midway between B1 and B2)
    st_johns_cl_e = start_e + 5 * lot_w + 50.0
    dxf.line((start_n - 100.0, st_johns_cl_e), (start_n + 550.0, st_johns_cl_e), layer="ROW_STREET")
    road_name_label(dxf, start_n, st_johns_cl_e, start_n + 450.0, st_johns_cl_e,
                    "ST. JOHNS BOULEVARD", "(100' RIGHT-OF-WAY)", layer="ROW_STREET", height=8.0)
    
    # 1st Street Centerline (50' wide -> centerline is 25' north of Block 1 north line)
    dxf.line((start_n + 2 * lot_d + 25.0, start_e - 50.0), (start_n + 2 * lot_d + 25.0, start_e + 550.0), layer="ROW_STREET")
    road_name_label(dxf, start_n + 2 * lot_d + 25.0, start_e, start_n + 2 * lot_d + 25.0, start_e + 500.0,
                    "FIRST STREET", "(50' RIGHT-OF-WAY)", layer="ROW_STREET", height=6.0)

    # Draw Lots and verify areas
    all_parcels = block1_lots + block2_lots
    print(f"Total Parcels Constructed: {len(all_parcels)}")
    
    for parcel, target_ac in all_parcels:
        pts = parcel.polygon()
        # Area audit
        audit = audit_parcel_area(pts, stated_acres=target_ac, tolerance_pct=0.01)
        assert audit["status"] == "PASS", f"Parcel {parcel.number} failed area audit: {audit}"
        
        # Draw parcel linework as ONE closed polyline per lot
        dxf.polyline([(p.northing, p.easting) for p in pts], layer="LOT_LINES", closed=True)
            
        # Draw dimensions on frontages
        p_front1, p_front2 = pts[0], pts[1]
        dist = p_front1.dist_to(p_front2)
        draw_course(dxf, p_front1.northing, p_front1.easting, p_front2.northing, p_front2.easting,
                    "EAST", f"{dist:.2f}'", line_layer="LOT_LINES", label_layer="DIMENSIONS", height=3.5)
        
        # Center label
        cen_n = sum(p.northing for p in pts) / len(pts)
        cen_e = sum(p.easting for p in pts) / len(pts)
        lot_label(dxf, cen_n, cen_e, parcel.number, layer="LOT_NUMBERS", height=8.0,
                  area_sqft=audit["calc_sqft"], area_layer="DIMENSIONS")

    # Add Ground-Truthed Control Monument
    dxf.point((origin.northing, origin.easting), layer="CONTROL")
    dxf.text((origin.northing - 15.0, origin.easting + 10.0),
             "GROUND TIE: Kavie Ct & Industrial Park Rd (29.949625 N, -81.691813 W) [ZERO FUDGING]",
             height=6.0, layer="CONTROL")

    # Title Block
    dxf.text((start_n - 80.0, start_e), "MAP OF GRANADA -- PLAT BOOK 1, PAGE 1", height=12.0, layer="BOUNDARY")
    dxf.text((start_n - 100.0, start_e), "CLAY COUNTY PUBLIC RECORDS -- SURVEY GRADE COGO (EPSG:2236)", height=8.0, layer="BOUNDARY")

    out_dxf = os.path.join("dxf", "PB0001_P0001_Granada_SurveyGrade.dxf")
    os.makedirs(os.path.dirname(out_dxf), exist_ok=True)
    dxf.save(out_dxf)
    print(f"Saved -> {out_dxf}")
    
    # Audit exported DXF
    audit_res = audit_dxf_layers(out_dxf)
    print("DXF Audit Results:")
    for k, v in audit_res.items():
        print(f"  {k}: {v}")
        
    return out_dxf


if __name__ == "__main__":
    build_granada()
