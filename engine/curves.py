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
from .cogo import Point, parse_bearing, azimuth_to_bearing


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


def solve_missing(radius=None, length=None, delta_deg=None, chord=None):
    """Solve for missing curve parameter given any two of radius/length/delta/chord.
    Supports all 6 pairs: (R, Delta), (R, L), (L, Delta), (R, C), (Delta, C), (L, C).
    """
    have = {k: v for k, v in dict(radius=radius, length=length,
                                   delta_deg=delta_deg, chord=chord).items() if v is not None}
    if len(have) < 2:
        raise ValueError("Need at least 2 parameters to solve circular curve")

    if "radius" in have and "delta_deg" in have:
        radius = float(have["radius"])
        delta_deg = float(have["delta_deg"])
        length = radius * math.radians(delta_deg)
        chord = 2.0 * radius * math.sin(math.radians(delta_deg) / 2.0)
    elif "radius" in have and "length" in have:
        radius = float(have["radius"])
        length = float(have["length"])
        delta_deg = math.degrees(length / radius)
        chord = 2.0 * radius * math.sin(math.radians(delta_deg) / 2.0)
    elif "length" in have and "delta_deg" in have:
        length = float(have["length"])
        delta_deg = float(have["delta_deg"])
        radius = length / math.radians(delta_deg)
        chord = 2.0 * radius * math.sin(math.radians(delta_deg) / 2.0)
    elif "radius" in have and "chord" in have:
        radius = float(have["radius"])
        chord = float(have["chord"])
        if chord > 2.0 * radius + 1e-7:
            raise ValueError(f"Chord {chord} cannot exceed diameter 2*R ({2.0*radius})")
        ratio = min(1.0, max(-1.0, chord / (2.0 * radius)))
        delta_rad = 2.0 * math.asin(ratio)
        delta_deg = math.degrees(delta_rad)
        length = radius * delta_rad
    elif "delta_deg" in have and "chord" in have:
        delta_deg = float(have["delta_deg"])
        chord = float(have["chord"])
        delta_rad = math.radians(delta_deg)
        denom = 2.0 * math.sin(delta_rad / 2.0)
        if abs(denom) < 1e-9:
            raise ValueError(f"Delta {delta_deg} too small to solve curve from chord")
        radius = chord / denom
        length = radius * delta_rad
    elif "length" in have and "chord" in have:
        length = float(have["length"])
        chord = float(have["chord"])
        if length < chord - 1e-7:
            raise ValueError(f"Arc length {length} cannot be smaller than chord {chord}")
        if abs(length - chord) < 1e-7:
            # Degenerate straight line
            radius = float("inf")
            delta_deg = 0.0
        else:
            # Solve sin(theta)/theta = chord / length for theta = delta_rad / 2
            ratio = chord / length
            # Taylor approximation as initial guess: sin(theta)/theta ~ 1 - theta^2/6
            theta = math.sqrt(max(0.0, 6.0 * (1.0 - ratio)))
            if theta == 0.0:
                theta = 0.1
            # Newton-Raphson on f(theta) = sin(theta) - ratio * theta = 0
            for _ in range(25):
                f_val = math.sin(theta) - ratio * theta
                f_prime = math.cos(theta) - ratio
                if abs(f_prime) < 1e-12:
                    break
                d_theta = f_val / f_prime
                theta -= d_theta
                if abs(d_theta) < 1e-12:
                    break
            delta_rad = 2.0 * theta
            delta_deg = math.degrees(delta_rad)
            radius = length / delta_rad
    else:
        raise ValueError("Could not solve curve with provided parameters")

    return dict(radius=radius, length=length, delta_deg=delta_deg, chord=chord)

