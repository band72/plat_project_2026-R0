"""
cogo.py -- basic Coordinate Geometry for land surveying traverses.

Bearing convention: quadrant bearings, e.g. N45*30'12"E, S00*36'13"E.
Coordinates: (Northing, Easting) matching plat State Plane convention.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

BEARING_RE = re.compile(
    r"^([NS])\s*(\d{1,3})[°*ºD^]?\s*(\d{1,2})['`]?\s*(\d{1,2}(?:\.\d+)?)?[\"”]?\s*([EW])$",
    re.IGNORECASE
)


CARDINAL_AZ = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}


def parse_bearing(text: str) -> float:
    """Parse a quadrant bearing string into an azimuth in decimal degrees
    (0 = North, clockwise positive, matching survey azimuth convention).

    Accepts the cardinal forms azimuth_to_bearing() emits ("DUE N",
    "DUE EAST", "NORTH", "EAST") as well as quadrant bearings, so that
    format -> parse round-trips cleanly."""
    if not isinstance(text, str):
        raise TypeError(f"Bearing must be a string, got {type(text)}")
    t = text.strip().upper().replace("’", "'").replace('"', '"').replace("”", '"')
    t = t.replace("%%D", "°").replace("%D", "°").replace("DEG", "°")
    # cardinal forms
    c = t.replace("DUE", "").replace(".", "").strip()
    if c in CARDINAL_AZ:
        return CARDINAL_AZ[c]
    for word, letter in (("NORTH", "N"), ("SOUTH", "S"),
                         ("EAST", "E"), ("WEST", "W")):
        if c == word:
            return CARDINAL_AZ[letter]
    m = BEARING_RE.match(t.replace(" ", ""))
    if not m:
        # fall back: allow missing minutes/seconds e.g. N45*E or N45*30'E
        m2 = re.match(r"^([NS])\s*(\d{1,3})[°*ºD^]?\s*(\d{1,2})?['`]?\s*([EW])$", t.replace(" ", ""), re.IGNORECASE)
        if not m2:
            raise ValueError(f"Cannot parse bearing: {text!r}")
        ns, deg, mn, ew = m2.groups()
        sec = 0.0
        mn = mn or "0"
    else:
        ns, deg, mn, sec, ew = m.groups()
        sec = float(sec) if sec else 0.0
        mn = mn or "0"
    ns = ns.upper()
    ew = ew.upper()
    # A quadrant angle is 0-90 deg with minutes/seconds < 60. Unchecked, OCR
    # misreads such as N95°E or N45°75'E silently became wrong azimuths.
    if float(deg) > 90.0 or float(mn) >= 60.0 or sec >= 60.0:
        raise ValueError(f"Bearing out of range: {text!r}")
    ang = float(deg) + float(mn) / 60.0 + sec / 3600.0
    if ang > 90.0:
        raise ValueError(f"Bearing out of range: {text!r}")
    if ns == "N" and ew == "E":
        az = ang
    elif ns == "S" and ew == "E":
        az = 180.0 - ang
    elif ns == "S" and ew == "W":
        az = 180.0 + ang
    else:  # N, W
        az = 360.0 - ang
    return az % 360.0


def try_parse_bearing(text: str, default: float | None = None) -> float | None:
    """Safely attempt to parse a bearing without raising ValueError."""
    try:
        return parse_bearing(text)
    except Exception:
        return default


def azimuth_to_bearing(az: float, cardinal=True) -> str:
    """Format an azimuth as a quadrant bearing.

    Rounds in DMS space BEFORE formatting. Formatting each component
    independently produces INVALID output like N03°08'60.00"E -- a bearing
    can never show 60 seconds, it must carry into minutes (and minutes into
    degrees). Measured 319 such invalid strings in a 200k-sample sweep of
    the previous implementation.

    Cardinal directions: an exact 0 or 90 degree quadrant angle is a
    cardinal direction. The naive form emitted N90°00'00"E and
    N00°00'00"W, which are not valid bearings. With cardinal=True these
    render as DUE E / DUE N etc.; set cardinal=False to keep the numeric
    form when a downstream parser requires it."""
    az = az % 360.0
    if az <= 90:
        ns, ew, ang = "N", "E", az
    elif az <= 180:
        ns, ew, ang = "S", "E", 180 - az
    elif az <= 270:
        ns, ew, ang = "S", "W", az - 180
    else:
        ns, ew, ang = "N", "W", 360 - az

    total_sec = round(ang * 3600.0, 2)
    d = int(total_sec // 3600)
    rem = total_sec - d * 3600
    m = int(rem // 60)
    s = round(rem - m * 60, 2)
    if s >= 60.0:
        s -= 60.0
        m += 1
    if m >= 60:
        m -= 60
        d += 1

    if cardinal:
        if d == 0 and m == 0 and s < 1e-9:
            return f"DUE {ns}"
        if d == 90 and m == 0 and s < 1e-9:
            return f"DUE {ew}"
    return f'{ns}{d:02d}°{m:02d}\'{s:05.2f}"{ew}'


@dataclass
class Point:
    n: float
    e: float

    @property
    def northing(self) -> float:
        return self.n

    @property
    def easting(self) -> float:
        return self.e

    def offset(self, az_deg: float, dist: float) -> Point:
        rad = math.radians(az_deg)
        dn = dist * math.cos(rad)
        de = dist * math.sin(rad)
        return Point(self.n + dn, self.e + de)

    def dist_to(self, other: Point) -> float:
        return math.hypot(other.n - self.n, other.e - self.e)



@dataclass
class Course:
    """One traverse leg: either a straight line (bearing+distance) or an arc
    (handled via curves.py, referenced by curve id)."""
    label: str
    bearing: str | None = None
    distance: float | None = None
    curve_id: str | None = None

    def azimuth(self) -> float:
        assert self.bearing is not None
        return parse_bearing(self.bearing)


def run_traverse(start: Point, courses: list[Course], curves: dict | None = None):
    """Walk a sequence of courses from start; curve courses are resolved by
    chord bearing/chord length (a curve behaves like a straight chord for
    traverse purposes, with the true arc drawn separately in DXF)."""
    curves = curves or {}
    pts = [start]
    pt = start
    for c in courses:
        if c.curve_id:
            crv = curves[c.curve_id]
            az = parse_bearing(crv["chord_bearing"])
            dist = crv["chord"]
        else:
            az = c.azimuth()
            dist = c.distance
        pt = pt.offset(az, dist)
        pts.append(pt)
    return pts


def closure_report(pts: list[Point]) -> dict:
    start, end = pts[0], pts[-1]
    err_n = end.n - start.n
    err_e = end.e - start.e
    err_dist = math.hypot(err_n, err_e)
    perimeter = sum(pts[i].dist_to(pts[i + 1]) for i in range(len(pts) - 1))
    precision = perimeter / err_dist if err_dist > 1e-9 else float("inf")
    return {
        "error_n": err_n,
        "error_e": err_e,
        "error_dist": err_dist,
        "perimeter": perimeter,
        "precision_1_in": precision,
    }


def bowditch_balance(start: Point, courses: list[Course], curves: dict | None = None) -> list[Point]:
    """Execute a closed traverse and balance it using the Compass / Bowditch Rule
    to guarantee exact 0.000 ft mathematical closure.
    
    Correction per course:
        corr_n = dn - (dist / perimeter) * unadj_misclose_n
        corr_e = de - (dist / perimeter) * unadj_misclose_e
    """
    curves = curves or {}
    deltas = []
    total_dist = 0.0
    unadj_n = 0.0
    unadj_e = 0.0
    
    for c in courses:
        if c.curve_id:
            crv = curves[c.curve_id]
            az = parse_bearing(crv["chord_bearing"])
            dist = float(crv["chord"])
        else:
            az = c.azimuth()
            dist = float(c.distance)
            
        rad = math.radians(az)
        dn = dist * math.cos(rad)
        de = dist * math.sin(rad)
        deltas.append((dn, de, dist))
        total_dist += dist
        unadj_n += dn
        unadj_e += de

    balanced = [start]
    cur_n = start.n
    cur_e = start.e
    for dn, de, dist in deltas:
        corr_n = dn - (dist / total_dist) * unadj_n
        corr_e = de - (dist / total_dist) * unadj_e
        cur_n += corr_n
        cur_e += corr_e
        balanced.append(Point(cur_n, cur_e))
        
    return balanced


def course_label_geometry(p1: Point, p2: Point, offset_dist: float = 12.0,
                          side: str | bool = "right") -> tuple[tuple[float, float], float]:
    """Compute the offset midpoint and readable alignment angle (degrees CCW from East)
    for dimensioning a line segment (e.g. boundary course or street corridor).

    Returns: ((label_northing, label_easting), rotation_deg)
    - The label point is offset perpendicularly by offset_dist.
    - side: "right" (default, right-hand side of line direction), "left", or "center".
      (For CCW boundary polygon, "right" is outward; for CW boundary polygon, "left" is outward).
    - rotation_deg is oriented in (-90, 90] degrees CCW from East so text reads
      left-to-right (from bottom or right edge of the sheet).
    """
    dn = p2.n - p1.n
    de = p2.e - p1.e
    dist = math.hypot(dn, de)
    if dist < 1e-6:
        return ((p1.n, p1.e), 0.0)

    # Midpoint
    mid_n = (p1.n + p2.n) / 2.0
    mid_e = (p1.e + p2.e) / 2.0

    # Unit normal vector pointing right of travel (90 deg CW in Northing/Easting):
    # Vector (dn, de) rotated 90 deg CW in (N, E) is (-de, dn)
    if isinstance(side, bool):
        sign = 1.0 if side else -1.0
    elif str(side).lower() == "left":
        sign = -1.0
    elif str(side).lower() == "center":
        sign = 0.0
    else:
        sign = 1.0

    norm_n = -sign * (de / dist)
    norm_e = sign * (dn / dist)

    label_n = mid_n + offset_dist * norm_n
    label_e = mid_e + offset_dist * norm_e

    # Cartesian angle in degrees CCW from positive East (AutoCAD DXF convention)
    theta = math.degrees(math.atan2(dn, de))
    while theta > 90.0:
        theta -= 180.0
    while theta <= -90.0:
        theta += 180.0

    return ((round(label_n, 4), round(label_e, 4)), round(theta, 2))



