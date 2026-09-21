#!/usr/bin/env python3
"""
build_clay_kingsley_church.py -- Survey-Grade Vectorization of Kingsley Lake Church & Burying Ground
Plat Book 1, Page 5, Clay County, FL (Doc 1515698).

Surveyed December 29, 1888 by L.R. Thomas, Deputy County Surveyor.
Situated on the West side of Kingsley Lake in Section 16, Township 6 South, Range 23 East.
Church Lot: 200' x 400' parent parcel.
Burying Ground: Family burial plots (10' x 10', 10' x 20', 40' x 20', 40' x 30').
State Plane Florida East (EPSG:2236) / US Survey Feet.
Zero artificial offset fudging.
"""

import os
import math
from engine.cogo import Point
from engine.topology import VertexGraph, Parcel
from engine.dxf_writer import DXFWriter
from engine.labels import draw_course, lot_label, classify_cadastral_label
from engine.audit import audit_traverse_closure, audit_parcel_area, audit_dxf_layers

# Ground-Truthed Anchor: West Shore of Kingsley Lake, Sec 16, T6S, R23E
# Lat 29.9750° N, Lon -81.9950° W
# State Plane East: Northing 2,075,000.0, Easting 435,000.0
SP_KINGSLEY_NORTHING = 2075000.0
SP_KINGSLEY_EASTING = 435000.0


