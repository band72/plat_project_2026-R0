"""Independent brute-force oracle for horizontal-curve geometry.

Shares NO code and NO derivation path with plat_curves.core / compound / plat_notation:

* Points are complex numbers ``n + i*e``; azimuth ``a`` (clockwise from north) is the unit vector ``exp(i*a)``, so a
  right turn (CW) is multiplication by ``exp(+i*phi)``.
* The arc is *walked*: heading is stepped by a small angle and the position integrated with Simpson's rule on
  ``exp(i*heading)``.  There is no ``R*tan(D/2)``, ``2R*sin(D/2)`` etc. anywhere.
* Tangent length = distance from PC to the real intersection of the back- and forward-tangent lines.
* Chord = |PT - PC| of the walked endpoints; arc length = Richardson-extrapolated polyline length of walked points.
* Radius point = intersection of the two radial (normal) lines, cross-checked against |RP-PC| = |RP-PT|.
* Middle ordinate / external = distances between the walked mid-arc point, the chord midpoint and the PI.
* Areas = shoelace on fine polygons (Richardson-extrapolated).
* Degree of curve = measured by walking 100 ft of arc / bisecting for a 100 ft chord.

Everything here is pure stdlib; local-frame walking (PC at origin, back tangent along azimuth 0) keeps the tiny-delta
cases well conditioned.
"""

from __future__ import annotations

import cmath
import functools
import math
import re
from dataclasses import dataclass

TWO_PI = 2.0 * math.pi


# --------------------------------------------------------------------------- basic complex helpers
def z(pt) -> complex:
    """(n, e) -> n + i e."""
    return complex(pt[0], pt[1])


def unit(az_deg: float) -> complex:
    """Unit vector of an azimuth (degrees clockwise from north)."""
    return cmath.exp(1j * math.radians(az_deg))


def az_of(v: complex) -> float:
    """Azimuth [0, 360) of a vector n + i e."""
    return math.degrees(cmath.phase(v)) % 360.0


def ang_diff(a: float, b: float) -> float:
    """Smallest signed difference a - b in degrees, in (-180, 180]."""
    d = (a - b) % 360.0
    return d - 360.0 if d > 180.0 else d


def cross(a: complex, b: complex) -> float:
    return a.real * b.imag - a.imag * b.real


def intersect_lines(p: complex, u: complex, q: complex, v: complex) -> complex:
    """Intersection of the infinite lines p + t*u and q + s*v."""
    den = cross(u, v)
    if den == 0.0:
        raise ZeroDivisionError("parallel lines")
    t = cross(q - p, v) / den
    return p + t * u


def shoelace(poly: list[complex]) -> float:
    """Absolute area of a simple polygon given as a vertex list (closed implicitly)."""
    acc = 0.0
    m = len(poly)
    for k in range(m):
        a, b = poly[k], poly[(k + 1) % m]
        acc += a.real * b.imag - b.real * a.imag
    return abs(acc) / 2.0


# --------------------------------------------------------------------------- dms / bearings (own implementation)
def dms_to_deg(d: float, m: float = 0.0, s: float = 0.0) -> float:
    return d + m / 60.0 + s / 3600.0


def deg_to_dms_parts(deg: float) -> tuple[int, int, float]:
    d = int(math.floor(deg))
    rem = (deg - d) * 60.0
    m = int(math.floor(rem))
    s = (rem - m) * 60.0
    return d, m, s


_BRG_RE = re.compile(r"^\s*([NS])\s*(\d+)\D+(\d+)\D+([\d.]+)\D*\s*([EW])\s*$", re.I)


def bearing_to_az(text: str) -> float:
    """Quadrant bearing 'S57°53'59"E' -> azimuth, done by hand."""
    m = _BRG_RE.match(text.replace("″", '"').replace("′", "'"))
    if not m:
        raise ValueError(text)
    ns, d, mi, se, ew = m.group(1).upper(), float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5).upper()
    a = dms_to_deg(d, mi, se)
    if ns == "N" and ew == "E":
        return a
    if ns == "S" and ew == "E":
        return 180.0 - a
    if ns == "S" and ew == "W":
        return 180.0 + a
    return 360.0 - a


def norm_bearing(text: str) -> str:
    """Strip whitespace so 'N 89°18'20" E' == 'N89°18'20"E' for string comparison."""
    return re.sub(r"\s+", "", text)


# --------------------------------------------------------------------------- the walked arc (local frame)
def _sgn(direction: str) -> int:
    return 1 if direction == "CW" else -1


