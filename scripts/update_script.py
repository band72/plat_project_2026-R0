with open("generate_lot_images_dxf.py", "r") as f:
    code = f.read()

# Replace draw_arc_segments to also add true CAD ARC entity:
old_def = """    def draw_arc_segments(arc_pts, layer="CURVE"):
        coords = [(p.n, p.e) for p in arc_pts]
        dxf.polyline(coords, layer=layer, closed=False)"""

new_def = """    def draw_arc_segments(arc_pts, center=None, radius=None, layer="CURVE"):
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
            dxf.arc((center.n, center.e), radius, sa, ea, layer="CAD_ARCS")"""

code = code.replace(old_def, new_def)
code = code.replace('dxf.add_layer("CURVE", "cyan", "CONTINUOUS")', 'dxf.add_layer("CURVE", "cyan", "CONTINUOUS")\n    dxf.add_layer("CAD_ARCS", "cyan", "CONTINUOUS")')
code = code.replace('draw_arc_segments(ret_pts_9, layer="CURVE")', 'draw_arc_segments(ret_pts_9, center=center_9_corner, radius=25.0, layer="CURVE")')
code = code.replace('draw_arc_segments(c2_pts_9, layer="CURVE")', 'draw_arc_segments(c2_pts_9, center=center_c2, radius=r_c2, layer="CURVE")')
code = code.replace('draw_arc_segments(c2_pts_10, layer="CURVE")', 'draw_arc_segments(c2_pts_10, center=center_c2, radius=r_c2, layer="CURVE")')
code = code.replace('draw_arc_segments(ret_pts_10, layer="CURVE")', 'draw_arc_segments(ret_pts_10, center=center_10_corner, radius=25.0, layer="CURVE")')
code = code.replace('draw_arc_segments(ret_pts_24, layer="CURVE")', 'draw_arc_segments(ret_pts_24, center=center_24_corner, radius=25.0, layer="CURVE")')
code = code.replace('draw_arc_segments(ret_pts_23, layer="CURVE")', 'draw_arc_segments(ret_pts_23, center=center_23_corner, radius=25.0, layer="CURVE")')

with open("generate_lot_images_dxf.py", "w") as f:
    f.write(code)

print("Updated generate_lot_images_dxf.py")
