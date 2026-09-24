"""
Derived road-centerline geometry for Beachwood Unit Two (PB 30 Pg 82 / 82A).

Every point here is COMPUTED from values printed on the plat -- the Sheet 1 caption boundary, the R/W widths,
the lot frontages and the ℄ Curve Data blocks. No coordinate is typed in. Each derived line is checked against a
second, independent plat source (e.g. the Beachwood Blvd ℄ is placed from the boundary and re-derived from the lot
frontages), and the residuals are reported instead of being hidden.

Conventions follow plugins/curves/plat_curves (SPEC.md): points are (n, e) feet, azimuths are degrees clockwise
from north. Plat reading rules used here:
  * Note 1 -- bearings/distances on curves are chords.
  * Note 2 -- distances at block corners run to the street-line (R/W) intersection, i.e. the fillet PI.
  * Note 4 -- radii not shown are 25'. Every street R/W corner is a 25' fillet (project rule).
  * ℄ Curve Data blocks are centerline values; R/W edge curves are concentric at R ± half-width.

Anchor: the Starfish Ave ℄ x Mangrove Ave ℄ intersection is (10000, 10000), the same local grid as
engine.cogo_road_centerlines, so the two can be compared point by point.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CURVES_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "curves"
if str(_CURVES_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_CURVES_PLUGIN_DIR))

from plat_curves.compound import corner_return, line_arc_intersections, row_edges  # noqa: E402
from plat_curves.core import Curve, PlacedCurve, az_to_bearing, bearing_to_az, deg_to_dms  # noqa: E402

Pt = tuple[float, float]

CAPTION_JSON = _CURVES_PLUGIN_DIR / "plat_curves" / "data" / "boundary_caption_pb30_p82.json"

FILLET_RADIUS = 25.0  # Note 4 + project rule: every street R/W corner is a 25' fillet
CHECK_TOL_FT = 0.05   # a derived value within 0.05' of its independent plat check passes

# Street bearings printed on Sheet 2 (azimuths)
AZ_EW = bearing_to_az("N87°35'30\"E")          # Starfish / Sail / Shellfish / Keel ℄ (and lot fronts)
AZ_MANGROVE_N = bearing_to_az("N02°24'30\"W")  # Mangrove Ave north leg, lot side lines
AZ_BLVD = bearing_to_az("N00°41'40\"W")        # Beachwood Blvd, parallel to the east boundary (course c26)
AZ_MANGROVE_S = bearing_to_az("S01°01'40\"E")  # Mangrove Ave south leg, parallel to course c2
AZ_SANDS_W = bearing_to_az("N88°58'20\"E")     # Sands / Cape Horn / drainage R/W at Mangrove (perp. to south leg)


# ----------------------------------------------------------------------------------------------------------------
# small 2-D helpers (n, e)
# ----------------------------------------------------------------------------------------------------------------
def _move(p: Pt, az_deg: float, d: float) -> Pt:
    a = math.radians(az_deg)
    return (p[0] + d * math.cos(a), p[1] + d * math.sin(a))


def _dist(a: Pt, b: Pt) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _az(a: Pt, b: Pt) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360.0


@dataclass(frozen=True)
class Line:
    """Infinite line through ``p`` with azimuth ``az`` (the direction of travel used for naming sides)."""

    p: Pt
    az: float

    def offset(self, d: float, side: str) -> Line:
        """Parallel line ``d`` feet to the ``"left"`` or ``"right"`` of the direction of travel."""
        turn = 90.0 if side == "right" else -90.0
        return Line(_move(self.p, self.az + turn, d), self.az)

    def intersect(self, other: Line) -> Pt:
        a1, a2 = math.radians(self.az), math.radians(other.az)
        d1 = (math.cos(a1), math.sin(a1))
        d2 = (math.cos(a2), math.sin(a2))
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) < 1e-12:
            raise ValueError("parallel lines do not intersect")
        dn, de = other.p[0] - self.p[0], other.p[1] - self.p[1]
        t = (dn * d2[1] - de * d2[0]) / den
        return (self.p[0] + t * d1[0], self.p[1] + t * d1[1])

    def station(self, q: Pt) -> float:
        """Signed distance of the foot of ``q`` along the line from ``p``."""
        a = math.radians(self.az)
        return (q[0] - self.p[0]) * math.cos(a) + (q[1] - self.p[1]) * math.sin(a)

    def signed_offset(self, q: Pt) -> float:
        """Perpendicular distance of ``q``: positive to the right of travel."""
        a = math.radians(self.az)
        return -(q[0] - self.p[0]) * math.sin(a) + (q[1] - self.p[1]) * math.cos(a)


# ----------------------------------------------------------------------------------------------------------------
# result records
# ----------------------------------------------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    derived: float
    plat: float
    source: str
    tol: float = CHECK_TOL_FT

    @property
    def residual(self) -> float:
        return self.derived - self.plat

    @property
    def ok(self) -> bool:
        return abs(self.residual) <= self.tol


@dataclass
class Street:
    id: str
    name: str
    centerline: Line
    row_width: float
    source: str

    @property
    def half(self) -> float:
        return self.row_width / 2.0

    def edge(self, side: str) -> Line:
        return self.centerline.offset(self.half, side)


@dataclass
class Intersection:
    id: str
    name: str
    point: Pt
    streets: tuple[str, str]
    kind: str  # "CL_X_CL" | "CL_X_BOUNDARY"
    source: str


@dataclass
class Fillet:
    id: str
    intersection: str
    location: str
    corner: Pt          # street-line intersection = fillet PI (Note 2)
    pc: Pt
    pt: Pt
    rp: Pt
    radius: float
    delta_deg: float
    tangent: float
    arc_length: float
    chord: float
    chord_bearing: str
    direction: str
    arc_pts: list[Pt] = field(default_factory=list, repr=False)
    # R/W corner cut off by the return: polygon PC -> ... -> PT through the actual R/W vertices (default: PC, PI, PT;
    # a corner on a bent R/W line lists the bend too)
    zone: list[Pt] = field(default_factory=list, repr=False)


@dataclass
class CenterlineRun:
    """A straight ℄ piece between two schedule points."""

    id: str
    street: str
    start: str
    end: str
    p0: Pt
    p1: Pt

    @property
    def length(self) -> float:
        return _dist(self.p0, self.p1)

    @property
    def bearing(self) -> str:
        return az_to_bearing(_az(self.p0, self.p1))


@dataclass
class CorridorPiece:
    """One ℄ element of a street (straight or ℄ arc) with its R/W half-width.

    Straight pieces may carry cap lines (the ℄ or boundary line the street ends on) so that the R/W edges end on
    that line instead of square to the ℄.
    """

    street: str
    half: float
    p0: Pt | None = None
    p1: Pt | None = None
    cap0: Line | None = None
    cap1: Line | None = None
    arc: PlacedCurve | None = None

    def contains(self, q: Pt, tol: float = 1e-6) -> bool:
        """Strictly inside this piece's R/W (the edges themselves are outside)."""
        if self.arc is not None:
            c = self.arc
            if abs(_dist(q, c.rp) - c.curve.radius) >= self.half - tol:
                return False
            swept = (c.curve.sign * (_az(c.rp, q) - c.radial_az_at(0.0))) % 360.0
            return tol < swept < c.curve.delta_deg - tol
        ln = Line(self.p0, _az(self.p0, self.p1))
        t = ln.station(q)
        return tol < t < _dist(self.p0, self.p1) - tol and abs(ln.signed_offset(q)) < self.half - tol

    def edges(self) -> list[tuple[str, Any]]:
        if self.arc is not None:
            e = row_edges(self.arc, 2.0 * self.half)
            return [("arc", e["inside"]), ("arc", e["outside"])]
        az = _az(self.p0, self.p1)
        out = []
        for side in ("left", "right"):
            ln = Line(self.p0, az).offset(self.half, side)
            a = self.cap0.intersect(ln) if self.cap0 else ln.p
            b = self.cap1.intersect(ln) if self.cap1 else _move(ln.p, az, _dist(self.p0, self.p1))
            out.append(("line", (a, b)))
        return out


def _on_segment(q: Pt, a: Pt, b: Pt, tol: float) -> bool:
    ab = _dist(a, b)
    if ab < tol:
        return _dist(q, a) < tol
    cross = ((b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0])) / ab
    t = ((q[0] - a[0]) * (b[0] - a[0]) + (q[1] - a[1]) * (b[1] - a[1])) / (ab * ab)
    return abs(cross) < tol and -tol <= t <= 1 + tol


