"""
curves.py -- circular curve solver for plat curve tables.

Clay County plat curve tables give: Length (arc), Radius, Delta, Chord
Bearing, Chord. That's actually over-determined (any 2 of R/L/Delta/chord
solve the rest) -- we use it as a consistency check, then compute PC/PT/RP
and generate arc vertices for DXF once we know the bearing of the incoming
tangent (or, for a standalone table row, the chord bearing + delta directly
gives tangent-in/tangent-out bearings, which is enough to draw the arc as a
free-standing entity placed at a known PC).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .cogo import Point, azimuth_to_bearing, parse_bearing


@dataclass
class Curve:
    id: str
    length: float
    radius: float
    delta_deg: float
    chord_bearing: str
    chord: float
    rot: str = "CCW"  # rotation sense as you travel PC->PT; set by caller/context

    def check(self, tol=0.05) -> bool:
        """Cross-check L = R*delta(rad) and chord = 2R sin(delta/2)."""
        calc_L = self.radius * math.radians(self.delta_deg)
        calc_chord = 2 * self.radius * math.sin(math.radians(self.delta_deg) / 2)
        return abs(calc_L - self.length) < tol and abs(calc_chord - self.chord) < tol

    @property
    def delta_rad(self) -> float:
        return math.radians(self.delta_deg)

    @property
    def tangent(self) -> float:
        return self.radius * math.tan(self.delta_rad / 2.0)

    @property
    def mid_ordinate(self) -> float:
        return self.radius * (1.0 - math.cos(self.delta_rad / 2.0))

    @property
    def external(self) -> float:
        c = math.cos(self.delta_rad / 2.0)
        return self.radius * (1.0 / c - 1.0) if c > 1e-9 else float("inf")

    @property
    def degree_curve(self) -> float:
        return 5729.57795 / self.radius if self.radius > 0 else 0.0

    @property
    def segment_area(self) -> float:
        return 0.5 * (self.radius ** 2) * (self.delta_rad - math.sin(self.delta_rad))

    @property
    def sector_area(self) -> float:
        return 0.5 * (self.radius ** 2) * self.delta_rad

    @property
    def fillet_area(self) -> float:
        return (self.radius * self.tangent) - self.sector_area

    @property
    def delta_dms(self) -> str:
        return deg_to_dms_str(self.delta_deg)

    def tangent_in_bearing(self) -> str:
        chord_az = parse_bearing(self.chord_bearing)
        half_delta = self.delta_deg / 2.0
        sign = 1 if self.rot == "CW" else -1
        t_az = (chord_az - sign * half_delta) % 360.0
        return azimuth_to_bearing(t_az)

    def tangent_out_bearing(self) -> str:
        chord_az = parse_bearing(self.chord_bearing)
        half_delta = self.delta_deg / 2.0
        sign = 1 if self.rot == "CW" else -1
        t_az = (chord_az + sign * half_delta) % 360.0
        return azimuth_to_bearing(t_az)

    def arc_points(self, pc: Point, n_segments: int = 24) -> list[Point]:
        """Generate points along the arc from PC to PT given rotation sense."""
        chord_az = parse_bearing(self.chord_bearing)
        half_delta = self.delta_deg / 2.0
        # tangent-in bearing = chord bearing rotated by -/+ half delta depending on rotation
        sign = 1 if self.rot == "CW" else -1
        tangent_in_az = (chord_az - sign * half_delta) % 360.0
        # radius point is 90 deg left (CCW curve) or right (CW curve) of tangent-in direction
        rp_az = (tangent_in_az + sign * 90.0) % 360.0
        rp = pc.offset(rp_az, self.radius)
        # bearing from RP to PC
        start_az = (rp_az + 180.0) % 360.0
        pts = []
        for i in range(n_segments + 1):
            frac = i / n_segments
            ang = start_az + sign * self.delta_deg * frac
            pts.append(rp.offset(ang, self.radius))
        return pts

    def pt_from_pc(self, pc: Point) -> Point:
        return self.arc_points(pc, n_segments=1)[-1]

    def align_and_determine_direction(
        self,
        pc: Point,
        pt: Point,
        skeleton_pts: list[Any],
        max_search_dist: float = 60.0,
    ) -> str:
        """Determines curve rotation direction ('CW' or 'CCW') by matching against
        the aligned skeleton scan linework, updates self.rot, and returns it."""
        res = determine_curve_direction_from_skeleton(
            pc=pc,
            pt=pt,
            skeleton_pts=skeleton_pts,
            radius=self.radius,
            delta_deg=self.delta_deg,
            max_search_dist=max_search_dist,
        )
        self.rot = res["rot"]
        return self.rot

    def fit_to_skeleton(
        self,
        pc: Point,
        pt: Point,
        skeleton_pts: list[Any],
        n_segments: int = 24,
    ) -> dict[str, Any]:
        """Aligns direction to skeleton, traces arc points, and calculates RMS fit error."""
        direction_info = determine_curve_direction_from_skeleton(
            pc=pc,
            pt=pt,
            skeleton_pts=skeleton_pts,
            radius=self.radius,
            delta_deg=self.delta_deg,
        )
        self.rot = direction_info["rot"]
        arc_pts = self.arc_points(pc, n_segments=n_segments)

        # Compute radius point for continuous radial residuals
        chord_az = parse_bearing(self.chord_bearing)
        half_delta = self.delta_deg / 2.0
        sign = 1 if self.rot == "CW" else -1
        tangent_in_az = (chord_az - sign * half_delta) % 360.0
        rp_az = (tangent_in_az + sign * 90.0) % 360.0
        rp = pc.offset(rp_az, self.radius)

        pcn = pc.n if hasattr(pc, "n") else pc[0]
        pce = pc.e if hasattr(pc, "e") else pc[1]
        ptn = pt.n if hasattr(pt, "n") else pt[0]
        pte = pt.e if hasattr(pt, "e") else pt[1]
        dn = ptn - pcn
        de = pte - pce
        c = math.hypot(dn, de)

        residuals = []
        for sp in skeleton_pts:
            pn = sp.n if hasattr(sp, "n") else sp[0]
            pe = sp.e if hasattr(sp, "e") else sp[1]
            if c > 1e-9:
                t = ((pn - pcn) * dn + (pe - pce) * de) / c
                t_frac = t / c
                if 0.0 <= t_frac <= 1.0:
                    rad_dist = math.hypot(pn - rp.n, pe - rp.e)
                    err = abs(rad_dist - self.radius)
                    if err <= 20.0:
                        residuals.append(err)

        if not residuals:
            for ap in arc_pts:
                dists = [ap.dist_to(sp if hasattr(sp, "dist_to") else Point(sp[0], sp[1]))
                         for sp in skeleton_pts
                         if abs(ap.n - (sp.n if hasattr(sp, "n") else sp[0])) < 50.0 and
                            abs(ap.e - (sp.e if hasattr(sp, "e") else sp[1])) < 50.0]
                if dists:
                    residuals.append(min(dists))

        rms = math.sqrt(sum(r ** 2 for r in residuals) / len(residuals)) if residuals else 0.0

        return {
            "rot": self.rot,
            "direction_info": direction_info,
            "arc_points": arc_pts,
            "rms_residual_ft": round(rms, 3),
            "max_residual_ft": round(max(residuals), 3) if residuals else 0.0,
        }



def deg_to_dms_str(deg_val: float) -> str:
    """Format decimal degrees into DMS string, e.g. 37°42'50\"."""
    d = int(deg_val)
    rem_m = (deg_val - d) * 60.0
    m = int(rem_m)
    s = round((rem_m - m) * 60.0, 1)
    if s >= 60.0:
        s -= 60.0
        m += 1
    if m >= 60:
        m -= 60
        d += 1
    s_int = int(s) if abs(s - int(s)) < 1e-3 else s
    return f"{d:02d}°{m:02d}'{s_int:02d}\"" if isinstance(s_int, int) else f"{d:02d}°{m:02d}'{s:04.1f}\""


