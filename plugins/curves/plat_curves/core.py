"""plat_curves.core -- horizontal-curve COGO primitives (stdlib only; never imports ``engine.*``).

Conventions (see SPEC.md): points are ``(n, e)`` feet, azimuths are degrees clockwise from north in ``[0, 360)``,
``"CW"`` = curve turns right going PC -> PT (radius point 90 deg to the right of travel), ``"CCW"`` = turns left.

Solving any two curve parameters
--------------------------------
A simple curve has two degrees of freedom.  Writing ``h = delta/2`` every length is ``R * g(h)``::

    L = 2h  C = 2 sin h  T = tan h  M = 2 sin^2(h/2)  E = 2 sin^2(h/2) / cos h        (arc_length, chord, ...)

``degree_arc`` (``Da = 18000/pi / R``) depends on R only, so it is just another way of giving the radius:
``(radius, degree_arc)`` is *under-determined* and ``degree_arc`` never resolves delta.

Of the 28 parameter pairs: 21 are direct closed forms (radius+length, delta+anything, degree_arc+length, and the
ratio pairs (C,T) (C,M) (T,E) (M,E) which invert analytically); (radius, degree_arc) is under-determined; the
ratio pairs (L,C) (L,T) (L,M) (L,E) (C,E) have no closed-form inverse for h (transcendental, or a cubic) and are
solved by bracketed bisection to full double precision -- each ratio is strictly monotonic in h on (0, pi/2), so
the root is unique.  The last pair, (T,M), is two-valued.
**(tangent, middle_ordinate)**: the ratio T/M has a minimum of ~3.33 at
delta ~ 103.6 deg, so any larger ratio is met by a shallow curve and by a deep one.  ``from_params`` returns the
smaller-delta (shallow) branch unless an extra parameter selects the other; ``Curve.solutions`` lists both.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

Pt = tuple[float, float]

PLAT_TOL_FT = 0.02
"""Tolerance (ft) for auditing plat-stated values (radii/T/L/C to 0.01 ft, delta to 1 arc-second)."""

DEGREE_ARC_CONST = 18000.0 / math.pi
"""5729.5779513... -- arc-definition degree of curve is ``DEGREE_ARC_CONST / R`` per 100 ft of arc."""

_HALF_PI = math.pi / 2.0

__all__ = [
    "DEGREE_ARC_CONST",
    "PLAT_TOL_FT",
    "Curve",
    "PlacedCurve",
    "Pt",
    "az",
    "az_to_bearing",
    "bearing_to_az",
    "deg_to_dms",
    "dist",
    "dms_to_deg",
    "offset",
]


# --------------------------------------------------------------------------------------------------------------
# angle / bearing helpers
# --------------------------------------------------------------------------------------------------------------
def _norm_az(x: float) -> float:
    """Wrap an azimuth into [0, 360) (guards the ``-1e-17 % 360 == 360.0`` float trap)."""
    r = x % 360.0
    return 0.0 if r >= 360.0 else r


def _wrap180(x: float) -> float:
    """Wrap an angle difference into [-180, 180)."""
    return ((x + 180.0) % 360.0) - 180.0


def _is_neg(x: float) -> bool:
    return math.copysign(1.0, x) < 0.0


def dms_to_deg(d: float, m: float = 0.0, s: float = 0.0) -> float:
    """Degrees/minutes/seconds -> decimal degrees.  A negative sign on any part makes the whole angle negative."""
    neg = _is_neg(d) or _is_neg(m) or _is_neg(s)
    val = abs(d) + abs(m) / 60.0 + abs(s) / 3600.0
    return -val if neg else val


def deg_to_dms(deg: float, places: int = 0) -> str:
    """Decimal degrees -> ``36°20'00"`` (seconds rounded to ``places`` decimals, with carry into minutes/degrees)."""
    if places < 0:
        raise ValueError("places must be >= 0")
    if not math.isfinite(deg):
        raise ValueError(f"cannot format non-finite angle {deg!r}")
    scale = 10**places
    n = round(abs(deg) * 3600.0 * scale)  # total seconds in units of 10**-places s
    d, rem = divmod(n, 3600 * scale)
    m, sec_scaled = divmod(rem, 60 * scale)
    whole, frac = divmod(sec_scaled, scale)
    sec = f"{whole:02d}" + (f".{frac:0{places}d}" if places else "")
    sign = "-" if (deg < 0 and n) else ""
    return f"{sign}{d}°{m:02d}'{sec}\""


