"""Plat curve-data notation: parse OCR'd curve text, audit stated values, diagnose right-of-way offset mix-ups.

Stdlib + ``plat_curves.core`` only.  Nothing here re-implements curve math: every recomputation goes through
``core.Curve`` (``Curve.from_params``), every angle/bearing conversion through ``core``.

Public API: ``parse_curve_data``, ``PlatCurveReading``, ``audit_reading``, ``diagnose_offset``, ``edge_radius``.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass, field, fields
from typing import Any

from plat_curves import core as _core
from plat_curves.core import Curve, bearing_to_az, dms_to_deg

PLAT_TOL_FT: float = getattr(_core, "PLAT_TOL_FT", 0.02)

# The plat prints radii / T / L / C to 0.01 ft and delta to 1 arc-second, so a printed value carries a half-unit
# (+-0.005 ft, +-0.5") rounding error.  Those half-units propagate into every recomputed quantity (see _basis_uncertainty).
LENGTH_HALF_UNIT_FT = 0.005
ANGLE_HALF_UNIT_DEG = 0.5 / 3600.0

KINDS = ("centerline", "row_edge", "lot_line", "boundary", "corner_return")

# Stated-parameter names (== Curve.from_params keyword names), in basis-preference order.
# R+delta first (both are printed to high relative precision and L = R*delta is linear in both); then R+L (linear,
# well conditioned for any delta); then R+T; R+C (T and C blow up / go flat as delta -> 180 deg, so they rank later);
# the M / E ordinates are last because they are the most rounding-sensitive at small delta.
_PARAMS = ("radius", "delta_deg", "arc_length", "tangent", "chord", "middle_ordinate", "external")
_LENGTHS = tuple(p for p in _PARAMS if p != "delta_deg")
_HALF_UNIT = {p: (ANGLE_HALF_UNIT_DEG if p == "delta_deg" else LENGTH_HALF_UNIT_FT) for p in _PARAMS}

_SHORT = {
    "radius": "R",
    "delta_deg": "Δ",
    "arc_length": "L",
    "tangent": "T",
    "chord": "C",
    "middle_ordinate": "M",
    "external": "E",
}


# --------------------------------------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------------------------------------

_DELTA_GLYPHS = "Δ∆△▵δ\U0001d6e5\U0001d6ab"  # Greek Delta, Increment, triangles, delta, math deltas

_DEG_MARKS = "°º˚⁰∘"  # degree sign, masculine ordinal, ring above, superscript zero, ring operator
_MIN_MARKS = "′’‘´`ʹʼ"  # prime, curly quotes, acute, grave, modifier primes
_SEC_MARKS = "″”“„‶ʺ〃"  # double prime, curly double quotes, ditto marks

_ANGLE = (
    r"(?<![\d.])(?P<d>\d{1,3}(?:\.\d+)?)(?!\d)\s*(?:°|(?=\s*\d{1,2}\s*'))\s*"  # degrees; the degree sign may be lost if minutes follow
    r"(?:(?P<m>\d{1,2}(?:\.\d+)?)\s*'"
    r"(?:\s*(?P<s>\d{1,2}(?:\.\d+)?)\s*\"|(?P<s2>\d{1,2}(?:\.\d+)?)(?![\d.]))?)?"  # minutes, optional seconds (mark may be lost)
)
_ANGLE_RE = re.compile(_ANGLE)
_DELTA_RE = re.compile(rf"(?<![A-Za-z])(?:[{_DELTA_GLYPHS}]|Delta|A)\s*\.?\s*[=:\-–—]?\s*{_ANGLE}", re.IGNORECASE)
# A delta LABEL with an explicit separator, used only to notice a delta that _DELTA_RE could not parse (never to guess it).
_DELTA_LABEL_RE = re.compile(
    rf"(?<![A-Za-z])(?:[{_DELTA_GLYPHS}]|Delta|A)\s*\.?\s*[=:\-–—]\s*(?P<rest>\S.{{0,14}})", re.IGNORECASE
)
_BEARING_RE = re.compile(
    r"(?<![A-Za-z])(?P<q1>[NS])\s*\.?\s*(?P<d>\d{1,2})\s*°\s*"
    r"(?:(?P<m>\d{1,2})\s*'\s*(?:(?P<s>\d{1,2}(?:\.\d+)?)\s*\"?)?)?\s*\.?\s*(?P<q2>[EW])(?![A-Za-z])",
    re.IGNORECASE,
)
_CHORD_BRG_LABEL_RE = re.compile(
    r"(?<![A-Za-z])(?:Ch(?:ord)?\.?\s*B(?:rg|earing|rng|g)|C\.?\s*B)\.?\s*[=:\-–—]?", re.IGNORECASE
)
_NUM = r"(?P<v>\d[\d,]*(?:\.\d+)?|\.\d+)"
_SEP = r"\s*\.?\s*[=:\-–—]"

# (key, label regex, separator required?)  -- most specific first; single-letter M / E need an explicit "=" / ":".
_LABELS: tuple[tuple[str, str, bool], ...] = (
    ("radius", r"Radius|Rad|R", False),
    ("tangent", r"Tangent|Tang|Tan|T", False),
    ("arc_length", r"Arc\s*Length|Arc\s*Len|Arc|Length|Len|L", False),
    ("chord", r"Chord(?:\s*Dist(?:ance)?)?|Ch\.?\s*Dist|Chd|Ch|C", False),
    ("middle_ordinate", r"Mid(?:dle)?\.?\s*Ord(?:inate)?|M\.\s*O|M", True),
    ("external", r"External|Ext|E", True),
)


def _normalize(text: str) -> str:
    """Fold OCR / typography variants of angle marks, dashes and whitespace into one ASCII-ish form."""
    t = str(text)
    t = t.translate({ord(c): "°" for c in _DEG_MARKS})
    t = t.translate({ord(c): "'" for c in _MIN_MARKS})
    t = t.translate({ord(c): '"' for c in _SEC_MARKS})
    t = t.replace("''", '"')  # two minute-marks in a row are a second-mark
    t = re.sub(r"(?<=\d)\s*[oO*](?=\s*\d{1,2}\s*')", "°", t)  # "36o20'00" -> degree sign lost to a letter o
    return re.sub(r"\s+", " ", t)  # \s also folds non-breaking spaces


def _to_float(token: str) -> float:
    """Number token -> float, tolerating thousands commas ("1,234.56") and comma decimals ("269,96")."""
    tok = token.strip()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", tok):
        return float(tok.replace(",", ""))
    if re.fullmatch(r"\d+,\d{1,2}", tok):
        return float(tok.replace(",", "."))
    return float(tok.replace(",", ""))


def _angle_from_match(m: re.Match[str], warnings: list[str], what: str) -> float | None:
    d = float(m.group("d"))
    mi = float(m.group("m")) if m.group("m") else 0.0
    se = float(m.group("s") or m.group("s2") or 0.0)
    if mi >= 60 or se >= 60:
        warnings.append(f"{what}: minutes/seconds out of range in {m.group(0).strip()!r}; ignored")
        return None
    return dms_to_deg(d, mi, se)


def _blank(text: str, span: tuple[int, int]) -> str:
    return text[: span[0]] + " " * (span[1] - span[0]) + text[span[1] :]


def _format_bearing(m: re.Match[str], warnings: list[str]) -> str | None:
    d = int(m.group("d"))
    mi = int(m.group("m") or 0)
    se = float(m.group("s") or 0)
    if d > 90 or mi >= 60 or se >= 60 or (d == 90 and (mi or se)):
        warnings.append(f"bearing {m.group(0).strip()!r} out of range; ignored")
        return None
    sec = f"{int(se):02d}" if se == int(se) else f"{se:05.2f}".rstrip("0")
    return f"{m.group('q1').upper()}{d}°{mi:02d}'{sec}\"{m.group('q2').upper()}"


def parse_curve_data_ex(text: str) -> tuple[dict[str, Any], list[str]]:
    """Like :func:`parse_curve_data` but also returns human-readable parse warnings (conflicts, rejected tokens)."""
    warnings: list[str] = []
    out: dict[str, Any] = {}
    t = _normalize(text)

    # Bearings first (their N/S/E/W letters would otherwise be mistaken for labels).  Per the plat's Note 1 every bearing
    # printed on a curve is a CHORD bearing, so the first valid bearing is the chord bearing.
    for m in list(_BEARING_RE.finditer(t)):
        brg = _format_bearing(m, warnings)
        if brg is None:
            continue
        if "chord_bearing" in out and out["chord_bearing"] != brg:
            warnings.append(f"extra bearing {brg} ignored (kept {out['chord_bearing']})")
        else:
            out["chord_bearing"] = brg
    t = _BEARING_RE.sub(" ", t)
    t = _CHORD_BRG_LABEL_RE.sub(" ", t)

    # Delta.
    dms = list(_DELTA_RE.finditer(t))
    label = _DELTA_LABEL_RE.search(t)
    if dms:
        for dm in dms:
            val = _angle_from_match(dm, warnings, "delta")
            if val is None:
                continue
            if "delta_deg" in out and abs(out["delta_deg"] - val) > 0.5 / 3600.0:
                warnings.append(f"conflicting delta: kept {out['delta_deg']:.6f}, ignored {val:.6f}")
            else:
                out.setdefault("delta_deg", val)
        for dm in reversed(dms):
            t = _blank(t, dm.span())
    else:
        loose = [m for m in _ANGLE_RE.finditer(t) if "°" in m.group(0) or m.group("m")]
        if len(loose) == 1:
            val = _angle_from_match(loose[0], warnings, "delta")
            if val is not None:
                out["delta_deg"] = val
                warnings.append(f"unlabeled angle {loose[0].group(0).strip()!r} taken as delta")
            t = _blank(t, loose[0].span())
    if "delta_deg" not in out and label and not dms:
        # e.g. Δ=36'20'00" or Δ=36 20 00: the degree sign was lost, so the value is ambiguous. Refuse loudly, don't guess.
        warnings.append(f"delta label found but no angle parsed near {label.group(0).strip()!r}; delta NOT set")
    if "delta_deg" in out and not 0.0 < out["delta_deg"] < 180.0:
        warnings.append(f"delta {out['delta_deg']:.6f} deg outside (0, 180); ignored")
        del out["delta_deg"]

    # Lengths.
    for key, label, need_sep in _LABELS:
        sep = _SEP if need_sep else r"\s*\.?\s*[=:\-–—]?"
        rx = re.compile(rf"(?<![A-Za-z])(?:{label})(?![A-Za-z]){sep}\s*{_NUM}", re.IGNORECASE)
        for m in list(rx.finditer(t)):
            try:
                val = _to_float(m.group("v"))
            except ValueError:
                continue
            if key in out and abs(out[key] - val) > 1e-9:
                warnings.append(f"conflicting {key}: kept {out[key]}, ignored {val}")
            else:
                out.setdefault(key, val)
        t = rx.sub(" ", t)

    return out, warnings


def parse_curve_data(text: str) -> dict:
    """Parse a plat curve-data string into ``{"delta_deg", "radius", "tangent", "arc_length", "chord", "chord_bearing"}``.

    Tolerant of OCR / typography: delta as ``Δ ∆ △ A`` (or ``Delta``), radius as ``R.=`` / ``R=`` / ``R:``,
    minutes as ``′ ' ’``, seconds as ``″ " ''`` (or lost entirely), ``T.=``, ``L=``, ``C=``, ``Ch. Brg``, and bearings
    like ``N.78°11'40"W.`` or ``S 57°53'59" E``.  Only keys actually found are returned; the chord bearing comes back
    normalised as ``S57°53'59"E``.  ``middle_ordinate`` / ``external`` are returned when labelled ``M.O.=`` / ``E=``.
    Use :func:`parse_curve_data_ex` to also get the warnings.
    """
    return parse_curve_data_ex(text)[0]


# --------------------------------------------------------------------------------------------------------------------
# Reading record
# --------------------------------------------------------------------------------------------------------------------


def _coerce_number(value: Any, *, angle: bool = False) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"not a number: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    s = _normalize(str(value))
    if angle:
        m = _ANGLE_RE.search(s)
        if m and ("°" in m.group(0) or m.group("m")):
            got = _angle_from_match(m, [], "delta")
            if got is not None:
                return got
    return _to_float(re.sub(r"[^\d.,]", "", s))


@dataclass
class PlatCurveReading:
    """One curve as printed on a plat.  ``None`` = unreadable / not printed.  Never fill a value by computing it."""

    id: str = ""
    sheet: int | None = None
    street: str = ""
    kind: str = "centerline"  # centerline | row_edge | lot_line | boundary | corner_return
    radius: float | None = None
    delta_deg: float | None = None
    tangent: float | None = None
    arc_length: float | None = None
    chord: float | None = None
    chord_bearing: str | None = None
    confidence: float = 1.0
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)  # crop, evidence, ambiguities, middle_ordinate, external, ...

    def __post_init__(self) -> None:
        for name in ("radius", "tangent", "arc_length", "chord"):
            setattr(self, name, _coerce_number(getattr(self, name)))
        self.delta_deg = _coerce_number(self.delta_deg, angle=True)
        if isinstance(self.notes, (list, tuple)):
            self.notes = "; ".join(str(n) for n in self.notes)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlatCurveReading:
        """Build from a ``data/*.json`` row; keys the dataclass does not know are kept in ``extra``."""
        names = {f.name for f in fields(cls)} - {"extra"}
        kwargs = {k: v for k, v in data.items() if k in names and v is not None}
        extra = {k: v for k, v in data.items() if k not in names}
        if isinstance(data.get("extra"), dict):
            extra = {**data["extra"], **extra}
        return cls(**kwargs, extra=extra)

    @classmethod
    def from_text(cls, text: str, **meta: Any) -> PlatCurveReading:
        """Build from raw curve-data text via :func:`parse_curve_data`; ``meta`` supplies id / sheet / street / kind."""
        parsed = parse_curve_data(text)
        extra = {k: parsed.pop(k) for k in ("middle_ordinate", "external") if k in parsed}
        return cls(**{**parsed, **meta}, extra=extra)

    def stated(self) -> dict[str, float]:
        """Numeric parameters that are actually printed (``Curve.from_params`` names), incl. M / E kept in ``extra``."""
        out: dict[str, float] = {}
        for name in _PARAMS:
            val = getattr(self, name, None)
            if val is None:
                val = _coerce_number(self.extra.get(name), angle=False)
            if val is not None:
                out[name] = float(val)
        return out

    def to_dict(self) -> dict[str, Any]:
        d = {f.name: getattr(self, f.name) for f in fields(self) if f.name != "extra"}
        return {**d, **self.extra}


def _as_reading(obj: PlatCurveReading | dict[str, Any]) -> PlatCurveReading:
    return obj if isinstance(obj, PlatCurveReading) else PlatCurveReading.from_dict(dict(obj))


# --------------------------------------------------------------------------------------------------------------------
# Recomputation and tolerance (all curve math delegated to core.Curve)
# --------------------------------------------------------------------------------------------------------------------


def _solve(pair: dict[str, float]) -> dict[str, float]:
    """Solve the curve from exactly two parameters; return every quantity keyed by parameter name (+ degree_arc)."""
    c = Curve.from_params(**pair)
    return {
        "radius": c.radius,
        "delta_deg": c.delta_deg,
        "arc_length": c.arc_length,
        "tangent": c.tangent,
        "chord": c.chord,
        "middle_ordinate": c.middle_ordinate,
        "external": c.external,
        "degree_arc": c.degree_arc,
    }


def _basis_uncertainty(pair: dict[str, float]) -> dict[str, float]:
    """First-order worst-case effect of the basis values' printing precision on every recomputed quantity.

    WHY THE TOLERANCE WIDENS.  The plat rounds R, T, L, C to 0.01 ft and delta to 1 arc-second, so each *basis* value
    is uncertain by +-0.005 ft / +-0.5".  A recomputed value inherits that: for the usual R + delta basis
    dL = delta_rad*0.005 + R*(0.5" in rad), dT = tan(delta/2)*0.005 + R*sec^2(delta/2)/2*(0.5" in rad), etc.  At R = 459 ft
    the 0.5" term is only ~0.001 ft, but at R = 5000 ft it is ~0.012 ft -- comparable to the flat 0.02 ft tolerance -- so a
    fixed tolerance would cry "inconsistent" on a perfectly good large-radius curve.  Rather than hand-derive each
    partial derivative for every possible basis pair, perturb each basis value by its half-unit, re-solve through
    ``core.Curve``, and take half the swing (a central difference == the first-order partial times the half-unit).  The
    two contributions are summed (worst case) and ADDED to the flat tolerance by the caller.
    """
    unc = dict.fromkeys(_PARAMS, 0.0)
    for name, val in pair.items():
        h = _HALF_UNIT[name]
        try:
            hi = _solve({**pair, name: val + h})
            lo = _solve({**pair, name: val - h})
        except ValueError:
            continue
        for p in _PARAMS:
            unc[p] += abs(hi[p] - lo[p]) / 2.0
    return unc


def _tolerance(param: str, tol: float, unc: dict[str, float], radius: float) -> float:
    """Effective tolerance for comparing a stated ``param`` with its recomputed value (feet; degrees for delta)."""
    if param == "delta_deg":
        # The flat tolerance is a length: the angle it subtends at this radius, plus delta's own 0.5" print rounding.
        return math.degrees(tol / radius) + unc["delta_deg"] + ANGLE_HALF_UNIT_DEG
    return tol + unc[param]


def _residuals(stated: dict[str, float], pair: tuple[str, str], tol: float) -> dict[str, Any]:
    """Solve ``pair`` from ``stated`` and compare every other stated value with the recomputation."""
    basis = {p: stated[p] for p in pair}
    rec = _solve(basis)
    unc = _basis_uncertainty(basis)
    res: dict[str, float] = {}
    tols: dict[str, float] = {}
    for p in stated:
        if p in pair:
            continue
        res[p] = stated[p] - rec[p]
        tols[p] = _tolerance(p, tol, unc, rec["radius"])
    ratio = max((abs(res[p]) / tols[p] for p in res), default=0.0)
    return {"pair": pair, "recomputed": rec, "residuals": res, "tolerance": tols, "worst_ratio": ratio}


def _invalid_reason(stated: dict[str, float]) -> str | None:
    for p, v in stated.items():
        if not math.isfinite(v) or v <= 0:
            return f"{_SHORT[p]} = {v!r} is not a positive finite number"
    if "delta_deg" in stated and not 0.0 < stated["delta_deg"] < 180.0:
        return f"Δ = {stated['delta_deg']:.6f} deg is outside (0, 180)"
    return None


def audit_reading(reading: PlatCurveReading | dict, tol: float = PLAT_TOL_FT) -> dict:
    """Recompute every curve quantity from the best-determined stated pair and report each stated value's residual.

    The basis is R + delta when both are printed, otherwise the first available pair in the order R, delta, L, T, C, M, E.
    Residual = stated - recomputed (feet, or degrees for delta; ``delta_residual_arcsec`` is also given).  A value is
    within tolerance when ``|residual| <= tol + basis rounding uncertainty`` (see ``_basis_uncertainty``).  Verdict:
    ``"consistent"`` (every redundant stated value within tolerance; ``n_checks`` says how many were tested, 0 means the
    reading is exactly determined and there was nothing to cross-check), ``"inconsistent"``, or ``"underdetermined"``
    (fewer than two parameters stated).  ``pair_scan`` re-solves from every other stated pair so the caller can see which
    value is the odd one out; ``suspects`` (>= 4 stated values only) lists parameters whose removal makes the rest agree.
    """
    r = _as_reading(reading)
    stated = r.stated()
    notes: list[str] = []
    if r.kind not in KINDS:
        notes.append(f"unknown kind {r.kind!r}")
    out: dict[str, Any] = {
        "id": r.id,
        "kind": r.kind,
        "stated": stated,
        "tol_ft": tol,
        "basis": None,
        "recomputed": {},
        "residuals": {},
        "tolerance": {},
        "within": {},
        "n_checks": 0,
        "worst": None,
        "pair_scan": [],
        "suspects": [],
        "verdict": "underdetermined",
        "reason": "",
        "notes": notes,
    }
    if r.chord_bearing:
        try:
            out["chord_bearing_az"] = bearing_to_az(r.chord_bearing)
        except (ValueError, TypeError) as exc:
            notes.append(f"chord_bearing {r.chord_bearing!r} not parseable: {exc}")
        notes.append("chord bearing is not auditable without the back-tangent azimuth")

    if len(stated) < 2:
        out["reason"] = f"only {len(stated)} curve parameter(s) stated; need 2 to determine a curve"
        return out
    bad = _invalid_reason(stated)
    if bad:
        out["verdict"], out["reason"] = "inconsistent", bad
        return out

    order = [p for p in _PARAMS if p in stated]
    scans: list[dict[str, Any]] = []
    for pair in itertools.combinations(order, 2):
        try:
            scans.append(_residuals(stated, pair, tol))
        except ValueError as exc:  # e.g. C > L: no such curve
            scans.append({"pair": pair, "error": str(exc), "worst_ratio": math.inf})
    out["pair_scan"] = scans

    best = scans[0]
    out["basis"] = best["pair"]
    if "error" in best:
        out["verdict"], out["reason"] = (
            "inconsistent",
            f"basis {'+'.join(_SHORT[p] for p in best['pair'])}: {best['error']}",
        )
        return out

    out["recomputed"] = best["recomputed"]
    out["residuals"] = best["residuals"]
    out["tolerance"] = best["tolerance"]
    out["within"] = {p: abs(best["residuals"][p]) <= best["tolerance"][p] for p in best["residuals"]}
    out["n_checks"] = len(best["residuals"])
    if "delta_deg" in best["residuals"]:
        out["delta_residual_arcsec"] = best["residuals"]["delta_deg"] * 3600.0
    if best["residuals"]:
        worst = max(best["residuals"], key=lambda p: abs(best["residuals"][p]) / best["tolerance"][p])
        out["worst"] = (worst, best["residuals"][worst])

    basis_txt = "+".join(_SHORT[p] for p in best["pair"])
    if not best["residuals"]:
        out["verdict"] = "consistent"
        out["reason"] = f"exactly determined by {basis_txt}; nothing redundant to cross-check"
    elif all(out["within"].values()):
        out["verdict"] = "consistent"
        out["reason"] = f"all {out['n_checks']} redundant value(s) reproduce from {basis_txt} within tolerance"
    else:
        out["verdict"] = "inconsistent"
        fails = [p for p, ok in out["within"].items() if not ok]
        out["reason"] = f"from {basis_txt}: " + ", ".join(
            f"{_SHORT[p]} stated {stated[p]:.4f} vs {best['recomputed'][p]:.4f} (resid {best['residuals'][p]:+.4f}, tol ±{best['tolerance'][p]:.4f})"
            for p in fails
        )
        if len(stated) >= 4:
            for p in order:
                rest = {k: v for k, v in stated.items() if k != p}
                sub = [_safe_ratio(rest, pair, tol) for pair in itertools.combinations([q for q in order if q != p], 2)]
                if sub and max(sub) <= 1.0:
                    out["suspects"].append(p)
    return out


def _safe_ratio(stated: dict[str, float], pair: tuple[str, str], tol: float) -> float:
    try:
        return _residuals(stated, pair, tol)["worst_ratio"]
    except ValueError:
        return math.inf


# --------------------------------------------------------------------------------------------------------------------
# Right-of-way offset diagnosis
# --------------------------------------------------------------------------------------------------------------------

_LMC = ("tangent", "arc_length", "chord")


def _normalize_direction(turn_direction: str) -> str:
    s = str(turn_direction).strip().upper()
    if s in ("CW", "R", "RIGHT"):
        return "CW"
    if s in ("CCW", "L", "LEFT"):
        return "CCW"
    raise ValueError(f"turn_direction must be 'CW' or 'CCW', got {turn_direction!r}")


def edge_radius(centerline_radius: float, row_width: float, turn_direction: str, side: str) -> dict[str, Any]:
    """Which right-of-way edge of a centerline curve is at radius R-w/2 (inside) and which at R+w/2 (outside).

    ``turn_direction`` is ``"CW"`` (turns right going PC -> PT) or ``"CCW"`` (turns left); ``side`` is ``"left"`` or
    ``"right"`` of the direction of travel (``"inside"`` / ``"outside"`` are also accepted).  The radius point is on the
    RIGHT of a CW curve, so its right-hand edge is the INSIDE edge (R - w/2) and its left-hand edge the OUTSIDE edge
    (R + w/2); a CCW curve is the mirror image.  Returns ``{"radius", "edge", "side", "turn_direction", "rp_side",
    "lots_toward_rp"}``: ``lots_toward_rp`` is True when the lots abutting that edge lie on the radius-point side of it
    (inside edge: shorter frontage, radial lot lines converge); False for the outside edge (lot lines diverge).
    Raises ``ValueError`` if the inside radius would be <= 0.
    """
    direction = _normalize_direction(turn_direction)
    s = str(side).strip().lower()
    rp_side = "right" if direction == "CW" else "left"
    if s in ("inside", "outside"):
        edge = s
        s = rp_side if edge == "inside" else ("left" if rp_side == "right" else "right")
    elif s in ("left", "right", "l", "r"):
        s = "left" if s.startswith("l") else "right"
        edge = "inside" if s == rp_side else "outside"
    else:
        raise ValueError(f"side must be 'left' or 'right' of travel, got {side!r}")
    half = row_width / 2.0
    radius = centerline_radius - half if edge == "inside" else centerline_radius + half
    if radius <= 0:
        raise ValueError(f"inside edge radius {centerline_radius} - {half} is not positive")
    return {
        "radius": radius,
        "edge": edge,
        "side": s,
        "turn_direction": direction,
        "rp_side": rp_side,
        "lots_toward_rp": edge == "inside",
    }


def _candidate_report(label: str, shift: float, radius: float, stated: dict[str, float], tol: float) -> dict[str, Any]:
    """Would R' = stated R + shift reproduce the stated T/L/C (delta stated)?  Same widening tolerance as the audit."""
    pair = {"radius": radius, "delta_deg": stated["delta_deg"]}
    rec = _solve(pair)
    unc = _basis_uncertainty(pair)
    res = {p: stated[p] - rec[p] for p in _LMC if p in stated}
    tols = {p: tol + unc[p] for p in res}
    return {
        "label": label,
        "shift": shift,
        "radius": radius,
        "residuals": res,
        "tolerance": tols,
        "max_residual": max((abs(v) for v in res.values()), default=math.inf),
        "fits": all(abs(res[p]) <= tols[p] for p in res),
    }


def diagnose_offset(reading: PlatCurveReading | dict, row_width: float = 60.0, tol: float = PLAT_TOL_FT) -> dict:
    """Test whether stated T / L / C disagree with the stated R only because of a right-of-way half-width mix-up.

    Plat centerline (℄) curve data and right-of-way-edge data differ by R +- row_width/2 (same delta, same radius point),
    and the two get confused.  With delta stated, T, L and C each imply a radius (T/tan(Δ/2), L/Δ, C/(2 sin(Δ/2))); the
    hypotheses tested are that the stated T/L/C belong to R + shift for shift in 0, +-w/2, +-w.  Returns
    ``{"hypothesis", "implied_centerline_R", "which_edge", "shift", "alternative", "candidates", "implied_radii", ...}``.
    ``hypothesis`` is one of: ``"stated values consistent (no offset)"``; ``"stated R is a R/W edge, not centerline"``
    (shift = +-w/2: T/L/C are the centerline's, ``which_edge`` says whether the stated R is the ``"inside"`` or
    ``"outside"`` edge; ``alternative`` gives the numerically identical opposite reading, that R is the centerline and
    T/L/C belong to an edge); ``"stated R and T/L/C are opposite R/W edges"`` (shift = +-w); ``"none"`` (no hypothesis
    reproduces the stated values -- ``implied_radius_shift`` still reports the raw offset for inspection).  Numbers alone
    cannot say WHICH of the two figures is the centerline's; the caller must decide from the source (℄ Curve Data block vs
    a drawn edge label).  If delta is not stated it is solved from a pair of stated T/L/C.
    """
    r = _as_reading(reading)
    stated = r.stated()
    w = float(row_width)
    out: dict[str, Any] = {
        "id": r.id,
        "row_width": w,
        "stated_radius": stated.get("radius"),
        "hypothesis": "none",
        "implied_centerline_R": None,
        "which_edge": None,
        "shift": None,
        "alternative": None,
        "candidates": [],
        "implied_radii": {},
        "implied_radius_shift": None,
        "reason": "",
    }
    if "radius" not in stated:
        out["reason"] = "radius not stated; nothing to compare"
        return out
    bad = _invalid_reason(stated)
    if bad:
        out["reason"] = bad
        return out
    r_s = stated["radius"]
    lmc = {p: stated[p] for p in _LMC if p in stated}
    if not lmc:
        out["reason"] = "none of T / L / C stated; nothing to compare with R"
        return out

    # Radius each stated T/L/C implies.  Delta is the same for concentric curves, so it is the fixed reference.
    delta = stated.get("delta_deg")
    r_impl_tol = tol
    if delta is not None:
        for p, v in lmc.items():
            out["implied_radii"][p] = _solve({"delta_deg": delta, p: v})["radius"]
        work = {"delta_deg": delta, **lmc}
    else:
        if len(lmc) < 2:
            out["reason"] = "Δ not stated and fewer than two of T / L / C: cannot separate radius from angle"
            return out
        first_two = tuple(p for p in _LMC if p in lmc)[:2]
        pair = {p: lmc[p] for p in first_two}
        try:
            sol = _solve(pair)
        except ValueError as exc:
            out["reason"] = f"stated T/L/C do not describe a curve: {exc}"
            return out
        delta = sol["delta_deg"]
        r_impl_tol = tol + _basis_uncertainty(pair)["radius"]
        out["implied_radii"] = {"+".join(first_two): sol["radius"]}
        out["implied_delta_deg"] = delta
        work = {"delta_deg": delta, **lmc}
        if len(lmc) == 3:  # third value must agree with the solved curve or the T/L/C themselves are inconsistent
            extra_p = next(p for p in _LMC if p in lmc and p not in first_two)
            unc = _basis_uncertainty(pair)
            if abs(lmc[extra_p] - sol[extra_p]) > tol + unc[extra_p]:
                out["reason"] = (
                    f"stated T/L/C are mutually inconsistent ({_SHORT[extra_p]} off by {lmc[extra_p] - sol[extra_p]:+.4f})"
                )
                return out

    ref_r = next(iter(out["implied_radii"].values()))
    out["implied_radius_shift"] = ref_r - r_s

    shifts = [(0.0, "as stated")]
    for k, name in ((0.5, "half-width"), (1.0, "full width")):
        shifts += [(+k * w, f"+{name}"), (-k * w, f"-{name}")]
    cands = []
    for shift, label in shifts:
        radius = r_s + shift
        if radius <= 0:
            continue
        if "delta_deg" in stated:
            cands.append(_candidate_report(label, shift, radius, work, tol))
        else:  # delta was solved from T/L/C: compare radii directly
            res = {"radius": ref_r - radius}
            cands.append(
                {
                    "label": label,
                    "shift": shift,
                    "radius": radius,
                    "residuals": res,
                    "tolerance": {"radius": r_impl_tol},
                    "max_residual": abs(res["radius"]),
                    "fits": abs(res["radius"]) <= r_impl_tol,
                }
            )
    out["candidates"] = cands
    fits = [c for c in cands if c["fits"]]
    if not fits:
        spread = max(out["implied_radii"].values()) - min(out["implied_radii"].values())
        if spread > tol + 2 * r_impl_tol:
            out["reason"] = f"stated T/L/C imply different radii (spread {spread:.3f} ft): {out['implied_radii']}"
            return out
        out["reason"] = (
            f"no offset in {{0, ±{w / 2:g}, ±{w:g}}} ft reproduces the stated T/L/C; implied radius differs from stated R by "
            f"{out['implied_radius_shift']:+.3f} ft"
        )
        return out

    hit = fits[0]  # candidates are ordered 0, +-w/2, +-w -> the simplest explanation wins
    shift = hit["shift"]
    out["shift"] = shift
    out["reason"] = f"T/L/C reproduce at R = {hit['radius']:.4f} (stated R {shift:+.4f})"
    if shift == 0.0:
        out["hypothesis"] = "stated values consistent (no offset)"
        out["implied_centerline_R"] = r_s
    elif abs(abs(shift) - w / 2.0) < 1e-9:
        out["hypothesis"] = "stated R is a R/W edge, not centerline"
        out["implied_centerline_R"] = hit["radius"]
        out["which_edge"] = "outside" if shift < 0 else "inside"
        out["alternative"] = {
            "hypothesis": "stated R is the centerline; stated T/L/C belong to a R/W edge",
            "implied_centerline_R": r_s,
            "which_edge_of_TLC": "outside" if shift > 0 else "inside",
            "edge_radius": hit["radius"],
        }
    else:
        out["hypothesis"] = "stated R and T/L/C are opposite R/W edges"
        out["implied_centerline_R"] = r_s + shift / 2.0
        out["which_edge"] = "outside" if shift < 0 else "inside"  # which edge the STATED R is
        out["alternative"] = None
    return out


__all__ = [
    "ANGLE_HALF_UNIT_DEG",
    "KINDS",
    "LENGTH_HALF_UNIT_FT",
    "PLAT_TOL_FT",
    "PlatCurveReading",
    "audit_reading",
    "diagnose_offset",
    "edge_radius",
    "parse_curve_data",
    "parse_curve_data_ex",
]
