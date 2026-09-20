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
    r"^([NS])\s*(\d{1,3})[°*]\s*(\d{1,2})['`]\s*(\d{1,2}(?:\.\d+)?)?\"?\s*([EW])$"
)


CARDINAL_AZ = {"N": 0.0, "E": 90.0, "S": 180.0, "W": 270.0}


def parse_bearing(text: str) -> float:
    """Parse a quadrant bearing string into an azimuth in decimal degrees
    (0 = North, clockwise positive, matching survey azimuth convention).

    Accepts the cardinal forms azimuth_to_bearing() now emits ("DUE N",
    "DUE EAST", "NORTH", "EAST") as well as quadrant bearings, so that
    format -> parse round-trips cleanly."""
    t = text.strip().upper().replace("’", "'").replace('"', '"')
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
        # fall back: allow missing seconds e.g. N45*30'E
        m2 = re.match(r"^([NS])(\d{1,3})[°*](\d{1,2})?['`]?([EW])$", t.replace(" ", ""))
        if not m2:
            raise ValueError(f"Cannot parse bearing: {text!r}")
        ns, deg, mn, ew = m2.groups()
        sec = 0.0
        mn = mn or "0"
    else:
        ns, deg, mn, sec, ew = m.groups()
        sec = float(sec) if sec else 0.0
    ang = float(deg) + float(mn) / 60.0 + sec / 3600.0
    if ns == "N" and ew == "E":
        az = ang
    elif ns == "S" and ew == "E":
        az = 180.0 - ang
    elif ns == "S" and ew == "W":
        az = 180.0 + ang
    else:  # N, W
        az = 360.0 - ang
    return az % 360.0


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

    def offset(self, az_deg: float, dist: float) -> "Point":
        rad = math.radians(az_deg)
        dn = dist * math.cos(rad)
        de = dist * math.sin(rad)
        return Point(self.n + dn, self.e + de)

    def dist_to(self, other: "Point") -> float:
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