_MARK_FIXES = (
    ("′", "'"), ("’", "'"), ("‘", "'"), ("´", "'"), ("`", "'"), ("″", '"'), ("”", '"'), ("“", '"'),
    ("''", '"'), ("º", "°"), ("˚", "°"), ("%%D", "°"), ("%%d", "°"), ("*", "°"),
)  # fmt: skip
_BEARING_RE = re.compile(
    r"""^\s*([NS])\s*
        (\d{1,3}(?:\.\d+)?)\s*[°D^-]?\s*
        (?:(\d{1,2}(?:\.\d+)?)\s*['-]?\s*
           (?:(\d{1,2}(?:\.\d+)?)\s*["-]?\s*)?
        )?
        ([EW])\s*$""",
    re.IGNORECASE | re.VERBOSE,
)
_CARDINALS = {"N": 0.0, "NORTH": 0.0, "E": 90.0, "EAST": 90.0, "S": 180.0, "SOUTH": 180.0, "W": 270.0, "WEST": 270.0}


def bearing_to_az(s: str) -> float:
    """Quadrant bearing (``S57°53'59"E``, ``N 89°18'20" E``, ``N45*30'E``, ``N89-18-20E``, ``DUE NORTH``) -> azimuth.

    Tolerates OCR-style marks (``′ ″ ’ ” * º %%D``) and missing minutes/seconds.  Out-of-range parts (degrees > 90,
    minutes/seconds >= 60) raise ``ValueError`` rather than silently producing a wrong azimuth.
    """
    if not isinstance(s, str):
        raise TypeError(f"bearing must be a string, got {type(s).__name__}")
    t = s.strip()
    for old, new in _MARK_FIXES:
        t = t.replace(old, new)
    card = re.sub(r"^\s*DUE\s+", "", t.upper()).strip(" .")
    if card in _CARDINALS:
        return _CARDINALS[card]
    m = _BEARING_RE.match(t)
    if not m:
        raise ValueError(f"cannot parse bearing {s!r}")
    ns, deg_s, min_s, sec_s, ew = m.groups()
    deg, mins, sec = float(deg_s), float(min_s or 0), float(sec_s or 0)
    if deg > 90.0 or mins >= 60.0 or sec >= 60.0 or dms_to_deg(deg, mins, sec) > 90.0 + 1e-12:
        raise ValueError(f"bearing out of range: {s!r}")
    ang = dms_to_deg(deg, mins, sec)
    ns, ew = ns.upper(), ew.upper()
    if ns == "N":
        a = ang if ew == "E" else 360.0 - ang
    else:
        a = 180.0 - ang if ew == "E" else 180.0 + ang
    return _norm_az(a)


def az_to_bearing(az: float, places: int = 0) -> str:
    """Azimuth -> quadrant bearing string like ``S57°53'59"E`` (seconds rounded to ``places``).

    Quadrant boundaries: 0..90 -> N-E, (90,180] -> S-E, (180,270) -> S-W, [270,360) -> N-W.
    """
    a = _norm_az(float(az))
    if a <= 90.0:
        ns, ang, ew = "N", a, "E"
    elif a <= 180.0:
        ns, ang, ew = "S", 180.0 - a, "E"
    elif a < 270.0:
        ns, ang, ew = "S", a - 180.0, "W"
    else:
        ns, ang, ew = "N", 360.0 - a, "W"
    return f"{ns}{deg_to_dms(ang, places)}{ew}"


