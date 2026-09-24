"""
tables.py -- Automated Line, Curve, and Lot Schedule table generation for CAD/GIS plats.

Generates professional land surveying tabular schedules:
  1. Lot Schedule: Lot #, Block, Width x Depth dimensions, Area (Sq Ft), Acreage (Ac), Perimeter (ft).
  2. Line Table: Line ID (L1, L2...), Bearing, Distance.
  3. Curve Table: Curve ID (C1, C2...), Radius, Arc Length, Chord Bearing, Chord Distance, Delta.

Features:
  - Draws CAD vector grid lines (outer border, header box, row lines, column dividers).
  - Clean text justification (centered numeric codes, aligned text).
  - Multi-column splitting so 50-100 lot tables fit neatly on sheet viewports without vertical overflow.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from engine.cogo import azimuth_to_bearing


@dataclass
class LotRow:
    lot: str
    block: str
    dimensions: str
    area_sqft: float
    acreage: float
    perimeter: float
    lines: str = ""
    curves: str = ""


@dataclass
class LineRow:
    line_id: str
    bearing: str
    distance: float


@dataclass
class CurveRow:
    curve_id: str
    radius: float
    length: float
    chord_bearing: str
    chord_dist: float
    delta_dms: str
    description: str = ""


def draw_cad_table(
    dxf,
    top_n: float,
    left_e: float,
    title: str,
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    row_height: float = 14.0,
    header_height: float = 18.0,
    title_height: float = 22.0,
    text_height: float = 5.5,
    title_text_height: float = 8.0,
    layer_border: str = "TABLE_BORDER",
    layer_text: str = "TABLE_TEXT",
    layer_header: str = "TABLE_HEADER",
    alignments: list[int] | None = None,
) -> tuple[float, float, float, float]:
    """Draw a ruled CAD table into the DXFWriter at (top_n, left_e).

    Returns: (bottom_n, right_e, total_width, total_height)
    DXF coordinates: Northing (Y), Easting (X).
    """
    num_cols = len(headers)
    total_w = sum(col_widths)
    num_rows = len(rows)
    total_h = title_height + header_height + num_rows * row_height
    bottom_n = top_n - total_h
    right_e = left_e + total_w

    if alignments is None:
        alignments = [1] * num_cols  # default center alignment

    # Register layers
    for lyr, col in [(layer_border, "white"), (layer_text, "white"), (layer_header, "yellow")]:
        if lyr not in dxf.layers:
            dxf.add_layer(lyr, col, "CONTINUOUS")

    # 1. Outer Border
    dxf.line((top_n, left_e), (top_n, right_e), layer=layer_border)
    dxf.line((bottom_n, left_e), (bottom_n, right_e), layer=layer_border)
    dxf.line((top_n, left_e), (bottom_n, left_e), layer=layer_border)
    dxf.line((top_n, right_e), (bottom_n, right_e), layer=layer_border)

    # 2. Title Row
    curr_n = top_n - title_height
    dxf.line((curr_n, left_e), (curr_n, right_e), layer=layer_border)
    mid_title_n = top_n - title_height / 2.0
    mid_title_e = left_e + total_w / 2.0
    dxf.text((mid_title_n, mid_title_e), title, height=title_text_height,
             layer=layer_header, halign=1, valign=2)

    # 3. Header Row
    prev_n = curr_n
    curr_n = prev_n - header_height
    dxf.line((curr_n, left_e), (curr_n, right_e), layer=layer_border)
    
    col_x = left_e
    for j, (h, w) in enumerate(zip(headers, col_widths, strict=True)):
        cell_mid_e = col_x + w / 2.0
        cell_mid_n = prev_n - header_height / 2.0
        dxf.text((cell_mid_n, cell_mid_e), h, height=text_height * 1.15,
                 layer=layer_header, halign=1, valign=2)
        if j > 0:
            # Vertical column separator in header
            dxf.line((prev_n, col_x), (curr_n, col_x), layer=layer_border)
        col_x += w

    # 4. Data Rows
    row_top = curr_n
    for r in rows:
        row_bot = row_top - row_height
        dxf.line((row_bot, left_e), (row_bot, right_e), layer=layer_border)

        col_x = left_e
        for j, (val, w) in enumerate(zip(r, col_widths, strict=True)):
            align = alignments[j] if j < len(alignments) else 1
            cell_mid_n = row_top - row_height / 2.0
            if align == 0:  # Left
                text_e = col_x + 6.0
            elif align == 2:  # Right
                text_e = col_x + w - 6.0
            else:  # Center
                text_e = col_x + w / 2.0

            dxf.text((cell_mid_n, text_e), str(val), height=text_height,
                     layer=layer_text, halign=align, valign=2)
            col_x += w
        row_top = row_bot

    # 5. Full-height Vertical Dividers for data columns
    col_x = left_e
    for j in range(1, num_cols):
        col_x += col_widths[j - 1]
        dxf.line((curr_n, col_x), (bottom_n, col_x), layer=layer_border)

    return (bottom_n, right_e, total_w, total_h)


def draw_split_table(
    dxf,
    top_n: float,
    left_e: float,
    title: str,
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    max_rows_per_col: int = 25,
    col_gap: float = 30.0,
    **kwargs
) -> list[tuple[float, float, float, float]]:
    """Draw a table split across multiple side-by-side columns if row count exceeds max_rows_per_col."""
    if len(rows) <= max_rows_per_col:
        return [draw_cad_table(dxf, top_n, left_e, title, headers, rows, col_widths, **kwargs)]

    results = []
    curr_e = left_e
    part = 1
    total_parts = math.ceil(len(rows) / max_rows_per_col)
    
    for start_idx in range(0, len(rows), max_rows_per_col):
        chunk = rows[start_idx:start_idx + max_rows_per_col]
        part_title = f"{title} (PART {part}/{total_parts})"
        res = draw_cad_table(dxf, top_n, curr_e, part_title, headers, chunk, col_widths, **kwargs)
        results.append(res)
        curr_e += res[2] + col_gap
        part += 1

    return results


def build_lot_schedules(
    parcels: list,
    known_curves: dict | None = None
) -> tuple[list[LotRow], list[LineRow], list[CurveRow]]:
    """Extract and tabulate all lots, lines, and curves.
    Computes exact square footage and acreage for all lots, even if they extend
    beyond the plat boundary.
    """
    known_curves = known_curves or {}
    lot_rows: list[LotRow] = []
    line_catalog: dict[tuple[str, float], str] = {}  # (bearing, rounded_dist) -> Line ID
    line_rows: list[LineRow] = []
    curve_rows: list[CurveRow] = []

    def get_line_id(bstr: str, dist: float) -> str:
        key = (bstr, round(dist, 2))
        if key not in line_catalog:
            lid = f"L{len(line_catalog) + 1}"
            line_catalog[key] = lid
            line_rows.append(LineRow(lid, bstr, round(dist, 2)))
        return line_catalog[key]

    for p in parcels:
        pts = p.polygon() if hasattr(p, "polygon") else getattr(p, "corners", [])
        if not pts:
            continue
        n = len(pts)
        area = p.area_sqft() if hasattr(p, "area_sqft") else getattr(p, "area", 0.0)
        acres = area / 43560.0

        # Calculate perimeter and edge lengths
        dists = []
        lot_line_ids = []
        for i in range(n):
            p1 = pts[i]
            p2 = pts[(i + 1) % n]
            d = p1.dist_to(p2) if hasattr(p1, "dist_to") else math.hypot(p2[0]-p1[0], p2[1]-p1[1])
            dists.append(d)
            dn = (p2.n - p1.n) if hasattr(p2, "n") else (p2[0] - p1[0])
            de = (p2.e - p1.e) if hasattr(p2, "e") else (p2[1] - p1[1])
            az = (math.degrees(math.atan2(de, dn)) + 360) % 360
            bstr = azimuth_to_bearing(az, cardinal=False)
            lid = get_line_id(bstr, d)
            lot_line_ids.append(lid)

        perim = sum(dists)
        w = min(dists) if len(dists) >= 4 else dists[0]
        dpth = max(dists) if len(dists) >= 4 else dists[-1]
        dim_str = getattr(p, "custom_dimensions", f"{w:.1f}' x {dpth:.1f}'")
        if hasattr(p, "custom_area"):
            area = p.custom_area
            acres = area / 43560.0
        if hasattr(p, "custom_perimeter"):
            perim = p.custom_perimeter
        curve_val = getattr(p, "curve_id", getattr(p, "curves", ""))

        # Parse block and lot
        pnum = str(p.number)
        blk = "-"
        if "Blk" in pnum:
            parts = pnum.split("-")
            blk = parts[0].replace("Blk", "")
            lot_label = parts[1].replace("Lot", "") if len(parts) > 1 else pnum
        elif "B" in pnum and "-Lot" in pnum:
            parts = pnum.split("-")
            blk = parts[0].replace("B", "")
            lot_label = parts[1].replace("Lot", "")
        elif "Lot" in pnum:
            lot_label = pnum.replace("Lot", "")
        else:
            lot_label = pnum

        lot_rows.append(LotRow(
            lot=lot_label,
            block=blk,
            dimensions=dim_str,
            area_sqft=round(area, 1),
            acreage=round(acres, 4),
            perimeter=round(perim, 1),
            lines=", ".join(lot_line_ids[:4]),
            curves=curve_val
        ))

    # Add known curves if provided
    for cid, cinfo in known_curves.items():
        curve_rows.append(CurveRow(
            curve_id=cid,
            radius=float(cinfo.get("radius", 0.0)),
            length=float(cinfo.get("arc_length", cinfo.get("length", 0.0))),
            chord_bearing=cinfo.get("chord_bearing", "-"),
            chord_dist=float(cinfo.get("chord", 0.0)),
            delta_dms=cinfo.get("delta", "-"),
            description=cinfo.get("desc", cinfo.get("description", ""))
        ))

    return lot_rows, line_rows, curve_rows
