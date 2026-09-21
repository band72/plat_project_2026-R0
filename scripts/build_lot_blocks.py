import sys
sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing, azimuth_to_bearing
from engine.lots import rect_row, rect_column_pair, Lot
from engine.dxf_writer import DXFWriter
import data.lots_sheets_3_4 as ld

dxf = DXFWriter()
dxf.add_layer("LOT_LINE", "cyan", "CONTINUOUS")
dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
dxf.add_layer("BLOCK_TITLE", "yellow", "CONTINUOUS")
dxf.add_layer("ROW_STREET", "gray", "DASHED")
dxf.add_layer("ROAD_NAME", "yellow", "CONTINUOUS")
dxf.add_layer("EASEMENT", "green", "DASHED")
dxf.add_layer("DIM-LABELS", "white", "CONTINUOUS")

all_lots = []      # (block_name, Lot)
block_reports = []

def draw_lot(lot: Lot, layer="LOT_LINE", dim_labels=True):
    pts = lot.close()
    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i + 1]
        dxf.line((p1.n, p1.e), (p2.n, p2.e), layer=layer)
        if dim_labels:
            # bearing/distance label at each side's midpoint, offset perpendicular
            import math
            dn, de = p2.n - p1.n, p2.e - p1.e
            dist = math.hypot(dn, de)
            az = math.degrees(math.atan2(de, dn)) % 360
            mid_n, mid_e = (p1.n + p2.n) / 2, (p1.e + p2.e) / 2
            perp_az = (az + 90) % 360
            off = mid_n + 1.2 * math.cos(math.radians(perp_az)), mid_e + 1.2 * math.sin(math.radians(perp_az))
            dxf.text(off, f"{azimuth_to_bearing(az)}  {dist:.2f}'", height=2.2, layer="DIM-LABELS")
    cen_n = sum(p.n for p in lot.corners) / len(lot.corners)
    cen_e = sum(p.e for p in lot.corners) / len(lot.corners)
    dxf.text((cen_n - 4, cen_e - 10), f"LOT {lot.number}", height=6, layer="TEXT-LABELS")
    dxf.text((cen_n - 12, cen_e - 10), f"{lot.area_sqft:,.0f} sf", height=4, layer="TEXT-LABELS")

def draw_easement(p1: Point, p2: Point, width=10.0, label=True):
    """Schematic 10' CCUA/CEC utility easement centered on a shared lot line,
    per Sheet 2 General Notes 6, 9, 10 (blanket + explicit utility easements)."""
    import math
    dn, de = p2.n - p1.n, p2.e - p1.e
    dist = math.hypot(dn, de)
    if dist < 1e-6:
        return
    az = math.degrees(math.atan2(de, dn)) % 360
    perp = (az + 90) % 360
    half = width / 2.0
    o1 = p1.offset(perp, half); o2 = p2.offset(perp, half)
    o3 = p2.offset(perp, -half); o4 = p1.offset(perp, -half)
    dxf.line((o1.n, o1.e), (o2.n, o2.e), layer="EASEMENT")
    dxf.line((o4.n, o4.e), (o3.n, o3.e), layer="EASEMENT")
    if label:
        mid_n, mid_e = (p1.n + p2.n) / 2, (p1.e + p2.e) / 2
        dxf.text((mid_n, mid_e), "10' CCUA/CEC EASEMENT", height=2.0, layer="TEXT-LABELS", rotation=(az if az <= 90 or az >= 270 else az - 180))

def block_title(origin: Point, text: str, dy=40):
    dxf.text((origin.n + dy, origin.e), text, height=10, layer="BLOCK_TITLE")

# ============ Block A: Lots 1-8 ============
origin_a = Point(n=0.0, e=0.0)  # local frame, NW corner of Lot 8
block_title(origin_a, "BLOCK A -- Sheet 3, Lots 1-8 (local coords)")
cfg = ld.BLOCK_A_LOTS_1_8
lots_a = rect_row(origin_a, cfg["front_bearing"], cfg["depth_bearing"],
                   widths=[cfg["lot_width"]] * len(cfg["numbers"]),
                   depth=cfg["lot_depth"], numbers=cfg["numbers"])
for lot in lots_a:
    draw_lot(lot)
    all_lots.append(("A", lot))
# shared interior side lines get a utility easement (all internal verticals
# between adjacent lots; the two outer ends do not, per plat convention)
for i in range(len(lots_a) - 1):
    shared_top = lots_a[i].corners[0]     # NW-ish corner of lot i shared w/ lot i+1's NE-ish
    shared_bot = lots_a[i].corners[3]
    draw_easement(shared_top, shared_bot, label=(i == 0))
# road name -- lots 1-8 front the Copeland Way / Tract E frontage
front_mid = Point(n=(lots_a[0].corners[0].n + lots_a[-1].corners[1].n) / 2,
                   e=(lots_a[0].corners[0].e + lots_a[-1].corners[1].e) / 2)
dxf.text((front_mid.n + 6, front_mid.e - 60), "COPELAND WAY (60' PRIVATE R/W)", height=6, layer="ROAD_NAME")
rear_mid = Point(n=(lots_a[0].corners[3].n + lots_a[-1].corners[2].n) / 2,
                  e=(lots_a[0].corners[3].e + lots_a[-1].corners[2].e) / 2)