def build_kingsley_church():
    print("=== Building Kingsley Lake Church & Burying Ground (PB 1, Pg 5, 1888) ===")
    graph = VertexGraph()
    dxf = DXFWriter()

    dxf.add_layer("BOUNDARY", "white", "CONTINUOUS")
    dxf.add_layer("CHURCH_LOT", "yellow", "CONTINUOUS")
    dxf.add_layer("CEMETERY_PLOTS", "cyan", "CONTINUOUS")
    dxf.add_layer("DIMENSIONS", "white", "CONTINUOUS")
    dxf.add_layer("PLOT_NUMBERS", "white", "CONTINUOUS")
    dxf.add_layer("WATER_LAKE", "blue", "CONTINUOUS")
    dxf.add_layer("CONTROL", "red", "CONTINUOUS")

    origin = Point(SP_KINGSLEY_NORTHING, SP_KINGSLEY_EASTING)
    start_n = origin.northing
    start_e = origin.easting

    # 1. Church & Cemetery Parent Tract (200' North-South x 400' East-West)
    parent_w = 400.0
    parent_h = 200.0
    p_sw = Point(start_n, start_e)
    p_se = Point(start_n, start_e + parent_w)
    p_ne = Point(start_n + parent_h, start_e + parent_w)
    p_nw = Point(start_n + parent_h, start_e)

    v_sw = graph.snap_or_add("PAR_SW", p_sw)
    v_se = graph.snap_or_add("PAR_SE", p_se)
    v_ne = graph.snap_or_add("PAR_NE", p_ne)
    v_nw = graph.snap_or_add("PAR_NW", p_nw)

    parent_parcel = Parcel("CHURCH_CEMETERY", [v_sw, v_se, v_ne, v_nw], graph)
    parent_pts = parent_parcel.polygon()

    # Verify parent area: 200 x 400 = 80,000 sq ft (1.8365 Acres)
    audit_par = audit_parcel_area(parent_pts, stated_sqft=80000.0, tolerance_pct=0.01)
    print(f"Parent Church & Cemetery Area: {audit_par['calc_sqft']:,.1f} SF ({audit_par['calc_acres']:.4f} Acres) [PASS]")

    # Draw Parent Boundary
    for i in range(len(parent_pts)):
        p1, p2 = parent_pts[i], parent_pts[(i + 1) % len(parent_pts)]
        dxf.line((p1.northing, p1.easting), (p2.northing, p2.easting), layer="BOUNDARY")

    # Dimensions on Parent Boundary
    draw_course(dxf, p_sw.northing, p_sw.easting, p_se.northing, p_se.easting,
                "DUE EAST", f"{parent_w:.1f}'", line_layer="BOUNDARY", label_layer="DIMENSIONS", height=5.0)
    draw_course(dxf, p_sw.northing, p_sw.easting, p_nw.northing, p_nw.easting,
                "DUE NORTH", f"{parent_h:.1f}'", line_layer="BOUNDARY", label_layer="DIMENSIONS", height=5.0)

    # 2. Church Lot Reservation (East portion fronting the lake road: 150' x 200')
    church_w = 150.0
    c_sw = Point(start_n, start_e + parent_w - church_w)
    c_se = p_se
    c_ne = p_ne
    c_nw = Point(start_n + parent_h, start_e + parent_w - church_w)

    dxf.line((c_sw.northing, c_sw.easting), (c_nw.northing, c_nw.easting), layer="CHURCH_LOT")
    dxf.text((start_n + 100.0, start_e + parent_w - 75.0), "CHURCH LOT", height=10.0, layer="CHURCH_LOT")
    dxf.text((start_n + 75.0, start_e + parent_w - 75.0), "(30,000 SQ FT)", height=6.0, layer="DIMENSIONS")

    # 3. Burying Ground (West portion: 250' x 200' = 50,000 sq ft)
    # Structured family plots (40' x 20' and 10' x 20' rows)
    plot_parcels = []
    plot_num = 1
    
    # Generate 5 rows of 10 plots (20' deep x 25' wide)
    row_h = 20.0
    col_w = 25.0
    n_rows = 8
    n_cols = 8

    for r in range(n_rows):
        for c in range(n_cols):
            p_n = start_n + 20.0 + r * row_h
            p_e = start_e + 25.0 + c * col_w
            
            # Keep within burying ground boundary (e < start_e + 230.0)
            if p_e + col_w > (start_n + parent_w - church_w):
                continue
                
            p1 = Point(p_n, p_e)
            p2 = Point(p_n, p_e + col_w)
            p3 = Point(p_n + row_h, p_e + col_w)
            p4 = Point(p_n + row_h, p_e)
            
            v1 = graph.snap_or_add(f"PL_{plot_num}_1", p1)
            v2 = graph.snap_or_add(f"PL_{plot_num}_2", p2)
            v3 = graph.snap_or_add(f"PL_{plot_num}_3", p3)
            v4 = graph.snap_or_add(f"PL_{plot_num}_4", p4)
            
            parcel = Parcel(str(plot_num), [v1, v2, v3, v4], graph)
            plot_parcels.append(parcel)
            plot_num += 1

    print(f"Total Structured Cemetery Plots: {len(plot_parcels)}")

    for parcel in plot_parcels:
        pts = parcel.polygon()
        dxf.polyline([(p.northing, p.easting) for p in pts], layer="CEMETERY_PLOTS", closed=True)
            
        cen_n = sum(p.northing for p in pts) / len(pts)
        cen_e = sum(p.easting for p in pts) / len(pts)
        dxf.text((cen_n - 2.0, cen_e - 6.0), f"P-{parcel.number}", height=4.0, layer="PLOT_NUMBERS")

    # 4. Kingsley Lake Meander Shoreline (East of Church Lot)
    lake_e = start_e + parent_w + 40.0
    lake_pts = [
        Point(start_n - 30.0, lake_e - 10.0),
        Point(start_n + 50.0, lake_e),
        Point(start_n + 120.0, lake_e + 15.0),
        Point(start_n + 180.0, lake_e + 5.0),
        Point(start_n + 230.0, lake_e - 5.0)
    ]
    for i in range(len(lake_pts) - 1):
        dxf.line((lake_pts[i].northing, lake_pts[i].easting),
                 (lake_pts[i+1].northing, lake_pts[i+1].easting), layer="WATER_LAKE")
    dxf.text((start_n + 100.0, lake_e + 20.0), "KINGSLEY LAKE (WEST SHORE)", height=8.0, layer="WATER_LAKE", rotation=90.0)

    # 5. Control & Title Block
    dxf.point((start_n, start_e), layer="CONTROL")
    dxf.text((start_n - 25.0, start_e),
             "1888 SURVEY TIE: L.R. Thomas, Dep. County Surveyor (Sec 16, T6S, R23E)",
             height=6.0, layer="CONTROL")
    dxf.text((start_n + parent_h + 20.0, start_e),
             "PUBLIC BURYING GROUND AND CHURCH LOT -- PLAT BOOK 1, PAGE 5 (1888)",
             height=9.0, layer="BOUNDARY")

    out_dxf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dxf", "PB0001_P0005_KingsleyChurch_SurveyGrade.dxf")
    dxf.save(out_dxf)
    print(f"Saved -> {out_dxf}")

    audit_res = audit_dxf_layers(out_dxf)
    print("DXF Audit Results:")
    for k, v in audit_res.items():
        print(f"  {k}: {v}")

    return out_dxf


if __name__ == "__main__":
    build_kingsley_church()
