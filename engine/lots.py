"""
lots.py -- generators for common plat lot patterns: straight rows of
rectangular lots and back-to-back columns split by a road R/W. Confirms
orthogonality (front bearing perpendicular to depth bearing) before building,
since that's a strong self-check against transcription error.
"""
from __future__ import annotations
from dataclasses import dataclass
from .cogo import Point, parse_bearing


@dataclass
class Lot:
    number: str
    corners: list  # list[Point], closed implicitly (last != first, caller closes)
    area_sqft: float = 0.0

    def close(self):
        return self.corners + [self.corners[0]]


def shoelace_area(pts):
    if not pts:
        return 0.0
    if pts[0] != pts[-1]:
        pts = list(pts) + [pts[0]]
    a = 0.0
    for i in range(len(pts) - 1):
        a += pts[i].e * pts[i + 1].n - pts[i + 1].e * pts[i].n
    return abs(a) / 2.0


def check_orthogonal(front_bearing: str, depth_bearing: str, tol_sec=5.0) -> bool:
    """Front and depth bearings should differ by exactly 90 deg for a
    rectangular lot grid. Returns True if within tol_sec arc-seconds."""
    a1 = parse_bearing(front_bearing)
    a2 = parse_bearing(depth_bearing)
    diff = abs((a1 - a2 + 180) % 360 - 180)  # smallest angle between the two azimuths
    return abs(diff - 90.0) * 3600 < tol_sec or abs(diff - 270.0) * 3600 < tol_sec


def rect_row(start: Point, front_bearing: str, depth_bearing: str,
             widths: list[float], depth: float, numbers: list[str]) -> list[Lot]:
    """Build a row of rectangular lots along `front_bearing` starting at
    `start` (the row's starting front corner), each `widths[i]` wide and a
    constant `depth` deep along `depth_bearing` (into the lot, away from the
    frontage). Returns lots in the same left-to-right order as `widths`."""
    assert check_orthogonal(front_bearing, depth_bearing), \
        f"front/depth bearings not orthogonal: {front_bearing} vs {depth_bearing}"
    front_az = parse_bearing(front_bearing)
    depth_az = parse_bearing(depth_bearing)
    lots = []
    cur = start
    for w, num in zip(widths, numbers):
        p1 = cur
        p2 = cur.offset(front_az, w)
        p3 = p2.offset(depth_az, depth)
        p4 = p1.offset(depth_az, depth)
        corners = [p1, p2, p3, p4]
        lot = Lot(number=num, corners=corners, area_sqft=shoelace_area(corners + [corners[0]]))
        lots.append(lot)
        cur = p2
    return lots


def rect_column_pair(start_a: Point, start_b: Point, front_bearing: str, depth_bearing: str,
                      width: float, depths: list[float], numbers_a: list[str],
                      numbers_b: list[str]) -> tuple[list[Lot], list[Lot]]:
    """Two back-to-back columns of lots (e.g. either side of a loop road),
    each column stacked along `depth_bearing`, lots `width` wide along
    `front_bearing`. start_a/start_b are each column's starting front-corner."""
    assert check_orthogonal(front_bearing, depth_bearing)
    depth_az = parse_bearing(depth_bearing)

    def _col(start, depths_, numbers_, reverse_depth):
        az = (depth_az + 180) % 360 if reverse_depth else depth_az
        cur = start
        out = []
        for d, num in zip(depths_, numbers_):
            p1 = cur
            p2 = cur.offset(parse_bearing(front_bearing), width)
            p3 = p2.offset(az, d)
            p4 = p1.offset(az, d)
            corners = [p1, p2, p3, p4]
            out.append(Lot(number=num, corners=corners,
                            area_sqft=shoelace_area(corners + [corners[0]])))
            cur = p4
        return out

    col_a = _col(start_a, depths, numbers_a, reverse_depth=False)
    col_b = _col(start_b, depths, numbers_b, reverse_depth=False)
    return col_a, col_b


def _segments_intersect(p1, p2, p3, p4) -> bool:
    """Proper segment intersection test (ignores shared endpoints)."""
    def orient(a, b, c):
        v = (b.e - a.e) * (c.n - a.n) - (b.n - a.n) * (c.e - a.e)
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    if p1 is p3 or p1 is p4 or p2 is p3 or p2 is p4:
        return False
    o1, o2 = orient(p1, p2, p3), orient(p1, p2, p4)
    o3, o4 = orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 != o2 and o3 != o4


def is_simple_polygon(pts) -> tuple[bool, str]:
    """Detect a self-intersecting (bowtie) polygon.

    WHY THIS EXISTS: shoelace_area() on a bowtie returns a NUMBER WITH NO
    WARNING -- a perfect bowtie returns 0.0, a partial one returns the
    difference of the two lobes. That silent failure is exactly what
    produced the bogus ~1,250 sf "lots" early in this project (the lobes
    cancelled instead of erroring). Any parcel area must be gated on this
    check, never taken on faith."""
    ring = [p for p in pts]
    if len(ring) > 1 and ring[0].dist_to(ring[-1]) < 1e-9:
        ring = ring[:-1]
    n = len(ring)
    if n < 3:
        return False, f"only {n} distinct vertices -- not a polygon"
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        for j in range(i + 1, n):
            c, d = ring[j], ring[(j + 1) % n]
            if j == i or (j + 1) % n == i:
                continue
            if _segments_intersect(a, b, c, d):
                return False, (f"self-intersecting: side {i}->{i+1} crosses "
                               f"side {j}->{(j+1) % n}")
    return True, "simple"


def safe_area(pts) -> float:
    """shoelace_area(), but REFUSES to return a number for a polygon that
    is not simple. Use this for any parcel whose area will be reported."""
    ok, msg = is_simple_polygon(pts)
    if not ok:
        raise ValueError(f"cannot compute area: {msg}")
    return shoelace_area(pts if pts[0].dist_to(pts[-1]) < 1e-9 else pts + [pts[0]])
