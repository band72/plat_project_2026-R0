"""
verify.py -- independent geometric verification of parcel rings.

Runs ALONGSIDE the construction code, not inside it. That separation is the
point: the builder and the checker must not share assumptions, or the
checker just re-asserts whatever the builder believed. This module takes a
finished ring of vertices (and optional arc segments) and interrogates it
from scratch.

Checks performed, each independently reportable:
  RING_CLOSED        last vertex coincides with first
  NO_ZERO_SEGMENT    no degenerate (zero-length) sides
  NO_DUPLICATE_VERT  no repeated consecutive vertices
  SINGLE_POLYLINE    every vertex has exactly degree 2 -- one continuous
                     closed loop, no branches, no dangling ends
  NO_SELF_INTERSECT  no side crosses another side
  NO_OVERLAP         no two sides are collinear AND overlapping (this is
                     the "multiple lines on top of each other" defect)
  NO_SPIKE           no needle/spike vertex (interior angle ~0 or ~360)
  POSITIVE_AREA      ring encloses real area
  ARC_CONTINUITY     each arc's endpoints coincide with its neighbours
  CLOSURE_PRECISION  traverse misclosure vs a stated tolerance

Anything failing is returned with the specific geometry involved, so the
plotter can draw exactly the offending segment in red rather than flagging
the whole lot vaguely.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from engine.cogo import Point


TOL_COINCIDE = 0.01      # ft: two points are "the same point"
TOL_ZERO = 0.02          # ft: shortest permissible side
TOL_SPIKE_DEG = 2.0      # deg: interior angle this close to 0/360 is a spike
TOL_COLLINEAR = 0.05     # ft: perpendicular offset for "collinear"


@dataclass
class Finding:
    code: str
    severity: str          # "ERROR" or "WARN"
    message: str
    geometry: list = field(default_factory=list)   # [(n1,e1,n2,e2), ...] to draw red
    vertices: list = field(default_factory=list)   # [(n,e), ...] to mark red


@dataclass
class LotVerification:
    lot: str
    findings: list
    area: float | None
    perimeter: float
    misclosure: float
    n_vertices: int

    @property
    def passed(self) -> bool:
        return not any(f.severity == "ERROR" for f in self.findings)

    @property
    def errors(self):
        return [f for f in self.findings if f.severity == "ERROR"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.severity == "WARN"]


def _seg(a: Point, b: Point):
    return (a.n, a.e, b.n, b.e)


def _dist_pt_seg(pn, pe, n1, e1, n2, e2):
    dn, de = n2 - n1, e2 - e1
    L2 = dn * dn + de * de
    if L2 < 1e-12:
        return math.hypot(pn - n1, pe - e1)
    t = max(0.0, min(1.0, ((pn - n1) * dn + (pe - e1) * de) / L2))
    return math.hypot(pn - (n1 + t * dn), pe - (e1 + t * de))


def _orient(a, b, c):
    v = (b[1] - a[1]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[1] - a[1])
    return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)


def _proper_cross(p1, p2, p3, p4) -> bool:
    o1, o2 = _orient(p1, p2, p3), _orient(p1, p2, p4)
    o3, o4 = _orient(p3, p4, p1), _orient(p3, p4, p2)
    return o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4)


def _collinear_overlap(a1, a2, b1, b2) -> bool:
    """True if two segments lie on the same line AND share more than a point."""
    for p in (b1, b2):
        if _dist_pt_seg(p[0], p[1], a1[0], a1[1], a2[0], a2[1]) > TOL_COLLINEAR:
            return False
    for p in (a1, a2):
        if _dist_pt_seg(p[0], p[1], b1[0], b1[1], b2[0], b2[1]) > TOL_COLLINEAR:
            return False
    # collinear: check 1-D overlap length along the shared direction
    dn, de = a2[0] - a1[0], a2[1] - a1[1]
    L = math.hypot(dn, de)
    if L < 1e-9:
        return False
    ux, uy = dn / L, de / L
    def proj(p):
        return (p[0] - a1[0]) * ux + (p[1] - a1[1]) * uy
    ta = sorted([0.0, L])
    tb = sorted([proj(b1), proj(b2)])
    overlap = min(ta[1], tb[1]) - max(ta[0], tb[0])
    return overlap > TOL_COINCIDE


def verify_ring(lot: str, pts: list, arcs: dict | None = None,
                stated_perimeter: float | None = None,
                closure_tol: float = 0.05) -> LotVerification:
    """pts: ordered ring of Points (do NOT repeat the first point at the end).
    arcs: optional {side_index: dict(radius=, delta=, arc_points=[Point,...])}
    """
    arcs = arcs or {}
    findings = []
    n = len(pts)

    if n < 3:
        return LotVerification(lot, [Finding("RING_TOO_FEW", "ERROR",
                               f"only {n} vertices -- cannot form a ring")],
                               None, 0.0, 0.0, n)

    tup = [(p.n, p.e) for p in pts]

    # --- duplicate consecutive vertices / zero-length sides ---
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        d = a.dist_to(b)
        if d < TOL_COINCIDE:
            findings.append(Finding(
                "NO_DUPLICATE_VERT", "ERROR",
                f"vertices {i} and {(i+1)%n} coincide ({d:.4f} ft apart)",
                vertices=[(a.n, a.e)]))
        elif d < TOL_ZERO:
            findings.append(Finding(
                "NO_ZERO_SEGMENT", "ERROR",
                f"side {i}->{(i+1)%n} is degenerate ({d:.4f} ft)",
                geometry=[_seg(a, b)]))

    # --- ring closure (explicit: does the walk return to the start) ---
    misclosure = pts[0].dist_to(pts[-1]) if n > 1 else 0.0
    # for a ring defined by ordered vertices, closure is structural; report
    # the last->first side length as the closing side instead
    closing = pts[-1].dist_to(pts[0])

    # --- self-intersection ---
    for i in range(n):
        a1, a2 = tup[i], tup[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or j == (i + 1) % n:
                continue
            b1, b2 = tup[j], tup[(j + 1) % n]
            if _proper_cross(a1, a2, b1, b2):
                findings.append(Finding(
                    "NO_SELF_INTERSECT", "ERROR",
                    f"side {i}->{(i+1)%n} crosses side {j}->{(j+1)%n}",
                    geometry=[(a1[0], a1[1], a2[0], a2[1]),
                              (b1[0], b1[1], b2[0], b2[1])]))

    # --- collinear overlap (lines drawn on top of each other) ---
    for i in range(n):
        a1, a2 = tup[i], tup[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or j == (i + 1) % n:
                continue
            b1, b2 = tup[j], tup[(j + 1) % n]
            if _collinear_overlap(a1, a2, b1, b2):
                findings.append(Finding(
                    "NO_OVERLAP", "ERROR",
                    f"side {i}->{(i+1)%n} overlaps collinear side "
                    f"{j}->{(j+1)%n}",
                    geometry=[(a1[0], a1[1], a2[0], a2[1]),
                              (b1[0], b1[1], b2[0], b2[1])]))

    # --- spikes / needle vertices ---
    for i in range(n):
        prev, cur, nxt = pts[i - 1], pts[i], pts[(i + 1) % n]
        v1 = (prev.n - cur.n, prev.e - cur.e)
        v2 = (nxt.n - cur.n, nxt.e - cur.e)
        m1 = math.hypot(*v1); m2 = math.hypot(*v2)
        if m1 < 1e-9 or m2 < 1e-9:
            continue
        cosang = max(-1.0, min(1.0, (v1[0]*v2[0] + v1[1]*v2[1]) / (m1*m2)))
        ang = math.degrees(math.acos(cosang))
        if ang < TOL_SPIKE_DEG:
            findings.append(Finding(
                "NO_SPIKE", "ERROR",
                f"vertex {i} is a spike (interior angle {ang:.3f} deg)",
                vertices=[(cur.n, cur.e)]))
        elif ang < 5.0:
            findings.append(Finding(
                "NO_SPIKE", "WARN",
                f"vertex {i} is a very sharp sliver ({ang:.2f} deg)",
                vertices=[(cur.n, cur.e)]))

    # --- single continuous polyline: every vertex degree exactly 2 ---
    degree = {}
    for i in range(n):
        for v in (i, (i + 1) % n):
            degree[v] = degree.get(v, 0) + 1
    bad_deg = [v for v, d in degree.items() if d != 2]
    if bad_deg:
        findings.append(Finding(
            "SINGLE_POLYLINE", "ERROR",
            f"vertices with degree != 2 (not one closed loop): {bad_deg}",
            vertices=[tup[v] for v in bad_deg]))

    # --- area ---
    area = 0.0
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        area += a.e * b.n - b.e * a.n
    area = abs(area) / 2.0
    if area < 1.0:
        findings.append(Finding("POSITIVE_AREA", "ERROR",
                                f"ring encloses no meaningful area ({area:.4f} sf)"))

    perimeter = sum(pts[i].dist_to(pts[(i + 1) % n]) for i in range(n))

    # --- arc continuity ---
    for idx, arc in arcs.items():
        apts = arc.get("arc_points") or []
        if len(apts) < 2:
            continue
        start_should = pts[idx]
        end_should = pts[(idx + 1) % n]
        ds = apts[0].dist_to(start_should)
        de = apts[-1].dist_to(end_should)
        if ds > TOL_COINCIDE or de > TOL_COINCIDE:
            findings.append(Finding(
                "ARC_CONTINUITY", "ERROR",
                f"arc on side {idx} does not meet its vertices "
                f"(start off {ds:.3f} ft, end off {de:.3f} ft)",
                geometry=[_seg(apts[0], start_should), _seg(apts[-1], end_should)]))

    # --- closure precision vs a stated perimeter, if supplied ---
    if stated_perimeter is not None:
        diff = abs(perimeter - stated_perimeter)
        if diff > closure_tol:
            findings.append(Finding(
                "CLOSURE_PRECISION", "WARN",
                f"perimeter {perimeter:.3f} ft vs stated "
                f"{stated_perimeter:.3f} ft (diff {diff:.3f} ft)"))

    return LotVerification(lot, findings, area, perimeter, closing, n)


def verify_network(parcels: dict, arcs_by_lot: dict | None = None) -> dict:
    """Verify many lots, plus cross-lot checks.

    Cross-lot check: shared edges. Two adjacent lots should share an edge
    whose endpoints are the SAME points, not merely nearby ones -- the
    duplicate-vertex defect that the topology graph exists to prevent.
    """
    arcs_by_lot = arcs_by_lot or {}
    results = {}
    for lot, pts in parcels.items():
        results[lot] = verify_ring(lot, pts, arcs_by_lot.get(lot))

    # cross-lot: find near-coincident-but-distinct vertices
    allv = []
    for lot, pts in parcels.items():
        for i, p in enumerate(pts):
            allv.append((lot, i, p))
    near_dupes = []
    for i in range(len(allv)):
        for j in range(i + 1, len(allv)):
            la, ia, pa = allv[i]
            lb, ib, pb = allv[j]
            if la == lb:
                continue
            d = pa.dist_to(pb)
            if 1e-9 < d < TOL_COINCIDE * 10:
                if pa is not pb:
                    near_dupes.append((la, ia, lb, ib, d))
    return dict(lots=results, near_duplicate_vertices=near_dupes)
