"""Compound / reverse curves, concentric offsets, corner returns, cul-de-sacs and lot lines on arcs.

Stdlib only; builds exclusively on :mod:`plat_curves.core` (Point = ``(n, e)``, azimuth = degrees clockwise from north,
``"CW"`` = turns right going PC -> PT, ``"CCW"`` = turns left).

Angle conventions used in this module (read before calling anything):

* ``delta_deg`` / ``second_delta_deg`` / ``.delta_deg`` are always the **central angle = deflection angle** of one arc
  (equal to the change of tangent direction along that arc). They are never interior angles.
* :func:`corner_return` takes the two street lines as *travel azimuths* (``az_in`` into the corner, ``az_out`` out of
  it), so the curve's Δ is the **deflection** ``|az_out - az_in|`` (wrapped). For two street lines meeting with an
  **interior** angle I (the wedge that contains the fillet, e.g. 90° at a square block corner), Δ = 180° - I.
* :func:`cul_de_sac` reports ``theta_prc_deg`` = angle at the bulb centre between the street axis (toward the street
  mouth) and the radial through each PRC. It is neither an interior nor a deflection angle of any street corner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from plat_curves.core import Curve, PlacedCurve, Pt, dist
from plat_curves.core import az as _az_between
from plat_curves.core import offset as _move

__all__ = [
    "CompoundCurve",
    "ReverseCurve",
    "concentric",
    "corner_return",
    "cul_de_sac",
    "line_angle_to_radial",
    "line_arc_intersections",
    "nonradial_line",
    "radial_line",
    "row_edges",
]

_EPS = 1e-9


def _wrap180(angle_deg: float) -> float:
    """Wrap an angle difference into [-180, 180)."""
    return (angle_deg + 180.0) % 360.0 - 180.0


def _check_s(placed: PlacedCurve, s: float) -> None:
    """Reject an arc distance outside the arc (0 <= s <= L, 1e-9 ft slack)."""
    if not -_EPS <= s <= placed.curve.arc_length + _EPS:
        raise ValueError(f"arc distance s={s} outside the arc [0, {placed.curve.arc_length}]")


def _flip(direction: str) -> str:
    return "CCW" if direction == "CW" else "CW"


# --------------------------------------------------------------------------------------------------------------------
# Concentric offsets / right-of-way edges
# --------------------------------------------------------------------------------------------------------------------


def concentric(placed: PlacedCurve, offset: float, side: str = "outside") -> PlacedCurve:
    """Concentric curve: same RP, same Δ, same direction; radius R + offset ("outside") or R - offset ("inside").

    "outside" means away from the radius point RP (larger radius), "inside" means toward RP (smaller radius) -- this is
    independent of CW/CCW. PC and PT stay on the same radial lines as the original (PC' = RP + R'·û(RP->PC)), and the
    back tangent azimuth is unchanged, so the offset curve is parallel to the original everywhere. Arc length scales
    with R (L' = L·R'/R) and the tangent length is NOT the original T (T' = R'·tan(Δ/2)).

    ``delta_deg`` is unchanged (central angle / deflection). Raises ``ValueError`` for a negative offset, an unknown
    side, or ``R - offset <= 0``.
    """
    if side not in ("outside", "inside"):
        raise ValueError(f"side must be 'outside' or 'inside', got {side!r}")
    if offset < 0:
        raise ValueError(f"offset must be >= 0 (use side= to choose the direction), got {offset}")
    curve = placed.curve
    new_radius = curve.radius + offset if side == "outside" else curve.radius - offset
    if new_radius <= 0:
        raise ValueError(f"inside offset {offset} >= radius {curve.radius}: offset curve collapses through the RP")
    new_pc = _move(placed.rp, placed.radial_az_at(0.0), new_radius)
    return PlacedCurve(
        curve=Curve(radius=new_radius, delta_deg=curve.delta_deg, direction=curve.direction),
        pc=new_pc,
        back_az=placed.back_az,
    )


def row_edges(placed_centerline: PlacedCurve, row_width: float) -> dict[str, PlacedCurve]:
    """Right-of-way edges of a curved street: centerline ± ``row_width``/2, as concentric curves.

    Returns ``{"outside": R + w/2, "inside": R - w/2}`` (relative to the RP). For a 269.96' / 36°20'00" centerline and
    a 60' ROW the edges are R = 299.96' and R = 239.96' with the same Δ. Raises ``ValueError`` if ``row_width <= 0``
    or the inside edge would have R <= 0.
    """
    if row_width <= 0:
        raise ValueError(f"row_width must be > 0, got {row_width}")
    half = row_width / 2.0
    return {
        "outside": concentric(placed_centerline, half, "outside"),
        "inside": concentric(placed_centerline, half, "inside"),
    }


# --------------------------------------------------------------------------------------------------------------------
# Reverse (PRC) and compound (PCC) curve pairs
# --------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _CurvePair:
    """Two consecutive arcs sharing a junction and a common tangent (base of PRC / PCC pairs)."""

    first: PlacedCurve
    second: PlacedCurve

    _REVERSE = False  # subclasses override: True = opposite turning direction

    @property
    def junction(self) -> Pt:
        """The PRC/PCC: the PT of the first arc (the PC of the second is checked against it by :meth:`check`)."""
        return self.first.pt

    @property
    def rp1(self) -> Pt:
        return self.first.rp

    @property
    def rp2(self) -> Pt:
        return self.second.rp

    @property
    def center_distance(self) -> float:
        """Actual |RP1 - RP2| in feet."""
        return dist(self.first.rp, self.second.rp)

    @property
    def expected_center_distance(self) -> float:
        """R1 + R2 for a reverse pair, |R1 - R2| for a compound pair."""
        r1, r2 = self.first.curve.radius, self.second.curve.radius
        return r1 + r2 if self._REVERSE else abs(r1 - r2)

    @property
    def total_arc_length(self) -> float:
        return self.first.curve.arc_length + self.second.curve.arc_length

    @property
    def net_deflection_deg(self) -> float:
        """Signed total change of tangent direction PC1 -> PT2 (CW positive): Δ1 - Δ2 (reverse) or Δ1 + Δ2 (compound)."""
        c1, c2 = self.first.curve, self.second.curve
        return c1.sign * c1.delta_deg + c2.sign * c2.delta_deg

    def check(self, tol: float = 1e-6) -> dict:
        """Numeric residuals for a valid pair (all ~0 when consistent; feet unless noted).

        * ``junction_gap``   -- distance between PT1 and PC2.
        * ``tangent_az``     -- common tangent azimuth difference at the junction, first.forward_az - second.back_az
          (degrees, wrapped to [-180, 180)).
        * ``collinearity``   -- perpendicular distance of the junction from the line RP1--RP2 (0 when RP1, RP2 and the
          junction are collinear, i.e. the arcs share a radial line there).
        * ``center_distance``-- |RP1 - RP2| minus (R1 + R2) for a reverse pair, minus |R1 - R2| for a compound pair.
        * ``turning``        -- 0.0 if the turning directions are opposite (reverse) / equal (compound), else 1.0.
        * ``ok``             -- True when every residual is within ``tol``.
        """
        j = self.first.pt
        rp1, rp2 = self.first.rp, self.second.rp
        d12 = dist(rp1, rp2)
        if d12 < _EPS:  # concentric arcs of equal radius (degenerate compound): centres coincide, radials agree
            colin = 0.0
        else:
            cross = (rp2[0] - rp1[0]) * (j[1] - rp1[1]) - (rp2[1] - rp1[1]) * (j[0] - rp1[0])
            colin = abs(cross) / d12
        same_turn = self.first.curve.direction == self.second.curve.direction
        turning = 0.0 if same_turn != self._REVERSE else 1.0
        out = {
            "junction_gap": dist(self.first.pt, self.second.pc),
            "tangent_az": _wrap180(self.first.forward_az - self.second.back_az),
            "collinearity": colin,
            "center_distance": d12 - self.expected_center_distance,
            "turning": turning,
        }
        out["ok"] = all(abs(v) <= tol for v in out.values())
        return out

    @classmethod
    def _second_from(cls, first: PlacedCurve, second_radius: float, second_delta_deg: float) -> PlacedCurve:
        direction = _flip(first.curve.direction) if cls._REVERSE else first.curve.direction
        return PlacedCurve(
            curve=Curve(radius=second_radius, delta_deg=second_delta_deg, direction=direction),
            pc=first.pt,
            back_az=first.forward_az,
        )


@dataclass(frozen=True)
class ReverseCurve(_CurvePair):
    """PRC: two arcs turning in OPPOSITE directions with a common tangent at the point of reverse curvature.

    Their radius points lie on opposite sides of the tangent, collinear with the PRC, |RP1 - RP2| = R1 + R2.
    Build the second arc from the first with :meth:`from_curves`, or wrap two independently built arcs in
    ``ReverseCurve(first, second)`` and call :meth:`check` to test them.
    """

    _REVERSE = True

    @property
    def prc(self) -> Pt:
        """Point of reverse curvature (PT of the first arc)."""
        return self.junction

    @classmethod
    def from_curves(cls, first: PlacedCurve, second_radius: float, second_delta_deg: float) -> ReverseCurve:
        """Append a reverse arc (opposite direction, radius ``second_radius``, central angle/deflection Δ2)."""
        return cls(first=first, second=cls._second_from(first, second_radius, second_delta_deg))


@dataclass(frozen=True)
class CompoundCurve(_CurvePair):
    """PCC: two arcs turning in the SAME direction with a common tangent at the point of compound curvature.

    Their radius points lie on the same side of the tangent, collinear with the PCC, |RP1 - RP2| = |R1 - R2|.
    """

    _REVERSE = False

    @property
    def pcc(self) -> Pt:
        """Point of compound curvature (PT of the first arc)."""
        return self.junction

    @classmethod
    def from_curves(cls, first: PlacedCurve, second_radius: float, second_delta_deg: float) -> CompoundCurve:
        """Append a compound arc (same direction, radius ``second_radius``, central angle/deflection Δ2)."""
        return cls(first=first, second=cls._second_from(first, second_radius, second_delta_deg))


# --------------------------------------------------------------------------------------------------------------------
# Corner return
# --------------------------------------------------------------------------------------------------------------------


def corner_return(corner: Pt, az_in: float, az_out: float, radius: float = 25.0) -> PlacedCurve:
    """Tangent fillet of ``radius`` between two street lines that meet at ``corner`` (the PI of the fillet).

    ``az_in``  = azimuth of travel INTO the corner along line 1; ``az_out`` = azimuth of travel OUT of the corner
    along line 2 (both are travel directions, in degrees). The curve's Δ is the DEFLECTION between them,
    Δ = |wrap(az_out - az_in)|; for a corner whose two lines make an INTERIOR angle I (the wedge holding the fillet)
    Δ = 180° - I, so a square block corner (I = 90°) has Δ = 90°.

    Geometry: T = R·tan(Δ/2) back along line 1 (PC) and forward along line 2 (PT), so both tangent points are
    equidistant from the corner; the RP lies on the bisector at R/cos(Δ/2) from the corner. For Δ = 90° and R = 25':
    T = 25', chord = R√2 = 35.355'. Direction is CW if the turn from ``az_in`` to ``az_out`` is to the right.

    Raises ``ValueError`` for a non-positive radius or parallel/antiparallel lines (Δ = 0 or 180°).
    """
    if radius <= 0:
        raise ValueError(f"radius must be > 0, got {radius}")
    delta = abs(_wrap180(az_out - az_in))
    if delta < _EPS or abs(delta - 180.0) < _EPS:
        raise ValueError(f"az_in={az_in} and az_out={az_out} are parallel: no fillet (Δ={delta})")
    return PlacedCurve.from_pi(corner, az_in, az_out, radius)


# --------------------------------------------------------------------------------------------------------------------
# Cul-de-sac with reverse-fillet throat
# --------------------------------------------------------------------------------------------------------------------


def cul_de_sac(
    center: Pt,
    bulb_radius: float,
    throat_half_width: float,
    fillet_radius: float = 25.0,
    axis_az: float = 0.0,
) -> dict:
    """Symmetric cul-de-sac bulb joined to a straight street by two reverse fillets (right-of-way boundary).

    ``center``            bulb centre C; ``bulb_radius`` Rb = right-of-way radius of the bulb.
    ``throat_half_width`` w = half the street right-of-way width (edge offset from the street axis).
    ``fillet_radius``     Rf (default 25', Sheet 2 Note 4).
    ``axis_az``           azimuth of travel along the street axis TOWARD the bulb (mouth -> dead end); default 0 = north.

    Each fillet is tangent to a street edge line and externally tangent to the bulb circle (a PRC), its RP lying
    OUTSIDE the right-of-way at lateral offset w + Rf from the axis and distance Rb + Rf from C:

        yf        = sqrt((Rb + Rf)² - (w + Rf)²)     distance from C along the axis toward the mouth to the fillet PC/RP
        theta_prc = asin((w + Rf) / (Rb + Rf))       angle at C between the mouth axis and each PRC radial
        fillet Δ  = 90° - theta_prc                  (= acos((w + Rf)/(Rb + Rf)))
        bulb sweep= 360° - 2·theta_prc               (going around the dead end, PRC1 -> PRC2)

    Net signed turning of the boundary (CW positive) is +Δf - sweep + Δf = -180°: it enters heading ``axis_az`` and
    leaves heading ``axis_az + 180°`` (a U-turn to the left overall).

    Path (looking along ``axis_az``): enter on the RIGHT street edge at ``pc``, fillet 1 (CW) to ``prc_1``, bulb (CCW,
    sweep > 180° so it is returned as two halves split at ``apex`` = C + Rb along the axis) to ``prc_2``, fillet 2 (CW)
    to ``pt`` on the LEFT street edge.

    Returns a dict with: ``yf, theta_prc_deg, fillet_delta_deg, bulb_sweep_deg, bulb_arc_length, fillet_arc_length,
    pc, prc_1, prc_2, pt, apex, rp_fillet_1, rp_fillet_2, center, axis_az, bulb_radius, throat_half_width,
    fillet_radius, fillet_1, fillet_2`` (PlacedCurve), ``bulb_1, bulb_2`` (PlacedCurve, CCW, Δ = 180° - theta_prc each),
    ``reverse_1, reverse_2`` (ReverseCurve pairs fillet_1|bulb_1 and bulb_2|fillet_2) and ``check`` (their
    ``check()`` dicts, bulb-half join residuals, ``net_turn_deg`` (= -180) and ``net_turn_residual_deg`` (~0)).

    Raises ``ValueError`` unless Rb > w > 0 and Rf > 0 (otherwise the fillet cannot reach the bulb).
    """
    rb, w, rf = bulb_radius, throat_half_width, fillet_radius
    if not (rb > 0 and w > 0 and rf > 0):
        raise ValueError("bulb_radius, throat_half_width and fillet_radius must all be > 0")
    if rb <= w:
        raise ValueError(f"bulb_radius {rb} must exceed throat_half_width {w}: no reverse-fillet solution")

    yf = math.sqrt((rb + rf) ** 2 - (w + rf) ** 2)
    theta = math.degrees(math.asin((w + rf) / (rb + rf)))
    fillet_delta = 90.0 - theta
    half_delta = 180.0 - theta  # each half of the bulb: PRC -> apex

    a = axis_az
    m = a + 180.0  # toward the street mouth
    base = _move(center, m, yf)  # foot of both fillet RPs on the axis
    right, left = a + 90.0, a - 90.0

    pc = _move(base, right, w)
    pt = _move(base, left, w)
    rp_1 = _move(base, right, w + rf)
    rp_2 = _move(base, left, w + rf)
    prc_1 = _move(center, m - theta, rb)
    prc_2 = _move(center, m + theta, rb)
    apex = _move(center, a, rb)

    fillet_curve = Curve(radius=rf, delta_deg=fillet_delta, direction="CW")
    bulb_curve = Curve(radius=rb, delta_deg=half_delta, direction="CCW")
    fillet_1 = PlacedCurve(curve=fillet_curve, pc=pc, back_az=a)
    # heading at PRC1 = a + Δf; bulb turns left through the apex (heading a - 90) to PRC2 (heading a + 90 + θ)
    bulb_1 = PlacedCurve(curve=bulb_curve, pc=prc_1, back_az=a + fillet_delta)
    bulb_2 = PlacedCurve(curve=bulb_curve, pc=apex, back_az=a - 90.0)
    fillet_2 = PlacedCurve(curve=fillet_curve, pc=prc_2, back_az=a + 90.0 + theta)

    reverse_1 = ReverseCurve(first=fillet_1, second=bulb_1)
    reverse_2 = ReverseCurve(first=bulb_2, second=fillet_2)
    # the two bulb halves must join at the apex on a common tangent (a simple continuation of one CCW arc)
    net_turn = fillet_delta - 2.0 * half_delta + fillet_delta  # CW positive: +Δf (CW) - sweep (CCW) + Δf (CW)
    check = {
        "reverse_1": reverse_1.check(),
        "reverse_2": reverse_2.check(),
        "bulb_halves_gap": dist(bulb_1.pt, bulb_2.pc),
        "bulb_halves_tangent_az": _wrap180(bulb_1.forward_az - bulb_2.back_az),
        "net_turn_deg": net_turn,
        "net_turn_residual_deg": _wrap180(net_turn + 180.0),  # boundary reverses direction: total turn = -180 (CCW)
        "fillet_2_end_gap": dist(fillet_2.pt, pt),
        "fillet_2_end_az": _wrap180(fillet_2.forward_az - m),
    }
    return {
        "center": center,
        "axis_az": axis_az,
        "bulb_radius": rb,
        "throat_half_width": w,
        "fillet_radius": rf,
        "yf": yf,
        "theta_prc_deg": theta,
        "fillet_delta_deg": fillet_delta,
        "bulb_sweep_deg": 2.0 * half_delta,
        "bulb_arc_length": math.radians(2.0 * half_delta) * rb,
        "fillet_arc_length": fillet_curve.arc_length,
        "pc": pc,
        "prc_1": prc_1,
        "prc_2": prc_2,
        "pt": pt,
        "apex": apex,
        "rp_fillet_1": rp_1,
        "rp_fillet_2": rp_2,
        "fillet_1": fillet_1,
        "fillet_2": fillet_2,
        "bulb_1": bulb_1,
        "bulb_2": bulb_2,
        "reverse_1": reverse_1,
        "reverse_2": reverse_2,
        "check": check,
    }


# --------------------------------------------------------------------------------------------------------------------
# Lot lines on / against an arc
# --------------------------------------------------------------------------------------------------------------------


def radial_line(placed: PlacedCurve, s: float, length: float, inward: bool = False) -> tuple[Pt, Pt]:
    """Lot line on the radial through the arc point at arc distance ``s`` from the PC.

    Returns ``(point_on_arc, far_end)``. ``inward=False`` runs away from the RP (azimuth ``radial_az_at(s)``);
    ``inward=True`` runs toward the RP (and may not be longer than R). ``length`` must be >= 0.
    """
    if length < 0:
        raise ValueError(f"length must be >= 0, got {length}")
    _check_s(placed, s)
    if inward and length > placed.curve.radius + _EPS:
        raise ValueError(f"inward length {length} exceeds radius {placed.curve.radius}: line passes the RP")
    p = placed.point_at(s)
    radial = placed.radial_az_at(s)
    return p, _move(p, radial + 180.0 if inward else radial, length)


def nonradial_line(placed: PlacedCurve, s: float, az: float, length: float) -> tuple[Pt, Pt]:
    """Lot line leaving the arc at arc distance ``s`` along azimuth ``az`` (a non-radial line, "NR" on plats).

    Returns ``(point_on_arc, far_end)`` where ``far_end`` is ``length`` feet from it along ``az``. ``length`` >= 0.
    Use :func:`line_angle_to_radial` to report how far the line departs from the radial.
    """
    if length < 0:
        raise ValueError(f"length must be >= 0, got {length}")
    _check_s(placed, s)
    p = placed.point_at(s)
    return p, _move(p, az, length)


def line_angle_to_radial(placed: PlacedCurve, s: float, az: float) -> float:
    """Signed angle (degrees, [-180, 180)) from the outward radial at arc distance ``s`` to a line of azimuth ``az``.

    0 = radial (away from RP), ±90 = tangent, ±180 = radial toward the RP. Positive = clockwise from the radial.
    """
    _check_s(placed, s)
    return _wrap180(az - placed.radial_az_at(s))


def line_arc_intersections(p0: Pt, p1: Pt, placed: PlacedCurve) -> list[dict]:
    """Intersections of the segment ``p0``--``p1`` with the ARC (not the full circle).

    Returns a list (0, 1 or 2 items, ordered along the segment) of ``{"point": (n, e), "s": arc distance from PC,
    "t": fraction along the segment}``. A tangent touch returns one item. Points beyond the segment ends or outside
    the arc [0, L] are dropped (with a 1e-9 ft tolerance at the ends). Raises ``ValueError`` if ``p0 == p1``.
    """
    d = (p1[0] - p0[0], p1[1] - p0[1])
    dd = d[0] * d[0] + d[1] * d[1]
    if dd < _EPS * _EPS:
        raise ValueError("segment endpoints coincide")
    seg_len = math.sqrt(dd)
    curve = placed.curve
    rp, radius = placed.rp, curve.radius
    # foot of the perpendicular from RP to the infinite line
    t0 = ((rp[0] - p0[0]) * d[0] + (rp[1] - p0[1]) * d[1]) / dd
    foot = (p0[0] + t0 * d[0], p0[1] + t0 * d[1])
    h = dist(foot, rp)
    if h > radius + _EPS:
        return []
    half = 0.0 if abs(h - radius) <= _EPS else math.sqrt(max(radius * radius - h * h, 0.0)) / seg_len
    ts = [t0] if half == 0.0 else [t0 - half, t0 + half]

    sgn = curve.sign
    start_az = placed.radial_az_at(0.0)
    tol_t = _EPS / seg_len
    out: list[dict] = []
    for t in ts:
        if t < -tol_t or t > 1.0 + tol_t:
            continue
        t = min(max(t, 0.0), 1.0)
        pt = (p0[0] + t * d[0], p0[1] + t * d[1])
        swept = (sgn * (_az_between(rp, pt) - start_az)) % 360.0
        if swept > 360.0 - 1e-9:  # numerical wrap of a point sitting exactly on the PC
            swept = 0.0
        s = math.radians(swept) * radius
        if s > curve.arc_length + _EPS:
            continue
        out.append({"point": pt, "s": min(s, curve.arc_length), "t": t})
    return out