def _walk(radius: float, angle_rad: float, direction: str, n: int) -> list[complex]:
    """Walk an arc of central angle `angle_rad` in n Simpson steps; local frame (start 0, heading az 0).

    Heading is the independent variable: h_k = sgn*k*dphi; ds = R*dphi; position += Simpson(exp(i*h)) * ds.
    """
    sg = _sgn(direction)
    dphi = angle_rad / n
    ds = radius * dphi
    p = 0j
    pts = [p]
    for k in range(n):
        h0 = sg * k * dphi
        f0 = cmath.exp(1j * h0)
        fm = cmath.exp(1j * (h0 + sg * dphi / 2.0))
        f1 = cmath.exp(1j * (h0 + sg * dphi))
        p += ds / 6.0 * (f0 + 4.0 * fm + f1)
        pts.append(p)
    return pts


def _steps_for(angle_rad: float, base: int = 400, per_rad: float = 1000.0) -> int:
    return max(base, int(math.ceil(angle_rad * per_rad)))


def walk_local_point(radius: float, s: float, direction: str) -> complex:
    """Local-frame position after walking arc distance s (s may be negative or exceed the curve length)."""
    if s == 0.0:
        return 0j
    ang = abs(s) / radius
    n = _steps_for(ang, base=60, per_rad=200.0)
    if s < 0.0:
        # walking backwards from the PC = walking forward on the opposite-turning arc, then reversing the vector
        return -_walk(radius, ang, "CCW" if direction == "CW" else "CW", n)[-1]
    return _walk(radius, ang, direction, n)[-1]


def _polyline_len(pts: list[complex]) -> float:
    return sum(abs(pts[k + 1] - pts[k]) for k in range(len(pts) - 1))


@dataclass(frozen=True)
class OracleArc:
    """Everything the oracle can say about a curve (R, delta, direction) in its local frame."""

    radius: float
    delta_deg: float
    direction: str
    length: float
    tangent: float
    chord: float
    middle_ordinate: float
    external: float
    sector_area: float
    segment_area: float
    fillet_area: float
    pt_local: complex
    pi_local: complex
    rp_local: complex
    mid_local: complex
    tangent_fwd: float  # PT -> PI distance (must equal `tangent`)

    @property
    def sgn(self) -> int:
        return _sgn(self.direction)


@functools.cache
def arc(radius: float, delta_deg: float, direction: str = "CW") -> OracleArc:
    """Brute-force everything for a curve.  Cached; pure function of (R, delta, direction)."""
    sg = _sgn(direction)
    ang = math.radians(delta_deg)
    n = _steps_for(ang)
    if n % 2:
        n += 1
    pts_n = _walk(radius, ang, direction, n)
    pts_2n = _walk(radius, ang, direction, 2 * n)
    pc = pts_2n[0]
    pt = pts_2n[-1]
    mid = pts_2n[n]  # exactly half-way in heading => half-way in arc

    # --- length: Richardson on the inscribed-polyline length (error ~ h^2)
    l1, l2 = _polyline_len(pts_n), _polyline_len(pts_2n)
    length = (4.0 * l2 - l1) / 3.0

    # --- tangent lines: back tangent from PC along az 0; forward tangent through PT with heading sg*delta
    u0 = 1.0 + 0j
    u1 = cmath.exp(1j * sg * ang)
    pi = intersect_lines(pc, u0, pt, u1)
    t_back = abs(pi - pc)
    t_fwd = abs(pt - pi)

    # --- radius point = intersection of the two normals (normal = tangent rotated 90 deg toward the centre)
    n0 = u0 * (1j * sg)
    n1 = u1 * (1j * sg)
    rp = intersect_lines(pc, n0, pt, n1)

    chord = abs(pt - pc)
    m_ord = abs(mid - (pc + pt) / 2.0)
    ext = abs(pi - mid)

    # --- areas by shoelace, Richardson on n / 2n (error ~ h^2)
    def areas(pts: list[complex]) -> tuple[float, float, float]:
        sector = shoelace([rp, *pts])
        segment = shoelace(list(pts))
        fillet = shoelace([*pts, pi])
        return sector, segment, fillet

    a1, a2 = areas(pts_n), areas(pts_2n)
    sec, seg, fil = ((4.0 * y - x) / 3.0 for x, y in zip(a1, a2, strict=True))

    return OracleArc(
        radius=radius,
        delta_deg=delta_deg,
        direction=direction,
        length=length,
        tangent=t_back,
        chord=chord,
        middle_ordinate=m_ord,
        external=ext,
        sector_area=sec,
        segment_area=seg,
        fillet_area=fil,
        pt_local=pt,
        pi_local=pi,
        rp_local=rp,
        mid_local=mid,
        tangent_fwd=t_fwd,
    )


