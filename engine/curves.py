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
    """Solve for missing curve parameter given any two of radius/length/delta/chord."""
    have = {k: v for k, v in dict(radius=radius, length=length,
                                   delta_deg=delta_deg, chord=chord).items() if v is not None}
    if "radius" in have and "delta_deg" in have:
        radius = have["radius"]; delta_deg = have["delta_deg"]
        length = radius * math.radians(delta_deg)
        chord = 2 * radius * math.sin(math.radians(delta_deg) / 2)
    elif "radius" in have and "length" in have:
        radius = have["radius"]; length = have["length"]
        delta_deg = math.degrees(length / radius)
        chord = 2 * radius * math.sin(math.radians(delta_deg) / 2)
    elif "length" in have and "delta_deg" in have:
        length = have["length"]; delta_deg = have["delta_deg"]
        radius = length / math.radians(delta_deg)
        chord = 2 * radius * math.sin(math.radians(delta_deg) / 2)
    else:
        raise ValueError("Need at least radius+delta, radius+length, or length+delta")
    return dict(radius=radius, length=length, delta_deg=delta_deg, chord=chord)