# --------------------------------------------------------------------------------------------------------------
# point helpers
# --------------------------------------------------------------------------------------------------------------
def offset(pt: Sequence[float], az_deg: float, dist: float) -> Pt:
    """Move ``dist`` feet from ``pt`` along azimuth ``az_deg``."""
    a = math.radians(az_deg)
    return (float(pt[0]) + dist * math.cos(a), float(pt[1]) + dist * math.sin(a))


def dist(a: Sequence[float], b: Sequence[float]) -> float:
    """Distance between two ``(n, e)`` points."""
    return math.hypot(b[0] - a[0], b[1] - a[1])


def az(a: Sequence[float], b: Sequence[float]) -> float:
    """Azimuth (deg clockwise from north, ``[0, 360)``) of the line from ``a`` to ``b``; raises if they coincide."""
    dn, de = b[0] - a[0], b[1] - a[1]
    if dn == 0.0 and de == 0.0:
        raise ValueError("azimuth of a zero-length line is undefined")
    return _norm_az(math.degrees(math.atan2(de, dn)))


# --------------------------------------------------------------------------------------------------------------
# Curve: parameter algebra
# --------------------------------------------------------------------------------------------------------------
_DIRS = ("CW", "CCW")
_LENGTHS = ("arc_length", "chord", "tangent", "middle_ordinate", "external")  # canonical order for ratio pairs
_PARAM_NAMES = ("radius", "delta_deg", "degree_arc", *_LENGTHS)
_PRIMARY_ORDER = ("radius", "delta_deg", "tangent", "arc_length", "chord", "middle_ordinate", "external")


def _g(name: str, h: float) -> float:
    """Length of type ``name`` for a unit-radius curve with half-angle ``h`` (radians)."""
    if name == "arc_length":
        return 2.0 * h
    if name == "chord":
        return 2.0 * math.sin(h)
    if name == "tangent":
        return math.tan(h)
    s2 = 2.0 * math.sin(h / 2.0) ** 2  # 1 - cos h, without cancellation at small h
    if name == "middle_ordinate":
        return s2
    if name == "external":
        return s2 / math.cos(h)
    raise KeyError(name)


def _h_from_radius(name: str, v: float, r: float) -> float:
    """Half-angle (rad) from radius + one length parameter (all closed form)."""
    x = v / r
    if name == "arc_length":
        h = x / 2.0
        if h >= _HALF_PI:
            raise ValueError(f"arc_length {v} >= pi*radius {math.pi * r:.4f}: delta would be >= 180 deg")
        return h
    if name == "chord":
        if x >= 2.0:
            raise ValueError(f"chord {v} >= 2*radius {2 * r}: delta would be >= 180 deg")
        return math.asin(x / 2.0)
    if name == "tangent":
        return math.atan(x)
    if name == "middle_ordinate":
        if x >= 1.0:
            raise ValueError(f"middle_ordinate {v} >= radius {r}: delta would be >= 180 deg")
        return 2.0 * math.atan(math.sqrt(x / (2.0 - x)))  # tan^2(h/2) = m/(2-m), m = 1-cos h
    if name == "external":
        return 2.0 * math.atan(math.sqrt(x / (2.0 + x)))  # tan^2(h/2) = x/(2+x), x = sec h - 1
    raise KeyError(name)


