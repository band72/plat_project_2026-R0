"""
labels.py -- professional survey-drawing label placement.

Standard convention followed (matches what's on the source plat and any
recorded survey drawing):
  - Bearing text sits ABOVE the line, distance text BELOW the line, both
    centered on the line's midpoint, both PARALLEL to the line.
  - Text is never drawn upside down: if the line's azimuth would put the
    text between 90 deg and 270 deg (reading right-to-left / upside down),
    the label angle is flipped 180 deg so it always reads left-to-right.
  - Text sits at a small perpendicular offset from the line so it doesn't
    overlap the linework itself.
"""
from __future__ import annotations

import math


def _upright(angle_deg: float) -> float:
    """Flip a text angle 180 deg if it would render upside down.  Vertical
    text reads bottom-to-top (90), so 270 flips too."""
    a = angle_deg % 360
    if 95 < a <= 275:          # 5 deg band: near-vertical text reads bottom-to-top
        a = (a + 180) % 360
    return a


# DXF TEXT justification codes: halign 1 = center; valign 1 = bottom, 3 = top
ALIGN_ABOVE = (1, 1)
ALIGN_BELOW = (1, 3)


def course_label_positions(n1, e1, n2, e2, bearing_offset=1.6, dist_offset=1.6):
    """Given a course's endpoints (local N,E), return the (position,
    rotation) for a bearing label above the line and a distance label
    below it, plus the upright text angle.

    "Above" is the text's own up direction after the upright flip, and the
    positions are *alignment points*: draw the bearing with
    ``bearing_align`` (bottom-center) and the distance with
    ``distance_align`` (top-center) so the offset is the true visible gap
    between glyphs and line on both sides, and both labels are centered on
    the course midpoint."""
    dn, de = n2 - n1, e2 - e1
    length = math.hypot(dn, de)
    if length < 1e-9:
        return None
    az = math.degrees(math.atan2(de, dn)) % 360        # azimuth, 0=N,90=E
    text_angle = _upright(90 - az)                       # DXF TEXT rotation is CCW from +X (=East)
    r = math.radians(text_angle)
    up_n, up_e = math.cos(r), -math.sin(r)               # text "up" as (N, E)
    mn, me = (n1 + n2) / 2, (e1 + e2) / 2
    bpos = (mn + up_n * bearing_offset, me + up_e * bearing_offset)
    dpos = (mn - up_n * dist_offset, me - up_e * dist_offset)
    return dict(bearing_pos=bpos, distance_pos=dpos, angle=text_angle, length=length,
                azimuth=az, bearing_align=ALIGN_ABOVE, distance_align=ALIGN_BELOW)


def draw_course(dxf, n1, e1, n2, e2, bearing_text, distance_text,
                line_layer, label_layer, height=3.0, bearing_offset=None,
                dist_offset=None, tick=True):
    """Draw one survey course with professional bearing/distance labels.
    Default offset is half the text height (uniform visible gap)."""
    dxf.line((n1, e1), (n2, e2), layer=line_layer)
    bo = 0.5 * height if bearing_offset is None else bearing_offset
    do = 0.5 * height if dist_offset is None else dist_offset
    pos = course_label_positions(n1, e1, n2, e2, bo, do)
    if pos is None:
        return
    dxf.text(pos["bearing_pos"], bearing_text, height=height,
             layer=label_layer, rotation=pos["angle"],
             halign=pos["bearing_align"][0], valign=pos["bearing_align"][1])
    dxf.text(pos["distance_pos"], distance_text, height=height * 0.92,
             layer=label_layer, rotation=pos["angle"],
             halign=pos["distance_align"][0], valign=pos["distance_align"][1])
    if tick:
        # small perpendicular tick marks at each end, standard survey practice
        dn, de = n2 - n1, e2 - e1
        length = math.hypot(dn, de)
        ux, uy = dn / length, de / length
        px, py = -uy, ux
        tl = height * 0.5
        for (tn, te) in ((n1, e1), (n2, e2)):
            dxf.line((tn - px * tl, te - py * tl), (tn + px * tl, te + py * tl),
                     layer=line_layer)


def road_name_label(dxf, n1, e1, n2, e2, name, width_text, layer,
                    height=5.0, offset=6.0):
    """Road name + width label centered on a road centerline segment,
    e.g. 'MARITIME OAK DRIVE' / \"(60' RIGHT-OF-WAY)\"."""
    pos = course_label_positions(n1, e1, n2, e2, offset, offset)
    if pos is None:
        return
    dxf.text(pos["bearing_pos"], name, height=height, layer=layer,
             rotation=pos["angle"], halign=1, valign=1)
    if width_text:
        dxf.text(pos["distance_pos"], width_text, height=height * 0.75,
                 layer=layer, rotation=pos["angle"], halign=1, valign=3)


def lot_label(dxf, centroid_n, centroid_e, number, layer, height=6.0,
             area_sqft=None, area_layer=None):
    dxf.text((centroid_n - height * 0.4, centroid_e - height * 1.3),
             str(number), height=height, layer=layer)
    if area_sqft is not None:
        dxf.text((centroid_n - height * 1.1, centroid_e - height * 1.3),
                 f"{area_sqft:,.0f} SF", height=height * 0.45,
                 layer=area_layer or layer)


def is_aliquot_dimension(text: str) -> bool:
    """Return True if text represents a linear survey/aliquot dimension
    (e.g. '330', '330\'', '660', '1320', '50.00\'', '75\''), NOT a lot number."""
    import re
    cleaned = re.sub(r"['\"\s]", "", text.strip())
    # Known aliquot and standard subdivision frontage/depth lengths
    known_dimensions = {
        "25", "30", "40", "50", "60", "70", "75", "80", "90", "100",
        "120", "125", "130", "150", "165", "200", "300", "330", "660",
        "1320", "2640", "5280"
    }
    if cleaned in known_dimensions:
        return True
    # Decimal feet (e.g. 50.00, 106.83, 330.15)
    if re.match(r"^\d+\.\d{1,3}$", cleaned):
        return True
    return False


def classify_cadastral_label(text: str) -> str:
    """Classify OCR text into its true cadastral layer, preventing
    misclassification like '330' -> 'LOT 330'."""
    import re
    t = text.strip()
    upper = t.upper()

    # Explicit lot indicators
    if re.match(r"^(LOT|PARCEL|TRACT|BLOCK)\b", upper):
        # But guard against 'LOT 330' where 330 was originally just a dimension
        m = re.match(r"^LOT\s+(\d+)$", upper)
        if m and m.group(1) in ("330", "660", "1320", "165"):
            return "DIMENSIONS"
        return "LOT_NUMBERS"

    # Acreage annotations
    if re.search(r"\b(ACRES?|AC\.?|SQ\.?\s*FT\.?|SF)\b", upper):
        return "DIMENSIONS"

    # Street keywords
    if re.search(r"\b(STREET|AVENUE|ROAD|BOULEVARD|BROADWAY|LANE|WAY|COURT|BLVD|AVE|ST|RD|CT|LN|HWY|DRIVE|DR)\b", upper):
        return "STREET_NAMES"


    # Dimensions
    if is_aliquot_dimension(t):
        return "DIMENSIONS"

    # Single or double digit integers could be lot numbers
    if re.match(r"^\d{1,3}$", t):
        val = int(t)
        if val in (165, 330, 660):
            return "DIMENSIONS"
        return "LOT_NUMBERS"

    return "TITLE_BLOCK"

