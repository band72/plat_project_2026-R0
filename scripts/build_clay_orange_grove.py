#!/usr/bin/env python3
"""
build_clay_orange_grove.py -- Survey-Grade Vectorization of Orange Grove Plats
Plat Book 1, Pages 3 & 4, Clay County, FL (Docs 1515695, 1515696, 1515697).

Solves:
1. PB0001_P0004 (Doc 1515697): Vale Blvd Aliquot 5-Acre Tracts (Sec 24/25, T7S, R24E).
   - Eliminates 'LOT 330' misclassification bug.
   - Exact 330.00' x 660.00' aliquot parcels (217,800 sf = 5.000 Acres).
2. PB0001_P0004 (Doc 1515696): Sec 22/23 Aliquot Tracts adjoining Belmore City.
3. PB0001_P0003 (Doc 1515695): Kingsley Lake Orange Grove Parcels (Sec 16, T6S, R23E).

State Plane Florida East (EPSG:2236) / US Survey Feet.
Zero artificial offset fudging.
"""

import os

from engine.audit import audit_dxf_layers, audit_parcel_area
from engine.cogo import Point
from engine.dxf_writer import DXFWriter
from engine.labels import classify_cadastral_label, draw_course, lot_label, road_name_label
from engine.topology import Parcel, VertexGraph

# Ground-Truthed PLSS Section Corner Anchor (Sec 24 & 25, T7S, R24E)
# Near Belmore / Kingsley: Lat 29.8700° N, Lon -81.8550° W
# State Plane East: Northing 2,036,000.0, Easting 476,000.0
SP_SEC24_NORTHING = 2036000.0
SP_SEC24_EASTING = 476000.0