def _bisect(f, lo: float, hi: float, what: str) -> float:
    """Root of ``f`` on ``[lo, hi]`` (needs a strict sign change), bisected to adjacent floats."""
    flo, fhi = f(lo), f(hi)
    if not flo * fhi < 0.0:
        raise ValueError(f"{what} cannot be realised by a simple curve with 0 < delta < 180 deg")
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if mid <= lo or mid >= hi:
            break
        fm = f(mid)
        if fm == 0.0:
            return mid
        if (fm < 0.0) == (flo < 0.0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


_H_LO = 1e-12
_H_HI = _HALF_PI - 1e-12
_H_STAR_TM = 2.0 * math.atan(math.sqrt(math.sqrt(5.0) - 2.0))  # where T/M is minimal (delta ~ 103.6 deg)


def _h_from_ratio(a: str, b: str, k: float) -> list[float]:
    """Half-angle(s) (rad) with ``g_a(h)/g_b(h) == k`` for canonical-ordered length names ``a`` before ``b``."""
    what = f"{a}/{b} ratio {k:.9g}"
    pair = (a, b)
    if pair == ("chord", "tangent"):  # C/T = 2 cos h
        if not 0.0 < k / 2.0 < 1.0:
            raise ValueError(f"{what} cannot be realised (need 0 < C/T < 2)")
        return [math.acos(k / 2.0)]
    if pair == ("chord", "middle_ordinate"):  # C/M = 2 cot(h/2)
        if k <= 2.0:
            raise ValueError(f"{what} cannot be realised (need chord/middle_ordinate > 2)")
        return [2.0 * math.atan(2.0 / k)]
    if pair == ("tangent", "external"):  # T/E = cot(h/2)
        if k <= 1.0:
            raise ValueError(f"{what} cannot be realised (need tangent/external > 1)")
        return [2.0 * math.atan(1.0 / k)]
    if pair == ("middle_ordinate", "external"):  # M/E = cos h
        if not 0.0 < k < 1.0:
            raise ValueError(f"{what} cannot be realised (need 0 < middle_ordinate/external < 1)")
        return [math.acos(k)]

    def ratio(h: float) -> float:
        return _g(a, h) / _g(b, h) - k

    if pair == ("tangent", "middle_ordinate"):  # two-valued: T/M has a minimum at h* -- both branches
        kmin = _g(a, _H_STAR_TM) / _g(b, _H_STAR_TM)
        if k < kmin * (1.0 - 1e-12):
            raise ValueError(f"{what} cannot be realised (need tangent/middle_ordinate >= {kmin:.6f})")
        if k <= kmin * (1.0 + 1e-12):
            return [_H_STAR_TM]
        return [_bisect(ratio, _H_LO, _H_STAR_TM, what), _bisect(ratio, _H_STAR_TM, _H_HI, what)]
    # (L,C) (L,T) (L,M) (L,E) (C,E): strictly monotonic in h -> one root
    return [_bisect(ratio, _H_LO, _H_HI, what)]


def _solve_pair(k1: str, v1: float, k2: str, v2: float) -> list[tuple[float, float]]:
    """All ``(radius, delta_deg)`` satisfying two parameters (each in radius/delta_deg/lengths)."""
    vals = {k1: v1, k2: v2}
    if k1 == k2:
        raise ValueError("need two different parameters")
    if "radius" in vals and "delta_deg" in vals:
        return [(vals["radius"], vals["delta_deg"])]
    if "radius" in vals:
        (name,) = (k for k in vals if k != "radius")
        r = vals["radius"]
        return [(r, math.degrees(2.0 * _h_from_radius(name, vals[name], r)))]
    if "delta_deg" in vals:
        (name,) = (k for k in vals if k != "delta_deg")
        h = math.radians(vals["delta_deg"]) / 2.0
        return [(vals[name] / _g(name, h), vals["delta_deg"])]
    a, b = sorted(vals, key=_LENGTHS.index)
    out = []
    for h in _h_from_ratio(a, b, vals[a] / vals[b]):
        out.append((vals[a] / _g(a, h), math.degrees(2.0 * h)))
    return out


def _clean_params(params: dict) -> dict[str, float]:
    """Drop ``None`` values, reject unknown names, require finite positive numbers."""
    unknown = sorted(set(params) - set(_PARAM_NAMES))
    if unknown:
        raise TypeError(f"unknown curve parameter(s) {unknown}; allowed: {list(_PARAM_NAMES)}")
    out: dict[str, float] = {}
    for k, v in params.items():
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            raise TypeError(f"{k} must be a number, got {v!r}") from None
        if not math.isfinite(fv) or fv <= 0.0:
            raise ValueError(f"{k} must be positive and finite, got {v!r}")
        out[k] = fv
    if "delta_deg" in out and out["delta_deg"] >= 180.0:
        raise ValueError(f"delta_deg must be < 180 for a simple curve, got {out['delta_deg']}")
    return out


def _check_direction(direction: str) -> str:
    d = str(direction).strip().upper()
    if d not in _DIRS:
        raise ValueError(f"direction must be 'CW' or 'CCW', got {direction!r}")
    return d


@dataclass(frozen=True)
class Curve:
    """A simple circular curve: radius (ft), central angle ``delta_deg`` (0 < delta < 180) and turn ``direction``.

    All derived quantities follow SPEC.md formulas.  ``degree_chord`` is ``nan`` for radii below 50 ft (the chord
    definition ``sin(Dc/2) = 50/R`` has no solution there).
    """

    radius: float
    delta_deg: float
    direction: str = "CW"

    def __post_init__(self) -> None:
        r, d = float(self.radius), float(self.delta_deg)
        if not (math.isfinite(r) and r > 0.0):
            raise ValueError(f"radius must be positive and finite, got {self.radius!r}")
        if not (math.isfinite(d) and 0.0 < d < 180.0):
            raise ValueError(f"delta_deg must satisfy 0 < delta < 180, got {self.delta_deg!r}")
        object.__setattr__(self, "radius", r)
        object.__setattr__(self, "delta_deg", d)
        object.__setattr__(self, "direction", _check_direction(self.direction))

    # -- derived quantities -------------------------------------------------------------------------------------
    @property
    def sign(self) -> int:
        """+1 for CW (turns right), -1 for CCW (turns left)."""
        return 1 if self.direction == "CW" else -1

    @property
    def delta_rad(self) -> float:
        return math.radians(self.delta_deg)

    @property
    def arc_length(self) -> float:
        """L = R * delta (rad)."""
        return self.radius * self.delta_rad

    @property
    def tangent(self) -> float:
        """T = R tan(delta/2)."""
        return self.radius * math.tan(self.delta_rad / 2.0)

    @property
    def chord(self) -> float:
        """C = 2R sin(delta/2)."""
        return 2.0 * self.radius * math.sin(self.delta_rad / 2.0)

    @property
    def middle_ordinate(self) -> float:
        """M = R (1 - cos(delta/2)) (computed as 2R sin^2(delta/4) to avoid cancellation)."""
        return self.radius * _g("middle_ordinate", self.delta_rad / 2.0)

    @property
    def external(self) -> float:
        """E = R (sec(delta/2) - 1)."""
        return self.radius * _g("external", self.delta_rad / 2.0)

    @property
    def degree_arc(self) -> float:
        """Arc-definition degree of curve (deg per 100 ft of arc) = 5729.5779513 / R."""
        return DEGREE_ARC_CONST / self.radius

    @property
    def degree_chord(self) -> float:
        """Chord-definition degree of curve (deg subtended by a 100 ft chord): ``sin(Dc/2) = 50/R``; nan if R < 50."""
        x = 50.0 / self.radius
        return 2.0 * math.degrees(math.asin(x)) if x <= 1.0 else math.nan

    @property
    def sector_area(self) -> float:
        """R^2 delta / 2."""
        return 0.5 * self.radius**2 * self.delta_rad

    @property
    def segment_area(self) -> float:
        """Area between chord and arc: R^2 (delta - sin delta) / 2."""
        return 0.5 * self.radius**2 * (self.delta_rad - math.sin(self.delta_rad))

    @property
    def fillet_area(self) -> float:
        """Spandrel between the two tangents and the arc: R*T - sector_area."""
        return self.radius * self.tangent - self.sector_area

    # -- construction from any two parameters -------------------------------------------------------------------
    def value_of(self, name: str) -> float:
        """Value of any name accepted by ``from_params`` (``radius``, ``delta_deg``, ``tangent``, ...)."""
        if name not in _PARAM_NAMES:
            raise KeyError(name)
        return float(getattr(self, name))

    @classmethod
    def solutions(cls, direction: str = "CW", *, tol: float = PLAT_TOL_FT, **params: float | None) -> list[Curve]:
        """Every curve consistent with ``params``, smallest delta first (see :meth:`from_params`).

        Normally one curve; two only for a bare ``(tangent, middle_ordinate)`` pair.
        Raises ``ValueError`` if under-determined, unrealisable, or the extra parameters disagree beyond ``tol``.
        """
        direction = _check_direction(direction)
        p = _clean_params(params)
        da = p.pop("degree_arc", None)
        eff = dict(p)
        if da is not None and "radius" not in eff:
            eff["radius"] = DEGREE_ARC_CONST / da  # Da *is* the radius here; nothing left to cross-check
            da = None
        primary = [k for k in _PRIMARY_ORDER if k in eff][:2]
        if len(primary) < 2:
            hint = " (degree_arc and radius are the same information)" if "radius" in eff and da is not None else ""
            raise ValueError(f"under-determined: need two independent parameters, got {sorted(params)}{hint}")
        checks = {k: v for k, v in eff.items() if k not in primary}
        if da is not None:  # radius AND degree_arc both given: cross-check Da as an implied radius, in feet
            checks["degree_arc"] = da
        checked = []
        for r, d in _solve_pair(primary[0], eff[primary[0]], primary[1], eff[primary[1]]):
            curve = cls(r, d, direction)  # validates 0 < delta < 180
            worst_name, worst = "", 0.0
            for name, given in checks.items():
                res = _residual_ft(curve, name, given)
                if res > worst:
                    worst_name, worst = name, res
            checked.append((worst, worst_name, curve))
        ok = [t for t in checked if t[0] <= tol]
        if not ok:
            worst, name, curve = min(checked, key=lambda t: t[0])
            raise ValueError(
                f"inconsistent {name}: given {checks[name]!r} but {primary[0]}={eff[primary[0]]!r} with "
                f"{primary[1]}={eff[primary[1]]!r} imply {curve.value_of(name):.6f} (off by {worst:.4f} ft > tol {tol})"
            )
        return [t[2] for t in sorted(ok, key=lambda t: t[2].delta_deg)]

    @classmethod
    def from_params(cls, direction: str = "CW", *, tol: float = PLAT_TOL_FT, **params: float | None) -> Curve:
        """Build a curve from any two (or more) of ``radius, delta_deg, arc_length, chord, tangent,
        middle_ordinate, external, degree_arc``.  ``None`` values are ignored.

        The first two given in the order radius, delta_deg, tangent, arc_length, chord, middle_ordinate, external
        (``degree_arc`` standing in for ``radius`` when radius is absent) define the curve; every other given
        parameter is cross-checked and ``ValueError`` names the one that disagrees by more than ``tol`` feet
        (``delta_deg`` residual = R * delta-error along the arc; ``degree_arc`` residual = implied-radius error).
        ``(radius, degree_arc)`` alone is under-determined.  A bare ``(tangent, middle_ordinate)`` pair is
        two-valued; the shallower curve (smaller delta) is returned -- use :meth:`solutions` for both.
        """
        return cls.solutions(direction, tol=tol, **params)[0]


def _residual_ft(curve: Curve, name: str, given: float) -> float:
    """Disagreement (feet) between the curve's value for ``name`` and the value ``given``."""
    if name == "delta_deg":
        return abs(math.radians(curve.delta_deg - given)) * curve.radius
    if name == "degree_arc":
        return abs(curve.radius - DEGREE_ARC_CONST / given)
    return abs(curve.value_of(name) - given)


# --------------------------------------------------------------------------------------------------------------
# PlacedCurve: a Curve located in the plane
# --------------------------------------------------------------------------------------------------------------
def _station_text(station: float) -> str:
    """Station in feet -> ``12+34.56`` (100 ft stations, hundredths, with carry)."""
    n = round(abs(station) * 100.0)
    hundreds, rem = divmod(n, 10000)
    sign = "-" if (station < 0 and n) else ""
    return f"{sign}{hundreds}+{rem / 100.0:05.2f}"


@dataclass(frozen=True)
class PlacedCurve:
    """A :class:`Curve` located by its PC and the azimuth of the back tangent (direction of travel at the PC)."""

    curve: Curve
    pc: Pt
    back_az: float

    def __post_init__(self) -> None:
        if len(self.pc) != 2 or not all(math.isfinite(c) for c in self.pc):
            raise ValueError(f"pc must be a finite (n, e) pair, got {self.pc!r}")
        if not math.isfinite(self.back_az):
            raise ValueError(f"back_az must be finite, got {self.back_az!r}")
        object.__setattr__(self, "pc", (float(self.pc[0]), float(self.pc[1])))
        object.__setattr__(self, "back_az", _norm_az(float(self.back_az)))

    # -- key points and directions ------------------------------------------------------------------------------
    @property
    def direction(self) -> str:
        return self.curve.direction

    @property
    def rp_az(self) -> float:
        """Azimuth PC -> RP (back_az + sgn*90)."""
        return _norm_az(self.back_az + self.curve.sign * 90.0)

    @property
    def forward_az(self) -> float:
        return _norm_az(self.back_az + self.curve.sign * self.curve.delta_deg)

    @property
    def chord_az(self) -> float:
        return _norm_az(self.back_az + self.curve.sign * self.curve.delta_deg / 2.0)

    @property
    def pi(self) -> Pt:
        return offset(self.pc, self.back_az, self.curve.tangent)

    @property
    def pt(self) -> Pt:
        return offset(self.pi, self.forward_az, self.curve.tangent)

    @property
    def rp(self) -> Pt:
        return offset(self.pc, self.rp_az, self.curve.radius)

    @property
    def chord_bearing(self) -> str:
        return az_to_bearing(self.chord_az)

    @property
    def back_bearing(self) -> str:
        return az_to_bearing(self.back_az)

    @property
    def forward_bearing(self) -> str:
        return az_to_bearing(self.forward_az)

    # -- along the arc (s = arc distance from PC; values outside 0..L extrapolate along the same circle) --------
    def _sweep_deg(self, s: float) -> float:
        return self.curve.sign * math.degrees(s / self.curve.radius)

    def azimuth_at(self, s: float) -> float:
        """Direction of travel at arc distance ``s`` from the PC."""
        return _norm_az(self.back_az + self._sweep_deg(s))

    def radial_az_at(self, s: float) -> float:
        """Azimuth from the RP out to the point at arc distance ``s`` (the outward radial)."""
        return _norm_az(self.rp_az + 180.0 + self._sweep_deg(s))

    def point_at(self, s: float) -> Pt:
        """Point at arc distance ``s`` from the PC."""
        return offset(self.rp, self.radial_az_at(s), self.curve.radius)

    def arc_points(self, n_segments: int = 24) -> list[Pt]:
        """``n_segments + 1`` points from PC to PT at equal arc spacing."""
        if n_segments < 1:
            raise ValueError("n_segments must be >= 1")
        length = self.curve.arc_length
        return [self.point_at(length * i / n_segments) for i in range(n_segments + 1)]

    def station_table(self, pc_station: float = 0.0, spacing: float = 100.0) -> list[dict]:
        """Rows for the PC, every full ``spacing``-ft station strictly between PC and PT, and the PT.

        Row keys: ``label`` ("PC" | "STA" | "PT"), ``station`` (ft), ``station_text`` ("12+34.56"), ``s`` (arc distance
        from PC, ft), ``deflection_deg`` (from the back tangent at the PC, = s/(2R) in degrees), ``deflection_dms``,
        ``chord`` (from the PC, = 2R sin(deflection)) and ``point`` ((n, e) on the arc).
        """
        if not spacing > 0.0:
            raise ValueError("spacing must be positive")
        r = self.curve.radius
        length = self.curve.arc_length
        pt_station = pc_station + length

        def row(label: str, station: float, s: float) -> dict:
            defl = s / (2.0 * r)  # radians
            defl_deg = math.degrees(defl)
            return {
                "label": label,
                "station": station,
                "station_text": _station_text(station),
                "s": s,
                "deflection_deg": defl_deg,
                "deflection_dms": deg_to_dms(defl_deg),
                "chord": 2.0 * r * math.sin(defl),
                "point": self.point_at(s),
            }

        rows = [row("PC", pc_station, 0.0)]
        eps = 0.005  # a station within half a hundredth of the PC/PT would print identically: skip it
        k = math.floor((pc_station + eps) / spacing) + 1
        while k * spacing < pt_station - eps:
            rows.append(row("STA", k * spacing, k * spacing - pc_station))
            k += 1
        rows.append(row("PT", pt_station, length))
        return rows

    # -- constructors -------------------------------------------------------------------------------------------
    @classmethod
    def from_pi(cls, pi: Sequence[float], back_az: float, forward_az: float, radius: float) -> PlacedCurve:
        """Fillet ``radius`` into the corner at ``pi`` between the back and forward tangent azimuths.

        Direction (CW if the forward tangent is clockwise of the back one) and delta come from the two azimuths.
        """
        d = _wrap180(forward_az - back_az)
        if abs(d) < 1e-12:
            raise ValueError("tangents are collinear: no deflection, no curve")
        if abs(d) >= 180.0 - 1e-12:
            raise ValueError("tangents reverse direction (deflection >= 180 deg): not a simple curve")
        curve = Curve(radius, abs(d), "CW" if d > 0 else "CCW")
        return cls(curve, offset(pi, back_az + 180.0, curve.tangent), back_az)

    @classmethod
    def from_pc_pt(
        cls, pc: Sequence[float], pt: Sequence[float], radius: float, direction: str, back_az: float | None = None
    ) -> PlacedCurve:
        """Curve of ``radius`` running PC -> PT (the *small* arc; delta < 180 deg, so ``chord < 2*radius``).

        With ``back_az=None`` the back tangent follows from the chord: ``back_az = chord_az - sgn*delta/2``.  If
        ``back_az`` is given it is used as the tangent and the resulting PT must land within ``PLAT_TOL_FT`` of ``pt``.
        """
        direction = _check_direction(direction)
        if not (math.isfinite(radius) and radius > 0.0):
            raise ValueError(f"radius must be positive and finite, got {radius!r}")
        chord = dist(pc, pt)
        if chord <= 0.0:
            raise ValueError("PC and PT coincide")
        ratio = chord / (2.0 * radius)
        if ratio >= 1.0:
            raise ValueError(f"chord {chord:.4f} >= diameter {2 * radius}: no small arc of radius {radius} joins PC/PT")
        curve = Curve(radius, 2.0 * math.degrees(math.asin(ratio)), direction)
        if back_az is None:
            back = az(pc, pt) - curve.sign * curve.delta_deg / 2.0
            return cls(curve, pc, back)
        placed = cls(curve, pc, back_az)
        miss = dist(placed.pt, pt)
        if miss > PLAT_TOL_FT:
            raise ValueError(f"back_az {back_az} puts the PT {miss:.4f} ft from the given PT (tol {PLAT_TOL_FT})")
        return placed

    @classmethod
    def from_rp(
        cls, rp: Sequence[float], radius: float, start_az_from_rp: float, delta_deg: float, direction: str
    ) -> PlacedCurve:
        """Curve about radius point ``rp`` starting on the radial ``start_az_from_rp`` (azimuth RP -> PC)."""
        curve = Curve(radius, delta_deg, direction)
        pc = offset(rp, start_az_from_rp, radius)
        back = start_az_from_rp + 180.0 - curve.sign * 90.0  # rp_az = start+180 = back + sgn*90
        return cls(curve, pc, back)

    @classmethod
    def from_pt(cls, pt: Sequence[float], forward_az: float, curve: Curve) -> PlacedCurve:
        """Place ``curve`` backwards from its PT, given the forward tangent azimuth at the PT."""
        back = forward_az - curve.sign * curve.delta_deg
        pi = offset(pt, forward_az + 180.0, curve.tangent)
        return cls(curve, offset(pi, back + 180.0, curve.tangent), back)