# --------------------------------------------------------------------------- degree of curve (measured)
def degree_arc(radius: float) -> float:
    """Heading change (deg) over 100 ft of arc, measured from finite-difference tangent directions."""
    eps = 1e-3

    def tangent_dir(s: float) -> complex:
        # direction of the chord p(s+eps) - p(s-eps) (central difference), local frame CW
        return walk_local_point(radius, s + eps, "CW") - walk_local_point(radius, s - eps, "CW")

    a0 = az_of(tangent_dir(1.0))
    a1 = az_of(tangent_dir(101.0))
    # CW: heading grows.  Difference over exactly 100 ft of arc.
    return (a1 - a0) % 360.0


def degree_chord(radius: float) -> float:
    """Central angle (deg) whose chord is 100 ft, found by bisection on walked positions (needs R >= 50)."""
    lo, hi = 0.0, math.pi
    for _ in range(80):
        mid = (lo + hi) / 2.0
        c = abs(walk_local_point(radius, radius * mid, "CW"))
        if c < 100.0:
            lo = mid
        else:
            hi = mid
    return math.degrees((lo + hi) / 2.0)


# --------------------------------------------------------------------------- placing a curve in the plane
@dataclass(frozen=True)
class OraclePlaced:
    """A walked curve placed at pc with back tangent azimuth back_az."""

    arc: OracleArc
    pc: complex
    back_az: float

    @property
    def rot(self) -> complex:
        return unit(self.back_az)

    def to_global(self, local: complex) -> complex:
        return self.pc + self.rot * local

    @property
    def pt(self) -> complex:
        return self.to_global(self.arc.pt_local)

    @property
    def pi(self) -> complex:
        return self.to_global(self.arc.pi_local)

    @property
    def rp(self) -> complex:
        return self.to_global(self.arc.rp_local)

    @property
    def forward_az(self) -> float:
        return (self.back_az + self.arc.sgn * self.arc.delta_deg) % 360.0

    @property
    def chord_az(self) -> float:
        return az_of(self.pt - self.pc)

    def point_at(self, s: float) -> complex:
        return self.to_global(walk_local_point(self.arc.radius, s, self.arc.direction))

    def azimuth_at(self, s: float) -> float:
        """Direction of travel at s: direction of the chord between two walked points symmetric about s.

        (For a circular arc that chord is exactly parallel to the tangent at s.)  Use 0 < s < L.
        """
        eps = min(0.01, 0.01 * self.arc.length)
        return az_of(self.point_at(s + eps) - self.point_at(s - eps))


def placed(radius: float, delta_deg: float, direction: str, pc, back_az: float) -> OraclePlaced:
    return OraclePlaced(arc(radius, delta_deg, direction), z(pc), back_az)


def as_pt(v: complex) -> tuple[float, float]:
    return (v.real, v.imag)


