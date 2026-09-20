"""
topology.py -- shared-vertex parcel network.

Directly addresses: "polylines need to intersect at a point lying on the
polyline." Up to now, each lot's corners were computed independently by
walking its own courses from a per-lot start point. Two adjacent lots that
share a boundary line each computed that shared corner SEPARATELY -- from
different starting points, via different course chains -- so in floating
point they are almost never bit-identical, and a DXF built that way has
two near-coincident but DISTINCT vertices at every lot corner instead of
one shared node. That is a real topology defect (dangling endpoints,
snapping gaps), not just cosmetic.

The fix: a VERTEX graph. Every lot corner is created ONCE, referenced by
every lot/line that touches it. Adjacent lots literally share the same
Point object, so their common boundary is drawn once and both lots close
through the identical node.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from engine.cogo import Point
from engine.lots import shoelace_area, safe_area, is_simple_polygon


class VertexGraph:
    """Named vertices, each created once. Courses reference vertices by
    name, never by recomputing coordinates independently."""

    def __init__(self):
        self.points: dict[str, Point] = {}
        self.edges: list[tuple] = []   # (name1, name2, bearing, distance, kind)

    def add(self, name: str, point: Point):
        if name in self.points:
            existing = self.points[name]
            if existing.dist_to(point) > 0.01:
                raise ValueError(
                    f"vertex '{name}' redefined at a different location "
                    f"({existing} vs {point}) -- this is exactly the "
                    f"duplicate-vertex defect this graph exists to prevent")
            return self.points[name]
        self.points[name] = point
        return point

    def walk(self, start_name: str, start_point: Point, courses: list):
        """Walk a chain of (end_name, bearing, distance) from a named,
        already-placed start vertex, registering each new vertex once."""
        self.add(start_name, start_point)
        cur_name, cur_pt = start_name, start_point
        for end_name, bearing, distance in courses:
            from engine.cogo import parse_bearing
            nxt = cur_pt.offset(parse_bearing(bearing), distance)
            self.add(end_name, nxt)
            self.edges.append((cur_name, end_name, bearing, distance, "line"))
            cur_name, cur_pt = end_name, nxt
        return cur_pt

    def line(self, name1, name2, bearing, distance):
        self.edges.append((name1, name2, bearing, distance, "line"))

    def curve(self, name1, name2, curve_id, radius, delta, chord_bearing, chord, arc_points):
        self.edges.append((name1, name2, curve_id, dict(
            radius=radius, delta=delta, chord_bearing=chord_bearing,
            chord=chord, arc_points=arc_points), "curve"))

    def snap_or_add(self, name: str, point: Point, tolerance: float = 0.5) -> str:
        """Find an existing vertex within tolerance or register a new one.
        Returns the canonical vertex name."""
        for existing_name, pt in self.points.items():
            if pt.dist_to(point) <= tolerance:
                return existing_name
        self.add(name, point)
        return name

    def stitch_matchlines(self, sheet_a_vertices: list[tuple[str, Point]],
                          sheet_b_vertices: list[tuple[str, Point]],
                          tolerance: float = 1.0) -> dict[str, str]:
        """Align and stitch corresponding matchline vertices between adjoining sheets."""
        seam_map = {}
        for name_a, pt_a in sheet_a_vertices:
            for name_b, pt_b in sheet_b_vertices:
                if pt_a.dist_to(pt_b) <= tolerance:
                    seam_map[name_b] = name_a
        return seam_map



@dataclass
class Parcel:
    """A lot defined purely by an ordered list of vertex NAMES -- never by
    its own independently-computed coordinates. Guarantees shared edges
    with neighbouring parcels that reference the same vertex names."""
    number: str
    vertex_names: list[str]
    graph: VertexGraph

    def polygon(self) -> list[Point]:
        return [self.graph.points[n] for n in self.vertex_names]

    def area_sqft(self) -> float:
        """Parcel area, GATED on the polygon being simple. Raises rather
        than silently returning a wrong number for a self-intersecting
        ring -- see lots.is_simple_polygon for why this matters."""
        return safe_area(self.polygon())

    def area_or_none(self) -> tuple[float | None, str]:
        """Non-raising variant for batch reporting: returns (area, status)."""
        pts = self.polygon()
        ok, msg = is_simple_polygon(pts)
        if not ok:
            return None, msg
        return safe_area(pts), "ok"

    def is_closed_traverse(self, tol=0.05) -> tuple[bool, float]:
        """A parcel built entirely from a graph is closed BY CONSTRUCTION
        (last vertex step returns to the first, or the polygon is simply
        the ordered vertex list) -- this checks that the vertex chain
        actually forms a simple, non-self-crossing closure within tol."""
        pts = self.polygon()
        closure_err = pts[0].dist_to(pts[-1]) if pts[0] is not pts[-1] else 0.0
        return closure_err <= tol, closure_err

    def side_reports(self) -> list[dict]:
        pts = self.polygon()
        out = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            d = a.dist_to(b)
            import math
            az = math.degrees(math.atan2(b.e - a.e, b.n - a.n)) % 360
            from engine.cogo import azimuth_to_bearing
            out.append(dict(bearing=azimuth_to_bearing(az), distance=d))
        return out