def solve_curve_all_parameters(
    radius: float | None = None,
    delta_deg: float | None = None,
    length: float | None = None,
    chord: float | None = None,
    tangent: float | None = None,
    mid_ordinate: float | None = None,
    external: float | None = None,
    degree_curve: float | None = None,
) -> dict[str, float | str]:
    """
    Omni-Parameter Circular Curve Solver.
    
    Given ANY 2 of the 8 standard curve parameters:
      - R (radius)
      - Delta (delta_deg, central angle)
      - L (length, arc length)
      - C (chord, chord length)
      - T (tangent, tangent length)
      - M (mid_ordinate, sagitta)
      - E (external, external secant)
      - D (degree_curve, arc definition 5729.578 / R)
      
    Computes all 8 parameters plus circular segment area, sector area, and fillet area.
    Supports all 28 parameter pair combinations.
    """
    have = {
        k: float(v)
        for k, v in dict(
            radius=radius,
            delta_deg=delta_deg,
            length=length,
            chord=chord,
            tangent=tangent,
            mid_ordinate=mid_ordinate,
            external=external,
            degree_curve=degree_curve,
        ).items()
        if v is not None
    }

    if len(have) < 2:
        raise ValueError("Need at least 2 parameters to solve circular curve")

    for k, val in have.items():
        if val <= 0.0:
            raise ValueError(f"Curve parameter {k} must be strictly positive, got {val}")

    # If degree of curve is provided, map to radius first
    if "degree_curve" in have and "radius" not in have:
        have["radius"] = 5729.57795 / have["degree_curve"]

    # --- Case 1: Radius and any other parameter ---
    if "radius" in have:
        R = have["radius"]
        if "delta_deg" in have:
            delta_d = have["delta_deg"]
        elif "length" in have:
            delta_d = math.degrees(have["length"] / R)
        elif "chord" in have:
            C = have["chord"]
            if C > 2.0 * R + 1e-7:
                raise ValueError(f"Chord {C} cannot exceed diameter 2*R ({2.0*R})")
            delta_d = math.degrees(2.0 * math.asin(min(1.0, C / (2.0 * R))))
        elif "tangent" in have:
            delta_d = math.degrees(2.0 * math.atan(have["tangent"] / R))
        elif "mid_ordinate" in have:
            M = have["mid_ordinate"]
            if M > R:
                raise ValueError(f"Mid-ordinate {M} cannot exceed radius R ({R})")
            delta_d = math.degrees(2.0 * math.acos(max(-1.0, 1.0 - M / R)))
        elif "external" in have:
            E = have["external"]
            delta_d = math.degrees(2.0 * math.acos(max(0.0, min(1.0, R / (R + E)))))
        elif "degree_curve" in have:
            # Over-determined check: D and R must match
            expected_D = 5729.57795 / R
            if abs(expected_D - have["degree_curve"]) > 0.05:
                raise ValueError(f"Inconsistent degree of curve {have['degree_curve']} vs radius {R}")
            raise ValueError("Radius and Degree of Curve are collinear; need one additional independent parameter")
        else:
            raise ValueError("Need an independent parameter alongside radius")

    # --- Case 2: Delta and any other parameter ---
    elif "delta_deg" in have:
        delta_d = have["delta_deg"]
        delta_r = math.radians(delta_d)
        if "length" in have:
            R = have["length"] / delta_r
        elif "chord" in have:
            R = have["chord"] / (2.0 * math.sin(delta_r / 2.0))
        elif "tangent" in have:
            R = have["tangent"] / math.tan(delta_r / 2.0)
        elif "mid_ordinate" in have:
            R = have["mid_ordinate"] / (1.0 - math.cos(delta_r / 2.0))
        elif "external" in have:
            c = math.cos(delta_r / 2.0)
            R = have["external"] / (1.0 / c - 1.0)
        else:
            raise ValueError("Need an independent parameter alongside delta")

    # --- Case 3: Length (Arc) and any other parameter ---
    elif "length" in have:
        L = have["length"]
        if "chord" in have:
            C = have["chord"]
            if L < C - 1e-7:
                raise ValueError(f"Arc length {L} cannot be smaller than chord {C}")
            ratio = min(1.0, C / L)
            theta = math.sqrt(max(0.0, 6.0 * (1.0 - ratio)))
            if theta == 0.0: theta = 0.1
            for _ in range(30):
                f_val = math.sin(theta) - ratio * theta
                f_prime = math.cos(theta) - ratio
                if abs(f_prime) < 1e-12: break
                d_theta = f_val / f_prime
                theta -= d_theta
                if abs(d_theta) < 1e-12: break
            delta_d = math.degrees(2.0 * theta)
            R = L / math.radians(delta_d)
        elif "tangent" in have:
            T = have["tangent"]
            # T = R tan(theta) = (L / 2theta) tan(theta) => tan(theta)/theta = 2T / L
            k = (2.0 * T) / L
            if k < 1.0:
                raise ValueError(f"Tangent {T} must satisfy 2*T >= L ({L})")
            theta = math.sqrt(max(0.0, 3.0 * (k - 1.0)))
            if theta == 0.0: theta = 0.1
            for _ in range(30):
                c = math.cos(theta)
                sec2 = 1.0 / (c * c) if abs(c) > 1e-9 else 1.0
                f_val = math.tan(theta) - k * theta
                f_prime = sec2 - k
                if abs(f_prime) < 1e-12: break
                d_theta = f_val / f_prime
                theta -= d_theta
                if abs(d_theta) < 1e-12: break
            delta_d = math.degrees(2.0 * theta)
            R = L / math.radians(delta_d)
        elif "mid_ordinate" in have:
            M = have["mid_ordinate"]
            # (1 - cos(theta)) / theta = 2M / L
            k = (2.0 * M) / L
            theta = 2.0 * k
            for _ in range(30):
                f_val = (1.0 - math.cos(theta)) - k * theta
                f_prime = math.sin(theta) - k
                if abs(f_prime) < 1e-12: break
                d_theta = f_val / f_prime
                theta -= d_theta
                if abs(d_theta) < 1e-12: break
            delta_d = math.degrees(2.0 * theta)
            R = L / math.radians(delta_d)
        elif "external" in have:
            E = have["external"]
            # (sec(theta) - 1) / theta = 2E / L
            k = (2.0 * E) / L
            theta = 2.0 * k
            for _ in range(30):
                c = math.cos(theta)
                sec = 1.0 / c if abs(c) > 1e-9 else 1.0
                tan = math.tan(theta)
                f_val = (sec - 1.0) - k * theta
                f_prime = sec * tan - k
                if abs(f_prime) < 1e-12: break
                d_theta = f_val / f_prime
                theta -= d_theta
                if abs(d_theta) < 1e-12: break
            delta_d = math.degrees(2.0 * theta)
            R = L / math.radians(delta_d)
        else:
            raise ValueError("Could not solve curve with length and provided parameter")

    # --- Case 4: Chord and Tangent / Mid-Ordinate / External ---
    elif "chord" in have:
        C = have["chord"]
        if "tangent" in have:
            T = have["tangent"]
            # cos(theta) = C / (2*T)
            cos_theta = C / (2.0 * T)
            if cos_theta > 1.0 or cos_theta < 0.0:
                raise ValueError(f"Incompatible chord {C} and tangent {T} (C/(2T)={cos_theta:.4f})")
            theta = math.acos(cos_theta)
            delta_d = math.degrees(2.0 * theta)
            R = T / math.tan(theta)
        elif "mid_ordinate" in have:
            M = have["mid_ordinate"]
            # Exact closed-form circle geometry sagitta theorem: R = M/2 + C^2 / (8M)
            R = (M / 2.0) + ((C ** 2) / (8.0 * M))
            theta = math.asin(min(1.0, C / (2.0 * R)))
            delta_d = math.degrees(2.0 * theta)
        elif "external" in have:
            E = have["external"]
            # E = R(sec(theta)-1), C = 2R sin(theta) => (sec(theta)-1) / (2 sin(theta)) = E / C
            k = E / C
            theta = 2.0 * math.atan(2.0 * k)
            for _ in range(30):
                c = math.cos(theta); s = math.sin(theta)
                sec = 1.0 / c if abs(c) > 1e-9 else 1.0
                f_val = (sec - 1.0) - 2.0 * k * s
                f_prime = sec * math.tan(theta) - 2.0 * k * c
                if abs(f_prime) < 1e-12: break
                d_theta = f_val / f_prime
                theta -= d_theta
                if abs(d_theta) < 1e-12: break
            delta_d = math.degrees(2.0 * theta)
            R = C / (2.0 * math.sin(theta))
        else:
            raise ValueError("Could not solve curve with chord and provided parameter")

    # --- Case 5: Tangent and Mid-Ordinate / External ---
    elif "tangent" in have:
        T = have["tangent"]
        if "external" in have:
            E = have["external"]
            # Circle tangent-secant theorem: T^2 = E * (2R + E) => 2RE = T^2 - E^2 => R = (T^2 - E^2)/(2E)
            if T <= E:
                raise ValueError(f"Tangent {T} must exceed external secant {E}")
            R = (T ** 2 - E ** 2) / (2.0 * E)
            theta = math.atan(T / R)
            delta_d = math.degrees(2.0 * theta)
        elif "mid_ordinate" in have:
            M = have["mid_ordinate"]
            # M/T = tan(theta/2) * cos(theta)
            k = M / T
            theta = 2.0 * k
            for _ in range(30):
                h = theta / 2.0
                c = math.cos(theta)
                f_val = math.tan(h) * c - k
                f_prime = 0.5 * (1.0 / (math.cos(h) ** 2)) * c - math.tan(h) * math.sin(theta)
                if abs(f_prime) < 1e-12: break
                d_theta = f_val / f_prime
                theta -= d_theta
                if abs(d_theta) < 1e-12: break
            delta_d = math.degrees(2.0 * theta)
            R = T / math.tan(theta)
        else:
            raise ValueError("Could not solve curve with tangent and provided parameter")

    # --- Case 6: Mid-Ordinate and External ---
    elif "mid_ordinate" in have and "external" in have:
        M = have["mid_ordinate"]
        E = have["external"]
        # (R - M)(R + E) = R^2 => R(E - M) = M*E => R = (M*E) / (E - M)
        if E <= M:
            raise ValueError(f"External secant {E} must strictly exceed mid-ordinate {M}")
        R = (M * E) / (E - M)
        theta = math.acos(max(-1.0, min(1.0, 1.0 - M / R)))
        delta_d = math.degrees(2.0 * theta)
    else:
        raise ValueError("Provided parameter combination cannot be resolved")

    # Final parameter calculations
    delta_r = math.radians(delta_d)
    half_delta = delta_r / 2.0
    cos_half = math.cos(half_delta)

    L = R * delta_r
    C = 2.0 * R * math.sin(half_delta)
    T = R * math.tan(half_delta)
    M = R * (1.0 - cos_half)
    E = R * (1.0 / cos_half - 1.0) if cos_half > 1e-9 else float("inf")
    D = 5729.57795 / R

    seg_area = 0.5 * (R ** 2) * (delta_r - math.sin(delta_r))
    sec_area = 0.5 * (R ** 2) * delta_r
    fillet_area = (R * T) - sec_area

    return {
        "radius": round(R, 4),
        "delta_deg": round(delta_d, 6),
        "delta_rad": delta_r,
        "delta_dms": deg_to_dms_str(delta_d),
        "length": round(L, 4),
        "chord": round(C, 4),
        "tangent": round(T, 4),
        "mid_ordinate": round(M, 4),
        "external": round(E, 4),
        "degree_curve": round(D, 5),
        "segment_area": round(seg_area, 2),
        "sector_area": round(sec_area, 2),
        "fillet_area": round(fillet_area, 2),
    }