def _in_fillet_corner(q: Pt, f: Fillet, tol: float = 1e-6) -> bool:
    """Between the fillet arc and the R/W corner it cuts off (polygon ``zone`` minus the fillet disk)."""
    if _dist(q, f.rp) <= f.radius + tol:
        return False
    poly = f.zone or [f.pc, f.corner, f.pt]
    edges = list(zip(poly, poly[1:] + poly[:1], strict=True))
    if any(_on_segment(q, a, b, tol) for a, b in edges):
        return True
    inside = False
    for a, b in edges:
        if (a[1] > q[1]) != (b[1] > q[1]):
            x = a[0] + (q[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x > q[0]:
                inside = not inside
    return inside


def _seg_seg(a: Pt, b: Pt, c: Pt, d: Pt) -> float | None:
    """Parameter t on a-b where it crosses c-d (both as segments), or None."""
    r = (b[0] - a[0], b[1] - a[1])
    q = (d[0] - c[0], d[1] - c[1])
    den = r[0] * q[1] - r[1] * q[0]
    if abs(den) < 1e-12:
        return None
    t = ((c[0] - a[0]) * q[1] - (c[1] - a[1]) * q[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    return t if (-1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9) else None


def trim_row_linework(corridors: list[CorridorPiece], fillets: list[Fillet]) -> list[tuple[str, list[Pt]]]:
    """R/W edges of every corridor, cut where they enter another street's R/W or a fillet's corner.

    Each edge is split at every fillet tangent point / corner and every crossing with another corridor's edge; a
    piece is kept only if its midpoint is outside every other corridor and outside every fillet corner zone.
    """
    all_edges = [(i, kind, g) for i, c in enumerate(corridors) for kind, g in c.edges()]
    marks = [p for f in fillets for p in (f.pc, f.pt, f.corner)]

    def keep(mid: Pt, owner: int) -> bool:
        if any(c.contains(mid) for j, c in enumerate(corridors) if j != owner):
            return False
        return not any(_in_fillet_corner(mid, f) for f in fillets)

    out: list[tuple[str, list[Pt]]] = []
    for i, kind, g in all_edges:
        street = corridors[i].street
        if kind == "line":
            a, b = g
            ln = Line(a, _az(a, b))
            length = _dist(a, b)
            ts = {0.0, 1.0}
            for m in marks:
                if abs(ln.signed_offset(m)) < 1e-6 and 0.0 < ln.station(m) < length:
                    ts.add(ln.station(m) / length)
            for j, k2, g2 in all_edges:
                if j == i:
                    continue
                if k2 == "line":
                    t = _seg_seg(a, b, g2[0], g2[1])
                    if t is not None:
                        ts.add(min(max(t, 0.0), 1.0))
                else:
                    ts.update(h["t"] for h in line_arc_intersections(a, b, g2))
            ts = sorted(ts)
            for t0, t1 in zip(ts, ts[1:], strict=False):
                if (t1 - t0) * length < 1e-6:
                    continue
                p0 = (a[0] + t0 * (b[0] - a[0]), a[1] + t0 * (b[1] - a[1]))
                p1 = (a[0] + t1 * (b[0] - a[0]), a[1] + t1 * (b[1] - a[1]))
                if keep(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), i):
                    out.append((street, [p0, p1]))
        else:
            arc = g
            L = arc.curve.arc_length
            ss = {0.0, L}
            for m in marks:
                if abs(_dist(m, arc.rp) - arc.curve.radius) < 1e-6:
                    sw = (arc.curve.sign * (_az(arc.rp, m) - arc.radial_az_at(0.0))) % 360.0
                    s_m = math.radians(sw) * arc.curve.radius
                    if 0.0 < s_m < L:
                        ss.add(s_m)
            for j, k2, g2 in all_edges:
                if j != i and k2 == "line":
                    ss.update(h["s"] for h in line_arc_intersections(g2[0], g2[1], arc))
            ss = sorted(ss)
            for s0, s1 in zip(ss, ss[1:], strict=False):
                if s1 - s0 < 1e-6:
                    continue
                if keep(arc.point_at((s0 + s1) / 2), i):
                    n = max(2, int((s1 - s0) / 5.0))
                    out.append((street, [arc.point_at(s0 + (s1 - s0) * k / n) for k in range(n + 1)]))
    return out


@dataclass
class CenterlineNetwork:
    boundary: list[dict[str, Any]] = field(default_factory=list)
    boundary_closure_ft: float = 0.0
    streets: dict[str, Street] = field(default_factory=dict)
    intersections: dict[str, Intersection] = field(default_factory=dict)
    runs: list[CenterlineRun] = field(default_factory=list)
    fillets: list[Fillet] = field(default_factory=list)
    curve_data: list[dict[str, Any]] = field(default_factory=list)
    placed_curves: dict[str, PlacedCurve] = field(default_factory=dict)  # ℄ curves placed with plat_curves
    corridors: list[CorridorPiece] = field(default_factory=list)
    row_linework: list[tuple[str, list[Pt]]] = field(default_factory=list)  # trimmed R/W edges (street, points)
    checks: list[Check] = field(default_factory=list)

    @property
    def all_checks_pass(self) -> bool:
        return all(c.ok for c in self.checks)


# ----------------------------------------------------------------------------------------------------------------
# solver
# ----------------------------------------------------------------------------------------------------------------
def load_caption_courses(path: Path = CAPTION_JSON) -> list[dict[str, Any]]:
    """The Sheet 1 caption, as transcribed digit by digit (plugins/curves data; closes 0.042')."""
    return json.loads(path.read_text())["courses"]


def fillet_at(fid: str, intersection: str, location: str, line1: Line, away1: float, line2: Line,
              away2: float, radius: float = FILLET_RADIUS) -> Fillet:
    """25' return at a block corner: the corner (PI) is where the two R/W lines meet (Note 2).

    ``away1`` / ``away2`` are the azimuths along which each block R/W line runs AWAY from the corner (along the
    block). Travel is taken in along line 1 (``away1 + 180``) and out along line 2 (``away2``), so both tangent
    points land on the block's own R/W lines, never inside the street opening.
    """
    corner = line1.intersect(line2)
    pc = corner_return(corner, (away1 + 180.0) % 360.0, away2 % 360.0, radius)
    c = pc.curve
    return Fillet(
        id=fid, intersection=intersection, location=location, corner=corner,
        pc=pc.pc, pt=pc.pt, rp=pc.rp, radius=c.radius, delta_deg=c.delta_deg,
        tangent=c.tangent, arc_length=c.arc_length, chord=c.chord,
        chord_bearing=pc.chord_bearing, direction=pc.direction, arc_pts=pc.arc_points(12),
    )


# ℄ Curve Data blocks as printed (Δ, R, T); the edge radii are R ± 30 on these 60' streets.
PLAT_CL_CURVE_DATA = [
    # id, street, sheet, Δ, R, T printed, direction (W->E / Marina-end travel)
    ("CL_SANSALVADORE", "San Salvadore Ave", 1, "36°20'00\"", 269.96, 88.59, "CW"),
    ("CL_CAPEHORN", "Cape Horn Ave", 1, "36°20'00\"", 327.01, 107.31, "CW"),
    ("CL_MARINA", "Marina Drive", 2, "37°42'50\"", 359.27, 122.70, "CW"),
    ("CL_SANDS", "Sands Ave", 2, "36°20'00\"", 459.36, 150.73, "CW"),
    ("CL_SHELLFISH", "Shellfish Drive", 2, "52°17'10\"", 167.95, 82.35, "CW"),
    ("CL_KEEL", "Keel Drive", 2, "52°17'10\"", 143.93, 70.65, "CW"),
]


def _wrap_sec(deg: float) -> float:
    """Angle difference in arc-seconds, wrapped to (-648000, 648000]."""
    return ((deg + 180.0) % 360.0 - 180.0) * 3600.0


def _dms(s: str) -> float:
    d, rest = s.split("°")
    m, rest = rest.split("'")
    sec = rest.rstrip('"')
    return int(d) + int(m) / 60.0 + float(sec) / 3600.0


def solve_network(origin: Pt = (10000.0, 10000.0)) -> CenterlineNetwork:
    net = CenterlineNetwork()
    chk = net.checks.append

    # -- 1. Boundary traverse (caption), anchored so the Mangrove/Starfish ℄ lands on ``origin``.
    #       c1 (S02°24'30"E) is parallel to Mangrove and c27 (S87°35'30"W) to Starfish; both ℄s sit 180' inside:
    #       west side 50' drainage R/W + 100' lot + 30' half street; north side 50' + 100' + 30'.
    pob = _move(_move(origin, AZ_MANGROVE_N, 180.0), (AZ_EW + 180.0) % 360.0, 180.0)
    p = pob
    pts = [pob]
    for c in load_caption_courses():
        p = _move(p, bearing_to_az(c["bearing"]), c["distance"])
        pts.append(p)
        net.boundary.append({"id": c["id"], "bearing": c["bearing"], "distance": c["distance"],
                             "start": pts[-2], "end": p})
    net.boundary_closure_ft = _dist(pts[-1], pob)
    bnd = {b["id"]: b for b in net.boundary}

    def bnd_line(cid: str) -> Line:
        b = bnd[cid]
        return Line(b["start"], bearing_to_az(b["bearing"]))

    # -- 2. Sheet 2 orthogonal grid. Starfish is the anchor; Sail, Shellfish, Keel are 260' apart
    #       (30 half street + 100 + 100 lot depths + 30 half street, printed on every block side line).
    mangrove = Street("MANGROVE_N", "Mangrove Avenue (north leg)", Line(origin, (AZ_MANGROVE_N + 180.0) % 360.0),
                      60.0, "Sheet 2: 60' R/W, ℄ N02°24'30\"W, 180' east of course c1")
    starfish = Street("STARFISH", "Starfish Avenue", Line(origin, AZ_EW), 60.0,
                      "Sheet 2: 60' R/W, ℄ S87°35'30\"W, 180' south of course c27")
    sail = Street("SAIL", "Sail Avenue", starfish.centerline.offset(260.0, "right"), 60.0,
                  "260' south of Starfish ℄ (Block 17: 30 + 100 + 100 + 30)")
    shellfish = Street("SHELLFISH", "Shellfish Drive (E-W leg)", starfish.centerline.offset(520.0, "right"), 60.0,
                       "260' south of Sail ℄ (Block 16: 30 + 100 + 100 + 30)")
    keel = Street("KEEL", "Keel Drive (E-W leg)", starfish.centerline.offset(780.0, "right"), 60.0,
                  "260' south of Shellfish ℄ (Block 15 east lots 9/10: 30 + 100 + 100 + 30)")

    # -- 3. Beachwood Boulevard: 80' R/W lying wholly inside the plat, east R/W = east boundary c26.
    #       Width evidence: north line 80.04' along S87°35'30"W (= 80/cos 1°42'50"); '80'' printed at Block 6;
    #       south line c25 N68°58'32"E 85.32' (= 80/cos 20°19'48").
    c26 = bnd_line("c26")
    blvd_cl = c26.offset(40.0, "left")  # c26 runs north; the Blvd lies west (left) of it
    blvd = Street("BEACHWOOD_BLVD", "Beachwood Boulevard", Line(blvd_cl.intersect(bnd_line("c25")), AZ_BLVD),
                  80.0, "Sheet 2: 80' R/W, ℄ 40' west of and parallel to east boundary c26 N00°41'40\"W 1247.95'")
    # -- 3b. Mangrove south leg: 180' inside course c2 (50' drainage R/W + 100' lots + 30'), deflecting where the
    #        two offset lines meet. Checked below against the Block 14 lot-6 split dimensions.
    mangrove_s = Street("MANGROVE_S", "Mangrove Avenue (south leg)", Line(
        mangrove.centerline.intersect(bnd_line("c2").offset(180.0, "left")), AZ_MANGROVE_S), 60.0,
        "Sheet 1/2: 60' R/W, ℄ N01°01'40\"W, 180' east of course c2")
    # Marina Dr west leg: Mangrove E R/W carries Block 16 Lots 1 and 33 (100' + 100') below Sail S R/W, so its
    # ℄ is 260' south of Sail -- the same line as the Shellfish Dr E-W leg (both 60').
    marina_w = Street("MARINA_W", "Marina Drive (west leg)", shellfish.centerline, 60.0,
                      "Block 16 Lots 1/33 (100' + 100') on Mangrove E R/W: ℄ collinear with Shellfish E-W")
    # Sands Ave / drainage R/W / Cape Horn Ave meet Mangrove's south leg square (N88°58'20"E). East side, from the
    # Marina S R/W street-line corner down Mangrove E R/W: Block 7 Lot 24 100.74', Lot 23 100', Sands 60',
    # Block 8 Lot 23 100', drainage R/W 40', Lot 22 100', Cape Horn 60'.
    ms_e = mangrove_s.edge("left")
    k_marina_s = marina_w.edge("right").intersect(ms_e)

    def square_to_south_leg(dist_below_k: float) -> Line:
        return Line(_move(k_marina_s, AZ_MANGROVE_S, dist_below_k), AZ_SANDS_W)

    sands_w = Street("SANDS_W", "Sands Avenue (west tangent)", square_to_south_leg(100.74 + 100.0 + 30.0), 60.0,
                     "Mangrove E R/W: Blk 7 Lot 24 100.74' + Lot 23 100' + 30' below Marina S R/W corner")
    drain_40 = Street("DRAIN_40", "40' Drainage R/W (Block 8 / Block 14)",
                      square_to_south_leg(100.74 + 100.0 + 60.0 + 100.0 + 20.0), 40.0,
                      "Mangrove E R/W: Blk 8 Lot 23 100' below Sands S R/W, 40' wide")
    capehorn_w = Street("CAPEHORN_W", "Cape Horn Avenue (west tangent)",
                        square_to_south_leg(100.74 + 100.0 + 60.0 + 100.0 + 40.0 + 100.0 + 30.0), 60.0,
                        "Mangrove E R/W: Blk 8 Lot 22 100' below the 40' drainage R/W")
    for s in (mangrove, mangrove_s, starfish, sail, shellfish, marina_w, keel, blvd, sands_w, drain_40, capehorn_w):
        net.streets[s.id] = s

    # Independent checks on the south leg (Block 14, the west side of Mangrove)
    ms_w = mangrove_s.edge("right")
    mn_w = mangrove.edge("right")
    v_wrw = mn_w.intersect(ms_w)
    starfish_s0 = starfish.edge("right")
    chk(Check("Mangrove W R/W deflection below Starfish S R/W (Blk 14 Lots 1-5 + Lot 6 east 60.45')",
              mn_w.station(v_wrw) - mn_w.station(mn_w.intersect(starfish_s0)), 461.88 + 60.45,
              "Block 14: 100 + 91.88 + 90 + 90 + 90 + 60.45"))
    lw1, lw2 = bnd_line("c1").offset(50.0, "left"), bnd_line("c2").offset(50.0, "left")
    v_lw = lw1.intersect(lw2)
    chk(Check("Block 14 west line deflection below Starfish S R/W (Lots 1-5 + Lot 6 west 59.22')",
              lw1.station(v_lw) - lw1.station(lw1.intersect(starfish_s0)), 461.88 + 59.22,
              "Block 14 west side, 50' inside c1/c2"))
    # West side stationing down Mangrove W R/W to Cape Horn N R/W: Lots 1-5, Lot 6 east (60.45 + 16.99), Lots 7-10
    # 4x75, Tract 'A' 40', drainage R/W 40', Lot 11 100'. The N-leg piece is measured to the deflection, the rest
    # along the south leg.
    s_leg_run = 16.99 + 4 * 75.0 + 40.0 + 40.0 + 100.0
    ch_n_west = _move(v_wrw, AZ_MANGROVE_S, s_leg_run)
    chk(Check("Cape Horn N R/W: Block 14 west-side sum vs Blocks 7/8 east-side sum (offset between them)",
              capehorn_w.edge("left").signed_offset(ch_n_west), 0.0,
              "W: 461.88+77.44+300+40+40+100 | E: 100.74+100+60+100+40+100", tol=0.05))
    drain_n_west = _move(v_wrw, AZ_MANGROVE_S, 16.99 + 4 * 75.0 + 40.0)
    chk(Check("40' drainage R/W N line: west side (Tract 'A') vs east side (Blk 8 Lot 23)",
              drain_40.edge("left").signed_offset(drain_n_west), 0.0, "both sides of Mangrove", tol=0.05))
    chk(Check("Block 14 Lot 6/7 line width (lot west line to Mangrove W R/W)",
              abs(lw2.signed_offset(_move(v_wrw, AZ_MANGROVE_S, 16.99))), 100.0, "Sheet 2 Lot 6/7 '100''"))

    # Independent check A: the north boundary length from the lot frontages. Block 17 north row
    # 93.50 + 15x75 + 111.54 = 1330.04 from Mangrove E R/W to the Blvd W R/W (both on Starfish S line).
    starfish_s = starfish.edge("right")
    blvd_w = blvd.edge("left")
    blk17_ne = starfish_s.intersect(blvd_w)
    blk17_nw = starfish_s.intersect(mangrove.edge("left"))
    chk(Check("Block 17 north row (Starfish S R/W, Mangrove E R/W to Blvd W R/W)",
              _dist(blk17_nw, blk17_ne), 93.50 + 15 * 75.0 + 111.54, "Sheet 2 Block 17 Lots 1-17 frontages"))
    sail_n, sail_s = sail.edge("left"), sail.edge("right")
    keel_n = keel.edge("left")
    chk(Check("Block 17 south row (Sail N R/W)", _dist(sail_n.intersect(mangrove.edge("left")),
              sail_n.intersect(blvd_w)), 93.50 + 15 * 75.0 + 105.56, "Block 17 Lots 34-18 frontages"))
    chk(Check("Block 16 north row (Sail S R/W)", _dist(sail_s.intersect(mangrove.edge("left")),
              sail_s.intersect(blvd_w)), 93.50 + 15 * 75.0 + 103.76, "Block 16 Lots 1-17 frontages"))
    # Block 18 south row runs from the west boundary: 50' drainage R/W + 103.50 + 17x75 + 113.34.
    starfish_n = starfish.edge("left")
    chk(Check("Block 18 south row (Starfish N R/W, boundary c1 to Blvd W R/W)",
              _dist(starfish_n.intersect(bnd_line("c1")), starfish_n.intersect(blvd_w)),
              50.0 + 103.50 + 17 * 75.0 + 113.34, "Block 18 Lots 1-19 + 50' drainage R/W"))
    # Blvd north line c27 across the Blvd: printed 80.04'.
    c27 = bnd_line("c27")
    chk(Check("Beachwood Blvd width on north line c27", _dist(c27.intersect(blvd_w), bnd["c26"]["end"]), 80.04,
              "Sheet 2 '80.04'' at the NE corner"))
    chk(Check("Beachwood Blvd width on south line c25", _dist(bnd["c25"]["start"], bnd["c25"]["end"]),
              80.0 / math.cos(math.radians(abs(((bearing_to_az(bnd["c25"]["bearing"]) - (AZ_BLVD + 90.0))
                                                   + 180.0) % 360.0 - 180.0))),
              "c25 85.32' vs 80' R/W crossed at 20°19'48\"", tol=0.01))
    # Block east lines along the Blvd W R/W: 100.04' (= 100 / cos 1°42'50") per 100' lot depth.
    chk(Check("Block 17 Lot 17 east line (Starfish S R/W to lot 17/18 line)",
              _dist(blk17_ne, starfish.centerline.offset(130.0, "right").intersect(blvd_w)), 100.04,
              "Sheet 2 '100.04''"))

    # -- 4. Intersection schedule (℄ x ℄ and ℄ x boundary)
    def add_int(iid: str, name: str, a: Street, b: Street | Line, src: str, kind: str = "CL_X_CL") -> Pt:
        other = b.centerline if isinstance(b, Street) else b
        q = a.centerline.intersect(other)
        net.intersections[iid] = Intersection(iid, name, q, (a.name, b.name if isinstance(b, Street) else src),
                                              kind, src)
        return q

    add_int("INT_STARFISH_MANGROVE", "Starfish Ave & Mangrove Ave", starfish, mangrove, "anchor (10000, 10000)")
    add_int("INT_SAIL_MANGROVE", "Sail Ave & Mangrove Ave", sail, mangrove, "℄ x ℄")
    add_int("INT_MARINA_MANGROVE", "Marina Dr (west leg) & Mangrove Ave", marina_w, mangrove, "℄ x ℄")
    add_int("INT_MANGROVE_DEFL", "Mangrove Ave deflection (N02°24'30\"W -> N01°01'40\"W)", mangrove, mangrove_s,
            "c1/c2 offsets 180' meet")
    add_int("INT_SANDS_MANGROVE", "Sands Ave & Mangrove Ave", sands_w, mangrove_s, "℄ x ℄")
    add_int("INT_DRAIN40_MANGROVE", "40' Drainage R/W & Mangrove Ave", drain_40, mangrove_s, "℄ x ℄")
    add_int("INT_CAPEHORN_MANGROVE", "Cape Horn Ave & Mangrove Ave", capehorn_w, mangrove_s, "℄ x ℄")
    add_int("INT_BLVD_NORTH_END", "Beachwood Blvd & north boundary c27", blvd, c27, "course c27", "CL_X_BOUNDARY")
    add_int("INT_STARFISH_BEACHWOOD", "Starfish Ave & Beachwood Blvd", starfish, blvd, "℄ x ℄")
    add_int("INT_SAIL_BEACHWOOD", "Sail Ave & Beachwood Blvd", sail, blvd, "℄ x ℄")
    add_int("INT_SHELLFISH_BEACHWOOD", "Shellfish Dr & Beachwood Blvd", shellfish, blvd, "℄ x ℄")
    add_int("INT_KEEL_BEACHWOOD", "Keel Dr & Beachwood Blvd", keel, blvd, "℄ x ℄")
    add_int("INT_BLVD_SOUTH_END", "Beachwood Blvd & south line c25 (Unit One)", blvd, bnd_line("c25"),
            "course c25", "CL_X_BOUNDARY")
    ints = net.intersections

    blvd_seq = ["INT_BLVD_NORTH_END", "INT_STARFISH_BEACHWOOD", "INT_SAIL_BEACHWOOD", "INT_SHELLFISH_BEACHWOOD",
                "INT_KEEL_BEACHWOOD", "INT_BLVD_SOUTH_END"]
    for a, b in zip(blvd_seq, blvd_seq[1:], strict=False):
        net.runs.append(CenterlineRun(f"RUN_BLVD_{len(net.runs) + 1}", blvd.name, a, b, ints[a].point, ints[b].point))
    for sid, a, b in (("STARFISH", "INT_STARFISH_MANGROVE", "INT_STARFISH_BEACHWOOD"),
                      ("SAIL", "INT_SAIL_MANGROVE", "INT_SAIL_BEACHWOOD")):
        net.runs.append(CenterlineRun(f"RUN_{sid}", net.streets[sid].name, a, b, ints[a].point, ints[b].point))

    # Blvd ℄ spacing: 260' perpendicular between streets = 260.13' along N00°41'40"W.
    along = 260.0 / math.cos(math.radians(AZ_EW - (AZ_BLVD + 90.0 - 360.0)))
    for a, b in zip(blvd_seq[1:4], blvd_seq[2:5], strict=True):
        chk(Check(f"Blvd ℄ {a} -> {b}", _dist(ints[a].point, ints[b].point), along,
                  "260' street spacing / cos 1°42'50\"", tol=1e-6))

    # -- 5. 25' fillets at every street R/W corner: (line, direction it runs AWAY from the corner along the block)
    S, N, E, W = (AZ_EW + 90.0) % 360, (AZ_EW - 90.0) % 360, AZ_EW, (AZ_EW + 180.0) % 360
    BN, BS = AZ_BLVD, (AZ_BLVD + 180.0) % 360
    fil = net.fillets.append
    m_w, m_e = mangrove.edge("right"), mangrove.edge("left")  # Mangrove centerline Line runs south
    # Mangrove x Starfish (Mangrove ends at Starfish; Block 18 is continuous on the north side)
    fil(fillet_at("F_STARFISH_MANGROVE_SW", "INT_STARFISH_MANGROVE", "SW: drainage-strip block Lot 1 NE",
                  starfish_s, W, m_w, S))
    fil(fillet_at("F_STARFISH_MANGROVE_SE", "INT_STARFISH_MANGROVE", "SE: Block 17 Lot 1 NW",
                  m_e, S, starfish_s, E))
    # Mangrove x Sail (Sail ends at Mangrove from the east)
    fil(fillet_at("F_SAIL_MANGROVE_NE", "INT_SAIL_MANGROVE", "NE: Block 17 Lot 34 SW",
                  sail_n, E, m_e, N))
    fil(fillet_at("F_SAIL_MANGROVE_SE", "INT_SAIL_MANGROVE", "SE: Block 16 Lot 1 NW",
                  m_e, S, sail_s, E))
    # Blvd x E-W streets: only the west side has corners (east R/W is the boundary)
    for iid, st, north_loc, south_loc in (
        ("INT_STARFISH_BEACHWOOD", starfish, "NW: Block 18 Lot 19 SE", "SW: Block 17 Lot 17 NE"),
        ("INT_SAIL_BEACHWOOD", sail, "NW: Block 17 Lot 18 SE", "SW: Block 16 Lot 17 NE"),
        ("INT_SHELLFISH_BEACHWOOD", shellfish, "NW: Block 16 Lot 18 SE", "SW: Block 15 Lot 9 NE"),
        ("INT_KEEL_BEACHWOOD", keel, "NW: Block 15 Lot 10 SE", "SW: Block 6 Lot 10 NE"),
    ):
        tag = iid.replace("INT_", "F_")
        fil(fillet_at(f"{tag}_NW", iid, north_loc, st.edge("left"), W, blvd_w, BN))
        fil(fillet_at(f"{tag}_SW", iid, south_loc, st.edge("right"), W, blvd_w, BS))

    # Mangrove south leg corners (Block 14 is continuous on the west down to the drainage R/W).
    SL_S, SL_N = AZ_MANGROVE_S, (AZ_MANGROVE_S + 180.0) % 360
    SW_E, SW_W = AZ_SANDS_W, (AZ_SANDS_W + 180.0) % 360
    m_e_n = mangrove.edge("left")
    fil(fillet_at("F_MARINA_MANGROVE_NE", "INT_MARINA_MANGROVE", "NE: Block 16 Lot 33 SW",
                  marina_w.edge("left"), E, m_e_n, N))
    fil(fillet_at("F_MARINA_MANGROVE_SE", "INT_MARINA_MANGROVE", "SE: Block 7 Lot 24 NW",
                  ms_e, SL_S, marina_w.edge("right"), E))
    for iid, st, n_loc, s_loc, both in (
        ("INT_SANDS_MANGROVE", sands_w, "NE: Block 7 Lot 23 SW", "SE: Block 8 Lot 23 NW", False),
        ("INT_DRAIN40_MANGROVE", drain_40, "NE: Block 8 Lot 23 SW", "SE: Block 8 Lot 22 NW", True),
        ("INT_CAPEHORN_MANGROVE", capehorn_w, "NE: Block 8 Lot 22 SW", "SE: Block 9 Lot 27 NW (Sheet 1)", True),
    ):
        tag = iid.replace("INT_", "F_")
        fil(fillet_at(f"{tag}_NE", iid, n_loc, st.edge("left"), SW_E, ms_e, SL_N))
        fil(fillet_at(f"{tag}_SE", iid, s_loc, ms_e, SL_S, st.edge("right"), SW_E))
        if both:
            w_n = "NW: Block 14 Tract 'A' SE" if "DRAIN" in iid else "NW: Block 14 Lot 11 SE"
            w_s = "SW: Block 14 Lot 11 NE" if "DRAIN" in iid else "SW: west block NE (Sheet 1)"
            fil(fillet_at(f"{tag}_NW", iid, w_n, ms_w, SL_N, st.edge("left"), SW_W))
            fil(fillet_at(f"{tag}_SW", iid, w_s, st.edge("right"), SW_W, ms_w, SL_S))
    # Marina SE fillet straddles Mangrove's E R/W deflection: its PT must land on the south leg (past the vertex).
    v_erw = m_e_n.intersect(ms_e)
    f_mse = next(x for x in net.fillets if x.id == "F_MARINA_MANGROVE_SE")
    # the real block corner is on the N-leg R/W (the S-leg line is only extended to find the PI)
    f_mse.zone = [f_mse.pc, v_erw, marina_w.edge("right").intersect(m_e_n), f_mse.pt]
    # (travel runs north up Mangrove into the corner, so the Mangrove-side tangent point is the fillet PC)
    chk(Check("F_MARINA_MANGROVE_SE: Mangrove-side tangent point south of the E R/W deflection (ft past it)",
              ms_e.station(f_mse.pc) - ms_e.station(v_erw),
              f_mse.tangent - (ms_e.station(v_erw) - ms_e.station(k_marina_s)),
              "T (R=25', Δ=88°37'10\") from the corner minus the corner-to-vertex distance", tol=1e-6))
    chk(Check("Marina S R/W corner is north of Mangrove E R/W deflection (ft)",
              ms_e.station(v_erw) - ms_e.station(k_marina_s), 3.03, "must be < T = 25' for the fillet to be valid",
              tol=0.05))

    # Fillet frontage checks (Note 2: corner distances run to the street-line intersection = fillet PI)
    def f(fid: str) -> Fillet:
        return next(x for x in net.fillets if x.id == fid)

    chk(Check("Block 17 Lot 17 north frontage to fillet PI", _dist(
        starfish_s.intersect(mangrove.edge("left").offset(30.0 + 93.50 + 15 * 75.0 - 30.0, "left")),
        f("F_STARFISH_BEACHWOOD_SW").corner), 111.54, "Sheet 2 '111.54''"))
    chk(Check("Block 18 Lot 19 south frontage to fillet PI", _dist(
        f("F_STARFISH_BEACHWOOD_NW").corner, starfish_n.intersect(bnd_line("c1").offset(50.0 + 103.50 + 17 * 75.0,
                                                                                         "left"))),
        113.34, "Sheet 2 '113.34''"))
    chk(Check("Block 15 Lot 9 north frontage (Shellfish S R/W) end at Blvd W R/W",
              _dist(f("F_SHELLFISH_BEACHWOOD_SW").corner, f("F_KEEL_BEACHWOOD_NW").corner),
              200.0 / math.cos(math.radians(1.0 + 42 / 60 + 50 / 3600)), "Block 15 east lines 100.04' + 100.04'",
              tol=0.1))
    _ = keel_n

    # -- 5b. Marina Drive ℄ curve (Sheet 2 ℄ Curve Data R=359.27' T=122.70' Δ=37°42'50", CW onto S54°41'40"E).
    #        PC from the NE side: Mangrove E R/W corner + Block 16 Lot 33 93.50' + Lot 32 89.76' to the radial
    #        Lot 31/32 line (N02°24'30"W = square to the tangent), then 30' to the ℄ on the same radial.
    marina_d = _dms("37°42'50\"")
    k_mar_n = marina_w.edge("left").intersect(mangrove.edge("left"))
    pc_marina = _move(_move(k_mar_n, AZ_EW, 93.50 + 89.76), (AZ_EW + 90.0) % 360, 30.0)
    marina_curve = PlacedCurve(curve=Curve(359.27, marina_d, "CW"), pc=pc_marina, back_az=AZ_EW)
    net.placed_curves["C_MARINA_CL"] = marina_curve
    marina_diag = Street("MARINA_DIAG", "Marina Drive (SE tangent)", Line(marina_curve.pt, marina_curve.forward_az),
                         60.0, "P.T. of the ℄ curve, forward tangent S54°41'40\"E (printed N54°41'40\"W)")
    net.streets[marina_diag.id] = marina_diag
    # Check 1: the SW side gives the same PC (Lots 24/25 99.93' + 83.26' to the radial Lot 25/26 line).
    pc_sw = _move(_move(k_marina_s, AZ_EW, 99.93 + 83.26), (AZ_EW - 90.0) % 360, 30.0)
    chk(Check("Marina ℄ PC: NE-side lots (93.50+89.76) vs SW-side lots (99.93+83.26)", _dist(pc_marina, pc_sw), 0.0,
              "Block 16 Lots 33/32 | Lots 24/25"))
    chk(Check("Marina forward tangent = S54°41'40\" E (printed on the diagonal)",
              _wrap_sec(marina_curve.forward_az - bearing_to_az("S54°41'40\"E")), 0.0, "arc-seconds", tol=1.0))
    # Check 2: printed R/W edge chords (Note 1) fall out of the concentric edges, bearing by bearing.
    edges = row_edges(marina_curve, 60.0)
    for side, chords in (("outside", [(85.24, "S86°07'22\"E"), (85.24, "S73°33'06\"E"), (85.24, "S60°58'49\"E")]),
                         ("inside", [(99.37, "N83°43'45\"W"), (99.36, "N66°22'20\"W"), (17.24, "N56°11'40\"W")])):
        e = edges[side]
        a = AZ_EW
        for i, (ch, brg) in enumerate(chords, 1):
            d = 2.0 * math.degrees(math.asin(ch / 2.0 / e.curve.radius))
            printed = bearing_to_az(brg)
            if printed > 180.0 and a < 180.0:  # printed reversed (N..W) -> compare as travel direction
                printed = (printed + 180.0) % 360.0
            chk(Check(f"Marina {'NE' if side == 'outside' else 'SW'} edge chord {i} ({ch}' on R={e.curve.radius:.2f}) "
                      "bearing", _wrap_sec(a + d / 2.0 - printed), 0.0, f"printed {brg}, arc-seconds", tol=3.0))
            a += d
        chk(Check(f"Marina {'NE' if side == 'outside' else 'SW'} edge chords sum to ℄ Δ (arc-seconds)",
                  _wrap_sec(a - AZ_EW - marina_d), 0.0, "Σ chord Δ = 37°42'50\"", tol=5.0))
    # Check 3: boundary course c20 ends on Marina's NE R/W (c21 S54°41'40"E 100.16' then runs along it).
    chk(Check("Boundary c20 end lies on Marina NE R/W (offset from ℄)",
              -marina_diag.centerline.signed_offset(bnd["c20"]["end"]), 30.0, "caption c20/c21"))
    add_int("INT_MARINA_PC", "Marina Dr ℄ P.C.", marina_w, Line(pc_marina, (AZ_EW + 90.0) % 360), "radial Lot 31/32")
    net.intersections["INT_MARINA_PI"] = Intersection("INT_MARINA_PI", "Marina Dr ℄ P.I.", marina_curve.pi,
                                                      ("Marina Drive", "Marina Drive"), "PI", "T = 122.70'")
    add_int("INT_MARINA_PT", "Marina Dr ℄ P.T.", marina_diag, Line(marina_curve.pt,
                                                                     (marina_curve.forward_az + 90.0) % 360), "P.T.")
    add_int("INT_MARINA_BOUNDARY", "Marina Dr ℄ & Unit One line (course c20)", marina_diag, bnd_line("c20"),
            "course c20", "CL_X_BOUNDARY")
    net.runs.append(CenterlineRun("RUN_MARINA_W", marina_w.name, "INT_MARINA_MANGROVE", "INT_MARINA_PC",
                                  ints["INT_MARINA_MANGROVE"].point, pc_marina))
    net.runs.append(CenterlineRun("RUN_MARINA_DIAG", marina_diag.name, "INT_MARINA_PT", "INT_MARINA_BOUNDARY",
                                  marina_curve.pt, ints["INT_MARINA_BOUNDARY"].point))

    # -- 5c. Shellfish Dr east branch (℄ R=167.95' Δ=52°17'10") and Keel Dr west end (℄ R=143.93' Δ=52°17'10").
    #        Each E-W leg curves left (going west) onto S35°18'20"W and meets Marina's diagonal square. The P.T. is
    #        fixed from the east by the lot rows (Note 2: from the Blvd W R/W street-line corner):
    #          Shellfish N R/W: Blk 16 Lot 18 97.78' + Lots 26-19 8x75' to the Lot 26/27 line + the printed 5.45'
    #                           stub to the edge P.T. tick;
    #          Keel N R/W:      Blk 15 Lot 10 90' + Lots 11-14 4x75' to the radial Lot 14/15 line (edge P.T.).
    #        Independent checks: the printed 25.0' / 25.18' tangent legs from Marina's NE R/W corners to the edge
    #        P.C.s, the 115+110+125' Block 15 frontage between the two mouths, and the printed edge chords.
    ne35 = bearing_to_az("N35°18'20\"E")
    branch_d = _dms("52°17'10\"")
    marina_ne = marina_diag.edge("left")

    def branch(cid: str, street: Street, radius: float, east_row: float) -> PlacedCurve:
        k = street.edge("left").intersect(blvd_w)
        edge_pt = _move(k, W, east_row)
        pt_cl = street.centerline.intersect(Line(edge_pt, (AZ_EW + 90.0) % 360))
        c = Curve(radius, branch_d, "CW")
        pc = _move(_move(pt_cl, W, c.tangent), (ne35 + 180.0) % 360, c.tangent)
        placed = PlacedCurve(curve=c, pc=pc, back_az=ne35)
        net.placed_curves[cid] = placed
        return placed

    shell_c = branch("C_SHELLFISH_CL", shellfish, 167.95, 97.78 + 8 * 75.0 + 5.45)
    keel_c = branch("C_KEEL_CL", keel, 143.93, 90.0 + 4 * 75.0)
    shell_ne = Street("SHELLFISH_NE", "Shellfish Drive (mouth tangent)", Line(shell_c.pc, ne35), 60.0,
                      "back tangent N35°18'20\"E from Marina ℄ to the ℄ P.C.")
    keel_ne = Street("KEEL_NE", "Keel Drive (mouth tangent)", Line(keel_c.pc, ne35), 60.0,
                     "back tangent N35°18'20\"E from Marina ℄ to the ℄ P.C.")
    net.streets[shell_ne.id] = shell_ne
    net.streets[keel_ne.id] = keel_ne
    for label, placed, leg, st_ne in (("Shellfish", shell_c, 25.0, shell_ne), ("Keel", keel_c, 25.18, keel_ne)):
        for side_name, side in (("NW", "left"), ("SE", "right")):
            edge_line = st_ne.edge(side)
            edge_pc = edge_line.intersect(Line(placed.pc, (ne35 + 90.0) % 360))
            chk(Check(f"{label} {side_name} edge: Marina NE R/W corner to edge P.C. (printed tangent leg)",
                      _dist(edge_line.intersect(marina_ne), edge_pc), leg, f"Sheet 2 '{leg}' N35°18'20\"E"))
    e_sh, e_k = row_edges(shell_c, 60.0), row_edges(keel_c, 60.0)
    chk(Check("Shellfish SE edge chord (R=137.95, full Δ)", e_sh["inside"].curve.chord, 121.56,
              "Sheet 2 '121.56' N61°26'55\"E'"))
    chk(Check("Shellfish SE edge chord bearing (arc-seconds)",
              _wrap_sec(e_sh["inside"].chord_az - bearing_to_az("N61°26'55\"E")), 0.0, "printed", tol=3.0))
    a = ne35
    for ch in (51.68, 68.75, 59.50):
        a += 2.0 * math.degrees(math.asin(ch / 2.0 / e_sh["outside"].curve.radius))
    chk(Check("Shellfish NW edge chords 51.68+68.75+59.50 on R=197.95 sum to ℄ Δ (arc-seconds)",
              _wrap_sec(a - ne35 - branch_d), 0.0, "Blk 16 Lots 29/28/27; tol = 3 chords x 0.005' rounding on R=197.95 (~5\" each)", tol=20.0))
    chk(Check("Keel SE edge chord (R=113.93, full Δ)", e_k["inside"].curve.chord, 100.40,
              "Sheet 2 '100.40' N61°26'55\"E'"))
    chk(Check("Keel NW edge chord Lot 15 bearing (75.29' on R=173.93, ends at P.T.) (arc-seconds)",
              _wrap_sec(AZ_EW - math.degrees(math.asin(75.29 / 2.0 / e_k["outside"].curve.radius))
                        - bearing_to_az("N75°05'30\"E")), 0.0, "printed N75°05'30\"E", tol=5.0))
    # (Keel NW Lot 16 chord 82.45' is a known plat discrepancy -- formula 82.05'; pinned in plugins/curves
    #  test_notation.py::TestPlatDiscrepancies -- so it is not used as a check here.)
    x_shell = marina_diag.centerline.intersect(shell_ne.centerline)
    x_keel = marina_diag.centerline.intersect(keel_ne.centerline)
    chk(Check("Shellfish-to-Keel mouth spacing on Marina ℄ (Blk 15 Lots 1+18+17 = 115+110+125, + 2x30)",
              _dist(x_shell, x_keel), 115.0 + 110.0 + 125.0 + 60.0, "Sheet 2 Marina NE R/W frontages"))
    chk(Check("Shellfish mouth lies on Marina's SE tangent (ft past Marina P.T.)",
              marina_diag.centerline.station(x_shell) > shell_ne.half + FILLET_RADIUS, True,
              "mouth corners are line x line", tol=0))
    net.intersections["INT_MARINA_SHELLFISH"] = Intersection(
        "INT_MARINA_SHELLFISH", "Shellfish Dr & Marina Dr", x_shell, ("Shellfish Drive", "Marina Drive"), "CL_X_CL",
        "mouth tangent x Marina ℄")
    net.intersections["INT_MARINA_KEEL"] = Intersection(
        "INT_MARINA_KEEL", "Keel Dr & Marina Dr", x_keel, ("Keel Drive", "Marina Drive"), "CL_X_CL",
        "mouth tangent x Marina ℄")
    for cid, pl, nm in (("SHELLFISH", shell_c, "Shellfish Dr"), ("KEEL", keel_c, "Keel Dr")):
        for tag, q in (("PC", pl.pc), ("PI", pl.pi), ("PT", pl.pt)):
            iid = f"INT_{cid}_{tag}"
            net.intersections[iid] = Intersection(iid, f"{nm} ℄ {tag[0]}.{tag[1]}.", q, (nm, nm), tag,
                                                  "placed ℄ curve")
    for rid, st_, a_, b_ in (("RUN_SHELLFISH_MOUTH", shell_ne, "INT_MARINA_SHELLFISH", "INT_SHELLFISH_PC"),
                             ("RUN_SHELLFISH_EW", shellfish, "INT_SHELLFISH_PT", "INT_SHELLFISH_BEACHWOOD"),
                             ("RUN_KEEL_MOUTH", keel_ne, "INT_MARINA_KEEL", "INT_KEEL_PC"),
                             ("RUN_KEEL_EW", keel, "INT_KEEL_PT", "INT_KEEL_BEACHWOOD")):
        net.runs.append(CenterlineRun(rid, st_.name, a_, b_, ints[a_].point, ints[b_].point))
    # Block 16 Lot 29: its last Marina NE edge chord (S60°58'49"E 85.24') ends at the edge P.T. and the Shellfish
    # north-mouth 25' return starts there -- so return T + mouth half-width + edge P.T. must meet on Marina's NE R/W.
    ne_edge_pt = row_edges(marina_curve, 60.0)["outside"].pt
    chk(Check("Shellfish N mouth return starts at Marina NE edge P.T. (Blk 16 Lot 29 corner), ft along NE R/W",
              marina_ne.station(marina_ne.intersect(shell_ne.edge("left"))) - FILLET_RADIUS
              - marina_ne.station(ne_edge_pt), 0.0, "Marina NE chord 3 ends where the 25' return begins"))
    # 25' fillets at the four mouth corners (Marina NE R/W x the mouth-tangent R/W edges, 90°).
    SE_ = marina_diag.centerline.az
    for tag, st_, n_loc, s_loc in (("SHELLFISH", shell_ne, "N: Block 16 Lot 29 S", "S: Block 15 Lot 1 W"),
                                   ("KEEL", keel_ne, "N: Block 15 Lot 17 S", "S: Block 6 Lot 6 W")):
        iid = f"INT_MARINA_{tag}"
        fil(fillet_at(f"F_MARINA_{tag}_N", iid, n_loc, st_.edge("left"), ne35, marina_ne, (SE_ + 180.0) % 360))
        fil(fillet_at(f"F_MARINA_{tag}_S", iid, s_loc, marina_ne, SE_, st_.edge("right"), ne35))

    # -- 5d. Sands Ave (℄ R=459.36') and Cape Horn Ave (℄ R=327.01'), both Δ=36°20'00" CW from N88°58'20"E onto
    #        S54°41'40"E. P.C. on the radial at the printed distance from the Mangrove E R/W street-line corner:
    #        Sands 80' (Blk 7 Lot 23 / Blk 8 Lot 23 straight frontage to the P.C. tick), Cape Horn 25.0' (printed
    #        N88°58'20"E tangent leg at Blk 8 Lot 22 and Blk 9 Lot 27). Checks: every printed edge chord (length from the
    #        printed bearing pattern) and the boundary: c19 (60.14') is Sands' crossing, c15 (62.53') Cape Horn's.
    d36 = _dms("36°20'00\"")
    ms_e_line = mangrove_s.edge("left")

    def diag_street(cid: str, street: Street, radius: float, leg: float, chords: dict[str, list[tuple[float, str]]],
                    exit_course: str) -> tuple[PlacedCurve, Street]:
        corner = street.edge("left").intersect(ms_e_line)
        pc = _move(_move(corner, AZ_SANDS_W, leg), (AZ_SANDS_W + 90.0) % 360, street.half)
        placed = PlacedCurve(curve=Curve(radius, d36, "CW"), pc=pc, back_az=AZ_SANDS_W)
        net.placed_curves[cid] = placed
        diag = Street(f"{street.id.replace('_W', '')}_DIAG", street.name.replace("west tangent", "SE tangent"),
                      Line(placed.pt, placed.forward_az), street.row_width, "P.T. of the ℄ curve on S54°41'40\"E")
        net.streets[diag.id] = diag
        edges = row_edges(placed, street.row_width)
        for side, lst in chords.items():
            e = edges[side]
            run = AZ_SANDS_W
            for ch, brg in lst:
                b = bearing_to_az(brg)
                if abs(((b - run + 180.0) % 360.0) - 180.0) > 90.0:  # printed in the reverse direction
                    b = (b + 180.0) % 360.0
                d_i = 2.0 * (((b - run + 180.0) % 360.0) - 180.0)
                chk(Check(f"{street.name.split(' (')[0]} {'N' if side == 'outside' else 'S'} edge chord {ch}' "
                          f"{brg} (R={e.curve.radius:.2f})", 2.0 * e.curve.radius * math.sin(math.radians(d_i / 2.0)),
                          ch, "chord from the printed bearing pattern", tol=0.01))
                run += d_i
            chk(Check(f"{street.name.split(' (')[0]} {'N' if side == 'outside' else 'S'} edge: printed chord "
                      "bearings close on ℄ Δ (arc-seconds)", _wrap_sec(run - AZ_SANDS_W - d36), 0.0,
                      "Δ = 36°20'00\"", tol=1.0))
        c = bnd[exit_course]
        mid = ((c["start"][0] + c["end"][0]) / 2.0, (c["start"][1] + c["end"][1]) / 2.0)
        chk(Check(f"{street.name.split(' (')[0]} ℄ passes through the midpoint of its boundary crossing {exit_course} "
                  f"({c['distance']}')", diag.centerline.signed_offset(mid), 0.0, "caption course"))
        return placed, diag

    sands_c, sands_diag = diag_street(
        "C_SANDS_CL", sands_w, 459.36, 80.0,
        {"outside": [(17.08, "S89°58'20\"W"), (76.78, "N84°31'40\"W"), (76.78, "N75°31'40\"W"),
                     (76.78, "N66°31'40\"W"), (62.59, "N58°21'40\"W")],
         "inside": [(17.48, "N89°51'40\"W"), (89.76, "N82°41'40\"W"), (89.76, "N70°41'40\"W"),
                    (74.84, "N59°41'40\"W")]}, "c19")
    capehorn_c, capehorn_diag = diag_street(
        "C_CAPEHORN_CL", capehorn_w, 327.01, 25.0,
        {"outside": [(70.50, "N85°21'40\"W"), (80.83, "N73°11'40\"W"), (74.64, "N60°41'40\"W")],
         "inside": [(72.39, "S84°01'40\"E"), (108.25, "S66°31'40\"E"), (6.91, "S55°21'40\"E")]}, "c15")
    # San Salvadore Ave (Sheet 1): N R/W is Blk 9 Lot 27 140' + Lot 26 109' below Cape Horn's S R/W along Mangrove's
    # E R/W; ℄ R=269.96' (plat block; the engine had the N edge 299.96'), P.C. 25.0' past the corner (printed
    # "25.0' N88°58'20"E" at Blk 9 Lot 26 and Blk 12 Lot 8); exits the plat through c13 (N04°16'43"W 77.88').
    ch_s_corner = capehorn_w.edge("right").intersect(ms_e_line)
    ss_w = Street("SANSALVADORE_W", "San Salvadore Avenue (west tangent)",
                  Line(_move(_move(ch_s_corner, AZ_MANGROVE_S, 140.0 + 109.0 + 30.0), (AZ_SANDS_W + 180.0) % 360,
                             30.0), AZ_SANDS_W), 60.0,
                  "Mangrove E R/W: Blk 9 Lot 27 140' + Lot 26 109' + 30' below Cape Horn S R/W")
    net.streets[ss_w.id] = ss_w
    ss_c, ss_diag = diag_street(
        "C_SANSALVADORE_CL", ss_w, 269.96, 25.0,
        {"outside": [(67.91, "N84°31'40\"W"), (66.18, "N71°41'40\"W"), (55.76, "N60°01'40\"W")],
         "inside": [(106.60, "N78°11'40\"W"), (44.61, "N60°01'40\"W")]}, "c13")
    chk(Check("San Salvadore diagonal ℄ is 260' SW of Cape Horn diagonal ℄ (Blk 9: 100 + 100 + 2x30)",
              capehorn_diag.centerline.signed_offset(ss_c.pt), 260.0, "Sheet 1 Block 9 lot depths"))
    add_int("INT_SANSALVADORE_MANGROVE", "San Salvadore Ave & Mangrove Ave", ss_w, mangrove_s, "℄ x ℄")
    for tag, q in (("PC", ss_c.pc), ("PI", ss_c.pi), ("PT", ss_c.pt)):
        iid = f"INT_SANSALVADORE_{tag}"
        net.intersections[iid] = Intersection(iid, f"San Salvadore Ave ℄ {tag[0]}.{tag[1]}.", q,
                                              ("San Salvadore Avenue", "San Salvadore Avenue"), tag, "placed ℄ curve")
    add_int("INT_SANSALVADORE_BOUNDARY", "San Salvadore Ave ℄ & Unit One line (course c13)", ss_diag,
            bnd_line("c13"), "course c13", "CL_X_BOUNDARY")
    fil(fillet_at("F_SANSALVADORE_MANGROVE_NE", "INT_SANSALVADORE_MANGROVE", "NE: Block 9 Lot 26 SW",
                  ss_w.edge("left"), AZ_SANDS_W, ms_e_line, (AZ_MANGROVE_S + 180.0) % 360))
    fil(fillet_at("F_SANSALVADORE_MANGROVE_SE", "INT_SANSALVADORE_MANGROVE", "SE: Block 12 Lot 8 NW",
                  ms_e_line, AZ_MANGROVE_S, ss_w.edge("right"), AZ_SANDS_W))
    chk(Check("Sands diagonal ℄ is 260' SW of Marina diagonal ℄ (Blk 7: 100 + 100 + 2x30)",
              marina_diag.centerline.signed_offset(sands_c.pt), 260.0,
              "Sheet 2 Block 7 lot depths (SW = right of SE travel = +)"))
    for cid, placed, diag, exit_course, nm in (("SANDS", sands_c, sands_diag, "c19", "Sands Ave"),
                                              ("CAPEHORN", capehorn_c, capehorn_diag, "c15", "Cape Horn Ave")):
        for tag, q in (("PC", placed.pc), ("PI", placed.pi), ("PT", placed.pt)):
            iid = f"INT_{cid}_{tag}"
            net.intersections[iid] = Intersection(iid, f"{nm} ℄ {tag[0]}.{tag[1]}.", q, (nm, nm), tag,
                                                  "placed ℄ curve")
        add_int(f"INT_{cid}_BOUNDARY", f"{nm} ℄ & Unit One line (course {exit_course})", diag,
                bnd_line(exit_course), f"course {exit_course}", "CL_X_BOUNDARY")

    # Street ends on the boundary (west strip / south line), for the ℄ runs and the R/W corridors.
    add_int("INT_STARFISH_WEST_END", "Starfish Ave & west boundary c1", starfish, bnd_line("c1"), "course c1",
            "CL_X_BOUNDARY")
    add_int("INT_DRAIN40_WEST_END", "40' drainage R/W & west boundary c2", drain_40, bnd_line("c2"), "course c2",
            "CL_X_BOUNDARY")
    add_int("INT_CAPEHORN_WEST_END", "Cape Horn Ave & west boundary c2", capehorn_w, bnd_line("c2"), "course c2",
            "CL_X_BOUNDARY")
    add_int("INT_MANGROVE_NORTH_END", "Mangrove Ave & north boundary c27", mangrove, c27, "course c27",
            "CL_X_BOUNDARY")
    add_int("INT_MANGROVE_SOUTH_END", "Mangrove Ave & south line c5", mangrove_s, bnd_line("c5"), "course c5",
            "CL_X_BOUNDARY")

    # -- 5e. R/W corridors and the trimmed R/W linework (edges cut at the 25' fillets and street openings)
    def cl(sid: str) -> Line:
        return net.streets[sid].centerline

    def P(iid: str) -> Pt:
        return net.intersections[iid].point

    defl = P("INT_MANGROVE_DEFL")
    bis = Line(defl, (mangrove.centerline.az + mangrove_s.centerline.az) / 2.0 + 90.0)
    drain_e = _move(ms_e_line.intersect(drain_40.edge("right")), AZ_SANDS_W, 96.80)  # S-side frontage (Blk 8 Lot 22)
    drain_e_cl = drain_40.centerline.intersect(Line(drain_e, (AZ_SANDS_W + 90.0) % 360))
    cor = net.corridors.append
    cor(CorridorPiece("Mangrove Avenue", 30.0, P("INT_MANGROVE_NORTH_END"), defl, c27, bis))
    cor(CorridorPiece("Mangrove Avenue", 30.0, defl, P("INT_MANGROVE_SOUTH_END"), bis, bnd_line("c5")))
    cor(CorridorPiece("Starfish Avenue", 30.0, P("INT_STARFISH_WEST_END"), P("INT_STARFISH_BEACHWOOD"),
                      bnd_line("c1"), blvd.centerline))
    cor(CorridorPiece("Sail Avenue", 30.0, P("INT_SAIL_MANGROVE"), P("INT_SAIL_BEACHWOOD"), cl("MANGROVE_N"),
                      blvd.centerline))
    cor(CorridorPiece("Beachwood Boulevard", 40.0, P("INT_BLVD_NORTH_END"), P("INT_BLVD_SOUTH_END"), c27,
                      bnd_line("c25")))
    for street, start, start_cap, cid, end, end_cap, half in (
        ("Marina Drive", "INT_MARINA_MANGROVE", cl("MANGROVE_N"), "C_MARINA_CL", "INT_MARINA_BOUNDARY",
         bnd_line("c20"), 30.0),
        ("Shellfish Drive", "INT_MARINA_SHELLFISH", cl("MARINA_DIAG"), "C_SHELLFISH_CL", "INT_SHELLFISH_BEACHWOOD",
         blvd.centerline, 30.0),
        ("Keel Drive", "INT_MARINA_KEEL", cl("MARINA_DIAG"), "C_KEEL_CL", "INT_KEEL_BEACHWOOD", blvd.centerline,
         30.0),
        ("Sands Avenue", "INT_SANDS_MANGROVE", cl("MANGROVE_S"), "C_SANDS_CL", "INT_SANDS_BOUNDARY", bnd_line("c19"),
         30.0),
        ("Cape Horn Avenue", "INT_CAPEHORN_WEST_END", bnd_line("c2"), "C_CAPEHORN_CL", "INT_CAPEHORN_BOUNDARY",
         bnd_line("c15"), 30.0),
        ("San Salvadore Avenue", "INT_SANSALVADORE_MANGROVE", cl("MANGROVE_S"), "C_SANSALVADORE_CL",
         "INT_SANSALVADORE_BOUNDARY", bnd_line("c13"), 30.0),
    ):
        pl = net.placed_curves[cid]
        cor(CorridorPiece(street, half, P(start), pl.pc, start_cap, None))
        cor(CorridorPiece(street, half, arc=pl))
        cor(CorridorPiece(street, half, pl.pt, P(end), None, end_cap))
    cor(CorridorPiece("40' Drainage R/W", 20.0, P("INT_DRAIN40_WEST_END"), drain_e_cl, bnd_line("c2"), None))
    net.row_linework = trim_row_linework(net.corridors, net.fillets)
    # every fillet tangent point must be the end of a kept R/W piece (the return joins the trimmed edges)
    ends = [q for _, pts in net.row_linework for q in (pts[0], pts[-1])]
    unjoined = [f"{f.id}:{tag}" for f in net.fillets for tag, q in (("PC", f.pc), ("PT", f.pt))
                if min(_dist(q, e) for e in ends) > 1e-6]
    chk(Check(f"Every 25' fillet joins trimmed R/W edges at both tangent points (unjoined: {unjoined[:4]})",
              float(len(unjoined)), 0.0, "R/W linework topology", tol=0))

    # -- 6. ℄ Curve Data self-consistency (T = R tan(Δ/2)) with the plugin's Curve
    for cid, street, sheet, d_str, r, t_printed, direction in PLAT_CL_CURVE_DATA:
        c = Curve(radius=r, delta_deg=_dms(d_str), direction=direction)
        rec = {"id": cid, "street": street, "sheet": sheet, "delta": d_str, "radius": r, "tangent_printed": t_printed,
               "tangent": c.tangent, "arc_length": c.arc_length, "chord": c.chord, "external": c.external,
               "middle_ordinate": c.middle_ordinate, "edge_radii": (r - 30.0, r + 30.0)}
        net.curve_data.append(rec)
        # Shellfish T is a known plat discrepancy (82.35 printed vs 82.43): report it at 0.1' tolerance.
        chk(Check(f"{street} ℄ T = R tan(Δ/2)", c.tangent, t_printed, "℄ Curve Data block",
                  tol=0.1 if cid == "CL_SHELLFISH" else 0.01))

    return net


# ----------------------------------------------------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------------------------------------------------
def schedule_report(net: CenterlineNetwork) -> str:
    out: list[str] = []
    w = out.append
    w("BEACHWOOD UNIT TWO -- DERIVED CENTERLINE GEOMETRY (engine/centerline_geometry.py)")
    w("=" * 110)
    w(f"Boundary caption traverse closure (unbalanced): {net.boundary_closure_ft:.3f} ft")
    w("")
    w("STREETS")
    for s in net.streets.values():
        w(f"  {s.id:<16} {s.name:<30} R/W {s.row_width:>4.0f}'  ℄ {az_to_bearing(s.centerline.az):<14} {s.source}")
    w("")
    w("INTERSECTION SCHEDULE (℄ x ℄ / ℄ x boundary)")
    w(f"  {'ID':<26} {'Northing':>11} {'Easting':>11}  Name")
    for i in net.intersections.values():
        w(f"  {i.id:<26} {i.point[0]:>11.3f} {i.point[1]:>11.3f}  {i.name}")
    w("")
    w("CENTERLINE RUNS")
    for r in net.runs:
        w(f"  {r.id:<14} {r.street:<22} {r.start:<24} -> {r.end:<24} {r.bearing:<14} {r.length:>9.3f}'")
    w("")
    w(f"CORNER FILLETS (R = {FILLET_RADIUS:.0f}' at every street R/W corner)")
    w(f"  {'ID':<30} {'Delta':>11} {'T':>7} {'L':>7} {'Chord':>7} {'Chord brg':<14} Dir  Corner (PI) N/E")
    for x in net.fillets:
        w(f"  {x.id:<30} {deg_to_dms(x.delta_deg):>11} {x.tangent:>7.3f} {x.arc_length:>7.3f} {x.chord:>7.3f} "
          f"{x.chord_bearing:<14} {x.direction:<4} {x.corner[0]:.3f} / {x.corner[1]:.3f}   {x.location}")
    w("")
    w("℄ CURVE DATA (plat blocks, checked with plat_curves.Curve)")
    w(f"  {'Street':<18} {'Delta':>11} {'R':>8} {'T plat':>7} {'T calc':>8} {'L':>8} {'Chord':>8} {'Edge R':>16}")
    for c in net.curve_data:
        w(f"  {c['street']:<18} {c['delta']:>11} {c['radius']:>8.2f} {c['tangent_printed']:>7.2f} {c['tangent']:>8.3f} "
          f"{c['arc_length']:>8.3f} {c['chord']:>8.3f} {c['edge_radii'][0]:>7.2f}/{c['edge_radii'][1]:.2f}")
    w("")
    w("INDEPENDENT CHECKS")
    for c in net.checks:
        w(f"  [{'PASS' if c.ok else 'FAIL'}] {c.name:<66} derived {c.derived:>10.3f}  plat {c.plat:>10.3f}  "
          f"resid {c.residual:+.3f}  ({c.source})")
    w("")
    w(f"ALL CHECKS PASS: {net.all_checks_pass}  ({sum(c.ok for c in net.checks)}/{len(net.checks)})")
    return "\n".join(out)


if __name__ == "__main__":
    print(schedule_report(solve_network()))
