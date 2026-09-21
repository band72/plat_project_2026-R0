#!/usr/bin/env python3
"""
generate_lot_images_dxf.py -- Generate CAD DXF for all lots shown in the user's plat images.
Subdivision: Beachwood Unit Two (Plat Book 30, Pages 82 & 82A, Duval County, FL).

Features:
- Pure lot boundaries: true LINE and ARC entities
- Complete circular curve geometry (R=25' corner returns and roadway curves)
- All dimensions cut back from P.I. to PC/PT
- NO P.I. angle bar glyphs or artificial tick marks drawn
- Standard professional CAD survey layers:
    * LOT_BOUNDARY (White/Continuous)
    * CURVE (Cyan/Continuous)
    * LOT_NUMBERS (Green/Text)
    * DIMENSIONS (Yellow/Text)
    * STREET_RW (Red/Continuous)
    * MONUMENTS (Magenta/Points & Circles)
"""
import math
import os
import sys

from engine.cogo import Point, parse_bearing, azimuth_to_bearing
from engine.curves import solve_curve_all_parameters
from engine.dxf_writer import DXFWriter

def create_dxf():
    print("=" * 80)
    print("  GENERATING SURVEY-GRADE CAD DXF FOR PLAT LOT IMAGES")
    print("=" * 80)

    dxf = DXFWriter()
    dxf.add_layer("LOT_BOUNDARY", "white", "CONTINUOUS")
    dxf.add_layer("CURVE", "cyan", "CONTINUOUS")
    dxf.add_layer("CAD_ARCS", "cyan", "CONTINUOUS")
    dxf.add_layer("LOT_NUMBERS", "green", "CONTINUOUS")
    dxf.add_layer("DIMENSIONS", "yellow", "CONTINUOUS")
    dxf.add_layer("STREET_RW", "red", "CONTINUOUS")
    dxf.add_layer("STREET_TEXT", "yellow", "CONTINUOUS")
    dxf.add_layer("MONUMENTS", "magenta", "CONTINUOUS")
    dxf.add_layer("CURVE_DATA", "cyan", "CONTINUOUS")

    def draw_prm(pt: Point):
        # Draw small circle and point for Permanent Reference Monument
        dxf.point((pt.n, pt.e), layer="MONUMENTS")
        # Draw small 1.5-ft radius circle as 12-segment polyline
        circ_pts = []
        for a in range(13):
            rad = math.radians(a * 30.0)
            circ_pts.append((pt.n + 1.5 * math.sin(rad), pt.e + 1.5 * math.cos(rad)))
        dxf.polyline(circ_pts, layer="MONUMENTS", closed=True)
        dxf.text((pt.n + 2.5, pt.e + 2.5), "P.R.M.", height=2.5, layer="MONUMENTS")

    def draw_arc_segments(arc_pts, center=None, radius=None, layer="CURVE"):
        coords = [(p.n, p.e) for p in arc_pts]
        dxf.polyline(coords, layer=layer, closed=False)
        if center is not None and radius is not None and len(arc_pts) >= 2:
            p_start = arc_pts[0]
            p_end = arc_pts[-1]
            a1 = (math.degrees(math.atan2(p_start.n - center.n, p_start.e - center.e)) + 360.0) % 360.0
            a2 = (math.degrees(math.atan2(p_end.n - center.n, p_end.e - center.e)) + 360.0) % 360.0
            # AutoCAD ARC entity is ALWAYS counter-clockwise from start_angle to end_angle:
            # Check if arc_pts[1] increases or decreases angle
            p_mid = arc_pts[len(arc_pts)//2]
            a_mid = (math.degrees(math.atan2(p_mid.n - center.n, p_mid.e - center.e)) + 360.0) % 360.0
            # If CCW: a1 -> a_mid -> a2
            diff_ccw = (a2 - a1) % 360.0
            diff_mid = (a_mid - a1) % 360.0
            if diff_mid < diff_ccw:
                sa, ea = a1, a2
            else:
                sa, ea = a2, a1
            dxf.arc((center.n, center.e), radius, sa, ea, layer="CAD_ARCS")

    def draw_line(p1: Point, p2: Point, layer="LOT_BOUNDARY", label=None, height=2.2):
        dxf.line((p1.n, p1.e), (p2.n, p2.e), layer=layer)
        if label:
            mid_n = (p1.n + p2.n) / 2.0
            mid_e = (p1.e + p2.e) / 2.0
            # compute angle
            dn = p2.n - p1.n
            de = p2.e - p1.e
            ang = math.degrees(math.atan2(dn, de))
            # keep text upright
            if ang > 90: ang -= 180
            elif ang < -90: ang += 180
            # normal offset
            dist = math.hypot(dn, de)
            if dist > 1e-4:
                un = -de / dist; ue = dn / dist
                off_n = mid_n + un * 2.0
                off_e = mid_e + ue * 2.0
            else:
                off_n, off_e = mid_n, mid_e
            dxf.text((off_n, off_e), label, height=height, layer="DIMENSIONS", rotation=ang, halign=1, valign=2)

    # ==========================================================================
    # PANEL 1: BLOCK 15 -- LOTS 9 & 10 (East Boundary C2 Curve & Corner Returns)
    # Origin at (N=0, E=0) for SE corner of Lot 9 / NE corner of Lot 10
    # ==========================================================================
    eaz = parse_bearing("N87°35'30\"E")
    waz = parse_bearing("S87°35'30\"W")
    naz = parse_bearing("N02°24'30\"W")
    saz = parse_bearing("S02°24'30\"E")

    # Mid-line between Lot 9 and Lot 10
    p_mid_east = Point(0.0, 0.0)
    p_mid_west = p_mid_east.offset(waz, 92.99)

    # Lot 9:
    # NW corner
    p9_nw = p_mid_west.offset(naz, 100.00)
    # North P.I. is 95.98' east of NW
    p9_pi = p9_nw.offset(eaz, 95.98)
    # NE corner curve: R=25.0', Delta=87°04'31", T=23.76'
    T9 = 23.76
    p9_pc = p9_pi.offset(waz, T9) # on North line
    # Arc of NE corner curve: 37.99'
    # Tangent from P.I. heading south along Beachwood Blvd is S05°19'59"E
    chord9_az = parse_bearing("S48°52'14\"E")
    p9_pt = p9_pc.offset(chord9_az, 34.44)
    # East boundary remaining C2 curve from p9_pt to p_mid_east:
    # Arc = 100.04 - 23.76 = 76.28'
    # Let us sample arc points for Beachwood Blvd curve (R=1959.86')
    r_c2 = 1959.86
    # Center of C2 curve is to the west
    # Mid-line radial bearing is S87°35'30"W
    center_c2 = p_mid_east.offset(waz, r_c2)

    # Lot 9 C2 arc:
    # angle at mid-line = math.atan2(p_mid_east.n - center_c2.n, p_mid_east.e - center_c2.e)
    ang_mid = math.atan2(p_mid_east.n - center_c2.n, p_mid_east.e - center_c2.e)
    # Delta for 76.28' arc = 76.28 / 1959.86 rad
    delta_lot9_c2 = 76.28 / r_c2
    c2_pts_9 = []
    for step in range(11):
        frac = step / 10.0
        ang = ang_mid + delta_lot9_c2 * (1.0 - frac)
        c2_pts_9.append(Point(center_c2.n + r_c2 * math.sin(ang), center_c2.e + r_c2 * math.cos(ang)))

    # Corner return arc for Lot 9 (R=25')
    center_9_corner = p9_pc.offset(saz, 25.0)
    ang_pc9 = math.atan2(p9_pc.n - center_9_corner.n, p9_pc.e - center_9_corner.e)
    delta_ret9 = math.radians(87.0 + 4.0/60.0 + 31.0/3600.0)
    ret_pts_9 = []
    for step in range(11):
        frac = step / 10.0
        ang = ang_pc9 - delta_ret9 * frac # CW
        ret_pts_9.append(Point(center_9_corner.n + 25.0 * math.sin(ang), center_9_corner.e + 25.0 * math.cos(ang)))

    # Draw Lot 9
    draw_line(p9_nw, p9_pc, layer="LOT_BOUNDARY", label="72.22' (95.98' to P.I.)")
    draw_arc_segments(ret_pts_9, center=center_9_corner, radius=25.0, layer="CURVE")
    draw_arc_segments(c2_pts_9, center=center_c2, radius=r_c2, layer="CURVE")
    draw_line(p_mid_east, p_mid_west, layer="LOT_BOUNDARY", label="92.99'")
    draw_line(p_mid_west, p9_nw, layer="LOT_BOUNDARY", label="100.00'   N 2°24'30\" W")

    # Annotations for Lot 9
    p9_center = Point((p9_nw.n + p_mid_west.n) / 2.0, (p9_nw.e + p_mid_east.e) / 2.0)
    dxf.text((p9_center.n + 4.0, p9_center.e - 5.0), "9", height=8.0, layer="LOT_NUMBERS", halign=1, valign=2)
    dxf.text((p9_center.n - 8.0, p9_center.e - 5.0), "9,372.1 SF", height=3.0, layer="DIMENSIONS", halign=1, valign=2)
    dxf.text((p9_center.n - 13.0, p9_center.e - 5.0), "0.2152 Acres", height=2.5, layer="DIMENSIONS", halign=1, valign=2)

    # Lot 10:
    # SW corner (P.R.M. monument)
    p10_sw = p_mid_west.offset(saz, 100.00)
    # SE P.I. is 90.00' east of SW
    p10_pi = p10_sw.offset(eaz, 90.00)
    T10 = 23.76
    p10_pt = p10_pi.offset(waz, T10) # on Keel Drive
    # SE corner curve: R=25.0', Delta=87°04'31", T=23.76'
    # Beachwood Blvd curve C2 continues south from p_mid_east for 76.28'
    delta_lot10_c2 = 76.28 / r_c2
    c2_pts_10 = []
    for step in range(11):
        frac = step / 10.0
        ang = ang_mid - delta_lot10_c2 * frac
        c2_pts_10.append(Point(center_c2.n + r_c2 * math.sin(ang), center_c2.e + r_c2 * math.cos(ang)))
    p10_pc = c2_pts_10[-1]

    # Corner return arc for Lot 10 (R=25')
    center_10_corner = p10_pt.offset(naz, 25.0)
    ang_pt10 = math.atan2(p10_pt.n - center_10_corner.n, p10_pt.e - center_10_corner.e)
    ret_pts_10 = []
    for step in range(11):
        frac = step / 10.0
        ang = (ang_pt10 + delta_ret9) - delta_ret9 * frac # from pc to pt
        ret_pts_10.append(Point(center_10_corner.n + 25.0 * math.sin(ang), center_10_corner.e + 25.0 * math.cos(ang)))

    # Draw Lot 10
    draw_arc_segments(c2_pts_10, center=center_c2, radius=r_c2, layer="CURVE")
    draw_arc_segments(ret_pts_10, center=center_10_corner, radius=25.0, layer="CURVE")
    draw_line(p10_pt, p10_sw, layer="LOT_BOUNDARY", label="66.24' (90.00' to P.I.)")
    draw_line(p10_sw, p_mid_west, layer="LOT_BOUNDARY", label="100.00'   N 2°24'30\" W")
    draw_prm(p10_sw)

    # Annotations for Lot 10
    p10_center = Point((p_mid_west.n + p10_sw.n) / 2.0, (p_mid_west.e + p_mid_east.e) / 2.0)
    dxf.text((p10_center.n + 4.0, p10_center.e - 5.0), "10", height=8.0, layer="LOT_NUMBERS", halign=1, valign=2)
    dxf.text((p10_center.n - 8.0, p10_center.e - 5.0), "9,073.1 SF", height=3.0, layer="DIMENSIONS", halign=1, valign=2)
    dxf.text((p10_center.n - 13.0, p10_center.e - 5.0), "0.2083 Acres", height=2.5, layer="DIMENSIONS", halign=1, valign=2)

    # Street R/W labels around Lots 9 & 10
    dxf.text((p9_nw.n + 15.0, p9_nw.e + 40.0), "SHELLFISH DRIVE (60' R/W)   N 87°35'30\" E", height=3.8, layer="STREET_TEXT")
    dxf.text((p10_sw.n - 18.0, p10_sw.e + 20.0), "KEEL DRIVE (60' R/W)   S 87°35'30\" W", height=3.8, layer="STREET_TEXT")
    dxf.text((p_mid_east.n, p_mid_east.e + 25.0), "BEACHWOOD BLVD (80' R/W)  C2: R=1959.86'", height=3.5, layer="STREET_TEXT", rotation=-90)

    # Curve Data Labels
    dxf.text((p9_pc.n + 6.0, p9_pc.e + 10.0), "R=25.00'  L=37.99'", height=2.2, layer="CURVE_DATA")
    dxf.text((p10_pt.n - 8.0, p10_pt.e + 5.0), "R=25.00'  L=37.99'", height=2.2, layer="CURVE_DATA")
    dxf.text((p_mid_east.n + 10.0, p_mid_east.e + 6.0), "Arc=100.04' (to P.I.)", height=2.2, layer="CURVE_DATA", rotation=-90)
    dxf.text((p_mid_east.n - 25.0, p_mid_east.e + 6.0), "Arc=100.04' (to P.I.)", height=2.2, layer="CURVE_DATA", rotation=-90)

    # ==========================================================================
    # PANEL 2: BLOCK 14 -- LOTS 24 & 23 (Mangrove Ave Frontage & Corner Returns)
    # Placed at Easting offset = 260.0 ft
    # ==========================================================================
    p14_base_e = 260.0
    p14_base_n = 0.0

    # Intermediate line between 23 and 24
    p24_sw = Point(p14_base_n, p14_base_e)
    p24_se = p24_sw.offset(parse_bearing("N88°58'20\"E"), 102.38)

    # Lot 24 NW P.I. is 100.74' north along Mangrove Ave (N01°01'40"W)
    p24_nw_pi = p24_sw.offset(parse_bearing("N01°01'40\"W"), 100.74)
    # NW corner return: R=25.0', Delta=88°37'10", T=24.40'
    T24 = 24.40
    p24_pc = p24_nw_pi.offset(parse_bearing("S01°01'40\"E"), T24) # on Mangrove Ave
    p24_pt = p24_nw_pi.offset(parse_bearing("N87°35'30\"E"), T24) # on North Street
    p24_ne = p24_nw_pi.offset(parse_bearing("N87°35'30\"E"), 99.93) # P.R.M. monument

    # Corner return arc for Lot 24 (R=25')
    center_24_corner = p24_pc.offset(parse_bearing("N88°58'20\"E"), 25.0)
    ang_pc24 = math.atan2(p24_pc.n - center_24_corner.n, p24_pc.e - center_24_corner.e)
    delta_ret24 = math.radians(88.0 + 37.0/60.0 + 10.0/3600.0)
    ret_pts_24 = []
    for step in range(11):
        frac = step / 10.0
        ang = ang_pc24 + delta_ret24 * frac # CCW
        ret_pts_24.append(Point(center_24_corner.n + 25.0 * math.sin(ang), center_24_corner.e + 25.0 * math.cos(ang)))

    # Draw Lot 24
    draw_line(p24_sw, p24_pc, layer="LOT_BOUNDARY", label="76.34' (100.74' to P.I.)")
    draw_arc_segments(ret_pts_24, center=center_24_corner, radius=25.0, layer="CURVE")
    draw_line(p24_pt, p24_ne, layer="LOT_BOUNDARY", label="75.53' (99.93' to P.I.)")
    draw_line(p24_ne, p24_se, layer="LOT_BOUNDARY", label="103.17'   S 2°24'30\" E")
    draw_line(p24_se, p24_sw, layer="LOT_BOUNDARY", label="102.38'   S 88°58'20\" W")
    draw_prm(p24_ne)

    # Annotations for Lot 24
    p24_center = Point(p24_sw.n + 50.0, p24_sw.e + 50.0)
    dxf.text((p24_center.n + 4.0, p24_center.e), "24", height=8.0, layer="LOT_NUMBERS", halign=1, valign=2)
    dxf.text((p24_center.n - 8.0, p24_center.e), "10,185.3 SF", height=3.0, layer="DIMENSIONS", halign=1, valign=2)
    dxf.text((p24_center.n - 13.0, p24_center.e), "0.2338 Acres", height=2.5, layer="DIMENSIONS", halign=1, valign=2)

    # Lot 23:
    # East line: 100.44' @ S01°58'48"W
    p23_se = p24_se.offset(parse_bearing("S01°58'48\"W"), 100.44)
    # South line seg 1: 17.08' @ S89°58'20"W
    p23_angle = p23_se.offset(parse_bearing("S89°58'20\"W"), 17.08)
    # South line seg 2 extends to SW P.I. (80.00' total from angle pt)
    p23_sw_pi = p23_angle.offset(parse_bearing("S88°58'20\"W"), 80.00)
    # SW corner return curve: R=25.0', Delta=90°00'00", T=25.00'
    T23 = 25.00
    p23_pc = p23_sw_pi.offset(parse_bearing("N88°58'20\"E"), T23) # on south street
    p23_pt = p23_sw_pi.offset(parse_bearing("N01°01'40\"W"), T23) # on Mangrove Ave

    # Corner return arc for Lot 23 (R=25')
    center_23_corner = p23_pc.offset(parse_bearing("N01°01'40\"W"), 25.0)
    ang_pc23 = math.atan2(p23_pc.n - center_23_corner.n, p23_pc.e - center_23_corner.e)
    delta_ret23 = math.radians(90.0)
    ret_pts_23 = []
    for step in range(11):
        frac = step / 10.0
        ang = ang_pc23 - delta_ret23 * frac # CW
        ret_pts_23.append(Point(center_23_corner.n + 25.0 * math.sin(ang), center_23_corner.e + 25.0 * math.cos(ang)))

    # Draw Lot 23
    draw_line(p24_se, p23_se, layer="LOT_BOUNDARY", label="100.44'   S 1°58'48\" W")
    draw_line(p23_se, p23_angle, layer="LOT_BOUNDARY", label="17.08'  S 89°58'20\" W")
    draw_line(p23_angle, p23_pc, layer="LOT_BOUNDARY", label="55.00' (80.00' to P.I.)")
    draw_arc_segments(ret_pts_23, center=center_23_corner, radius=25.0, layer="CURVE")
    draw_line(p23_pt, p24_sw, layer="LOT_BOUNDARY", label="75.00' (100.00' to P.I.)")

    # Annotations for Lot 23
    p23_center = Point(p24_sw.n - 50.0, p24_sw.e + 50.0)
    dxf.text((p23_center.n + 4.0, p23_center.e), "23", height=8.0, layer="LOT_NUMBERS", halign=1, valign=2)
    dxf.text((p23_center.n - 8.0, p23_center.e), "9,842.5 SF", height=3.0, layer="DIMENSIONS", halign=1, valign=2)
    dxf.text((p23_center.n - 13.0, p23_center.e), "0.2259 Acres", height=2.5, layer="DIMENSIONS", halign=1, valign=2)

    # Street R/W labels around Lots 24 & 23
    dxf.text((p24_nw_pi.n + 15.0, p24_nw_pi.e + 30.0), "STREET (60' R/W)   N 87°35'30\" E", height=3.8, layer="STREET_TEXT")
    dxf.text((p23_sw_pi.n - 18.0, p23_sw_pi.e + 20.0), "STREET (60' R/W)   N 88°58'20\" E", height=3.8, layer="STREET_TEXT")
    dxf.text((p24_sw.n, p24_sw.e - 20.0), "MANGROVE AVENUE (60' R/W)   N 01°01'40\" W", height=3.8, layer="STREET_TEXT", rotation=90)

    # Curve Data Labels for Lots 24 & 23
    dxf.text((p24_nw_pi.n + 6.0, p24_nw_pi.e - 2.0), "R=25.00'  L=38.67'", height=2.2, layer="CURVE_DATA")
    dxf.text((p23_sw_pi.n - 8.0, p23_sw_pi.e - 2.0), "R=25.00'  L=39.27'", height=2.2, layer="CURVE_DATA")

    # Title Block
    dxf.text((150.0, 150.0), "BEACHWOOD UNIT TWO -- PLAT BOOK 30, PAGES 82 & 82A, DUVAL COUNTY, FL", height=6.0, layer="STREET_TEXT")
    dxf.text((135.0, 150.0), "CADASTRAL SURVEY AUDIT: LOTS 9 & 10 (BLOCK 15) AND LOTS 23 & 24 (BLOCK 14)", height=4.5, layer="STREET_TEXT")
    dxf.text((122.0, 150.0), "ALL LOT CORNER RETURNS MODELED WITH TRUE CURVES (R=25.00') & DEDUCTED TANGENTS", height=3.2, layer="STREET_TEXT")

    out_path = "dxf/PB0030_P0082_User_Lots_MapCheck.dxf"
    dxf.save(out_path)
    print(f"Master DXF saved to: {out_path}")

    # Also save companion copy
    alt_path = "dxf/PB0030_P0082_Lot_Images.dxf"
    dxf.save(alt_path)
    print(f"Companion DXF saved to: {alt_path}")

if __name__ == "__main__":
    create_dxf()