def solve_missing(radius=None, length=None, delta_deg=None, chord=None):
    """
    Solve for missing curve parameter given any two of radius/length/delta/chord.
    Fully backwards-compatible with the original 6-way solver.
    """
    res = solve_curve_all_parameters(radius=radius, delta_deg=delta_deg, length=length, chord=chord)
    return dict(
        radius=res["radius"],
        length=res["length"],
        delta_deg=res["delta_deg"],
        chord=res["chord"],
    )


def verify_curve_consistency(curve: Curve, tol: float = 0.05) -> bool:
    """Verify internal mathematical consistency of all 4 circular curve parameters."""
    return curve.check(tol=tol)


def curve_segment_area(radius: float, delta_deg: float) -> float:
    """Calculate circular segment area between arc and chord: A = 0.5 * R^2 * (theta - sin(theta))."""
    if radius <= 0 or delta_deg <= 0:
        return 0.0
    theta = math.radians(delta_deg)
    return 0.5 * (radius ** 2) * (theta - math.sin(theta))


_INK_CACHE: dict = {}


def _ink_for(skeleton_pts):
    """InkField for a list of skeleton points, built once per list (an InkField passes through)."""
    from engine.curve_follow import InkField
    if isinstance(skeleton_pts, InkField):
        return skeleton_pts
    first = skeleton_pts[0]
    key = (id(skeleton_pts), len(skeleton_pts), getattr(first, "n", first[0] if not hasattr(first, "n") else 0.0))
    if key not in _INK_CACHE:
        if len(_INK_CACHE) > 8:
            _INK_CACHE.clear()
        _INK_CACHE[key] = InkField.from_points(skeleton_pts)
    return _INK_CACHE[key]