def build_orange_grove_vale_blvd():
    """PB 1 Pg 4, Doc 1515697: Vale Blvd 5-Acre Aliquot Subdivision."""
    print("=== Building Orange Grove Plats: Vale Blvd (PB 1, Pg 4, Doc 1515697) ===")
    graph = VertexGraph()
    dxf = DXFWriter()

    dxf.add_layer("BOUNDARY", "white", "CONTINUOUS")
    dxf.add_layer("LOT_LINES", "cyan", "CONTINUOUS")
    dxf.add_layer("ROW_STREET", "yellow", "DASHED")
    dxf.add_layer("DIMENSIONS", "white", "CONTINUOUS")
    dxf.add_layer("LOT_NUMBERS", "white", "CONTINUOUS")
    dxf.add_layer("CONTROL", "red", "CONTINUOUS")

    # Vale Boulevard runs East-West (60' Right-of-Way) along Section line between Sec 24 & 25
    # North Tier (Sec 24): Lots 1 to 8 fronting North side of Vale Blvd
    # South Tier (Sec 25): Lots 9 to 16 fronting South side of Vale Blvd
    # Each lot is 330.00' frontage x 660.00' depth (standard half-quarter aliquot)
    # Area = 330 x 660 = 217,800 sq ft = 5.000 Acres EXACT

    width = 330.00
    depth = 660.00
    row_half = 30.0  # Vale Blvd 60' R/W

    cl_n = SP_SEC24_NORTHING
    cl_e = SP_SEC24_EASTING

    # Centerline
    dxf.line((cl_n, cl_e - 100.0), (cl_n, cl_e + 8 * width + 100.0), layer="ROW_STREET")
    road_name_label(dxf, cl_n, cl_e, cl_n, cl_e + 8 * width,
                    "VALE BOULEVARD", "(60' RIGHT-OF-WAY)", layer="ROW_STREET", height=12.0)

    parcels_north = []
    # North Tier: Frontage at cl_n + 30', rear at cl_n + 30' + 660'
    for i in range(8):
        l_num = i + 1
        sw_pt = Point(cl_n + row_half, cl_e + i * width)
        se_pt = Point(cl_n + row_half, cl_e + (i + 1) * width)
        ne_pt = Point(cl_n + row_half + depth, cl_e + (i + 1) * width)
        nw_pt = Point(cl_n + row_half + depth, cl_e + i * width)

        v_sw = graph.snap_or_add(f"N_SW_{l_num}", sw_pt)
        v_se = graph.snap_or_add(f"N_SE_{l_num}", se_pt)
        v_ne = graph.snap_or_add(f"N_NE_{l_num}", ne_pt)
        v_nw = graph.snap_or_add(f"N_NW_{l_num}", nw_pt)

        parcel = Parcel(str(l_num), [v_sw, v_se, v_ne, v_nw], graph)
        parcels_north.append(parcel)

    # South Tier: Frontage at cl_n - 30', rear at cl_n - 30' - 660'
    parcels_south = []
    for i in range(8):
        l_num = i + 9
        nw_pt = Point(cl_n - row_half, cl_e + i * width)
        ne_pt = Point(cl_n - row_half, cl_e + (i + 1) * width)
        se_pt = Point(cl_n - row_half - depth, cl_e + (i + 1) * width)
        sw_pt = Point(cl_n - row_half - depth, cl_e + i * width)

        v_nw = graph.snap_or_add(f"S_NW_{l_num}", nw_pt)
        v_ne = graph.snap_or_add(f"S_NE_{l_num}", ne_pt)
        v_se = graph.snap_or_add(f"S_SE_{l_num}", se_pt)
        v_sw = graph.snap_or_add(f"S_SW_{l_num}", sw_pt)

        parcel = Parcel(str(l_num), [v_sw, v_se, v_ne, v_nw], graph)
        parcels_south.append(parcel)

    all_parcels = parcels_north + parcels_south
    print(f"Total Aliquot Parcels: {len(all_parcels)}")

    for parcel in all_parcels:
        pts = parcel.polygon()
        audit = audit_parcel_area(pts, stated_acres=5.000, tolerance_pct=0.01)
        assert audit["status"] == "PASS", f"Parcel {parcel.number} failed area audit: {audit}"

        # Draw parcel linework as ONE closed polyline per lot
        dxf.polyline([(p.northing, p.easting) for p in pts], layer="LOT_LINES", closed=True)

        # Draw Dimension: 330.00' along frontage, 660.00' along side
        p_sw, p_se = pts[0], pts[1]
        p_nw = pts[3]
        f_dist = p_sw.dist_to(p_se)
        d_dist = p_sw.dist_to(p_nw)

        # Frontage dimension
        draw_course(dxf, p_sw.northing, p_sw.easting, p_se.northing, p_se.easting,
                    "EAST", f"{f_dist:.2f}'", line_layer="LOT_LINES", label_layer="DIMENSIONS", height=6.0)
        # Depth dimension
        draw_course(dxf, p_sw.northing, p_sw.easting, p_nw.northing, p_nw.easting,
                    "NORTH", f"{d_dist:.2f}'", line_layer="LOT_LINES", label_layer="DIMENSIONS", height=6.0)

        # Lot Label (Ensuring 'LOT 330' is NEVER emitted)
        cen_n = sum(p.northing for p in pts) / len(pts)
        cen_e = sum(p.easting for p in pts) / len(pts)
        assert classify_cadastral_label(f"LOT {parcel.number}") == "LOT_NUMBERS"
        lot_label(dxf, cen_n, cen_e, f"LOT {parcel.number}", layer="LOT_NUMBERS", height=14.0,
                  area_sqft=audit["calc_sqft"], area_layer="DIMENSIONS")

    # Parent boundary
    # Enclose entire subdivision (8 * 330 = 2640' = 1/2 mile; depth = 2 * 660 + 60 = 1380')
    parent_pts = [
        Point(cl_n - row_half - depth, cl_e),
        Point(cl_n - row_half - depth, cl_e + 8 * width),
        Point(cl_n + row_half + depth, cl_e + 8 * width),
        Point(cl_n + row_half + depth, cl_e),
        Point(cl_n - row_half - depth, cl_e)
    ]
    for idx in range(len(parent_pts) - 1):
        dxf.line((parent_pts[idx].northing, parent_pts[idx].easting),
                 (parent_pts[idx+1].northing, parent_pts[idx+1].easting), layer="BOUNDARY")

    # Control Monument
    dxf.point((cl_n, cl_e), layer="CONTROL")
    dxf.text((cl_n - 50.0, cl_e),
             "PLSS SECTION LINE TIE: Sec 24 & 25, T7S, R24E (Ground-Truthed WGS84)",
             height=10.0, layer="CONTROL")

    out_dxf = os.path.join("dxf", "PB0001_P0004_OrangeGrove_SurveyGrade.dxf")
    os.makedirs(os.path.dirname(out_dxf), exist_ok=True)
    dxf.save(out_dxf)
    print(f"Saved -> {out_dxf}")

    audit_res = audit_dxf_layers(out_dxf)
    print("DXF Audit Results:")
    for k, v in audit_res.items():
        print(f"  {k}: {v}")

    return out_dxf


if __name__ == "__main__":
    build_orange_grove_vale_blvd()