# --------------------------------------------------------------------------- inverse problems (numerical root finding)
def solve_bisect(f, lo: float, hi: float, iters: int = 200) -> float:
    """Root of f on [lo, hi] (f(lo), f(hi) of opposite sign)."""
    flo = f(lo)
    for _ in range(iters):
        mid = (lo + hi) / 2.0
        fm = f(mid)
        if (fm < 0) == (flo < 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2.0


def chord_walk(radius: float, delta_deg: float) -> float:
    """Straight-line distance between the ends of a walked arc (light single-walk version, no caching)."""
    ang = math.radians(delta_deg)
    return abs(_walk(radius, ang, "CW", _steps_for(ang, base=200, per_rad=500.0))[-1])


def length_walk(radius: float, delta_deg: float) -> float:
    """Arc length as the Richardson-extrapolated polyline length of a walked arc (light, no caching)."""
    ang = math.radians(delta_deg)
    n = _steps_for(ang, base=200, per_rad=500.0)
    return (4.0 * _polyline_len(_walk(radius, ang, "CW", 2 * n)) - _polyline_len(_walk(radius, ang, "CW", n))) / 3.0


def delta_from_radius_and_chord(radius: float, chord: float) -> float:
    """Central angle (deg) that gives a walked chord of the requested length on this radius."""
    return solve_bisect(lambda deg: chord_walk(radius, deg) - chord, 1e-6, 179.999999, iters=60)


def delta_from_radius_and_arc(radius: float, length: float) -> float:
    """Central angle (deg) for a measured (walked) arc length."""
    return solve_bisect(lambda deg: length_walk(radius, deg) - length, 1e-6, 179.999999, iters=60)


# --------------------------------------------------------------------------- line / arc intersections
def line_arc_roots(p0, p1, plc: OraclePlaced, samples: int = 4000) -> list[tuple[complex, float]]:
    """Brute-force segment/arc intersections.  Returns (point, arc distance s) sorted along the segment.

    Sign-change scan of (|P(t) - RP| - R) on the segment, bisection refine, then keep roots whose polar angle from RP
    lies inside the swept arc (arc distance s measured from the PC by polar-angle difference).
    """
    a, b = z(p0), z(p1)
    rp = plc.rp
    r = plc.arc.radius
    sg = plc.arc.sgn
    pc_ang = cmath.phase(plc.pc - rp)

    def f(t: float) -> float:
        return abs(a + t * (b - a) - rp) - r

    out: list[tuple[complex, float]] = []
    prev_t, prev_f = 0.0, f(0.0)
    for k in range(1, samples + 1):
        t = k / samples
        ft = f(t)
        if (prev_f < 0) != (ft < 0):  # transversal crossing between prev_t and t
            root_t = solve_bisect(f, prev_t, t, iters=100)
            pt = a + root_t * (b - a)
            sweep = (sg * (cmath.phase(pt - rp) - pc_ang)) % TWO_PI
            if sweep > TWO_PI - 1e-9:  # a root sitting on the PC can wrap to ~2*pi by rounding
                sweep = 0.0
            s = sweep * r
            if s <= plc.arc.length + 1e-9:
                out.append((pt, s))
        prev_t, prev_f = t, ft
    return out


# --------------------------------------------------------------------------- tangent fillet (corner return)
def corner_fillet(corner, az_in: float, az_out: float, radius: float) -> dict:
    """Brute force: circle of `radius` tangent to line 1 (through corner along az_in) and line 2 (along az_out).

    Center = intersection of the two lines each shifted `radius` toward the inside of the turn; tangent points are
    the feet of the perpendiculars.  Returns center, tangent points, deflection and turn direction.
    """
    c = z(corner)
    u_in, u_out = unit(az_in), unit(az_out)
    turn = ang_diff(az_out, az_in)  # + = right turn (CW)
    sg = 1 if turn > 0 else -1
    # inward normal = 90 deg toward the turn side
    n_in = u_in * (1j * sg)
    n_out = u_out * (1j * sg)
    centre = intersect_lines(c + radius * n_in, u_in, c + radius * n_out, u_out)

    def foot(line_pt: complex, u: complex) -> complex:
        # foot of perpendicular from centre onto line (line_pt, u)
        w = centre - line_pt
        return line_pt + u * (w.real * u.real + w.imag * u.imag)

    pc = foot(c, u_in)
    pt = foot(c, u_out)
    return {
        "centre": centre,
        "pc": pc,
        "pt": pt,
        "delta_deg": abs(turn),
        "direction": "CW" if sg > 0 else "CCW",
        "tangent": abs(pc - c),
        "tangent_out": abs(pt - c),
        "chord": abs(pt - pc),
    }


# --------------------------------------------------------------------------- cul-de-sac reverse-fillet (numerical)
def cul_de_sac_numeric(bulb_radius: float, throat_half_width: float, fillet_radius: float) -> dict:
    """Fillet circle tangent to the throat line (offset w from the axis) and externally tangent to the bulb.

    Frame: bulb centre at origin, x along the throat axis (outward from the bulb), y across.  The fillet centre lies on
    y = w + Rf (outside the road); root-find x so that |F - O| = Rb + Rf.  PRC = point on the line O->F at Rb from O.
    """
    rb, w, rf = bulb_radius, throat_half_width, fillet_radius
    y = w + rf

    def f(x: float) -> float:
        return math.hypot(x, y) - (rb + rf)

    x = solve_bisect(f, 0.0, 10.0 * (rb + rf) + 1.0)
    fc = complex(x, y)
    prc = fc * (rb / abs(fc))
    tp = complex(x, w)  # throat tangent point (foot of perpendicular from F onto y = w)
    theta = math.degrees(math.atan2(prc.imag, prc.real))
    return {"yf": x, "fillet_centre": fc, "prc": prc, "throat_tangent": tp, "theta_prc_deg": theta}