def determine_curve_direction_from_skeleton(
    pc: Point,
    pt: Point,
    skeleton_pts: list[Any],
    radius: float | None = None,
    delta_deg: float | None = None,
    max_search_dist: float = 60.0,
    fallback_rot: str = "CCW",
    resolution_ft: float = 2.0,
) -> dict[str, Any]:
    """Decide whether a circular curve runs 'CW' or 'CCW' from PC to PT, using the
    aligned skeleton scan (a list of Points, or an engine.curve_follow.InkField).

    The verdict comes from curve_follow.choose_curve_side: both candidate arcs are
    slid over the ink and scored by how much of each lands on ink running the same way.
    'rot' is the scan's answer ONLY when 'decided' is True. Otherwise -- the two arcs
    differ by less than resolution_ft can resolve (mid-ordinate under ~5 ft for a real
    scan), or no ink follows either -- 'rot' is fallback_rot and 'verdict' / 'reason'
    say why. A caller must not override a known side unless 'decided'.

    (An earlier version took the sign of the MEDIAN lateral offset of every skeleton
    point in a corridor along the chord. That measures which side of the chord has more
    ink -- lot lines, text, the block interior -- not which way the arc bulges. On
    Beachwood it changed 9 of 18 coded sides at confidence 0.00. The offset statistics
    below are kept as descriptive values only; they no longer decide anything.)

    In the survey coordinate system (Northing, Easting), travelling PC -> PT:
      a 'CW' arc turns right and bulges to the LEFT of the chord (signed offset > 0);
      a 'CCW' arc turns left and bulges to the RIGHT (signed offset < 0).

    Returns: direction/rot ('CW' or 'CCW'), decided (bool), verdict (DECIDED |
    INDETERMINATE | AMBIGUOUS | NO_INK | NO_CURVE_DATA), reason, observed_mid_ordinate,
    theoretical_mid_ordinate, mid_ordinate_error, mean_offset, median_offset,
    peak_offset, sample_count, confidence (share of the arc the winning side is
    followed along, 0 if undecided).
    """
    pcn = pc.n if hasattr(pc, "n") else pc[0]
    pce = pc.e if hasattr(pc, "e") else pc[1]
    ptn = pt.n if hasattr(pt, "n") else pt[0]
    pte = pt.e if hasattr(pt, "e") else pt[1]

    dn = ptn - pcn
    de = pte - pce
    c = math.hypot(dn, de)
    empty = {
        "direction": fallback_rot, "rot": fallback_rot, "decided": False,
        "verdict": "NO_CURVE_DATA", "reason": "zero-length chord",
        "observed_mid_ordinate": 0.0, "theoretical_mid_ordinate": 0.0, "mid_ordinate_error": 0.0,
        "mean_offset": 0.0, "median_offset": 0.0, "peak_offset": 0.0, "sample_count": 0,
        "confidence": 0.0,
    }
    if c < 1e-9:
        return empty

    theo_m = None
    if radius is not None and delta_deg is not None:
        theo_m = radius * (1.0 - math.cos(math.radians(delta_deg) / 2.0))

    effective_search_dist = max_search_dist
    if theo_m is not None and theo_m > 0:
        effective_search_dist = min(max_search_dist, max(8.0, 3.5 * theo_m))

    # Descriptive corridor statistics (NOT used for the decision)
    offsets: list[float] = []
    min_n = min(pcn, ptn) - effective_search_dist
    max_n = max(pcn, ptn) + effective_search_dist
    min_e = min(pce, pte) - effective_search_dist
    max_e = max(pce, pte) + effective_search_dist
    pts_iter = skeleton_pts.points if hasattr(skeleton_pts, "points") else skeleton_pts
    for p in pts_iter:
        pn = p.n if hasattr(p, "n") else p[0]
        pe = p.e if hasattr(p, "e") else p[1]
        if pn < min_n or pn > max_n or pe < min_e or pe > max_e:
            continue
        t_frac = (((pn - pcn) * dn + (pe - pce) * de) / c) / c
        if 0.08 <= t_frac <= 0.92:
            off = (de * (pn - pcn) - dn * (pe - pce)) / c
            if abs(off) <= effective_search_dist:
                offsets.append(off)

    stats = dict(empty)
    stats["theoretical_mid_ordinate"] = round(theo_m, 4) if theo_m is not None else None
    stats["mid_ordinate_error"] = None
    stats["sample_count"] = len(offsets)
    if offsets:
        sorted_offs = sorted(offsets)
        peak_off = max(offsets, key=abs)
        stats.update(mean_offset=round(float(sum(offsets) / len(offsets)), 4),
                     median_offset=round(float(sorted_offs[len(sorted_offs) // 2]), 4),
                     peak_offset=round(peak_off, 4), observed_mid_ordinate=round(abs(peak_off), 4),
                     mid_ordinate_error=round(abs(abs(peak_off) - theo_m), 4) if theo_m is not None else None)

    if radius is None or delta_deg is None:
        stats.update(verdict="NO_CURVE_DATA", reason="radius and delta are needed to test the two arcs")
        return stats
    if len(pts_iter) == 0:
        stats.update(verdict="NO_INK", reason="no skeleton points")
        return stats

    from engine.curve_follow import choose_curve_side
    az = (math.degrees(math.atan2(de, dn)) + 360.0) % 360.0
    probe = Curve(id="_scan_probe", length=radius * math.radians(delta_deg), radius=radius,
                  delta_deg=delta_deg, chord_bearing=azimuth_to_bearing(az), chord=c, rot="CW")
    res = choose_curve_side(probe, pc, _ink_for(skeleton_pts), tol_ft=resolution_ft)
    stats.update(verdict=res.verdict, reason=res.reason)
    if res.side is not None:
        stats.update(direction=res.side, rot=res.side, decided=True,
                     confidence=round(float(res.fits[res.side].cover), 4))
    # NOTE: there is deliberately NO fallback to the median offset of the points in the
    # corridor when the scan cannot decide. That measures which side of the chord has more
    # ink (lot lines, text, the block interior), not which way the arc bulges. As a fallback
    # it "decided" 7 of Beachwood's 18 curved sides and flipped Marina lots 29-31 to CW --
    # the side a common-circle test proves wrong -- leaving those lots 266 sq ft off. Exact
    # synthetic arcs are decided properly by passing a tighter resolution_ft; an undecided
    # answer stays undecided.
    return stats


def trace_curve_from_skeleton(
    id: str,
    pc: Point,
    pt: Point,
    radius: float,
    skeleton_pts: list[Any],
    chord_bearing: str | None = None,
    n_segments: int = 24,
    fallback_rot: str | None = None,
) -> Curve:
    """Trace and construct a circular Curve between PC and PT, using the aligned
    skeleton scan to determine curve direction. If the scan cannot decide the side
    (see determine_curve_direction_from_skeleton) the side is fallback_rot, or a
    ValueError if none was given -- it never silently picks one."""
    pcn = pc.n if hasattr(pc, "n") else pc[0]
    pce = pc.e if hasattr(pc, "e") else pc[1]
    ptn = pt.n if hasattr(pt, "n") else pt[0]
    pte = pt.e if hasattr(pt, "e") else pt[1]

    dn = ptn - pcn
    de = pte - pce
    chord_dist = math.hypot(dn, de)
    if chord_dist > 2.0 * radius:
        radius = chord_dist / 2.0  # limit radius to semicircle

    # Central angle Delta
    sin_half_delta = max(-1.0, min(1.0, chord_dist / (2.0 * radius)))
    half_delta_rad = math.asin(sin_half_delta)
    delta_deg = math.degrees(2.0 * half_delta_rad)
    arc_length = radius * math.radians(delta_deg)

    if chord_bearing is None:
        az = (math.degrees(math.atan2(de, dn)) + 360.0) % 360.0
        chord_bearing = azimuth_to_bearing(az)

    # Determine direction from aligned skeleton scan
    dir_info = determine_curve_direction_from_skeleton(
        pc=pc, pt=pt, skeleton_pts=skeleton_pts, radius=radius, delta_deg=delta_deg,
        fallback_rot=fallback_rot or "CCW",
    )
    if not dir_info["decided"] and fallback_rot is None:
        raise ValueError(f"the scan cannot decide this curve's side: {dir_info['reason']}")
    rot = dir_info["rot"]

    return Curve(
        id=id,
        length=round(arc_length, 4),
        radius=round(radius, 4),
        delta_deg=round(delta_deg, 6),
        chord_bearing=chord_bearing,
        chord=round(chord_dist, 4),
        rot=rot,
    )