dxf.text((rear_mid.n - 8, rear_mid.e - 60), "TRACT E (BUFFER)", height=6, layer="ROAD_NAME")
total_w_a = cfg["lot_width"] * len(cfg["numbers"])
block_reports.append(dict(block="A", n_lots=len(lots_a),
                           expected_each_sqft=cfg["lot_width"] * cfg["lot_depth"],
                           computed_areas=[round(l.area_sqft, 1) for l in lots_a],
                           row_total_width=total_w_a))

# ============ Block B: Murrell Loop columns ============
origin_b_start = Point(n=1000.0, e=0.0)  # offset away from block A on canvas
cfg = ld.BLOCK_B_MURRELL_LOOP
block_title(origin_b_start, "BLOCK B -- Sheet 3, Murrell Loop lots 29-32, 37-40 (local coords)")
front_az = parse_bearing(cfg["front_bearing"])
start_b_col2 = origin_b_start.offset(front_az, cfg["lot_width"] + cfg["row_width"])
col_west, col_east = rect_column_pair(
    origin_b_start, start_b_col2, cfg["front_bearing"], cfg["depth_bearing"],
    width=cfg["lot_width"], depths=[cfg["lot_depth"]] * 4,
    numbers_a=cfg["numbers_west"], numbers_b=cfg["numbers_east"],
)
for lot in col_west + col_east:
    draw_lot(lot)
    all_lots.append(("B", lot))
# interior side easements within each column (between stacked lots)
for col in (col_west, col_east):
    for i in range(len(col) - 1):
        draw_easement(col[i].corners[3], col[i].corners[2], label=(i == 0 and col is col_west))
# draw Murrell Loop centerline schematic between columns
loop_top = origin_b_start.offset(front_az, cfg["lot_width"] + cfg["row_width"] / 2)
loop_bot = loop_top.offset(parse_bearing(cfg["depth_bearing"]), cfg["lot_depth"] * 4)
dxf.line((loop_top.n, loop_top.e), (loop_bot.n, loop_bot.e), layer="ROW_STREET")
dxf.text((loop_top.n + 5, loop_top.e), "MURRELL LOOP (60' PRIVATE R/W, schematic C/L)",
          height=5, layer="ROAD_NAME")
block_reports.append(dict(block="B", n_lots=len(col_west + col_east),
                           expected_each_sqft=cfg["lot_width"] * cfg["lot_depth"],
                           computed_areas=[round(l.area_sqft, 1) for l in col_west + col_east]))

# ============ Block C: Sheet 4 lots 33-36 ============
origin_c = Point(n=2000.0, e=0.0)
block_title(origin_c, "BLOCK C -- Sheet 4, Lots 33-36 (local coords)")
cfg = ld.BLOCK_C_LOTS_33_36
top = cfg["top_row"]
lots_top = rect_row(origin_c, cfg["front_bearing"], cfg["depth_bearing"],
                     widths=top["widths"], depth=top["depths"][0], numbers=top["numbers"])
# top row depths differ slightly (113.67 vs 113.64) -- rect_row assumes one depth;
# rebuild lot 2 of top row with its own depth for exactness
from engine.lots import shoelace_area
front_az_c = parse_bearing(cfg["front_bearing"])
depth_az_c = parse_bearing(cfg["depth_bearing"])
p_start2 = origin_c.offset(front_az_c, top["widths"][0])
p1 = p_start2
p2 = p_start2.offset(front_az_c, top["widths"][1])
p3 = p2.offset(depth_az_c, top["depths"][1])
p4 = p1.offset(depth_az_c, top["depths"][1])
lots_top[1] = Lot(number=top["numbers"][1], corners=[p1, p2, p3, p4],
                   area_sqft=shoelace_area([p1, p2, p3, p4, p1]))
for lot in lots_top:
    draw_lot(lot)
    all_lots.append(("C", lot))
draw_easement(lots_top[0].corners[1], lots_top[0].corners[2])  # shared side, lots 35/34

bot = cfg["bottom_row"]
origin_c_row2 = origin_c.offset(depth_az_c, top["depths"][0])
lots_bot = rect_row(origin_c_row2, cfg["front_bearing"], cfg["depth_bearing"],
                     widths=bot["widths"], depth=bot["depths"][0], numbers=bot["numbers"])
for lot in lots_bot:
    draw_lot(lot)
    all_lots.append(("C", lot))
draw_easement(lots_bot[0].corners[1], lots_bot[0].corners[2])  # shared side, lots 36/33
dxf.text((origin_c.n + 6, origin_c.e - 20), "MURRELL LOOP / TRACT C (OPEN SPACE)", height=6, layer="ROAD_NAME")
block_reports.append(dict(block="C", n_lots=len(lots_top + lots_bot),
                           computed_areas=[round(l.area_sqft, 1) for l in lots_top + lots_bot]))

out_path = "dxf/PB0082_P0035_TrailRidgeEstates_iter2_lotblocks.dxf"
dxf.save(out_path)

print("Saved:", out_path)
print("Total lots drawn:", len(all_lots))
for r in block_reports:
    print(r)
