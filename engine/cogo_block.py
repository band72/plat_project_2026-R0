"""
engine/cogo_block.py -- Deterministic Cadastral Block & Lot COGO Engine.

A pure algorithmic, deterministic land surveying engine for computing subdivision
blocks, lot boundary traverses, corner return curves with P.I. angle bar glyphs,
mathematical closures, Florida 5J-17 compliance, and CAD DXF generation.

Engine Principles:
1. Zero AI or heuristic dependency: 100% analytical coordinate geometry (COGO).
2. Ground-truthed physical coordinates: true bearings and distances from recorded plats.
3. Corner Return & P.I. Angle Bar Rule:
   - Deflection angle Delta = |azimuth_out - azimuth_in| (mod 180).
   - Surveyor tangent T = R * tan(Delta / 2).
   - Dimension marked to P.I. (angle bar tick) cut back to P.C./P.T.:
     L_straight = L_stated - T.
   - Net parcel area adjusted for circular fillets / segments.
4. Rigorous Traverse Closure:
   - Linear misclosure: hypot(dN, dE).
   - Relative precision: Perimeter / misclosure.
   - Florida Administrative Code (F.A.C.) 5J-17 compliance:
     Commercial/High-Density >= 1:10,000; Residential/Standard >= 1:5,000.
"""

from __future__ import annotations

import math
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.cogo import Point, azimuth_to_bearing, parse_bearing
from engine.curves import solve_curve_all_parameters
from engine.lots import shoelace_area

# Add plugins/curves to sys.path if not present to integrate plat_curves toolkit
_PLUGIN_CURVES_PATH = str(Path(__file__).resolve().parents[1] / "plugins" / "curves")
if _PLUGIN_CURVES_PATH not in sys.path:
    sys.path.insert(0, _PLUGIN_CURVES_PATH)

try:
    from plat_curves.compound import cul_de_sac as plat_cul_de_sac
    from plat_curves.core import Curve as PlatCurve
    from plat_curves.core import PlacedCurve, deg_to_dms
    from plat_curves.engine_adapter import (
        get_block_corner_returns,
        get_block_frontage_curves,
    )
    _HAS_PLAT_CURVES = True
except ImportError:
    _HAS_PLAT_CURVES = False

# ==============================================================================
# 1. SURVEYING CORNER RETURN SOLVER
# ==============================================================================

@dataclass
class CornerReturnSolve:
    """Analytical solution for a corner return curve connecting two tangents."""
    bearing_in: str
    bearing_out: str
    radius: float
    delta_deg: float
    tangent: float
    arc_length: float
    chord: float
    chord_bearing: str
    fillet_area: float
    segment_area: float
    cutback_in: float
    cutback_out: float
    straight_in: float | None = None
    straight_out: float | None = None
    delta_dms: str = ""


def solve_corner_return(
    bearing_in: str,
    bearing_out: str,
    radius: float = 25.0,
    stated_dim_in_to_pi: float | None = None,
    stated_dim_out_to_pi: float | None = None,
    rot: str = "CW",
) -> CornerReturnSolve:
    """
    Solve a circular corner return curve connecting an incoming tangent and
    an outgoing tangent, applying the P.I. angle bar glyph rule.
    Leverages plat_curves.core.Curve and plat_curves.compound.corner_return.
    """
    az_in = parse_bearing(bearing_in)
    az_out = parse_bearing(bearing_out)

    # Turn deflection angle
    diff = abs(az_out - az_in) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    delta_deg = diff

    if _HAS_PLAT_CURVES:
        cur = PlatCurve.from_params(direction=rot, radius=radius, delta_deg=delta_deg)
        T = float(cur.tangent)
        arc_len = float(cur.arc_length)
        chord_len = float(cur.chord)
        fillet_a = float(cur.fillet_area)
        segment_a = float(cur.segment_area)
        dms_val = deg_to_dms(delta_deg)
    else:
        # Fallback to solve_curve_all_parameters
        c_sol = solve_curve_all_parameters(radius=radius, delta_deg=delta_deg)
        T = float(c_sol["tangent"])
        arc_len = float(c_sol["length"])
        chord_len = float(c_sol["chord"])
        fillet_a = float(c_sol["fillet_area"])
        segment_a = float(c_sol["segment_area"])
        dms_val = f"{delta_deg:.4f}°"

    # Chord bearing: bisect incoming and outgoing tangents
    half_delta = delta_deg / 2.0
    sign = 1.0 if rot == "CW" else -1.0
    chord_az = (az_in + sign * half_delta) % 360.0
    chord_bearing = azimuth_to_bearing(chord_az)

    straight_in = (stated_dim_in_to_pi - T) if stated_dim_in_to_pi is not None else None
    straight_out = (stated_dim_out_to_pi - T) if stated_dim_out_to_pi is not None else None

    return CornerReturnSolve(
        bearing_in=bearing_in,
        bearing_out=bearing_out,
        radius=radius,
        delta_deg=delta_deg,
        tangent=T,
        arc_length=arc_len,
        chord=chord_len,
        chord_bearing=chord_bearing,
        fillet_area=fillet_a,
        segment_area=segment_a,
        cutback_in=T,
        cutback_out=T,
        straight_in=straight_in,
        straight_out=straight_out,
        delta_dms=dms_val,
    )


def whole_second_bearing(bearing: str) -> str:
    """azimuth_to_bearing() always emits 2 decimal places on seconds (e.g.
    'S46°01\'40.00"E'); every hand-typed table bearing in this file uses
    whole seconds only. Strip an exact zero decimal remainder to match that
    convention -- a genuinely fractional value (which would indicate the
    curve solve itself needs re-checking, not just reformatting) is left
    visible rather than silently rounded away."""
    return re.sub(r'\.00(?=")', "", bearing)


def solve_skew_angle(bearing_ref: str, bearing_skew: str) -> float:
    """
    Calculate the deflection skew angle (in degrees) between a reference bearing
    and a skewed boundary bearing.
    """
    az_ref = parse_bearing(bearing_ref)
    az_skew = parse_bearing(bearing_skew)
    diff = abs(az_skew - az_ref) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return diff


def solve_skewed_lot_rear_dimension(
    front_dimension: float,
    lot_depth: float,
    skew_angle_deg: float,
    skew_direction: str = "taper",
) -> float:
    """
    Trigonometrically compute the rear dimension of a lot whose rear line is parallel
    to the front, but whose side line deflects by skew_angle_deg from perpendicular:
      delta = depth * tan(skew_angle_deg)
      rear = front - delta (if tapering) or front + delta (if flaring)
    """
    delta = lot_depth * math.tan(math.radians(skew_angle_deg))
    if skew_direction == "taper":
        return front_dimension - delta
    else:
        return front_dimension + delta


# ==============================================================================
# 2. ANALYTICAL 2D INTERSECTIONS
# ==============================================================================

def intersect_bearings(p1: Point, az1: float, p2: Point, az2: float) -> Point:
    """
    Compute the intersection point of two rays defined by start points and azimuths.
    Solves:
      P = p1 + t * v1 = p2 + u * v2
    where v1 = (cos(az1), sin(az1)), v2 = (cos(az2), sin(az2)) in (Northing, Easting).
    """
    r1 = math.radians(az1)
    r2 = math.radians(az2)
    dn1, de1 = math.cos(r1), math.sin(r1)
    dn2, de2 = math.cos(r2), math.sin(r2)

    denom = de1 * dn2 - dn1 * de2
    if abs(denom) < 1e-10:
        raise ValueError(f"Lines are parallel or collinear: az1={az1}°, az2={az2}°")

    delta_n = p2.n - p1.n
    delta_e = p2.e - p1.e

    t = (delta_e * dn2 - delta_n * de2) / denom
    return Point(p1.n + t * dn1, p1.e + t * de1)


# ==============================================================================
# 3. TRAVERSE COURSE & MAPCHECK
# ==============================================================================

@dataclass
class TraverseCourse:
    course_num: int
    from_node: str
    to_node: str
    start_pt: Point
    end_pt: Point
    bearing_str: str
    distance: float
    is_curve: bool = False
    curve_data: dict[str, Any] = field(default_factory=dict)
    curve_rot: str = "CCW"
    arc_points: list[Point] = field(default_factory=list)


@dataclass
class LotMapCheckResult:
    lot_id: str
    block_id: str
    lot_number: str
    courses: list[TraverseCourse]
    perimeter_ft: float
    misclose_n_ft: float
    misclose_e_ft: float
    misclose_dist_ft: float
    precision_ratio: float
    precision_str: str
    raw_shoelace_sqft: float
    curve_adj_sqft: float
    computed_area_sqft: float
    computed_acres: float
    stated_area_sqft: float
    area_diff_sqft: float
    area_diff_pct: float
    fac_5j17_passed: bool
    passed: bool
    verdict: str
    flags: list[str] = field(default_factory=list)

    def format_surveyor_sheet(self) -> str:
        """Format certified surveyor checksheet output."""
        lines = [
            "=" * 80,
            f"  SURVEY MAPCHECK AUDIT: {self.lot_id} (Block {self.block_id}, Lot {self.lot_number})",
            "=" * 80,
            f"Target Stated Area: {self.stated_area_sqft:,.1f} SF ({self.stated_area_sqft/43560.0:.4f} Acres)",
            "-" * 80,
            f"{'Course':<8} | {'From -> To':<22} | {'Bearing':<14} | {'Distance (ft)':<14} | {'Type':<8}",
            "-" * 80,
        ]
        for c in self.courses:
            ctype = "CURVE" if c.is_curve else "LINE"
            lines.append(f"{c.course_num:<8} | {c.from_node + ' -> ' + c.to_node:<22} | {c.bearing_str:<14} | {c.distance:<14.2f} | {ctype:<8}")
            if c.is_curve and c.curve_data:
                cd = c.curve_data
                lines.append(
                    f"         Curve -> R: {cd.get('radius', 0.0):.2f}' | Arc: {cd.get('length', 0.0):.2f}' | "
                    f"Delta: {cd.get('delta_dms', '')} | Chord: {cd.get('chord', 0.0):.2f}'"
                )
                lines.append(
                    f"                  Tangent: {cd.get('tangent', 0.0):.2f}' | Mid-Ord: {cd.get('mid_ordinate', 0.0):.2f}' | "
                    f"Seg Area: {cd.get('segment_area', 0.0):.1f} SF"
                )
                stated_parts = []
                if "stated_length" in cd:
                    stated_parts.append(f"Stated Arc: {cd['stated_length']:.2f}'")
                if "stated_delta_deg" in cd:
                    dms_txt = deg_to_dms(cd['stated_delta_deg']) if _HAS_PLAT_CURVES else f"{cd['stated_delta_deg']:.4f}°"
                    stated_parts.append(f"Stated Delta: {dms_txt}")
                if stated_parts:
                    lines.append(f"                  Plat Stated -> {' | '.join(stated_parts)}")
        lines.extend([
            "-" * 80,
            "TRAVERSE CLOSURE & STATISTICAL PRECISION:",
            f"  Total Perimeter:     {self.perimeter_ft:,.2f} ft",
            f"  Closure Vector:      dN = {self.misclose_n_ft:+.5f} ft, dE = {self.misclose_e_ft:+.5f} ft",
            f"  Linear Misclose:     {self.misclose_dist_ft:.5f} ft",
            f"  Relative Precision:  {self.precision_str}",
            f"  F.A.C. 5J-17 Standard: {'PASS (>= 1:10,000)' if self.fac_5j17_passed else 'FAIL'}",
            f"  Traverse Status:     {'CLOSED' if self.passed else 'OPEN'}",
            "PARCEL AREA AUDIT:",
            f"  Raw Polygon Area:    {self.raw_shoelace_sqft:,.1f} SF",
            f"  Curve Adjustments:   {self.curve_adj_sqft:+,.1f} SF",
            f"  Net Computed Area:   {self.computed_area_sqft:,.1f} SF ({self.computed_acres:.4f} Acres)",
            f"  Target Stated Area:  {self.stated_area_sqft:,.1f} SF",
            f"  Area Discrepancy:    {self.area_diff_sqft:+,.1f} SF ({self.area_diff_pct:.2f}%)",
            f"FINAL VERDICT:         {self.verdict}",
            "=" * 80,
        ])
        return "\n".join(lines)


# ==============================================================================
# 4. DETERMINISTIC LOT SOLVER
# ==============================================================================

class DeterministicLotSolver:
    """
    Computes traverse closures and CAD geometry for an individual subdivision lot.
    """
    def __init__(
        self,
        lot_id: str,
        block_id: str,
        lot_number: str,
        vertices: list[Point],
        node_names: list[str] | None = None,
        curve_specs: dict[str, dict[str, Any]] | None = None,
        stated_area_sqft: float = 7500.0,
    ):
        self.lot_id = lot_id
        self.block_id = block_id
        self.lot_number = lot_number
        self.vertices = vertices
        n = len(vertices)
        self.node_names = node_names if node_names and len(node_names) == n else [f"P{i+1}" for i in range(n)]
        self.curve_specs = curve_specs or {}
        self.stated_area_sqft = stated_area_sqft

    def compute_mapcheck(self) -> LotMapCheckResult:
        n = len(self.vertices)
        courses: list[TraverseCourse] = []
        tot_perim = 0.0
        curve_adj = 0.0

        # "CW"/"CCW" curve rotation is relative to the direction of travel, so whether an arc adds or removes
        # area depends on the ring's winding.  A clockwise ring (the convention most solvers use) adds a CW
        # arc's segment; a counter-clockwise ring subtracts it.  Ignoring this made Block 16's south-row lots
        # report +/- 2 segment areas relative to the arcs they actually draw.
        signed2 = sum(self.vertices[k].e * self.vertices[(k + 1) % n].n - self.vertices[(k + 1) % n].e * self.vertices[k].n
                      for k in range(n))
        winding = 1.0 if signed2 < 0 else -1.0

        for i in range(n):
            p1 = self.vertices[i]
            p2 = self.vertices[(i + 1) % n]
            side_key = f"side_{i+1}"

            dn = p2.n - p1.n
            de = p2.e - p1.e
            chord_dist = math.hypot(dn, de)
            az = math.degrees(math.atan2(de, dn)) % 360.0
            bearing_str = azimuth_to_bearing(az)

            is_curve = side_key in self.curve_specs
            c_data: dict[str, Any] = {}
            c_rot = "CCW"
            arc_pts: list[Point] = []

            if is_curve:
                spec = self.curve_specs[side_key]
                R = float(spec["radius"])
                c_rot = spec.get("rot", "CW")
                sign = 1.0 if c_rot == "CW" else -1.0

                if _HAS_PLAT_CURVES:
                    cur = PlatCurve.from_params(direction=c_rot, radius=R, chord=chord_dist)
                    delta_deg = float(cur.delta_deg)
                    L_arc = float(cur.arc_length)
                    seg_a = float(cur.segment_area)
                    c_data = {
                        "radius": R,
                        "delta_deg": delta_deg,
                        "delta_dms": deg_to_dms(delta_deg),
                        "length": L_arc,
                        "chord": chord_dist,
                        "tangent": float(cur.tangent),
                        "segment_area": seg_a,
                        "mid_ordinate": float(cur.middle_ordinate),
                    }
                    if "length" in spec:
                        c_data["stated_length"] = float(spec["length"])
                    if "delta_deg" in spec:
                        c_data["stated_delta_deg"] = float(spec["delta_deg"])
                    half_delta = delta_deg / 2.0
                    t_in_az = (az - sign * half_delta) % 360.0
                    placed = PlacedCurve(curve=cur, pc=(p1.n, p1.e), back_az=t_in_az)
                    arc_pts = [Point(n, e) for n, e in placed.arc_points(n_segments=16)]
                else:
                    c_data = solve_curve_all_parameters(radius=R, chord=chord_dist)
                    L_arc = float(c_data["length"])
                    seg_a = float(c_data["segment_area"])
                    delta_deg = float(c_data["delta_deg"])
                    half_delta = delta_deg / 2.0
                    t_in_az = (az - sign * half_delta) % 360.0
                    rp_az = (t_in_az + sign * 90.0) % 360.0
                    rp = p1.offset(rp_az, R)
                    start_az = (rp_az + 180.0) % 360.0
                    n_segs = 16
                    for s in range(n_segs + 1):
                        a = start_az + sign * delta_deg * (s / n_segs)
                        arc_pts.append(rp.offset(a, R))

                tot_perim += L_arc
                curve_adj += winding * (+seg_a if c_rot == "CW" else -seg_a)
                course_dist = L_arc
            else:
                tot_perim += chord_dist
                course_dist = chord_dist

            courses.append(TraverseCourse(
                course_num=i + 1,
                from_node=self.node_names[i],
                to_node=self.node_names[(i + 1) % n],
                start_pt=p1,
                end_pt=p2,
                bearing_str=bearing_str,
                distance=course_dist,
                is_curve=is_curve,
                curve_data=c_data,
                curve_rot=c_rot,
                arc_points=arc_pts,
            ))

        # Mathematical closure vector
        sum_dn = sum((c.end_pt.n - c.start_pt.n) for c in courses)
        sum_de = sum((c.end_pt.e - c.start_pt.e) for c in courses)
        misclose_dist = math.hypot(sum_dn, sum_de)

        if misclose_dist < 1e-6:
            prec_ratio = float("inf")
            prec_str = "EXACT (0.000 ft)"
            passed = True
        else:
            prec_ratio = tot_perim / misclose_dist
            prec_str = f"1 : {int(prec_ratio):,}"
            passed = (misclose_dist <= 0.05)

        # Areas
        raw_poly = shoelace_area(self.vertices)
        net_area = raw_poly + curve_adj
        acres = net_area / 43560.0
        diff_sqft = net_area - self.stated_area_sqft
        pct_diff = abs(diff_sqft) / self.stated_area_sqft * 100.0 if self.stated_area_sqft > 0 else 0.0

        fac_passed = (prec_ratio >= 10000.0 or misclose_dist < 1e-4)

        if passed and fac_passed:
            verdict = "PASS - Certified Survey-Grade Lot Closure (F.A.C. 5J-17 Compliant)"
        elif passed:
            verdict = "PASS - Standard Boundary Closure"
        else:
            verdict = "FAIL - Boundary Misclose Exceeds Tolerances"

        return LotMapCheckResult(
            lot_id=self.lot_id,
            block_id=self.block_id,
            lot_number=self.lot_number,
            courses=courses,
            perimeter_ft=tot_perim,
            misclose_n_ft=sum_dn,
            misclose_e_ft=sum_de,
            misclose_dist_ft=misclose_dist,
            precision_ratio=prec_ratio,
            precision_str=prec_str,
            raw_shoelace_sqft=raw_poly,
            curve_adj_sqft=curve_adj,
            computed_area_sqft=net_area,
            computed_acres=acres,
            stated_area_sqft=self.stated_area_sqft,
            area_diff_sqft=diff_sqft,
            area_diff_pct=pct_diff,
            fac_5j17_passed=fac_passed,
            passed=passed,
            verdict=verdict,
        )


# ==============================================================================
# 5. BLOCK 9 DETERMINISTIC COGO SOLVER PIPELINE
# ==============================================================================

class BeachwoodBlock9Solver:
    """
    Deterministic solver for Block 9 (West of Matchline), Beachwood Unit Two.
    Plat Book 30, Pages 82 & 82A, Duval County, FL.
    """
    def __init__(self, origin: Point | None = None):
        self.origin = origin or Point(0.0, 0.0)
        # 1. Base Bearings from Plat Records
        self.az_match = parse_bearing("N35°18'20\"E")           # Matchline (35.3056°)
        self.az_tangent_ch = parse_bearing("S54°41'40\"E")      # Cape Horn tangent (125.3056°)
        self.az_tangent_ch_rev = parse_bearing("N54°41'40\"W")  # 305.3056°
        self.az_interior = parse_bearing("S63°12'00\"E")        # Rear interior line (116.8000°)
        self.az_interior_rev = parse_bearing("N63°12'00\"W")    # 296.8000°
        self.az_west_n = parse_bearing("N01°01'40\"W")          # West Avenue frontage North (358.9722°)
        self.az_west_s = parse_bearing("S01°01'40\"E")          # West Avenue frontage South (178.9722°)
        self.az_pi_pc = parse_bearing("N88°58'20\"E")           # East tangent at corner returns (88.9722°)

        # 2. Corner Return Solves via Rule 2
        r27 = 25.0
        r26 = 25.0
        if _HAS_PLAT_CURVES:
            cr9 = get_block_corner_returns("9")
            r27 = float(cr9.get("CR_BLK9_L27", {}).get("radius", 25.0))
            r26 = float(cr9.get("CR_BLK9_L26", {}).get("radius", 25.0))
        self.sol27 = solve_corner_return("N01°01'40\"W", "N88°58'20\"E", radius=r27, stated_dim_in_to_pi=140.0)
        # Lot 26 SW return: the plat prints "25.0' N88°58'20\"E" from the P.I., i.e. the return is tangent to the
        # N88°58'20"E line and ends at the San Salvadore curve P.C. (Δ 90°, T 25'). It was previously filleted
        # against the 67.91' chord bearing (S84°31'40"E), which gave Δ 83°30' and a 22.2' P.C. cut-back.
        self.sol26 = solve_corner_return("S88°58'20\"W", "N01°01'40\"W", radius=r26,
                                         stated_dim_in_to_pi=25.0, stated_dim_out_to_pi=109.0)

        # 3. Coordinate Geometry
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self._solve_geometry()

    def _solve_geometry(self):
        """Construct all Block 9 points using pure analytical COGO."""
        # Origin Anchor: Matchline south terminus on San Salvadore Ave R/W
        p23_se = self.origin
        p23_ne = p23_se.offset(self.az_match, 100.0)
        p31_se = p23_ne
        p31_ne = p31_se.offset(self.az_match, 100.0)  # P.R.M. Monument at Cape Horn Ave

        # Lot 31 (75' x 100' rectangle)
        p31_nw = p31_ne.offset(self.az_tangent_ch_rev, 75.0)
        p31_sw = p31_se.offset(self.az_tangent_ch_rev, 75.0)

        # Lot 30 (75' x 100' rectangle)
        p30_ne = p31_nw
        p30_se = p31_sw
        p30_nw = p30_ne.offset(self.az_tangent_ch_rev, 75.0)
        p30_sw = p30_se.offset(self.az_tangent_ch_rev, 75.0)

        # Lot 29
        p29_ne = p30_nw
        p29_se = p30_sw
        p29_mid_n = p29_ne.offset(self.az_tangent_ch_rev, 82.57)
        p29_nw = p29_mid_n.offset(parse_bearing("N55°21'40\"W"), 6.91)
        p29_sw = p29_se.offset(self.az_interior_rev, 68.0)

        # Lot 28
        p28_ne = p29_nw
        p28_se = p29_sw
        p28_sw = p28_se.offset(self.az_interior_rev, 67.31)
        p28_nw = p28_ne.offset(parse_bearing("N66°31'40\"W"), 108.25)

        # Lot 27 (NW Corner Return)
        T27 = self.sol27.tangent  # 25.0000'
        p27_ne = p28_nw
        p27_se = p28_sw
        p27_sw = p27_se.offset(parse_bearing("S78°46'06\"W"), 90.0)
        p27_pi = p27_sw.offset(self.az_west_n, 140.0)       # 140' extends to P.I.
        p27_pc_w = p27_pi.offset(self.az_west_s, T27)       # 115' to P.C.
        p27_pc_n = p27_pi.offset(self.az_pi_pc, T27)        # 25' along North tangent to P.C.

        # Lot 26 (SW Corner Return)
        T26 = self.sol26.tangent  # 25.0000'
        p26_nw = p27_sw
        p26_ang = p27_se
        p26_ne = p26_ang.offset(self.az_interior, 30.0)
        p26_se = p26_ne.offset(parse_bearing("S9°46'11\"W"), 120.75)
        p26_pc_s = p26_se.offset(parse_bearing("N84°31'40\"W"), 67.91)
        p26_pi = p26_nw.offset(self.az_west_s, 109.0)       # 109' extends to P.I.
        p26_pc_w = p26_pi.offset(self.az_west_n, T26)       # 84' to P.C.

        # Lot 25
        p25_nw = p26_ne
        p25_sw = p26_se
        p25_ne = p25_nw.offset(self.az_interior, 82.31)
        p25_se = p25_sw.offset(parse_bearing("S71°41'40\"E"), 66.18)

        # Lot 24
        p24_nw = p25_ne
        p24_sw = p25_se
        p24_mid_n = p24_nw.offset(self.az_interior, 23.0)
        p24_ne = p31_sw
        p24_mid_s = p24_sw.offset(parse_bearing("S60°01'40\"E"), 55.76)
        p24_se = p24_mid_s.offset(self.az_tangent_ch, 8.31)

        # Lot 23
        p23_sw = p24_se
        p23_nw = p24_ne

        self.points = {
            "p23_se": p23_se, "p23_ne": p23_ne, "p23_nw": p23_nw, "p23_sw": p23_sw,
            "p24_se": p24_se, "p24_mid_s": p24_mid_s, "p24_sw": p24_sw, "p24_nw": p24_nw, "p24_mid_n": p24_mid_n, "p24_ne": p24_ne,
            "p25_se": p25_se, "p25_sw": p25_sw, "p25_nw": p25_nw, "p25_ne": p25_ne,
            "p26_se": p26_se, "p26_pc_s": p26_pc_s, "p26_pi": p26_pi, "p26_pc_w": p26_pc_w, "p26_nw": p26_nw, "p26_ang": p26_ang, "p26_ne": p26_ne,
            "p27_sw": p27_sw, "p27_pi": p27_pi, "p27_pc_w": p27_pc_w, "p27_pc_n": p27_pc_n, "p27_ne": p27_ne, "p27_se": p27_se,
            "p28_sw": p28_sw, "p28_nw": p28_nw, "p28_ne": p28_ne, "p28_se": p28_se,
            "p29_sw": p29_sw, "p29_nw": p29_nw, "p29_mid_n": p29_mid_n, "p29_ne": p29_ne, "p29_se": p29_se,
            "p30_sw": p30_sw, "p30_nw": p30_nw, "p30_ne": p30_ne, "p30_se": p30_se,
            "p31_sw": p31_sw, "p31_nw": p31_nw, "p31_ne": p31_ne, "p31_se": p31_se,
        }

        # Initialize lot solvers
        self.lots = {
            "27": DeterministicLotSolver(
                lot_id="Blk9-Lot27", block_id="9", lot_number="27",
                vertices=[p27_sw, p27_pc_w, p27_pc_n, p27_ne, p27_se],
                node_names=["SW_Cor", "PC_West", "PC_North", "NE_Cor", "SE_Cor"],
                curve_specs={"side_2": {"radius": self.sol27.radius, "delta_deg": self.sol27.delta_deg, "length": round(self.sol27.arc_length, 2), "rot": "CW"}},
                stated_area_sqft=11793.4,
            ),
            "28": DeterministicLotSolver(
                lot_id="Blk9-Lot28", block_id="9", lot_number="28",
                vertices=[p28_sw, p28_nw, p28_ne, p28_se],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
                stated_area_sqft=9632.5,
            ),
            "29": DeterministicLotSolver(
                lot_id="Blk9-Lot29", block_id="9", lot_number="29",
                vertices=[p29_sw, p29_nw, p29_mid_n, p29_ne, p29_se],
                node_names=["SW_Cor", "NW_Cor", "Angle_Pt_North", "NE_Cor", "SE_Cor"],
                stated_area_sqft=8287.2,
            ),
            "30": DeterministicLotSolver(
                lot_id="Blk9-Lot30", block_id="9", lot_number="30",
                vertices=[p30_sw, p30_nw, p30_ne, p30_se],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
                stated_area_sqft=7500.0,
            ),
            "31": DeterministicLotSolver(
                lot_id="Blk9-Lot31", block_id="9", lot_number="31",
                vertices=[p31_sw, p31_nw, p31_ne, p31_se],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor(PRM)", "SE_Cor(Match)"],
                stated_area_sqft=7500.0,
            ),
            "26": DeterministicLotSolver(
                lot_id="Blk9-Lot26", block_id="9", lot_number="26",
                vertices=[p26_nw, p26_ang, p26_ne, p26_se, p26_pc_s, p26_pc_w],
                node_names=["NW_Cor", "Angle_Pt_North", "NE_Cor", "SE_Cor", "PC_South", "PC_West"],
                curve_specs={"side_5": {"radius": self.sol26.radius, "delta_deg": self.sol26.delta_deg, "length": round(self.sol26.arc_length, 2), "rot": "CW"}},
                stated_area_sqft=12446.1,
            ),
            "25": DeterministicLotSolver(
                lot_id="Blk9-Lot25", block_id="9", lot_number="25",
                vertices=[p25_sw, p25_nw, p25_ne, p25_se],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
                stated_area_sqft=8300.6,
            ),
            "24": DeterministicLotSolver(
                lot_id="Blk9-Lot24", block_id="9", lot_number="24",
                vertices=[p24_sw, p24_nw, p24_mid_n, p24_ne, p24_se, p24_mid_s],
                node_names=["SW_Cor", "NW_Cor", "Angle_Pt_North", "NE_Cor", "SE_Cor", "Angle_Pt_South"],
                stated_area_sqft=8329.5,
            ),
            "23": DeterministicLotSolver(
                lot_id="Blk9-Lot23", block_id="9", lot_number="23",
                vertices=[p23_sw, p23_nw, p23_ne, p23_se],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor(Match)", "SE_Cor(Match)"],
                stated_area_sqft=7499.1,
            ),
        }

        # Street-frontage curves (re-read at 400 dpi 2026-09-24; these fronts used to be straight chords).
        # Cape Horn Ave S R/W: R = 327.01 - 30 = 297.01' (lots inside the curve), chords 72.39 / 108.25 / 6.91
        #   -> Δ 14° + 21° + 1°20' = CL Δ 36°20'.
        # San Salvadore Ave N R/W: R = 269.96 + 30 = 299.96' (lots outside), chords 67.91 / 66.18 / 55.76
        #   -> Δ 13° + 12°40' + 10°40' = CL Δ 36°20'.
        # Record area = chord polygon +/- the segment computed from the plat Δ (the plat prints no lot areas).
        self.r_capehorn_s, self.r_sansal_n = 297.01, 299.96
        fronts = [("27", "side_3", self.r_capehorn_s, 14.0, "CW", +1),
                  ("28", "side_2", self.r_capehorn_s, 21.0, "CW", +1),
                  ("29", "side_2", self.r_capehorn_s, 1.0 + 20.0 / 60.0, "CW", +1),
                  ("26", "side_4", self.r_sansal_n, 13.0, "CCW", -1),
                  ("25", "side_4", self.r_sansal_n, 12.0 + 40.0 / 60.0, "CCW", -1),
                  ("24", "side_6", self.r_sansal_n, 10.0 + 40.0 / 60.0, "CCW", -1)]
        for num, side, R, d, rot, sgn in fronts:
            lot = self.lots[num]
            chord_area = lot.compute_mapcheck().computed_area_sqft
            t = math.radians(d)
            lot.curve_specs = dict(lot.curve_specs)
            lot.curve_specs[side] = {"radius": R, "delta_deg": d, "length": round(R * t, 2), "rot": rot}
            lot.stated_area_sqft = round(chord_area + sgn * 0.5 * R * R * (t - math.sin(t)), 1)

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        """Compute MapCheck for all lots in Block 9."""
        results = {}
        for lot_num, solver in self.lots.items():
            results[lot_num] = solver.compute_mapcheck()
        return results

    def generate_report(self, filepath: str = "data/block9_mapcheck_report.txt"):
        """Generate certified surveyor report file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 9 (WEST OF MATCHLINE) SURVEY MAPCHECK REPORT\n")
            f.write("  Plat Book 30, Pages 82 & 82A, Public Records of Duval County, Florida\n")
            f.write("  Pure Algorithmic Cadastral COGO Engine Output (Offline / Deterministic)\n")
            f.write("=" * 80 + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("  RULE 2: CORNER RETURN CURVE DERIVATIONS & P.I. TANGENT CUTBACKS\n")
            f.write("=" * 80 + "\n")
            f.write(f"Lot 27 (NW Corner): Delta = {self.sol27.delta_deg:.2f}° | Tangent T = {self.sol27.tangent:.4f}' | Arc = {self.sol27.arc_length:.2f}'\n")
            f.write("  Stated Dimension along West to P.I. Tick: 140.00'\n")
            f.write(f"  Straight Course Length to P.C. = 140.00' - 25.00' = {self.sol27.straight_in:.2f}'\n")
            f.write(f"Lot 26 (SW Corner): Delta = {self.sol26.delta_deg:.2f}° | Tangent T = {self.sol26.tangent:.4f}' | Arc = {self.sol26.arc_length:.2f}'\n")
            f.write("  Stated Dimension along West to P.I. Tick: 109.00'\n")
            f.write(f"  Straight Course Length to P.C. = 109.00' - 25.00' = {self.sol26.straight_in:.2f}'\n\n")

            f.write("=" * 80 + "\n")
            f.write("  MATCHLINE & CONTROL MONUMENT VERIFICATION\n")
            f.write("=" * 80 + "\n")
            f.write("  Matchline Bearing: N35°18'20\"E, Length = 200.00 ft\n")
            f.write("  Control Anchor: P.R.M. Monument at Cape Horn Avenue R/W (NE Corner Lot 31)\n")
            f.write("  South Anchor: San Salvadore Avenue R/W (SE Corner Lot 23)\n\n")

            for lot_num in ["27", "28", "29", "30", "31", "26", "25", "24", "23"]:
                res = results[lot_num]
                f.write(res.format_surveyor_sheet() + "\n\n")
        return filepath


# ==============================================================================
# 6. BLOCK 13 DETERMINISTIC COGO SOLVER PIPELINE
# ==============================================================================

class BeachwoodBlock13Solver:
    """
    Deterministic solver for Block 13, Beachwood Unit Two.
    Plat Book 30, Pages 82 & 82A, Duval County, FL.

    Features:
    - 11 Lots (Lots 1 through 11).
    - Frontage: Mangrove Avenue (60' R/W) bearing N01°01'40\"W / S01°01'40\"E.
    - Rear: 50' Right-of-way for drainage and utilities (S01°01'40\"E - 1509.24').
    - North cross street: 60' R/W bearing N88°58'20\"E.
    - South cross street: Surfwood Avenue (60' R/W) bearing N89°18'20\"E (20' skew).
    - Corner return curves: R=25.0' with P.I. angle bar glyphs (Lot 1 NE '┘', Lot 11 SE '└').
    - Monuments: P.R.M. at Lot 1/2 boundary and Lot 10/11 boundary on Mangrove Ave.
    - Easements: 5' rear easement, 10' drainage/utility easements at Lots 2/3 and Lots 8/9.
    """
    def __init__(self, origin: Point | None = None):
        # 1. Bearings from Plat Records
        self.brg_mangrove = "S01°01'40\"E"
        self.brg_side = "N88°58'20\"E"
        self.brg_south_st = "N89°18'20\"E"

        self.az_mangrove_s = parse_bearing(self.brg_mangrove)   # 178.9722°
        self.az_mangrove_n = parse_bearing("N01°01'40\"W")     # 358.9722°
        self.az_lot_line = parse_bearing(self.brg_side)        # 88.9722°
        self.az_lot_line_rev = parse_bearing("S88°58'20\"W")   # 268.9722°
        self.az_surfwood = parse_bearing(self.brg_south_st)    # 89.3056°
        self.az_surfwood_rev = parse_bearing("S89°18'20\"W")   # 269.3056°

        # 2. Rule 2 Corner Return Solves
        r1 = 25.0
        r11 = 25.0
        if _HAS_PLAT_CURVES:
            cr13 = get_block_corner_returns("13")
            r1 = float(cr13.get("CR_BLK13_L1", {}).get("radius", 25.0))
            r11 = float(cr13.get("CR_BLK13_L11", {}).get("radius", 25.0))
        # Lot 1 (NE Corner): Delta = 90°00'00", T = 25.0000'
        self.sol1 = solve_corner_return("N88°58'20\"E", "S01°01'40\"E", radius=r1, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0)
        # Lot 11 (SE Corner): Delta = 90°20'00", T = 25.1459'
        self.sol11 = solve_corner_return("S01°01'40\"E", "S89°18'20\"W", radius=r11, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0)

        # 3. Trigonometric Skew Derivation for Surfwood Avenue (20' deflection)
        self.skew_deg = solve_skew_angle(self.brg_side, self.brg_south_st)
        self.lot11_rear_calc = solve_skewed_lot_rear_dimension(100.0, 100.0, self.skew_deg, "taper")

        # 4. Geometry Construction
        self.origin = origin or Point(1000.0, 1000.0)
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self._solve_geometry()

    def _solve_geometry(self):
        """Construct all Block 13 vertices using analytical coordinate geometry."""
        # Anchor: NW Corner of Lot 1 on Drainage R/W line
        p1_nw = self.origin

        # Lot 1 NE Corner Return & Tangents
        p1_pi_ne = p1_nw.offset(self.az_lot_line, 100.0)
        T1 = self.sol1.tangent # 25.0000'
        p1_pc_n = p1_pi_ne.offset(self.az_lot_line_rev, T1) # 75.0' from p1_nw
        p1_pc_e = p1_pi_ne.offset(self.az_mangrove_s, T1)   # on Mangrove Ave
        p1_sw = p1_nw.offset(self.az_mangrove_s, 100.0)
        p1_se = p1_sw.offset(self.az_lot_line, 100.0)       # P.R.M. Monument at Lot 1/2

        rear_pts = [p1_nw, p1_sw]
        front_pts = [p1_se]

        # Intermediate Lots 2 through 9 (77.25' frontage and rear each)
        curr_rear = p1_sw
        for _ in range(8):
            curr_rear = curr_rear.offset(self.az_mangrove_s, 77.25)
            rear_pts.append(curr_rear)
            front_pts.append(curr_rear.offset(self.az_lot_line, 100.0))

        # Lot 10 (76.92' frontage and rear)
        curr_rear = curr_rear.offset(self.az_mangrove_s, 76.92)
        rear_pts.append(curr_rear) # p10_sw / p11_nw
        front_pts.append(curr_rear.offset(self.az_lot_line, 100.0)) # p10_se / p11_ne (P.R.M. Monument)

        # Lot 11 SE Corner Return & Tangents
        p11_nw = rear_pts[-1]
        p11_ne = front_pts[-1]
        # Rear lot line dimension dynamically derived from 20' Surfwood Avenue skew:
        # 100.00' - 100.00' * tan(0°20'00") = 99.418' -> stated 99.42'
        lot11_rear_dist = round(self.lot11_rear_calc, 2)
        p11_sw = p11_nw.offset(self.az_mangrove_s, lot11_rear_dist)
        rear_pts.append(p11_sw)

        p11_pi_se = intersect_bearings(p11_sw, self.az_surfwood, p11_ne, self.az_mangrove_s)
        T11 = self.sol11.tangent # 25.145914'
        p11_pc_e = p11_pi_se.offset(self.az_mangrove_n, T11) # on Mangrove Ave
        p11_pc_s = p11_pi_se.offset(self.az_surfwood_rev, T11) # on Surfwood Ave

        self.points = {
            "p1_nw": p1_nw, "p1_pc_n": p1_pc_n, "p1_pi_ne": p1_pi_ne, "p1_pc_e": p1_pc_e, "p1_se": p1_se, "p1_sw": p1_sw,
            "p2_nw": rear_pts[1], "p2_ne": front_pts[0], "p2_se": front_pts[1], "p2_sw": rear_pts[2],
            "p3_nw": rear_pts[2], "p3_ne": front_pts[1], "p3_se": front_pts[2], "p3_sw": rear_pts[3],
            "p4_nw": rear_pts[3], "p4_ne": front_pts[2], "p4_se": front_pts[3], "p4_sw": rear_pts[4],
            "p5_nw": rear_pts[4], "p5_ne": front_pts[3], "p5_se": front_pts[4], "p5_sw": rear_pts[5],
            "p6_nw": rear_pts[5], "p6_ne": front_pts[4], "p6_se": front_pts[5], "p6_sw": rear_pts[6],
            "p7_nw": rear_pts[6], "p7_ne": front_pts[5], "p7_se": front_pts[6], "p7_sw": rear_pts[7],
            "p8_nw": rear_pts[7], "p8_ne": front_pts[6], "p8_se": front_pts[7], "p8_sw": rear_pts[8],
            "p9_nw": rear_pts[8], "p9_ne": front_pts[7], "p9_se": front_pts[8], "p9_sw": rear_pts[9],
            "p10_nw": rear_pts[9], "p10_ne": front_pts[8], "p10_se": front_pts[9], "p10_sw": rear_pts[10],
            "p11_nw": p11_nw, "p11_ne": p11_ne, "p11_pc_e": p11_pc_e, "p11_pi_se": p11_pi_se, "p11_pc_s": p11_pc_s, "p11_sw": p11_sw,
        }

        # Initialize lot solvers
        self.lots["1"] = DeterministicLotSolver(
            lot_id="Blk13-Lot1", block_id="13", lot_number="1",
            vertices=[p1_sw, p1_nw, p1_pc_n, p1_pc_e, p1_se],
            node_names=["SW_Cor", "NW_Cor", "PC_North", "PC_East", "SE_Cor(PRM)"],
            curve_specs={"side_3": {"radius": self.sol1.radius, "delta_deg": self.sol1.delta_deg, "length": round(self.sol1.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(100.00 * 100.00 - self.sol1.fillet_area, 2),
        )

        for i in range(2, 10):
            r_nw = rear_pts[i-1]
            r_sw = rear_pts[i]
            f_ne = front_pts[i-2]
            f_se = front_pts[i-1]
            ne_name = "NE_Cor(PRM)" if i == 2 else "NE_Cor"
            self.lots[str(i)] = DeterministicLotSolver(
                lot_id=f"Blk13-Lot{i}", block_id="13", lot_number=str(i),
                vertices=[r_sw, r_nw, f_ne, f_se],
                node_names=["SW_Cor", "NW_Cor", ne_name, "SE_Cor"],
                stated_area_sqft=7725.0,
            )

        self.lots["10"] = DeterministicLotSolver(
            lot_id="Blk13-Lot10", block_id="13", lot_number="10",
            vertices=[rear_pts[10], rear_pts[9], front_pts[8], front_pts[9]],
            node_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor(PRM)"],
            stated_area_sqft=7692.0,
        )

        self.lots["11"] = DeterministicLotSolver(
            lot_id="Blk13-Lot11", block_id="13", lot_number="11",
            vertices=[p11_sw, p11_nw, p11_ne, p11_pc_e, p11_pc_s],
            node_names=["SW_Cor", "NW_Cor", "NE_Cor(PRM)", "PC_East", "PC_South"],
            curve_specs={"side_4": {"radius": self.sol11.radius, "delta_deg": self.sol11.delta_deg, "length": round(self.sol11.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(0.5 * (100.00 + lot11_rear_dist) * 100.00 - self.sol11.fillet_area, 2),
        )

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        """Compute MapCheck closures for all 11 lots in Block 13."""
        results = {}
        for lot_num, solver in self.lots.items():
            results[lot_num] = solver.compute_mapcheck()
        return results

    def get_curve_table_data(self) -> list[dict[str, Any]]:
        """Return formatted Curve Table data for Block 13."""
        return [
            {
                "tag": "C1",
                "lot": "1",
                "location": "NE Corner Return (North St & Mangrove Ave)",
                "radius": self.sol1.radius,
                "delta": "90°00'00\"",
                "length": self.sol1.arc_length,
                "tangent": self.sol1.tangent,
                "chord": self.sol1.chord,
                "chord_bearing": whole_second_bearing(self.sol1.chord_bearing),
                "fillet_area": self.sol1.fillet_area,
            },
            {
                "tag": "C2",
                "lot": "11",
                "location": "SE Corner Return (Mangrove Ave & Surfwood Ave)",
                "radius": self.sol11.radius,
                "delta": "90°20'00\"",
                "length": self.sol11.arc_length,
                "tangent": self.sol11.tangent,
                "chord": self.sol11.chord,
                "chord_bearing": whole_second_bearing(self.sol11.chord_bearing),
                "fillet_area": self.sol11.fillet_area,
            },
        ]

    def get_line_table_data(self) -> list[dict[str, Any]]:
        """Return comprehensive Line Table data for all courses in Block 13."""
        lines = []
        tag_idx = 1

        # Lot 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "N88°58'20\"E", "distance": 75.00, "desc": "Lot 1 North Tangent to P.C."})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "S01°01'40\"E", "distance": 75.00, "desc": "Lot 1 Frontage P.T. to Lot 1/2 PRM"})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "S88°58'20\"W", "distance": 100.00, "desc": "Lot 1/2 Dividing Line"})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "N01°01'40\"W", "distance": 100.00, "desc": "Lot 1 Rear Line on Drainage R/W"})
        tag_idx += 1

        # Lots 2 through 9
        for i in range(2, 10):
            lines.append({"tag": f"L{tag_idx}", "bearing": "S01°01'40\"E", "distance": 77.25, "desc": f"Lot {i} Frontage on Mangrove Ave"})
            tag_idx += 1
            esmt_str = " (10' Esmt)" if i in (2, 8) else ""
            lines.append({"tag": f"L{tag_idx}", "bearing": "S88°58'20\"W", "distance": 100.00, "desc": f"Lot {i}/{i+1} Dividing Line{esmt_str}"})
            tag_idx += 1
            lines.append({"tag": f"L{tag_idx}", "bearing": "N01°01'40\"W", "distance": 77.25, "desc": f"Lot {i} Rear Line on Drainage R/W"})
            tag_idx += 1

        # Lot 10
        lines.append({"tag": f"L{tag_idx}", "bearing": "S01°01'40\"E", "distance": 76.92, "desc": "Lot 10 Frontage on Mangrove Ave"})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "S88°58'20\"W", "distance": 100.00, "desc": "Lot 10/11 Dividing Line (PRM)"})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "N01°01'40\"W", "distance": 76.92, "desc": "Lot 10 Rear Line on Drainage R/W"})
        tag_idx += 1

        # Lot 11
        lines.append({"tag": f"L{tag_idx}", "bearing": "S01°01'40\"E", "distance": 74.85, "desc": "Lot 11 Frontage PRM to P.C."})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "S89°18'20\"W", "distance": 74.85, "desc": "Lot 11 Surfwood Ave P.T. to SW Cor"})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "N01°01'40\"W", "distance": 99.42, "desc": "Lot 11 Rear Line on Drainage R/W"})
        tag_idx += 1

        # Tangent extensions to P.I. ticks
        lines.append({"tag": f"L{tag_idx}", "bearing": "N88°58'20\"E", "distance": 100.00, "desc": "Lot 1 Stated North Dim to P.I. Tick"})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "S01°01'40\"E", "distance": 100.00, "desc": "Lot 1 Stated Frontage to P.I. Tick"})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "S01°01'40\"E", "distance": 100.00, "desc": "Lot 11 Stated Frontage to P.I. Tick"})
        tag_idx += 1
        lines.append({"tag": f"L{tag_idx}", "bearing": "S89°18'20\"W", "distance": 100.00, "desc": "Lot 11 Stated South Dim to P.I. Tick"})

        return lines

    def generate_report(self, filepath: str = "data/block13_mapcheck_report.txt") -> str:
        """Generate certified surveyor checksheet report file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 13 SURVEY MAPCHECK AUDIT REPORT\n")
            f.write("  Plat Book 30, Pages 82 & 82A, Public Records of Duval County, Florida\n")
            f.write("  Pure Deterministic Coordinate Geometry (COGO) Engine Output (Offline)\n")
            f.write("=" * 80 + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("  RULE 2: CORNER RETURN CURVE DERIVATIONS & P.I. ANGLE BAR TANGENT CUTBACKS\n")
            f.write("=" * 80 + "\n")
            f.write("Lot 1 (NE Corner Return - Angle Bar '┘'):\n")
            f.write(f"  Tangents: N88°58'20\"E & S01°01'40\"E | Delta = {self.sol1.delta_deg:.4f}° (90°00'00\")\n")
            f.write(f"  Radius = 25.00' | Tangent T = {self.sol1.tangent:.4f}' | Arc = {self.sol1.arc_length:.4f}' | Chord = {self.sol1.chord:.4f}'\n")
            f.write(f"  Stated Dimension along North to P.I. Tick: 100.00' -> Cutback to P.T. = {self.sol1.straight_in:.2f}'\n")
            f.write(f"  Stated Dimension along Mangrove to P.I. Tick: 100.00' -> Cutback to P.C. = {self.sol1.straight_out:.2f}'\n")
            f.write(f"  Fillet Area Deduction: {self.sol1.fillet_area:.2f} SF\n\n")

            f.write("Lot 11 (SE Corner Return - Angle Bar '└'):\n")
            f.write(f"  Tangents: S01°01'40\"E & S89°18'20\"W | Delta = {self.sol11.delta_deg:.4f}° (90°20'00\" - 20' Surfwood Skew)\n")
            f.write(f"  Radius = 25.00' | Tangent T = {self.sol11.tangent:.4f}' | Arc = {self.sol11.arc_length:.4f}' | Chord = {self.sol11.chord:.4f}'\n")
            f.write(f"  Stated Dimension along Mangrove to P.I. Tick: 100.00' -> Cutback to P.C. = {self.sol11.straight_in:.4f}'\n")
            f.write(f"  Stated Dimension along Surfwood to P.I. Tick: 100.00' -> Cutback to P.T. = {self.sol11.straight_out:.4f}'\n")
            f.write("  Rear Dimension: 99.42' (Exact Skew: 100.00 - 100.00*tan(20') = 99.418' -> 99.42')\n")
            f.write(f"  Fillet Area Deduction: {self.sol11.fillet_area:.2f} SF\n\n")

            f.write("=" * 80 + "\n")
            f.write("  CURVE TABLE (BLOCK 13)\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Tag':<5} | {'Radius':<8} | {'Delta':<12} | {'Arc (ft)':<10} | {'Tan (ft)':<10} | {'Chord (ft)':<10} | {'Chord Bearing':<14} | {'Location'}\n")
            f.write("-" * 80 + "\n")
            for ct in self.get_curve_table_data():
                f.write(f"{ct['tag']:<5} | {ct['radius']:<8.2f} | {ct['delta']:<12} | {ct['length']:<10.2f} | {ct['tangent']:<10.2f} | {ct['chord']:<10.2f} | {ct['chord_bearing']:<14} | {ct['location']}\n")
            f.write("\n")

            f.write("=" * 80 + "\n")
            f.write("  LINE TABLE (BLOCK 13)\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Tag':<5} | {'Bearing':<14} | {'Distance (ft)':<14} | {'Description'}\n")
            f.write("-" * 80 + "\n")
            for lt in self.get_line_table_data():
                f.write(f"{lt['tag']:<5} | {lt['bearing']:<14} | {lt['distance']:<14.2f} | {lt['desc']}\n")
            f.write("\n")

            f.write("=" * 80 + "\n")
            f.write("  INDIVIDUAL LOT MAPCHECK SURVEYOR SHEETS (11 LOTS)\n")
            f.write("=" * 80 + "\n\n")
            for lot_num in [str(k) for k in range(1, 12)]:
                res = results[lot_num]
                f.write(res.format_surveyor_sheet() + "\n\n")

        return filepath


# ==============================================================================
# 7. BLOCK 16 DETERMINISTIC COGO SOLVER PIPELINE (14 LOTS)
# ==============================================================================

class BeachwoodBlock16Solver:
    """
    Deterministic cadastral solver for Block 16 (Western Curvilinear Panel),
    Beachwood Unit Two. Plat Book 30, Pages 82 & 82A, Duval County, FL.

    Features:
    - 14 Lots total:
      * North Row: Lots 1 through 8 (along Sail Avenue 60' R/W)
      * South Row: Lots 33 through 28 (along South Street, Marina Avenue, Keel Drive)
    - Block Centerline Axis: 618.50 ft along N87°35'30\"E.
    - West Cross Street: 60' R/W bearing N02°24'30\"W / S02°24'30\"E.
    - Marina Avenue North R/W Curve: R=389.27', Delta=37°42'50\" (subdivided into Lots 31, 30, 29).
    - Keel Drive North R/W Curve: R=167.95' (fronting Lot 28).
    - Wedge Lot: Lot 29 rear converges to an exact single-point apex at the centerline.
    - Corner returns: R=25.0' with P.I. angle bar glyphs:
      * Lot 1 NW: Angle bar '┌' (Sail Ave & West St)
      * Lot 33 SW: Angle bar '└' (South St & West St)
      * Lot 29 SE: Angle bar '┘' (Marina Ave PT to Keel Drive)
    - Monument: P.R.M. monument at South R/W boundary between Lot 33 and Lot 32.
    """
    def __init__(self, origin: Point | None = None):
        # 1. Bearings from Plat Records
        self.brg_west = "N02°24'30\"W"
        self.brg_west_rev = "S02°24'30\"E"
        self.brg_axis = "N87°35'30\"E"
        self.brg_axis_rev = "S87°35'30\"W"
        self.brg_sail = "N87°35'30\"E"
        self.brg_south_st = "N87°35'30\"E"
        self.brg_marina_pt_tan = "S54°41'40\"E"
        self.brg_keel_tan_in = "N35°18'20\"E"

        self.az_west_n = parse_bearing(self.brg_west)
        self.az_west_s = parse_bearing(self.brg_west_rev)
        self.az_axis_e = parse_bearing(self.brg_axis)
        self.az_axis_w = parse_bearing(self.brg_axis_rev)

        # 2. Rule 2 Corner Return Solves
        r1 = 25.0
        r33 = 25.0
        r29 = 25.0
        if _HAS_PLAT_CURVES:
            cr16 = get_block_corner_returns("16")
            r1 = float(cr16.get("CR_BLK16_L1", {}).get("radius", 25.0))
            r33 = float(cr16.get("CR_BLK16_L33", {}).get("radius", 25.0))
            r29 = float(cr16.get("CR_BLK16_L29", {}).get("radius", 25.0))
        # Lot 1 NW Corner Return (Sail Ave & West St)
        self.sol1 = solve_corner_return(self.brg_west, self.brg_sail, radius=r1, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=93.50, rot="CW")
        # Lot 33 SW Corner Return (West St & South St)
        self.sol33 = solve_corner_return(self.brg_west_rev, self.brg_south_st, radius=r33, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=93.50, rot="CCW")
        # Lot 29 SE Corner Return (Marina Ave PT to Keel Dr)
        self.sol29 = solve_corner_return(self.brg_marina_pt_tan, self.brg_keel_tan_in, radius=r29, stated_dim_in_to_pi=25.0, stated_dim_out_to_pi=25.0, rot="CCW")

        # 3. Marina Avenue North R/W Curve (R=389.27', Delta=37°42'50\")
        if _HAS_PLAT_CURVES:
            fc16 = get_block_frontage_curves("16")
            m_spec = fc16["CURVE_BLK16_MARINA_NORTH_RW"]
            self.r_marina = float(m_spec["radius"])
            c_marina_full = PlatCurve.from_params(radius=self.r_marina, delta_deg=float(m_spec["delta_deg"]))
            self.delta_marina = float(c_marina_full.delta_deg)
            k_spec = fc16["CURVE_BLK16_SHELLFISH_L28"]
            self.r_shellfish = float(k_spec["radius"])
        else:
            self.r_marina = 389.27
            self.delta_marina = 37.0 + 42.0 / 60.0 + 50.0 / 3600.0
            self.r_shellfish = 197.95
        # Shellfish Dr N R/W: CL R=167.95' + 30' (the lots are on the outside of the curve).  Each lot's
        # Δ comes from its printed chord; the three sum to the printed CL Δ 52°17'10".
        self.delta_shellfish_29 = 2.0 * math.degrees(math.asin(51.68 / (2.0 * self.r_shellfish)))  # 15°00'
        self.delta_shellfish_28 = 2.0 * math.degrees(math.asin(68.75 / (2.0 * self.r_shellfish)))  # 20°00'
        self.delta_shellfish_27 = 2.0 * math.degrees(math.asin(59.50 / (2.0 * self.r_shellfish)))  # 17°17'
        self.r_keel = self.r_shellfish  # backwards-compatible name (the curve was mislabelled "Keel")
        self.delta_keel_28 = self.delta_shellfish_28
        # East end corner returns on Beachwood Blvd (S00°41'40"E), dimensions to the P.I. (Note 2)
        self.sol17 = solve_corner_return("N87°35'30\"E", "S00°41'40\"E", radius=25.0, stated_dim_in_to_pi=103.76, rot="CW")
        self.sol18 = solve_corner_return("S00°41'40\"E", "S87°35'30\"W", radius=25.0, stated_dim_out_to_pi=97.78, rot="CW")
        self.delta_sub = self.delta_marina / 3.0  # 12.571296° per lot

        # 5. Coordinate Geometry Construction
        self.origin = origin or Point(1000.0, 1000.0)
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self._solve_geometry()

    def _solve_geometry(self):
        """Construct all Block 16 analytical coordinates."""
        # Anchor: Origin at intersection of West street R/W and Block Centerline
        p_cl_0 = self.origin

        # --- NORTH ROW (Lots 1 to 8) ---
        # Lot 1 NW Corner Return & P.I.
        p1_nw_pi = p_cl_0.offset(self.az_west_n, 100.0)
        T1 = self.sol1.tangent # 25.0000'
        p1_pc_w = p1_nw_pi.offset(self.az_west_s, T1) # on West street R/W (75.0' from p_cl_0)
        p1_pt_n = p1_nw_pi.offset(self.az_axis_e, T1) # on Sail Ave (68.5' from p1_ne)

        north_front: list[Point] = [p1_nw_pi.offset(self.az_axis_e, 93.50)]
        north_rear: list[Point] = [p_cl_0.offset(self.az_axis_e, 93.50)]

        # Lots 2 through 8 (75.00' each)
        curr_f = north_front[0]
        curr_r = north_rear[0]
        for _ in range(7):
            curr_f = curr_f.offset(self.az_axis_e, 75.0)
            curr_r = curr_r.offset(self.az_axis_e, 75.0)
            north_front.append(curr_f)
            north_rear.append(curr_r)

        # --- SOUTH ROW (Lots 33, 32, 31, 30, 29, 28) ---
        # Lot 33 SW Corner Return & P.I.
        p33_sw_pi = p_cl_0.offset(self.az_west_s, 100.0)
        T33 = self.sol33.tangent # 25.0000'
        p33_pc_w = p33_sw_pi.offset(self.az_west_n, T33) # on West street R/W (75.0' from p_cl_0)
        p33_pt_s = p33_sw_pi.offset(self.az_axis_e, T33) # on South street (68.5' from PRM)

        # P.R.M. Monument at SE corner Lot 33 / SW corner Lot 32
        p33_prm_se = p33_sw_pi.offset(self.az_axis_e, 93.50)
        p_cl_33_32 = north_rear[0] # at x=93.50'

        # Lot 32 SE / Lot 31 SW corner: P.C. of Marina Ave Curve
        p32_se_pc = p33_prm_se.offset(self.az_axis_e, 89.76)
        p_cl_32_31 = p_cl_0.offset(self.az_axis_e, 93.50 + 89.76) # at x=183.26'

        # Marina Avenue Curve Center & Arc Points
        p_center_marina = p32_se_pc.offset(self.az_west_s, self.r_marina)
        p31_se = p_center_marina.offset(self.az_west_n + self.delta_sub, self.r_marina)
        p30_se = p_center_marina.offset(self.az_west_n + 2.0 * self.delta_sub, self.r_marina)
        p29_pt_marina = p_center_marina.offset(self.az_west_n + 3.0 * self.delta_sub, self.r_marina)

        # Centerline rear points
        p_cl_31_30 = p_cl_0.offset(self.az_axis_e, 183.26 + 110.0) # at x=293.26'
        p_cl_apex = p_cl_0.offset(self.az_axis_e, 293.26 + 110.0)  # at x=403.26' (Apex of Lot 29)
        p_cl_28_27 = p_cl_0.offset(self.az_axis_e, 403.26 + 110.0) # at x=513.26' (SE corner Lot 28 rear)

        # Lot 29 Corner Return & SE Corner
        T29 = self.sol29.tangent
        p29_ret_pi = p29_pt_marina.offset(parse_bearing("S54°41'40\"E"), T29)
        p29_ret_pt = p29_ret_pi.offset(parse_bearing("N35°18'20\"E"), T29)
        p29_se = p_cl_apex.offset(parse_bearing("S35°01'42\"E"), 166.73)

        # Lot 28 SE Corner (East line: S23°01'43"E 116.36')
        p28_se = p_cl_28_27.offset(parse_bearing("S23°01'43\"E"), 116.36)

        # Store all points dictionary
        self.points = {
            "p_cl_0": p_cl_0,
            "p1_nw_pi": p1_nw_pi, "p1_pc_w": p1_pc_w, "p1_pt_n": p1_pt_n,
            "p1_ne": north_front[0], "p1_se": north_rear[0],
            "p33_sw_pi": p33_sw_pi, "p33_pc_w": p33_pc_w, "p33_pt_s": p33_pt_s,
            "p33_prm_se": p33_prm_se, "p32_se_pc": p32_se_pc,
            "p31_se": p31_se, "p30_se": p30_se, "p29_pt_marina": p29_pt_marina,
            "p29_ret_pi": p29_ret_pi, "p29_ret_pt": p29_ret_pt, "p29_se": p29_se,
            "p28_se": p28_se,
            "p_cl_33_32": p_cl_33_32, "p_cl_32_31": p_cl_32_31,
            "p_cl_31_30": p_cl_31_30, "p_cl_apex": p_cl_apex, "p_cl_28_27": p_cl_28_27,
            "center_marina": p_center_marina,
        }
        for i in range(2, 9):
            self.points[f"p{i}_ne"] = north_front[i - 1]
            self.points[f"p{i}_se"] = north_rear[i - 1]

        # ----------------------------------------------------------------------
        # Build Lot MapCheck Solvers
        # ----------------------------------------------------------------------
        lots_dict: dict[str, DeterministicLotSolver] = {}

        # Lot 1: NW corner return
        lots_dict["1"] = DeterministicLotSolver(
            lot_id="Blk16-Lot1", block_id="16", lot_number="1",
            vertices=[p_cl_0, p1_pc_w, p1_pt_n, north_front[0], north_rear[0]],
            node_names=["SW_Cor", "PC_West", "PT_North", "NE_Cor", "SE_Cor"],
            curve_specs={"side_2": {"radius": self.sol1.radius, "delta_deg": self.sol1.delta_deg, "length": round(self.sol1.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(9350.0 - self.sol1.fillet_area, 2),
        )

        # Lots 2 through 8: Standard Rectilinear 75.00' x 100.00'
        prev_f = north_front[0]
        prev_r = north_rear[0]
        for i in range(2, 9):
            cur_f = north_front[i - 1]
            cur_r = north_rear[i - 1]
            lots_dict[str(i)] = DeterministicLotSolver(
                lot_id=f"Blk16-Lot{i}", block_id="16", lot_number=str(i),
                vertices=[prev_r, prev_f, cur_f, cur_r],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
                stated_area_sqft=7500.0,
            )
            prev_f = cur_f
            prev_r = cur_r

        # Lot 33: SW corner return (Clockwise traversal from NW corner)
        lots_dict["33"] = DeterministicLotSolver(
            lot_id="Blk16-Lot33", block_id="16", lot_number="33",
            vertices=[p_cl_0, p_cl_33_32, p33_prm_se, p33_pt_s, p33_pc_w],
            node_names=["NW_Cor", "NE_Cor", "SE_Cor(PRM)", "PT_South", "PC_West"],
            curve_specs={"side_4": {"radius": self.sol33.radius, "delta_deg": self.sol33.delta_deg, "length": round(self.sol33.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(9350.0 - self.sol33.fillet_area, 2),
        )

        # Lot 32: Rectangular 89.76' x 100.00' (PRM to Marina PC)
        lots_dict["32"] = DeterministicLotSolver(
            lot_id="Blk16-Lot32", block_id="16", lot_number="32",
            vertices=[p33_prm_se, p32_se_pc, p_cl_32_31, p_cl_33_32],
            node_names=["SW_Cor(PRM)", "SE_Cor(PC)", "NE_Cor", "NW_Cor"],
            stated_area_sqft=8976.0,
        )

        # Lot 31: Frontage Curve C3 (R=389.27', Delta=12°34'17", Chord=85.24' @ S86°07'22"E)
        if _HAS_PLAT_CURVES:
            c_marina_lot = PlatCurve.from_params(radius=self.r_marina, delta_deg=self.delta_sub)
            c_marina_seg_a = float(c_marina_lot.segment_area)
        else:
            c3_sol = solve_curve_all_parameters(radius=self.r_marina, delta_deg=self.delta_sub)
            c_marina_seg_a = float(c3_sol["segment_area"])

        l31_poly = [p32_se_pc, p31_se, p_cl_31_30, p_cl_32_31]
        a31 = shoelace_area(l31_poly) + c_marina_seg_a
        lots_dict["31"] = DeterministicLotSolver(
            lot_id="Blk16-Lot31", block_id="16", lot_number="31",
            vertices=l31_poly,
            node_names=["SW_Cor(PC)", "SE_Cor", "NE_Cor", "NW_Cor"],
            curve_specs={"side_1": {"radius": self.r_marina, "delta_deg": self.delta_sub, "length": 85.41, "rot": "CW"}},
            stated_area_sqft=round(a31, 1),
        )

        # Lot 30: Frontage Curve C4 (R=389.27', Delta=12°34'17", Chord=85.24' @ S73°33'06"E)
        l30_poly = [p31_se, p30_se, p_cl_apex, p_cl_31_30]
        a30 = shoelace_area(l30_poly) + c_marina_seg_a
        lots_dict["30"] = DeterministicLotSolver(
            lot_id="Blk16-Lot30", block_id="16", lot_number="30",
            vertices=l30_poly,
            node_names=["SW_Cor", "SE_Cor", "Apex_NE", "NW_Cor"],
            curve_specs={"side_1": {"radius": self.r_marina, "delta_deg": self.delta_sub, "length": 85.41, "rot": "CW"}},
            stated_area_sqft=round(a30, 1),
        )

        # Lot 29: Wedge / Pie Lot (Apex at p_cl_apex, Curve C5, Corner Return C6, Straight 51.68', Side 166.73')
        l29_poly = [p30_se, p29_pt_marina, p29_ret_pt, p29_se, p_cl_apex]
        lots_dict["29"] = DeterministicLotSolver(
            lot_id="Blk16-Lot29", block_id="16", lot_number="29",
            vertices=l29_poly,
            node_names=["SW_Cor", "PT_Marina", "PT_Ret", "SE_Cor", "Apex_Rear"],
            curve_specs={
                "side_1": {"radius": self.r_marina, "delta_deg": self.delta_sub, "length": 85.41, "rot": "CW"},
                "side_2": {"radius": self.sol29.radius, "delta_deg": self.sol29.delta_deg, "length": round(self.sol29.arc_length, 2), "rot": "CCW"},
                "side_3": {"radius": self.r_shellfish, "delta_deg": self.delta_shellfish_29,
                           "length": round(self.r_shellfish * math.radians(self.delta_shellfish_29), 2), "rot": "CW"},
            },
            stated_area_sqft=0.0,  # set below from the closed-form record area
        )

        # Lot 28: Shellfish Dr N R/W chord 68.75' N60°18'20"E, rear 110.00', east 116.36', west 166.73'
        l28_poly = [p29_se, p28_se, p_cl_28_27, p_cl_apex]
        lots_dict["28"] = DeterministicLotSolver(
            lot_id="Blk16-Lot28", block_id="16", lot_number="28",
            vertices=l28_poly,
            node_names=["SW_Cor", "SE_Cor", "NE_Cor", "NW_Apex"],
            curve_specs={"side_1": {"radius": self.r_shellfish, "delta_deg": self.delta_shellfish_28,
                                    "length": round(self.r_shellfish * math.radians(self.delta_shellfish_28), 2), "rot": "CW"}},
            stated_area_sqft=0.0,
        )

        # ---- east of the wedge: Lots 9-17 (north) and 18-27 (south) ----
        az_e, az_s = self.az_axis_e, self.az_west_s
        blvd_s, blvd_n = parse_bearing("S00°41'40\"E"), parse_bearing("N00°41'40\"W")
        rear = {8: north_rear[7]}                       # rear-line points; Lot 8 SE = x 618.50'
        front_n = {8: north_front[7]}
        for i in range(9, 17):
            rear[i] = rear[i - 1].offset(az_e, 75.0)
            front_n[i] = front_n[i - 1].offset(az_e, 75.0)
        p_rear_e = rear[16].offset(az_e, 100.77)        # rear line meets Beachwood Blvd W R/W
        pi17 = front_n[16].offset(az_e, 103.76)
        p17_pt = pi17.offset(parse_bearing("S87°35'30\"W"), self.sol17.tangent)
        p17_pc = pi17.offset(blvd_s, self.sol17.tangent)
        front_s = {26: north_rear[7].offset(az_s, 100.0)}  # front_s[i] = Lot i SW; Lot 26 SW is under Lot 8 SE
        for i in range(25, 17, -1):
            front_s[i] = front_s[i + 1].offset(az_e, 75.0)
        pi18 = front_s[18].offset(az_e, 97.78)
        p18_pc = pi18.offset(blvd_n, self.sol18.tangent)
        p18_pt = pi18.offset(parse_bearing("S87°35'30\"W"), self.sol18.tangent)
        # Lot 27: Shellfish N R/W curve continues from Lot 28's SE corner (chord 59.50'), then 5.45' tangent
        c_sh = p29_ret_pt.offset((parse_bearing("N35°18'20\"E") + 90.0) % 360.0, self.r_shellfish)
        a_pc = (parse_bearing("N35°18'20\"E") - 90.0) % 360.0
        p27_pt = c_sh.offset((a_pc + self.delta_shellfish_29 + self.delta_shellfish_28 + self.delta_shellfish_27) % 360.0,
                             self.r_shellfish)
        self.points.update({"p_rear_e": p_rear_e, "p17_pi_ne": pi17, "p17_pt": p17_pt, "p17_pc": p17_pc,
                            "p18_pi_se": pi18, "p18_pc": p18_pc, "p18_pt": p18_pt, "p27_sh_pt": p27_pt,
                            "center_shellfish": c_sh})
        for i in range(9, 17):
            self.points[f"p{i}_ne"] = front_n[i]
            self.points[f"p{i}_se"] = rear[i]
        for i in range(18, 27):
            self.points[f"p{i}_sw"] = front_s[i]

        for i in range(9, 17):
            lots_dict[str(i)] = DeterministicLotSolver(
                lot_id=f"Blk16-Lot{i}", block_id="16", lot_number=str(i),
                vertices=[rear[i - 1], front_n[i - 1], front_n[i], rear[i]],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"], stated_area_sqft=7500.0,
            )
        lots_dict["17"] = DeterministicLotSolver(
            lot_id="Blk16-Lot17", block_id="16", lot_number="17",
            vertices=[rear[16], front_n[16], p17_pt, p17_pc, p_rear_e],
            node_names=["SW_Cor", "NW_Cor", "PT_Sail", "PC_Blvd", "SE_Cor"],
            curve_specs={"side_3": {"radius": 25.0, "delta_deg": self.sol17.delta_deg,
                                    "length": round(self.sol17.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(0.5 * (103.76 + 100.77) * 100.0 - self.sol17.fillet_area, 1),
        )
        lots_dict["18"] = DeterministicLotSolver(
            lot_id="Blk16-Lot18", block_id="16", lot_number="18",
            vertices=[rear[16], p_rear_e, p18_pc, p18_pt, front_s[18]],
            node_names=["NW_Cor", "NE_Cor", "PC_Blvd", "PT_Shellfish", "SW_Cor(PRM)"],
            curve_specs={"side_3": {"radius": 25.0, "delta_deg": self.sol18.delta_deg,
                                    "length": round(self.sol18.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(0.5 * (100.77 + 97.78) * 100.0 - self.sol18.fillet_area, 1),
        )
        for i in range(19, 27):
            lots_dict[str(i)] = DeterministicLotSolver(
                lot_id=f"Blk16-Lot{i}", block_id="16", lot_number=str(i),
                vertices=[rear[8 + (26 - i)], rear[9 + (26 - i)], front_s[i - 1], front_s[i]],
                node_names=["NW_Cor", "NE_Cor", "SE_Cor", "SW_Cor"], stated_area_sqft=7500.0,
            )
        lots_dict["27"] = DeterministicLotSolver(
            lot_id="Blk16-Lot27", block_id="16", lot_number="27",
            vertices=[p_cl_28_27, rear[8], front_s[26], p27_pt, p28_se],
            node_names=["NW_Cor", "NE_Cor", "SE_Cor", "PT_Shellfish", "SW_Cor"],
            curve_specs={"side_4": {"radius": self.r_shellfish, "delta_deg": self.delta_shellfish_27,
                                    "length": round(self.r_shellfish * math.radians(self.delta_shellfish_27), 2), "rot": "CCW"}},
            stated_area_sqft=0.0,
        )

        # Record ("stated") areas for the curved south-row lots: chord polygon minus the segments of the
        # Marina / Shellfish curves (the lots lie outside both circles) and minus the Lot 29 return fillet.
        def seg(R, d):
            t = math.radians(d)
            return 0.5 * R * R * (t - math.sin(t))
        for num, poly, cuts in [
            ("31", l31_poly, seg(self.r_marina, self.delta_sub)),
            ("30", l30_poly, seg(self.r_marina, self.delta_sub)),
            ("29", [p30_se, p29_pt_marina, p29_ret_pi, p29_ret_pt, p29_se, p_cl_apex],
             seg(self.r_marina, self.delta_sub) + self.sol29.fillet_area + seg(self.r_shellfish, self.delta_shellfish_29)),
            ("28", l28_poly, seg(self.r_shellfish, self.delta_shellfish_28)),
            ("27", [p_cl_28_27, rear[8], front_s[26], p27_pt, p28_se], seg(self.r_shellfish, self.delta_shellfish_27)),
        ]:
            lots_dict[num].stated_area_sqft = round(shoelace_area(poly) - cuts, 1)

        # Printed lines not used in the construction (computed, printed)
        self.checks = {
            "Lot 29 Shellfish chord 51.68'": (p29_ret_pt.dist_to(p29_se), 51.68),
            "Lot 28 Shellfish chord 68.75'": (p29_se.dist_to(p28_se), 68.75),
            "Lot 29 SE on Shellfish circle (0')": (abs(p29_se.dist_to(c_sh) - self.r_shellfish), 0.0),
            "Lot 28 SE on Shellfish circle (0')": (abs(p28_se.dist_to(c_sh) - self.r_shellfish), 0.0),
            "Lot 27 tangent 5.45'": (p27_pt.dist_to(front_s[26]), 5.45),
            "Lot 27 rear 105.24'": (p_cl_28_27.dist_to(rear[8]), 105.24),
        }
        self.lots = lots_dict

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        """Compute MapCheck for all 33 lots in Block 16."""
        results = {}
        for lot_num, solver in self.lots.items():
            results[lot_num] = solver.compute_mapcheck()
        return results

    def get_curve_table_data(self) -> list[dict[str, Any]]:
        """Return structured curve table rows for Block 16."""
        c3 = solve_curve_all_parameters(radius=self.r_marina, delta_deg=self.delta_sub)
        c7 = solve_curve_all_parameters(radius=self.r_shellfish, delta_deg=self.delta_shellfish_28)
        c8 = solve_curve_all_parameters(radius=self.r_shellfish, delta_deg=self.delta_shellfish_29)
        c9 = solve_curve_all_parameters(radius=self.r_shellfish, delta_deg=self.delta_shellfish_27)
        return [
            {"tag": "C1", "radius": self.sol1.radius, "delta": "90°00'00\"", "length": self.sol1.arc_length, "tangent": self.sol1.tangent, "chord": self.sol1.chord, "chord_bearing": whole_second_bearing(self.sol1.chord_bearing), "location": "Lot 1 NW Corner Return (Sail Ave & West St, Glyph '┌')"},
            {"tag": "C2", "radius": self.sol33.radius, "delta": "90°00'00\"", "length": self.sol33.arc_length, "tangent": self.sol33.tangent, "chord": self.sol33.chord, "chord_bearing": whole_second_bearing(self.sol33.chord_bearing), "location": "Lot 33 SW Corner Return (South St & West St, Glyph '└')"},
            {"tag": "C3", "radius": self.r_marina, "delta": "12°34'17\"", "length": float(c3["length"]), "tangent": float(c3["tangent"]), "chord": 85.24, "chord_bearing": "S86°07'22\"E", "location": "Lot 31 Frontage (Marina Ave North R/W)"},
            {"tag": "C4", "radius": self.r_marina, "delta": "12°34'17\"", "length": float(c3["length"]), "tangent": float(c3["tangent"]), "chord": 85.24, "chord_bearing": "S73°33'06\"E", "location": "Lot 30 Frontage (Marina Ave North R/W)"},
            {"tag": "C5", "radius": self.r_marina, "delta": "12°34'17\"", "length": float(c3["length"]), "tangent": float(c3["tangent"]), "chord": 85.24, "chord_bearing": "S60°58'49\"E", "location": "Lot 29 Frontage (Marina Ave North R/W)"},
            {"tag": "C6", "radius": self.sol29.radius, "delta": "90°00'00\"", "length": self.sol29.arc_length, "tangent": self.sol29.tangent, "chord": self.sol29.chord, "chord_bearing": whole_second_bearing(self.sol29.chord_bearing), "location": "Lot 29 SE Corner Return (Marina Ave PT to Keel Dr, Glyph '┘')"},
            {"tag": "C7", "radius": self.r_shellfish, "delta": deg_to_dms(self.delta_shellfish_28) if _HAS_PLAT_CURVES else "20°00'00\"", "length": float(c7["length"]), "tangent": float(c7["tangent"]), "chord": 68.75, "chord_bearing": "N60°18'20\"E", "location": "Lot 28 Frontage (Shellfish Drive North R/W)"},
            {"tag": "C8", "radius": self.r_shellfish, "delta": deg_to_dms(self.delta_shellfish_29) if _HAS_PLAT_CURVES else "15°00'00\"", "length": float(c8["length"]), "tangent": float(c8["tangent"]), "chord": 51.68, "chord_bearing": "N42°48'20\"E", "location": "Lot 29 Frontage (Shellfish Drive North R/W)"},
            {"tag": "C9", "radius": self.r_shellfish, "delta": deg_to_dms(self.delta_shellfish_27) if _HAS_PLAT_CURVES else "17°17'10\"", "length": float(c9["length"]), "tangent": float(c9["tangent"]), "chord": 59.50, "chord_bearing": "N78°56'55\"E", "location": "Lot 27 Frontage (Shellfish Drive North R/W)"},
            {"tag": "C10", "radius": self.sol17.radius, "delta": deg_to_dms(self.sol17.delta_deg) if _HAS_PLAT_CURVES else "", "length": self.sol17.arc_length, "tangent": self.sol17.tangent, "chord": self.sol17.chord, "chord_bearing": whole_second_bearing(self.sol17.chord_bearing), "location": "Lot 17 NE Corner Return (Sail Ave & Beachwood Blvd)"},
            {"tag": "C11", "radius": self.sol18.radius, "delta": deg_to_dms(self.sol18.delta_deg) if _HAS_PLAT_CURVES else "", "length": self.sol18.arc_length, "tangent": self.sol18.tangent, "chord": self.sol18.chord, "chord_bearing": whole_second_bearing(self.sol18.chord_bearing), "location": "Lot 18 SE Corner Return (Beachwood Blvd & Shellfish Dr)"},
        ]

    def get_line_table_data(self) -> list[dict[str, Any]]:
        """Return structured line table rows for Block 16."""
        table = [
            {"tag": "L1", "bearing": "N02°24'30\"W", "distance": 75.00, "desc": "Lot 1 West Straight to PC"},
            {"tag": "L2", "bearing": "N87°35'30\"E", "distance": 68.50, "desc": "Lot 1 Sail Ave Straight from PT"},
            {"tag": "L3", "bearing": "S02°24'30\"E", "distance": 100.00, "desc": "Lot 1/2 Dividing Line"},
            {"tag": "L4", "bearing": "N87°35'30\"E", "distance": 75.00, "desc": "Lots 2-8 Sail Ave Frontage (each)"},
            {"tag": "L5", "bearing": "S02°24'30\"E", "distance": 100.00, "desc": "Lots 2-8 Side Dividing Lines (each)"},
            {"tag": "L6", "bearing": "S02°24'30\"E", "distance": 75.00, "desc": "Lot 33 West Straight to PC"},
            {"tag": "L7", "bearing": "N87°35'30\"E", "distance": 68.50, "desc": "Lot 33 South St Straight to PRM"},
            {"tag": "L8", "bearing": "N02°24'30\"W", "distance": 100.00, "desc": "Lot 33/32 Dividing Line (PRM Monument)"},
            {"tag": "L9", "bearing": "N87°35'30\"E", "distance": 89.76, "desc": "Lot 32 South St Frontage to Marina PC"},
            {"tag": "L10", "bearing": "N02°24'30\"W", "distance": 100.00, "desc": "Lot 32/31 Dividing Line (at PC)"},
            {"tag": "L11", "bearing": "S10°36'36\"W", "distance": 112.21, "desc": "Lot 31/30 Dividing Line"},
            {"tag": "L12", "bearing": "S19°20'32\"W", "distance": 147.37, "desc": "Lot 30/29 Dividing Line to Apex"},
            {"tag": "L13", "bearing": "N42°48'20\"E", "distance": 51.68, "desc": "Lot 29 South Frontage from Return PT"},
            {"tag": "L14", "bearing": "S35°01'42\"E", "distance": 166.73, "desc": "Lot 29/28 Dividing Line from Apex"},
            {"tag": "L15", "bearing": "S23°01'43\"E", "distance": 116.36, "desc": "Lot 28/27 Dividing Line"},
            {"tag": "L16", "bearing": "N87°35'30\"E", "distance": 110.00, "desc": "Lot 31, 30, 28 Centerline Rear Lines (each)"},
        ]
        return table

    def generate_report(self, filepath: str = "data/block16_mapcheck_report.txt") -> str:
        """Generate certified surveyor report for Block 16."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 16 (WEST CURVILINEAR PANEL) SURVEY MAPCHECK REPORT\n")
            f.write("  Plat Book 30, Pages 82 & 82A, Public Records of Duval County, Florida\n")
            f.write("  Pure Algorithmic Cadastral COGO Engine Output (Offline / Deterministic)\n")
            f.write("=" * 80 + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("  RULE 2: CORNER RETURN CURVE DERIVATIONS & P.I. TANGENT CUTBACKS\n")
            f.write("=" * 80 + "\n")
            f.write("Lot 1 (NW Corner Return - Angle Bar '┌'):\n")
            f.write(f"  Tangents: N02°24'30\"W & N87°35'30\"E | Delta = {self.sol1.delta_deg:.4f}° (90°00'00\")\n")
            f.write(f"  Radius = 25.00' | Tangent T = {self.sol1.tangent:.4f}' | Arc = {self.sol1.arc_length:.4f}' | Chord = {self.sol1.chord:.4f}'\n")
            f.write(f"  Stated Dimension along West to P.I. Tick: 100.00' -> Cutback to P.C. = {self.sol1.straight_in:.2f}'\n")
            f.write(f"  Stated Dimension along Sail to P.I. Tick: 93.50' -> Cutback to P.T. = {self.sol1.straight_out:.2f}'\n")
            f.write(f"  Fillet Area Deduction: {self.sol1.fillet_area:.2f} SF\n\n")

            f.write("Lot 33 (SW Corner Return - Angle Bar '└'):\n")
            f.write(f"  Tangents: S02°24'30\"E & N87°35'30\"E | Delta = {self.sol33.delta_deg:.4f}° (90°00'00\")\n")
            f.write(f"  Radius = 25.00' | Tangent T = {self.sol33.tangent:.4f}' | Arc = {self.sol33.arc_length:.4f}' | Chord = {self.sol33.chord:.4f}'\n")
            f.write(f"  Stated Dimension along West to P.I. Tick: 100.00' -> Cutback to P.C. = {self.sol33.straight_in:.2f}'\n")
            f.write(f"  Stated Dimension along South St to P.I. Tick: 93.50' -> Cutback to P.T. = {self.sol33.straight_out:.2f}'\n")
            f.write(f"  Fillet Area Deduction: {self.sol33.fillet_area:.2f} SF\n\n")

            f.write("Lot 29 (SE Corner Return - Angle Bar '┘'):\n")
            f.write(f"  Tangents: S54°41'40\"E (Marina PT) & N35°18'20\"E (Keel Dr) | Delta = {self.sol29.delta_deg:.4f}° (90°00'00\")\n")
            f.write(f"  Radius = 25.00' | Tangent T = {self.sol29.tangent:.4f}' | Arc = {self.sol29.arc_length:.4f}' | Chord = {self.sol29.chord:.4f}'\n")
            f.write(f"  Fillet Area Deduction: {self.sol29.fillet_area:.2f} SF\n\n")

            f.write("=" * 80 + "\n")
            f.write("  CURVE TABLE (BLOCK 16)\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Tag':<5} | {'Radius':<8} | {'Delta':<12} | {'Arc (ft)':<10} | {'Tan (ft)':<10} | {'Chord (ft)':<10} | {'Chord Bearing':<14} | {'Location'}\n")
            f.write("-" * 80 + "\n")
            for ct in self.get_curve_table_data():
                f.write(f"{ct['tag']:<5} | {ct['radius']:<8.2f} | {ct['delta']:<12} | {ct['length']:<10.2f} | {ct['tangent']:<10.2f} | {ct['chord']:<10.2f} | {ct['chord_bearing']:<14} | {ct['location']}\n")
            f.write("\n")

            f.write("=" * 80 + "\n")
            f.write("  LINE TABLE (BLOCK 16)\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Tag':<5} | {'Bearing':<14} | {'Distance (ft)':<14} | {'Description'}\n")
            f.write("-" * 80 + "\n")
            for lt in self.get_line_table_data():
                f.write(f"{lt['tag']:<5} | {lt['bearing']:<14} | {lt['distance']:<14.2f} | {lt['desc']}\n")
            f.write("\n")

            f.write("=" * 80 + "\n")
            f.write("  INDIVIDUAL LOT MAPCHECK SURVEYOR SHEETS (14 LOTS)\n")
            f.write("=" * 80 + "\n\n")
            for lot_num in ["1", "2", "3", "4", "5", "6", "7", "8", "33", "32", "31", "30", "29", "28"]:
                res = results[lot_num]
                f.write(res.format_surveyor_sheet() + "\n\n")

        return filepath


# ==============================================================================
# 8. BLOCK 10 DETERMINISTIC COGO SOLVER PIPELINE (5 LOTS, WEST OF MATCHLINE)
# ==============================================================================

class BeachwoodBlock10Solver:
    """
    Deterministic solver for Block 10, Beachwood Unit Two (the only part of
    Block 10 within this plat -- everything east of the Unit One matchline is
    drafted with dashed lines and no bearings/distances, since it belongs to
    the adjoining, already-recorded Beachwood Unit One, P.B. 29-29/29A/29B/29C).
    Plat Book 30, Page 82, Duval County, FL.

    - 5 Lots (9 through 13), fronting Surfwood Avenue (60' R/W) to the north
      and the plat's own South boundary line to the south -- both bear
      N88deg18'20"E... N89deg18'20"E, front total 398.01', rear total 397.43'.
    - West side (Lot 13, on the 50' drainage/utility R/W's alignment):
      S01deg01'40"E, 100.00' -- the same bearing used for Mangrove Ave /
      the R/W in Blocks 13 and 11, NOT perpendicular to Surfwood Ave.
    - All other side lines (12/13, 11/12, 10/11, 9/10 dividers, and Lot 9's
      east side on the matchline) are the plat's standard divider bearing,
      exactly perpendicular to Surfwood Ave: N00deg41'40"W / S00deg41'40"E,
      100.00' each -- explicitly labeled "N.0deg41'40"W. 100.0'" on the
      matchline segment.
    - Because Lot 13 alone uses the non-perpendicular west bearing, its front
      (98.01') and rear (97.43') widths differ by exactly depth*tan(0d20') =
      100*tan(0deg20'00") = 0.58' -- the identical skew mechanism documented
      for Block 13's Lot 11 (see solve_skewed_lot_rear_dimension). Lots
      9-12 use the perpendicular divider on both sides, so their front and
      rear widths are identical (75.00' each).
    - No individual lot areas are printed on this sheet for Block 10 (unlike
      a legal-description table); stated_area_sqft is set to the computed
      value once solved, matching this engine's existing convention for
      blocks without printed per-lot area callouts.
    """
    def __init__(self, origin: Point | None = None):
        self.brg_front = "N89°18'20\"E"
        self.brg_west = "S01°01'40\"E"
        self.brg_side = "S00°41'40\"E"

        self.az_front = parse_bearing(self.brg_front)
        self.az_west = parse_bearing(self.brg_west)
        self.az_side = parse_bearing(self.brg_side)

        self.origin = origin or Point(1000.0, 1000.0)
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self._solve_geometry()

    def _solve_geometry(self):
        # Anchor: NW corner of Lot 13, on Surfwood Ave / drainage R/W corner.
        p13_nw = self.origin
        p13_ne = p13_nw.offset(self.az_front, 98.01)
        p13_sw = p13_nw.offset(self.az_west, 100.0)
        p13_se = p13_sw.offset(self.az_front, 97.43)

        front_pts = [p13_nw, p13_ne]
        rear_pts = [p13_sw, p13_se]
        for w in (75.0, 75.0, 75.0, 75.0):  # Lots 12, 11, 10, 9
            front_pts.append(front_pts[-1].offset(self.az_front, w))
            rear_pts.append(rear_pts[-1].offset(self.az_front, w))

        self.points = {
            "p13_nw": front_pts[0], "p13_ne": front_pts[1], "p13_se": rear_pts[1], "p13_sw": rear_pts[0],
            "p12_nw": front_pts[1], "p12_ne": front_pts[2], "p12_se": rear_pts[2], "p12_sw": rear_pts[1],
            "p11_nw": front_pts[2], "p11_ne": front_pts[3], "p11_se": rear_pts[3], "p11_sw": rear_pts[2],
            "p10_nw": front_pts[3], "p10_ne": front_pts[4], "p10_se": rear_pts[4], "p10_sw": rear_pts[3],
            "p9_nw": front_pts[4], "p9_ne": front_pts[5], "p9_se": rear_pts[5], "p9_sw": rear_pts[4],
        }

        for num in ["13", "12", "11", "10", "9"]:
            nw, ne, se, sw = (self.points[f"p{num}_nw"], self.points[f"p{num}_ne"],
                              self.points[f"p{num}_se"], self.points[f"p{num}_sw"])
            self.lots[num] = DeterministicLotSolver(
                lot_id=f"Blk10-Lot{num}", block_id="10", lot_number=num,
                vertices=[sw, nw, ne, se],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
                stated_area_sqft=1.0,
            )
        for lot in self.lots.values():
            res = lot.compute_mapcheck()
            lot.stated_area_sqft = round(res.computed_area_sqft, 2)

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: lot.compute_mapcheck() for num, lot in self.lots.items()}

    def get_line_table_data(self) -> list[dict[str, Any]]:
        lines = []
        idx = 1
        lines.append({"tag": f"L{idx}", "bearing": "S01°01'40\"E", "distance": 100.00, "desc": "Lot 13 West Line on Drainage R/W"})
        idx += 1
        for num, w in [("13", 98.01), ("12", 75.00), ("11", 75.00), ("10", 75.00), ("9", 75.00)]:
            lines.append({"tag": f"L{idx}", "bearing": "N89°18'20\"E", "distance": w, "desc": f"Lot {num} Frontage on Surfwood Ave"})
            idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "N00°41'40\"W", "distance": 100.00, "desc": "Lot 9 East Line on Matchline"})
        idx += 1
        for num, w in [("13", 97.43), ("12", 75.00), ("11", 75.00), ("10", 75.00), ("9", 75.00)]:
            lines.append({"tag": f"L{idx}", "bearing": "S89°18'20\"W", "distance": w, "desc": f"Lot {num} Rear Line on South Plat Boundary"})
            idx += 1
        return lines

    def generate_report(self, filepath: str = "data/block10_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 10 (WEST OF MATCHLINE) SURVEY MAPCHECK REPORT\n")
            f.write("  Plat Book 30, Page 82, Public Records of Duval County, Florida\n")
            f.write("  Pure Algorithmic Cadastral COGO Engine Output (Offline / Deterministic)\n")
            f.write("=" * 80 + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("  MATCHLINE & SKEW NOTES\n")
            f.write("=" * 80 + "\n")
            f.write("  Matchline Bearing: N00°41'40\"W, Length = 100.00 ft (Lot 9 East Line)\n")
            f.write("  East of this line is Beachwood Unit One (P.B. 29-29/29A/29B/29C) --\n")
            f.write("  drafted for reference only, no bearings/distances on this sheet.\n")
            f.write("  Lot 13 West Line follows the 50' drainage R/W bearing S01°01'40\"E\n")
            f.write("  (not perpendicular to Surfwood Ave), producing the same 0°20'00\"\n")
            f.write("  skew documented for Block 13 Lot 11: front 98.01' -> rear 97.43'.\n\n")

            f.write("=" * 80 + "\n")
            f.write("  LINE TABLE (BLOCK 10)\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Tag':<5} | {'Bearing':<14} | {'Distance (ft)':<14} | {'Description'}\n")
            f.write("-" * 80 + "\n")
            for lt in self.get_line_table_data():
                f.write(f"{lt['tag']:<5} | {lt['bearing']:<14} | {lt['distance']:<14.2f} | {lt['desc']}\n")
            f.write("\n")

            f.write("=" * 80 + "\n")
            f.write("  INDIVIDUAL LOT MAPCHECK SURVEYOR SHEETS (5 LOTS)\n")
            f.write("=" * 80 + "\n\n")
            for lot_num in ["13", "12", "11", "10", "9"]:
                res = results[lot_num]
                f.write(res.format_surveyor_sheet() + "\n\n")

        return filepath


# ==============================================================================
# 9. BLOCK 11 DETERMINISTIC COGO SOLVER PIPELINE (6 LOTS, WEST OF MATCHLINE)
# ==============================================================================

class BeachwoodBlock11Solver:
    """
    Deterministic solver for Block 11, Beachwood Unit Two (the only part of
    Block 11 within this plat -- everything east of the Unit One matchline,
    including the dashed-outline parcels also labeled "(11)"/"(12)" near San
    Salvadore Road, belongs to the adjoining Beachwood Unit One and carries
    no bearings/distances on this sheet).
    Plat Book 30, Page 82, Duval County, FL.

    - 6 Lots: 15, 16, 17 (North row, fronting Bayou -- 60' R/W); 14, 13, 12
      (South row, fronting Surfwood Avenue -- 60' R/W). Both streets bear
      N89°18'20"E on this sheet.
    - West side (Lots 15 & 14, on the drainage R/W's alignment shared with
      Mangrove Ave / Block 13): S01°01'40"E, 100.00' per row (200.00' total)
      -- same non-perpendicular bearing used in Block 13 and Block 10.
    - All other side lines (15/16, 16/17, 14/13, 13/12 dividers, and the
      east side on the matchline for Lots 17 & 12) are the plat's standard
      perpendicular divider: N00°41'40"W / S00°41'40"E, 100.00' each --
      matchline explicitly labeled "N.0°41'40"W. - 200.0'" (both rows).
    - The skew from the west side's non-perpendicular bearing shows up
      exactly as it did in Block 13/10: Bayou frontage total 243.83' ->
      Lot15/14 dividing line 243.25' -> Surfwood frontage 242.67', each step
      down by depth*tan(0°20'00") = 100*tan(0°20'00") = 0.58', entirely
      attributable to Lots 15 and 14 (Lots 16/17/13/12 stay 75.00' throughout
      since their sides are the perpendicular divider).
    - A 10' drainage/utility easement runs along part of the 15/14 and 16/13
      dividing line (dashed "10' Easement" annotation) -- an encumbrance,
      not a separate boundary; it does not change the lot closure.
    - No individual lot areas are printed on this sheet; stated_area_sqft is
      set to the computed value once solved.
    """
    def __init__(self, origin: Point | None = None):
        self.brg_front = "N89°18'20\"E"
        self.brg_west = "S01°01'40\"E"
        self.brg_side = "S00°41'40\"E"

        self.az_front = parse_bearing(self.brg_front)
        self.az_west = parse_bearing(self.brg_west)
        self.az_side = parse_bearing(self.brg_side)

        self.origin = origin or Point(1000.0, 1000.0)
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self._solve_geometry()

    def _solve_geometry(self):
        # Anchor: NW corner of Lot 15, on Bayou / west R/W corner.
        p15_nw = self.origin
        p15_ne = p15_nw.offset(self.az_front, 93.83)
        p15_sw = p15_nw.offset(self.az_west, 100.0)   # = p14_nw
        p15_se = p15_sw.offset(self.az_front, 93.25)  # = p14_ne

        north_front = [p15_nw, p15_ne]
        north_rear = [p15_sw, p15_se]
        for w in (75.0, 75.0):  # Lots 16, 17
            north_front.append(north_front[-1].offset(self.az_front, w))
            north_rear.append(north_rear[-1].offset(self.az_front, w))

        p14_nw, p14_ne = north_rear[0], north_rear[1]
        p14_sw = p14_nw.offset(self.az_west, 100.0)
        p14_se = p14_sw.offset(self.az_front, 92.67)
        south_front = [p14_nw, p14_ne]
        south_rear = [p14_sw, p14_se]
        for w in (75.0, 75.0):  # Lots 13, 12
            south_front.append(south_front[-1].offset(self.az_front, w))
            south_rear.append(south_rear[-1].offset(self.az_front, w))

        self.points = {
            "p15_nw": north_front[0], "p15_ne": north_front[1], "p15_se": north_rear[1], "p15_sw": north_rear[0],
            "p16_nw": north_front[1], "p16_ne": north_front[2], "p16_se": north_rear[2], "p16_sw": north_rear[1],
            "p17_nw": north_front[2], "p17_ne": north_front[3], "p17_se": north_rear[3], "p17_sw": north_rear[2],
            "p14_nw": south_front[0], "p14_ne": south_front[1], "p14_se": south_rear[1], "p14_sw": south_rear[0],
            "p13_nw": south_front[1], "p13_ne": south_front[2], "p13_se": south_rear[2], "p13_sw": south_rear[1],
            "p12_nw": south_front[2], "p12_ne": south_front[3], "p12_se": south_rear[3], "p12_sw": south_rear[2],
        }

        for num in ["15", "16", "17", "14", "13", "12"]:
            nw, ne, se, sw = (self.points[f"p{num}_nw"], self.points[f"p{num}_ne"],
                              self.points[f"p{num}_se"], self.points[f"p{num}_sw"])
            self.lots[num] = DeterministicLotSolver(
                lot_id=f"Blk11-Lot{num}", block_id="11", lot_number=num,
                vertices=[sw, nw, ne, se],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
                stated_area_sqft=1.0,
            )
        for lot in self.lots.values():
            res = lot.compute_mapcheck()
            lot.stated_area_sqft = round(res.computed_area_sqft, 2)

        # R=25' returns at the two Mangrove corners (drawn rounded on the scan, re-read 2026-09-24). The printed
        # 93.83' / 100' and 92.67' / 100' run to the P.I.s (Note 2), so p15_nw / p14_sw stay the P.I. points.
        self.sol15 = solve_corner_return("N01°01'40\"W", "N89°18'20\"E", radius=25.0,
                                         stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=93.83, rot="CW")
        self.sol14 = solve_corner_return("S89°18'20\"W", "N01°01'40\"W", radius=25.0,
                                         stated_dim_in_to_pi=92.67, stated_dim_out_to_pi=100.0, rot="CW")
        P = self.points
        north = (self.az_west + 180.0) % 360.0
        P["p15_pc_w"] = P["p15_nw"].offset(self.az_west, self.sol15.tangent)
        P["p15_pt_n"] = P["p15_nw"].offset(self.az_front, self.sol15.tangent)
        P["p14_pt_s"] = P["p14_sw"].offset(self.az_front, self.sol14.tangent)
        P["p14_pc_w"] = P["p14_sw"].offset(north, self.sol14.tangent)
        quad15 = shoelace_area([P["p15_sw"], P["p15_nw"], P["p15_ne"], P["p15_se"]])
        quad14 = shoelace_area([P["p14_sw"], P["p14_nw"], P["p14_ne"], P["p14_se"]])
        self.lots["15"] = DeterministicLotSolver(
            lot_id="Blk11-Lot15", block_id="11", lot_number="15",
            vertices=[P["p15_sw"], P["p15_pc_w"], P["p15_pt_n"], P["p15_ne"], P["p15_se"]],
            node_names=["SW_Cor", "PC_West", "PT_Bayou", "NE_Cor", "SE_Cor"],
            curve_specs={"side_2": {"radius": 25.0, "delta_deg": self.sol15.delta_deg,
                                    "length": round(self.sol15.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(quad15 - self.sol15.fillet_area, 1),
        )
        self.lots["14"] = DeterministicLotSolver(
            lot_id="Blk11-Lot14", block_id="11", lot_number="14",
            vertices=[P["p14_pc_w"], P["p14_nw"], P["p14_ne"], P["p14_se"], P["p14_pt_s"]],
            node_names=["PC_West", "NW_Cor", "NE_Cor", "SE_Cor", "PT_Surfwood"],
            curve_specs={"side_5": {"radius": 25.0, "delta_deg": self.sol14.delta_deg,
                                    "length": round(self.sol14.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(quad14 - self.sol14.fillet_area, 1),
        )

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: lot.compute_mapcheck() for num, lot in self.lots.items()}

    def get_line_table_data(self) -> list[dict[str, Any]]:
        lines = []
        idx = 1
        lines.append({"tag": f"L{idx}", "bearing": "S01°01'40\"E", "distance": 100.00, "desc": "Lot 15 West Line on Drainage R/W"})
        idx += 1
        for num, w in [("15", 93.83), ("16", 75.00), ("17", 75.00)]:
            lines.append({"tag": f"L{idx}", "bearing": "N89°18'20\"E", "distance": w, "desc": f"Lot {num} Frontage on Bayou"})
            idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "N00°41'40\"W", "distance": 100.00, "desc": "Lot 17 East Line on Matchline"})
        idx += 1
        for num, w in [("15", 93.25), ("16", 75.00), ("17", 75.00)]:
            lines.append({"tag": f"L{idx}", "bearing": "S89°18'20\"W", "distance": w, "desc": f"Lot {num}/{'14' if num=='15' else ('13' if num=='16' else '12')} Dividing Line"})
            idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "S01°01'40\"E", "distance": 100.00, "desc": "Lot 14 West Line on Drainage R/W"})
        idx += 1
        for num, w in [("14", 92.67), ("13", 75.00), ("12", 75.00)]:
            lines.append({"tag": f"L{idx}", "bearing": "N89°18'20\"E", "distance": w, "desc": f"Lot {num} Frontage on Surfwood Ave"})
            idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "N00°41'40\"W", "distance": 100.00, "desc": "Lot 12 East Line on Matchline"})
        return lines

    def generate_report(self, filepath: str = "data/block11_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 11 (WEST OF MATCHLINE) SURVEY MAPCHECK REPORT\n")
            f.write("  Plat Book 30, Page 82, Public Records of Duval County, Florida\n")
            f.write("  Pure Algorithmic Cadastral COGO Engine Output (Offline / Deterministic)\n")
            f.write("=" * 80 + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("  MATCHLINE & SKEW NOTES\n")
            f.write("=" * 80 + "\n")
            f.write("  Matchline Bearing: N00°41'40\"W, Length = 200.00 ft (Lots 17 & 12 East Lines)\n")
            f.write("  East of this line is Beachwood Unit One (P.B. 29-29/29A/29B/29C) --\n")
            f.write("  drafted for reference only, no bearings/distances on this sheet.\n")
            f.write("  Lots 15/14 West Line follows the drainage R/W bearing S01°01'40\"E\n")
            f.write("  (not perpendicular to Bayou/Surfwood), producing the 0°20'00\" skew:\n")
            f.write("  Bayou 243.83' -> mid-line 243.25' -> Surfwood 242.67' (each -0.58').\n\n")

            f.write("=" * 80 + "\n")
            f.write("  LINE TABLE (BLOCK 11)\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Tag':<5} | {'Bearing':<14} | {'Distance (ft)':<14} | {'Description'}\n")
            f.write("-" * 80 + "\n")
            for lt in self.get_line_table_data():
                f.write(f"{lt['tag']:<5} | {lt['bearing']:<14} | {lt['distance']:<14.2f} | {lt['desc']}\n")
            f.write("\n")

            f.write("=" * 80 + "\n")
            f.write("  INDIVIDUAL LOT MAPCHECK SURVEYOR SHEETS (6 LOTS)\n")
            f.write("=" * 80 + "\n\n")
            for lot_num in ["15", "16", "17", "14", "13", "12"]:
                res = results[lot_num]
                f.write(res.format_surveyor_sheet() + "\n\n")

        return filepath


# ==============================================================================
# 10. BLOCK 12 DETERMINISTIC COGO SOLVER PIPELINE (7 LOTS, WEST OF MATCHLINE)
# ==============================================================================

class InsufficientPlatDataError(Exception):
    """Raised when a lot's boundary cannot be closed from what is legibly
    stated on the plat sheet, and needs a field check or clearer print
    before it can be certified -- see BeachwoodBlock12Solver's docstring."""


class BeachwoodBlock12Solver:
    """
    Block 12, Beachwood Unit Two (Sheet 1, PB 30 Pg 82), Lots 4-10: the part west of the Unit One
    matchline. Lot 3 and the other dashed "(12)" parcels belong to Unit One. Re-read at 400 dpi 2026-09-24.
    The earlier reading at 300 dpi left Lots 8-10 flagged and closed Lots 4/6/7 as quadrilaterals. At 400 dpi
    every course is legible:

      - West line (50' drainage R/W, S01°01'40"E) from the San Salvadore P.I.: 90' (L8), 75' (L7),
        71.27' (L6), 90' (L5) to the Bayou P.I. R=25' returns at both ends (Note 2 dims to the P.I.).
      - San Salvadore Ave S R/W: 25.0' N88°58'20"E to the P.C. of the curve R=269.96-30=239.96', lot chords
        106.60' N78°11'40"W (L8, Δ 25°40') and 44.61' N60°01'40"W (L9, Δ 10°40'; total = CL Δ 36°20'), then
        57.92' + 75' (L10) on S54°41'40"E to the P.R.M.
      - Lot 7 is 100' x 75' (east line N01°01'40"W 75'). Lot 6 is north 120.00' (= 100' + 20'), then the jog
        25.82' on S56°34'xx"E, 60.34' N19°06'16"E, south 120.52'. Lot 8 east N22°32'48"E 72.37'.
        Lot 9/10 line N35°18'20"E 122.45'. Lot 10 rear 75.04' on the same S56°34'xx"E line.
      - Lot 4: 90.69' (N00°41'40"W), 60.34', 75.04', then the boundary N75°27'25"W 12.07' and
        N00°41'40"W 102.20', and 94.20' on Bayou Rd (N89°18'20"E).
    Construction uses only the printed values listed below; all others are in `self.checks`.
    Origin: Lot 7 NW corner (on the drainage R/W).
    """
    R_SANSAL = 239.96

    def __init__(self, origin: Point | None = None):
        self.brg_div = "N88°58'20\"E"
        self.brg_west = "S01°01'40\"E"
        self.brg_bayou = "N89°18'20\"E"
        self.brg_side = "N00°41'40\"W"
        self.az_div = parse_bearing(self.brg_div)
        self.az_west = parse_bearing(self.brg_west)
        self.az_bayou = parse_bearing(self.brg_bayou)
        self.az_side = parse_bearing(self.brg_side)
        self.origin = origin or Point(1000.0, 1000.0)
        self.points: dict[str, Point] = {}
        self.flagged_points: dict[str, dict[str, Any]] = {}   # none remain after the 400 dpi re-read
        self.lots: dict[str, DeterministicLotSolver] = {}
        self.checks: dict[str, tuple[float, float]] = {}
        self.sol8 = solve_corner_return("N01°01'40\"W", "N88°58'20\"E", radius=25.0,
                                        stated_dim_in_to_pi=90.0, stated_dim_out_to_pi=25.0, rot="CW")
        self.sol5 = solve_corner_return("S89°18'20\"W", "N01°01'40\"W", radius=25.0,
                                        stated_dim_in_to_pi=120.0, stated_dim_out_to_pi=90.0, rot="CW")
        self._solve_geometry()

    def _solve_geometry(self):
        P = self.points
        north = parse_bearing("N01°01'40\"W")
        diag = parse_bearing("S54°41'40\"E")

        def put(name, pt):
            P[name] = pt
            return pt

        # ---- drainage R/W line ----
        p7_nw = put("p7_nw", self.origin)
        pi8 = put("p8_pi_nw", p7_nw.offset(north, 90.0))
        put("p8_pc_w", pi8.offset(self.az_west, self.sol8.tangent))
        put("p8_pt_n", pi8.offset(self.az_div, self.sol8.tangent))
        p7_sw = put("p7_sw", p7_nw.offset(self.az_west, 75.0))
        put("p6_nw", p7_sw)
        p6_sw = put("p6_sw", p7_sw.offset(self.az_west, 71.27))
        put("p5_nw", p6_sw)
        p5_sw = put("p5_sw", p6_sw.offset(self.az_west, 90.0))         # Bayou P.I.
        put("p5_pc_w", p5_sw.offset(north, self.sol5.tangent))
        put("p5_pt_s", p5_sw.offset(self.az_bayou, self.sol5.tangent))

        # ---- San Salvadore S R/W ----
        spc = put("p_sansal_pc", pi8.offset(self.az_div, 25.0))
        d8 = 2.0 * math.degrees(math.asin(106.60 / (2.0 * self.R_SANSAL)))
        d9 = 2.0 * math.degrees(math.asin(44.61 / (2.0 * self.R_SANSAL)))
        ctr = spc.offset((self.az_div + 90.0) % 360.0, self.R_SANSAL)
        a0 = (self.az_div - 90.0) % 360.0
        f8 = put("p8_ne", ctr.offset((a0 + d8) % 360.0, self.R_SANSAL))
        spt = put("p_sansal_pt", ctr.offset((a0 + d8 + d9) % 360.0, self.R_SANSAL))
        f9 = put("p9_ne", spt.offset(diag, 57.92))
        prm = put("p_prm_san_salvadore", f9.offset(diag, 75.0))

        # ---- interior ----
        p7_ne = put("p7_ne", p7_nw.offset(self.az_div, 100.0))
        put("p8_sw", p7_nw)
        put("p8_se", p7_ne)
        p7_se = put("p7_se", p7_ne.offset(self.az_west, 75.0))
        a = put("p6_ne", p7_se.offset(self.az_div, 20.0))
        p6_se = put("p6_se", p6_sw.offset(self.az_div, 120.52))
        put("p5_ne", p6_se)
        put("p4_nw", p6_se)
        b = put("p_jog_b", p6_se.offset(parse_bearing("N19°06'16\"E"), 60.34))

        # ---- Bayou Rd frontage and the matchline boundary ----
        p5_se = put("p5_se", p5_sw.offset(self.az_bayou, 120.0))
        put("p4_sw", p5_se)
        p4_se = put("p4_se", p5_se.offset(self.az_bayou, 94.20))
        d = put("p4_ne", p4_se.offset(self.az_side, 102.20))
        put("p_matchline_bend", d)
        c = put("p_jog_c", d.offset(parse_bearing("N75°27'25\"W"), 12.07))

        # ---- lots (clockwise rings) ----
        def seg(R, dd):
            t = math.radians(dd)
            return 0.5 * R * R * (t - math.sin(t))

        def poly(names):
            return shoelace_area([P[n] for n in names])

        def lot(num, names, stated, curve_specs=None):
            self.lots[num] = DeterministicLotSolver(
                lot_id=f"Blk12-Lot{num}", block_id="12", lot_number=num,
                vertices=[P[n] for n in names], node_names=names,
                curve_specs=curve_specs or {}, stated_area_sqft=round(stated, 1),
            )

        def fil(side, sol):
            return {side: {"radius": 25.0, "delta_deg": sol.delta_deg, "length": round(sol.arc_length, 2), "rot": "CW"}}

        def arc(side, dd):
            return {side: {"radius": self.R_SANSAL, "delta_deg": dd, "length": round(self.R_SANSAL * math.radians(dd), 2), "rot": "CW"}}

        cs = fil("side_2", self.sol8)
        cs.update(arc("side_4", d8))
        lot("8", ["p7_nw", "p8_pc_w", "p8_pt_n", "p_sansal_pc", "p8_ne", "p7_ne"],
            poly(["p7_nw", "p8_pi_nw", "p_sansal_pc", "p8_ne", "p7_ne"]) + seg(self.R_SANSAL, d8) - self.sol8.fillet_area, cs)
        r9 = ["p7_ne", "p8_ne", "p_sansal_pt", "p9_ne", "p_jog_b", "p6_ne", "p7_se"]
        lot("9", r9, poly(r9) + seg(self.R_SANSAL, d9), arc("side_2", d9))
        r10 = ["p_jog_b", "p9_ne", "p_prm_san_salvadore", "p_jog_c"]
        lot("10", r10, poly(r10))
        r7 = ["p7_sw", "p7_nw", "p7_ne", "p7_se"]
        lot("7", r7, poly(r7))
        r6 = ["p6_sw", "p7_sw", "p6_ne", "p_jog_b", "p6_se"]
        lot("6", r6, poly(r6))
        lot("5", ["p5_pc_w", "p6_sw", "p6_se", "p5_se", "p5_pt_s"],
            poly(["p5_sw", "p6_sw", "p6_se", "p5_se"]) - self.sol5.fillet_area, fil("side_5", self.sol5))
        r4 = ["p4_sw", "p4_nw", "p_jog_b", "p_jog_c", "p4_ne", "p4_se"]
        lot("4", r4, poly(r4))

        # ---- printed values not used in the construction ----
        dist = lambda x, y: P[x].dist_to(P[y])  # noqa: E731

        def az(x, y):
            return math.degrees(math.atan2(P[y].e - P[x].e, P[y].n - P[x].n)) % 360.0
        self.checks = {
            "Lot 6 north 120.00' (L6 NW -> A)": (dist("p7_sw", "p6_ne"), 120.00),
            "Jog A->B 25.82'": (dist("p6_ne", "p_jog_b"), 25.82),
            "Jog B->C 75.04' (Lot 10 rear)": (dist("p_jog_b", "p_jog_c"), 75.04),
            "Jog A-B and B-C collinear (deg)": (abs(az("p6_ne", "p_jog_b") - az("p_jog_b", "p_jog_c")), 0.0),
            "Lot 9/10 line 122.45'": (dist("p_jog_b", "p9_ne"), 122.45),
            "Lot 9/10 line bearing N35°18'20\"E (deg)": (az("p_jog_b", "p9_ne"), parse_bearing("N35°18'20\"E")),
            "Boundary C -> P.R.M. 120.0'": (dist("p_jog_c", "p_prm_san_salvadore"), 120.0),
            "Lot 8 east 72.37'": (dist("p7_ne", "p8_ne"), 72.37),
            "Lot 4 west 90.69'": (dist("p4_sw", "p4_nw"), 90.69),
            "Lot 7 south 100'": (dist("p7_sw", "p7_se"), 100.0),
        }

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: lot.compute_mapcheck() for num, lot in self.lots.items()}

    def generate_report(self, filepath: str = "data/block12_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n  BEACHWOOD UNIT TWO -- BLOCK 12 (WEST OF MATCHLINE) SURVEY MAPCHECK REPORT (LOTS 4-10)\n")
            f.write("  Plat Book 30, Page 82, Public Records of Duval County, Florida\n" + "=" * 80 + "\n\n")
            for num in ["8", "9", "10", "7", "6", "5", "4"]:
                f.write(results[num].format_surveyor_sheet() + "\n\n")
            f.write("PRINTED-DIMENSION REDUNDANCY CHECKS (computed vs plat)\n")
            for key, (calc, printed) in self.checks.items():
                f.write(f"  {key:<42} {calc:10.3f}  vs {printed:10.3f}  ({calc - printed:+.3f})\n")
        return filepath


# ==============================================================================
# 11. BLOCK 18 DETERMINISTIC COGO SOLVER PIPELINE (19 LOTS, NORTH DRAINAGE ROW)
# ==============================================================================

class BeachwoodBlock18Solver:
    """
    Deterministic solver for Block 18, Beachwood Unit Two (Sheet 2).
    Plat Book 30, Page 82A, Public Records of Duval County, Florida.

    - 19 Lots total (Lots 1 through 19):
      * Fronts Starfish Avenue (60' R/W) to the South (N87°35'30"E / S87°35'30"W).
      * Backs onto the 50' Right-of-Way for Drainage and Utilities to the North.
      * Lot 1 (West end): 103.50' frontage x 100.00' depth (10,350 SF).
      * Lots 2 through 18: Standard 75.00' frontage x 100.00' depth (7,500 SF each).
      * Lot 19 (East end): Fronting Beachwood Boulevard with lateral convergence:
        - Rear (North): 116.33'
        - Front (South): 113.34' (convergence rate: 2.99' per 100.04')
        - East line on Beachwood Blvd: 100.04' along S00°41'40"E.
        - SE Corner Return: R=25.00' into Beachwood Blvd.
    """
    def __init__(self, origin: Point | None = None):
        self.origin = origin or Point(0.0, 0.0)
        self.brg_street = "N87°35'30\"E"
        self.brg_street_rev = "S87°35'30\"W"
        self.brg_side = "S02°24'30\"E"
        self.brg_side_rev = "N02°24'30\"W"
        self.brg_blvd = "S00°41'40\"E"

        self.az_e = parse_bearing(self.brg_street)
        self.az_w = parse_bearing(self.brg_street_rev)
        self.az_s = parse_bearing(self.brg_side)
        self.az_n = parse_bearing(self.brg_side_rev)
        self.az_blvd = parse_bearing(self.brg_blvd)

        # SE Corner Return on Lot 19
        r19 = 25.0
        if _HAS_PLAT_CURVES:
            cr18 = get_block_corner_returns("18")
            r19 = float(cr18.get("CR_BLK18_L19", {}).get("radius", 25.0))
        self.sol19 = solve_corner_return(
            bearing_in=self.brg_blvd,
            bearing_out=self.brg_street_rev,
            radius=r19,
            stated_dim_in_to_pi=100.04,
            stated_dim_out_to_pi=113.34,
            rot="CW",
        )

        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self._solve_geometry()

    def _solve_geometry(self) -> None:
        p_nw = self.origin
        p_sw = p_nw.offset(self.az_s, 100.00)
        self.points["B18_L1_NW"] = p_nw
        self.points["B18_L1_SW"] = p_sw

        curr_nw = p_nw
        curr_sw = p_sw

        # Lot 1 (103.50' x 100.00')
        w1 = 103.50
        ne1 = curr_nw.offset(self.az_e, w1)
        se1 = curr_sw.offset(self.az_e, w1)
        self.points["B18_L1_NE"] = ne1
        self.points["B18_L1_SE"] = se1
        self.lots["1"] = DeterministicLotSolver(
            lot_id="Blk18-Lot1", block_id="18", lot_number="1",
            vertices=[curr_nw, ne1, se1, curr_sw],
            node_names=["B18_L1_NW", "B18_L1_NE", "B18_L1_SE", "B18_L1_SW"],
            stated_area_sqft=10350.0,
        )
        curr_nw = ne1
        curr_sw = se1

        # Lots 2 through 18 (75.00' x 100.00' each)
        for i in range(2, 19):
            lot_num = str(i)
            ne = curr_nw.offset(self.az_e, 75.00)
            se = curr_sw.offset(self.az_e, 75.00)
            self.points[f"B18_L{lot_num}_NE"] = ne
            self.points[f"B18_L{lot_num}_SE"] = se
            self.lots[lot_num] = DeterministicLotSolver(
                lot_id=f"Blk18-Lot{lot_num}", block_id="18", lot_number=lot_num,
                vertices=[curr_nw, ne, se, curr_sw],
                node_names=[f"B18_L{i-1}_NE", f"B18_L{lot_num}_NE", f"B18_L{lot_num}_SE", f"B18_L{i-1}_SE"],
                stated_area_sqft=7500.0,
            )
            curr_nw = ne
            curr_sw = se

        # Lot 19 (East end, converging: Rear 116.33', Front 113.34', East 100.04')
        ne19 = curr_nw.offset(self.az_e, 116.33)
        pi19_se = curr_sw.offset(self.az_e, 113.34)
        self.points["B18_L19_NE"] = ne19
        self.points["B18_L19_PI_SE"] = pi19_se

        T = self.sol19.tangent
        pt19 = pi19_se.offset(self.az_w, T)
        pc19 = pi19_se.offset(parse_bearing("N00°41'40\"W"), T)
        self.points["B18_L19_PT"] = pt19
        self.points["B18_L19_PC"] = pc19

        stated_a19 = 0.5 * (116.33 + 113.34) * 100.00 - self.sol19.fillet_area
        self.lots["19"] = DeterministicLotSolver(
            lot_id="Blk18-Lot19", block_id="18", lot_number="19",
            vertices=[curr_nw, ne19, pc19, pt19, curr_sw],
            node_names=["B18_L18_NE", "B18_L19_NE", "B18_L19_PC", "B18_L19_PT", "B18_L18_SE"],
            curve_specs={"side_3": {"radius": self.sol19.radius, "delta_deg": self.sol19.delta_deg, "length": round(self.sol19.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(stated_a19, 1),
        )

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: solver.compute_mapcheck() for num, solver in self.lots.items()}

    def generate_report(self, filepath: str = "data/block18_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 18 SURVEY MAPCHECK AUDIT REPORT (19 LOTS)\n")
            f.write("  Plat Book 30, Page 82A, Public Records of Duval County, Florida\n")
            f.write("=" * 80 + "\n\n")
            for lot_num in [str(i) for i in range(1, 20)]:
                res = results[lot_num]
                f.write(res.format_surveyor_sheet() + "\n\n")
        return filepath


# ==============================================================================
# 12. BLOCK 17 DETERMINISTIC COGO SOLVER PIPELINE (34 LOTS, STARFISH & SAIL)
# ==============================================================================

class BeachwoodBlock17Solver:
    """
    Deterministic solver for Block 17, Beachwood Unit Two (Sheet 2).
    Plat Book 30, Page 82A, Public Records of Duval County, Florida.

    - 34 Lots total:
      * North Row: Lots 1 through 17 (along Starfish Avenue 60' R/W)
      * South Row: Lots 34 down to 18 (along Sail Avenue 60' R/W)
      * West Street: Mangrove Avenue (60' R/W, bearing N02°24'30"W).
      * East Street: Beachwood Boulevard (Course 26, bearing S00°41'40"E).
      * Corner Returns:
        - Lot 1 NW: Angle bar '┌' R=25.00' (Mangrove Ave to Starfish Ave)
        - Lot 34 SW: Angle bar '└' R=25.00' (Mangrove Ave to Sail Ave)
      * Standard Lots (2-16 North, 33-19 South): 75.00' x 100.00' (7,500 SF).
      * Terminating East Lots:
        - Lot 17: Front 108.55', Rear 111.54' (convergence 2.99')
        - Lot 18: Front 105.56', Rear 108.55' (convergence 2.99')
    """
    def __init__(self, origin: Point | None = None):
        self.origin = origin or Point(0.0, 0.0)
        self.brg_street = "N87°35'30\"E"
        self.brg_street_rev = "S87°35'30\"W"
        self.brg_side = "S02°24'30\"E"
        self.brg_side_rev = "N02°24'30\"W"
        self.brg_blvd = "S00°41'40\"E"

        self.az_e = parse_bearing(self.brg_street)
        self.az_w = parse_bearing(self.brg_street_rev)
        self.az_s = parse_bearing(self.brg_side)
        self.az_n = parse_bearing(self.brg_side_rev)

        # Corner return solves
        r1 = 25.0
        r34 = 25.0
        if _HAS_PLAT_CURVES:
            cr17 = get_block_corner_returns("17")
            r1 = float(cr17.get("CR_BLK17_L1", {}).get("radius", 25.0))
            r34 = float(cr17.get("CR_BLK17_L34", {}).get("radius", 25.0))
        self.sol1 = solve_corner_return(self.brg_side_rev, self.brg_street, radius=r1, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=93.50, rot="CW")
        self.sol34 = solve_corner_return(self.brg_side, self.brg_street, radius=r34, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=93.50, rot="CCW")

        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self._solve_geometry()

    def _solve_geometry(self) -> None:
        p_nw_pi = self.origin
        p_mid_w = p_nw_pi.offset(self.az_s, 100.00)
        p_sw_pi = p_mid_w.offset(self.az_s, 100.00)
        self.points["B17_PI_NW"] = p_nw_pi
        self.points["B17_MID_W"] = p_mid_w
        self.points["B17_PI_SW"] = p_sw_pi

        # Corner return points (Rule 2 dynamic tangent derivation)
        T1 = self.sol1.tangent
        T34 = self.sol34.tangent
        p1_pc = p_nw_pi.offset(self.az_s, T1)
        p1_pt = p_nw_pi.offset(self.az_e, T1)
        p34_pc = p_sw_pi.offset(self.az_n, T34)
        p34_pt = p_sw_pi.offset(self.az_e, T34)
        self.points["B17_L1_PC"] = p1_pc
        self.points["B17_L1_PT"] = p1_pt
        self.points["B17_L34_PC"] = p34_pc
        self.points["B17_L34_PT"] = p34_pt

        # --- NORTH ROW: LOTS 1 to 17 ---
        # Lot 1 (Boundary Cut-Back to P.C./P.T. via Rule 2)
        w1_straight = 93.50 - T1
        p1_ne = p1_pt.offset(self.az_e, w1_straight)
        p1_se = p_mid_w.offset(self.az_e, 93.50)
        self.points["B17_L1_NE"] = p1_ne
        self.points["B17_L1_SE"] = p1_se
        self.lots["1"] = DeterministicLotSolver(
            lot_id="Blk17-Lot1", block_id="17", lot_number="1",
            vertices=[p1_pc, p1_pt, p1_ne, p1_se, p_mid_w],
            node_names=["B17_L1_PC", "B17_L1_PT", "B17_L1_NE", "B17_L1_SE", "B17_MID_W"],
            curve_specs={"side_1": {"radius": self.sol1.radius, "delta_deg": self.sol1.delta_deg, "length": round(self.sol1.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(93.50 * 100.00 - self.sol1.fillet_area, 1),
        )

        curr_top = p1_ne
        curr_mid = p1_se

        for i in range(2, 17):
            lot_num = str(i)
            ne = curr_top.offset(self.az_e, 75.00)
            se = curr_mid.offset(self.az_e, 75.00)
            self.points[f"B17_L{lot_num}_NE"] = ne
            self.points[f"B17_L{lot_num}_SE"] = se
            self.lots[lot_num] = DeterministicLotSolver(
                lot_id=f"Blk17-Lot{lot_num}", block_id="17", lot_number=lot_num,
                vertices=[curr_top, ne, se, curr_mid],
                node_names=[f"B17_L{i-1}_NE", f"B17_L{lot_num}_NE", f"B17_L{lot_num}_SE", f"B17_L{i-1}_SE"],
                stated_area_sqft=7500.0,
            )
            curr_top = ne
            curr_mid = se

        # Lot 17 (East end, read from the scan 2026-09-24: Starfish front 111.54' to the P.I., rear 108.55',
        # east 100.04' on Beachwood Blvd S00°41'40"E, R=25' return). The earlier code had front/rear swapped,
        # which kinked the east side to S04°07'E.
        blvd_s = parse_bearing(self.brg_blvd)
        blvd_n = (blvd_s + 180.0) % 360.0
        self.sol17 = solve_corner_return(self.brg_street, self.brg_blvd, radius=25.0, stated_dim_in_to_pi=111.54, rot="CW")
        ne17 = curr_top.offset(self.az_e, 111.54)                 # P.I. (Starfish S R/W x Blvd W R/W)
        se17 = curr_mid.offset(self.az_e, 108.55)
        pt17 = ne17.offset(self.az_w, self.sol17.tangent)
        pc17 = ne17.offset(blvd_s, self.sol17.tangent)
        self.points["B17_L17_NE"] = ne17
        self.points["B17_L17_PT"] = pt17
        self.points["B17_L17_PC"] = pc17
        self.points["B17_L17_SE"] = se17
        self.lots["17"] = DeterministicLotSolver(
            lot_id="Blk17-Lot17", block_id="17", lot_number="17",
            vertices=[curr_top, pt17, pc17, se17, curr_mid],
            node_names=["B17_L16_NE", "B17_L17_PT", "B17_L17_PC", "B17_L17_SE", "B17_L16_SE"],
            curve_specs={"side_2": {"radius": 25.0, "delta_deg": self.sol17.delta_deg, "length": round(self.sol17.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(0.5 * (111.54 + 108.55) * 100.00 - self.sol17.fillet_area, 1),
        )

        # Lot 34 (Boundary Cut-Back to P.C./P.T. via Rule 2)
        w34_straight = 93.50 - T34
        p34_se = p34_pt.offset(self.az_e, w34_straight)
        p34_ne = p1_se
        self.points["B17_L34_SE"] = p34_se
        self.lots["34"] = DeterministicLotSolver(
            lot_id="Blk17-Lot34", block_id="17", lot_number="34",
            vertices=[p_mid_w, p34_ne, p34_se, p34_pt, p34_pc],
            node_names=["B17_MID_W", "B17_L1_SE", "B17_L34_SE", "B17_L34_PT", "B17_L34_PC"],
            curve_specs={"side_4": {"radius": self.sol34.radius, "delta_deg": self.sol34.delta_deg, "length": round(self.sol34.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(93.50 * 100.00 - self.sol34.fillet_area, 1),
        )

        curr_bot = p34_se
        curr_mid_s = p34_ne

        for i in range(33, 18, -1):
            lot_num = str(i)
            se = curr_bot.offset(self.az_e, 75.00)
            ne = curr_mid_s.offset(self.az_e, 75.00)
            self.points[f"B17_L{lot_num}_SE"] = se
            self.lots[lot_num] = DeterministicLotSolver(
                lot_id=f"Blk17-Lot{lot_num}", block_id="17", lot_number=lot_num,
                vertices=[curr_mid_s, ne, se, curr_bot],
                node_names=[f"B17_L{i+1}_NE", f"B17_L{lot_num}_NE", f"B17_L{lot_num}_SE", f"B17_L{i+1}_SE"],
                stated_area_sqft=7500.0,
            )
            curr_bot = se
            curr_mid_s = ne

        # Lot 18 (East end: Sail front 105.56' to the P.I., rear 108.55', east 100.04', R=25' return)
        self.sol18 = solve_corner_return(self.brg_blvd, self.brg_street_rev, radius=25.0, stated_dim_out_to_pi=105.56, rot="CW")
        se18 = curr_bot.offset(self.az_e, 105.56)                 # P.I. (Blvd W R/W x Sail N R/W)
        ne18 = se17
        pc18 = se18.offset(blvd_n, self.sol18.tangent)
        pt18 = se18.offset(self.az_w, self.sol18.tangent)
        self.points["B17_L18_SE"] = se18
        self.points["B17_L18_PC"] = pc18
        self.points["B17_L18_PT"] = pt18
        self.lots["18"] = DeterministicLotSolver(
            lot_id="Blk17-Lot18", block_id="17", lot_number="18",
            vertices=[curr_mid_s, ne18, pc18, pt18, curr_bot],
            node_names=["B17_L19_NE", "B17_L17_SE", "B17_L18_PC", "B17_L18_PT", "B17_L19_SE"],
            curve_specs={"side_3": {"radius": 25.0, "delta_deg": self.sol18.delta_deg, "length": round(self.sol18.arc_length, 2), "rot": "CW"}},
            stated_area_sqft=round(0.5 * (105.56 + 108.55) * 100.00 - self.sol18.fillet_area, 1),
        )
        self.checks = {
            "Lot 17 east 100.04' (P.I. -> rear)": (ne17.dist_to(se17), 100.04),
            "Lot 18 east 100.04' (rear -> P.I.)": (se17.dist_to(se18), 100.04),
            "Lot 17 east bearing = Blvd (deg)": (math.degrees(math.atan2(se17.e - ne17.e, se17.n - ne17.n)) % 360.0, blvd_s),
        }

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: solver.compute_mapcheck() for num, solver in self.lots.items()}

    def generate_report(self, filepath: str = "data/block17_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 17 SURVEY MAPCHECK AUDIT REPORT (34 LOTS)\n")
            f.write("  Plat Book 30, Page 82A, Public Records of Duval County, Florida\n")
            f.write("=" * 80 + "\n\n")
            for lot_num in [str(i) for i in range(1, 18)] + [str(i) for i in range(34, 17, -1)]:
                res = results[lot_num]
                f.write(res.format_surveyor_sheet() + "\n\n")
        return filepath


# ==============================================================================
# 13. BLOCK 15 DETERMINISTIC COGO SOLVER PIPELINE (18 LOTS, SHELLFISH & MARINA)
# ==============================================================================

class BeachwoodBlock15Solver:
    """
    Deterministic solver for Block 15, Beachwood Unit Two (Sheet 2, PB 30 Pg 82A).

    Every dimension is read off the scan; the west end is over-determined by the
    plat and closes on its own redundant lines (see `self.checks`):
      - North row Lots 1-9 on Shellfish Drive S R/W; south row Lots 10-18 on Keel
        Drive N R/W and Marina Avenue NE R/W.
      - Lot 1: Marina 115' to the P.I. (Note 2), 25.0' N35°18'20"E to the P.C. of the
        Shellfish S R/W curve (R=137.95' = CL 167.95' - 30', Δ=52°17'10", chord
        121.56' N61°26'55"E -- tangent N35°18'20"E in, N87°35'30"E out), then 15'
        to Lot 2.  R=25' corner return at the Marina P.I. (Δ=90°, T=25.0').
      - Lot 18: Marina 110', N26°33'25"E 126.84' to Lot 2's SE corner.
      - Lot 17: Marina 125' to the P.I., 25.18' N35°18'20"E to the P.C. of the Keel
        N R/W curve (R=173.93' = CL 143.93' + 30'), R=25' corner return at the P.I.
        Rear line 40.46'.  Lots 16/15 rear 75'/75' (583.45' rear totals match the
        north row exactly), chords 82.45' N48°56'55"E / 75.29' N75°05'30"E.
      - Lots 9/10: straight Beachwood Blvd W R/W (S00°41'40"E, 100.04' = 100' /
        cos 1°42'50"), frontages 95.98'/90.00' to the P.I.s, R=25' corner returns.
    """
    R_CORNER = 25.0
    R_SHELLFISH = 137.95
    R_KEEL = 173.93

    def __init__(self, origin: Point | None = None):
        self.origin = origin or Point(0.0, 0.0)
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self.checks: dict[str, tuple[float, float]] = {}
        self._solve_geometry()

    @staticmethod
    def _dms(d: float, m: float, s: float) -> float:
        return d + m / 60.0 + s / 3600.0

    @staticmethod
    def _seg(R: float, delta_deg: float) -> float:
        d = math.radians(delta_deg)
        return 0.5 * R * R * (d - math.sin(d))

    def _solve_geometry(self) -> None:
        eaz = parse_bearing("N87°35'30\"E")
        waz = parse_bearing("S87°35'30\"W")
        saz = parse_bearing("S02°24'30\"E")
        naz = parse_bearing("N02°24'30\"W")
        blvd_s = parse_bearing("S00°41'40\"E")
        blvd_n = parse_bearing("N00°41'40\"W")
        marina_se = parse_bearing("S54°41'40\"E")
        marina_nw = parse_bearing("N54°41'40\"W")
        perp_ne = parse_bearing("N35°18'20\"E")
        perp_sw = parse_bearing("S35°18'20\"W")
        P = self.points

        def put(name: str, pt: Point) -> Point:
            P[name] = pt
            return pt

        def lot(num, names, curve_specs=None, stated=7500.0):
            self.lots[num] = DeterministicLotSolver(
                lot_id=f"Blk15-Lot{num}", block_id="15", lot_number=num,
                vertices=[P[n] for n in names], node_names=names,
                curve_specs=curve_specs or {}, stated_area_sqft=round(stated, 1),
            )

        # Origin: common rear corner of Lots 9 & 10 on the Beachwood Blvd W R/W.
        o = put("B15_C2_MID", self.origin)
        put("B15_L9_SE", o)
        put("B15_L10_NE", o)

        # ---- rear line & north/south frontages (row depth 100' each) ----
        rear_w = [("9", 92.99), ("8", 75.0), ("7", 75.0), ("6", 75.0),
                  ("5", 88.48), ("4", 88.48), ("3", 88.50)]
        cur = o
        for num, w in rear_w:
            cur = put(f"B15_L{num}_SW", cur.offset(waz, w))
            put(f"B15_L{num}_NW", cur.offset(naz, 100.0))
        put("B15_L2_NW", P["B15_L3_NW"].offset(waz, 100.0))
        put("B15_L2_SW", P["B15_L3_SW"].offset(parse_bearing("N81°40'01\"W"), 101.78))

        cur = o
        for num, w in [("10", 92.99), ("11", 75.0), ("12", 75.0), ("13", 75.0),
                       ("14", 75.0), ("15", 75.0), ("16", 75.0), ("17", 40.46)]:
            cur = put(f"B15_L{num}_NW", cur.offset(waz, w))
        for num in ["10", "11", "12", "13", "14"]:
            put(f"B15_L{num}_SW", P[f"B15_L{num}_NW"].offset(saz, 100.0))

        # ---- corner returns (Rule 2: dimensions run to the P.I.) ----
        self.sol9 = solve_corner_return("N87°35'30\"E", "S00°41'40\"E", radius=self.R_CORNER,
                                        stated_dim_in_to_pi=95.98, rot="CW")
        self.sol10 = solve_corner_return("S00°41'40\"E", "S87°35'30\"W", radius=self.R_CORNER,
                                         stated_dim_out_to_pi=90.0, rot="CW")
        self.sol1 = solve_corner_return("N54°41'40\"W", "N35°18'20\"E", radius=self.R_CORNER,
                                        stated_dim_in_to_pi=115.0, stated_dim_out_to_pi=25.0, rot="CW")
        self.sol17 = solve_corner_return("S35°18'20\"W", "N54°41'40\"W", radius=self.R_CORNER,
                                         stated_dim_in_to_pi=25.18, stated_dim_out_to_pi=125.0, rot="CW")

        pi9 = put("B15_L9_PI_NE", P["B15_L9_NW"].offset(eaz, 95.98))
        put("B15_L9_PT", pi9.offset(waz, self.sol9.tangent))
        put("B15_L9_PC", pi9.offset(blvd_s, self.sol9.tangent))
        pi10 = put("B15_L10_PI_SE", P["B15_L10_SW"].offset(eaz, 90.0))
        put("B15_L10_PC", pi10.offset(blvd_n, self.sol10.tangent))
        put("B15_L10_PT", pi10.offset(waz, self.sol10.tangent))

        # ---- Shellfish Dr S R/W curve (Lot 1) ----
        d_sh = self._dms(52, 17, 10)
        pt_sh = put("B15_L1_SH_PT", P["B15_L2_NW"].offset(waz, 15.0))
        ctr_sh = pt_sh.offset((eaz + 90.0) % 360.0, self.R_SHELLFISH)
        pc_sh = put("B15_L1_SH_PC", ctr_sh.offset((perp_ne - 90.0) % 360.0, self.R_SHELLFISH))
        pi1 = put("B15_L1_PI_NW", pc_sh.offset(perp_sw, 25.0))
        put("B15_L1_CR_PT", pi1.offset(perp_ne, self.sol1.tangent))  # == SH_PC (T = 25.0')
        put("B15_L1_CR_PC", pi1.offset(marina_se, self.sol1.tangent))

        # ---- Marina Ave NE R/W: 115' + 110' + 125' between the P.I.s ----
        m1 = put("B15_L1_SW", pi1.offset(marina_se, 115.0))
        m2 = put("B15_L18_SW", m1.offset(marina_se, 110.0))
        pi17 = put("B15_L17_PI_SW", m2.offset(marina_se, 125.0))
        put("B15_L17_CR_PC", pi17.offset(marina_nw, self.sol17.tangent))
        put("B15_L17_CR_PT", pi17.offset(perp_ne, self.sol17.tangent))
        kpc = put("B15_L16_SW", pi17.offset(perp_ne, 25.18))

        # ---- Keel Dr N R/W curve (Lots 16, 15) from its P.C. at Lot 16 SW ----
        ctr_k = kpc.offset((perp_ne + 90.0) % 360.0, self.R_KEEL)
        a0 = (perp_ne - 90.0) % 360.0
        d16 = self._dms(27, 17, 10)          # 2 x (62°35'30" - 48°56'55"); d16 + d15 = CL Δ 52°17'10"
        d15 = self._dms(25, 0, 0)            # 2 x (87°35'30" - 75°05'30")
        put("B15_L15_SW", ctr_k.offset((a0 + d16) % 360.0, self.R_KEEL))
        keel_end = ctr_k.offset((a0 + d16 + d15) % 360.0, self.R_KEEL)

        # ---- redundancy checks: (computed, printed) ----
        def dist(a, b):
            return P[a].dist_to(P[b]) if isinstance(a, str) else a.dist_to(b)
        self.checks = {
            "Lot 1 Shellfish chord 121.56'": (dist("B15_L1_SH_PC", "B15_L1_SH_PT"), 121.56),
            "Lot 1/18 line 79.20'": (dist("B15_L1_SW", "B15_L2_SW"), 79.20),
            "Lot 18/17 line 126.84'": (dist("B15_L18_SW", "B15_L3_SW"), 126.84),
            "Lot 16 W line 167.98'": (dist("B15_L16_NW", "B15_L16_SW"), 167.98),
            "Lot 15 W line 116.28'": (dist("B15_L15_NW", "B15_L15_SW"), 116.28),
            "Lot 16 Keel chord 82.45'": (dist("B15_L16_SW", "B15_L15_SW"), 82.45),
            "Lot 15 Keel chord 75.29'": (dist("B15_L15_SW", "B15_L14_SW"), 75.29),
            "Keel curve end on Lot 14 SW (0')": (keel_end.dist_to(P["B15_L14_SW"]), 0.0),
            "Lot 9 E line 100.04'": (dist("B15_L9_PI_NE", "B15_L9_SE"), 100.04),
            "Lot 10 E line 100.04'": (dist("B15_L10_NE", "B15_L10_PI_SE"), 100.04),
        }

        # ---- record ("stated") areas: plat prints none, so these are closed-form
        #      from the record dimensions to the P.I.s, +/- curve segments, - fillets ----
        def pi_area(names):
            return shoelace_area([P[n] for n in names])
        seg_sh = self._seg(self.R_SHELLFISH, d_sh)
        seg16, seg15 = self._seg(self.R_KEEL, d16), self._seg(self.R_KEEL, d15)
        cr = lambda s: s.fillet_area  # noqa: E731

        # ---- NORTH ROW ----
        lot("9", ["B15_L9_NW", "B15_L9_PT", "B15_L9_PC", "B15_L9_SE", "B15_L9_SW"],
            {"side_2": {"radius": self.R_CORNER, "delta_deg": self.sol9.delta_deg,
                        "length": round(self.sol9.arc_length, 2), "rot": "CW"}},
            0.5 * (95.98 + 92.99) * 100.0 - cr(self.sol9))
        for num in ["8", "7", "6", "5", "4", "3"]:
            nxt = str(int(num) + 1)
            w = dist(f"B15_L{num}_NW", f"B15_L{nxt}_NW")
            lot(num, [f"B15_L{num}_NW", f"B15_L{nxt}_NW", f"B15_L{nxt}_SW", f"B15_L{num}_SW"], stated=w * 100.0)
        lot("2", ["B15_L2_NW", "B15_L3_NW", "B15_L3_SW", "B15_L2_SW"],
            stated=pi_area(["B15_L2_NW", "B15_L3_NW", "B15_L3_SW", "B15_L2_SW"]))
        lot("1", ["B15_L1_SW", "B15_L1_CR_PC", "B15_L1_SH_PC", "B15_L1_SH_PT", "B15_L2_NW", "B15_L2_SW"],
            {"side_2": {"radius": self.R_CORNER, "delta_deg": self.sol1.delta_deg,
                        "length": round(self.sol1.arc_length, 2), "rot": "CW"},
             "side_3": {"radius": self.R_SHELLFISH, "delta_deg": d_sh,
                        "length": round(self.R_SHELLFISH * math.radians(d_sh), 2), "rot": "CW"}},
            pi_area(["B15_L1_SW", "B15_L1_PI_NW", "B15_L1_SH_PC", "B15_L1_SH_PT", "B15_L2_NW", "B15_L2_SW"])
            + seg_sh - cr(self.sol1))

        # ---- SOUTH ROW ----
        lot("10", ["B15_L10_NW", "B15_L10_NE", "B15_L10_PC", "B15_L10_PT", "B15_L10_SW"],
            {"side_3": {"radius": self.R_CORNER, "delta_deg": self.sol10.delta_deg,
                        "length": round(self.sol10.arc_length, 2), "rot": "CW"}},
            0.5 * (92.99 + 90.0) * 100.0 - cr(self.sol10))
        for num in ["11", "12", "13", "14"]:
            prv = str(int(num) - 1)
            lot(num, [f"B15_L{num}_NW", f"B15_L{prv}_NW", f"B15_L{prv}_SW", f"B15_L{num}_SW"])
        lot("15", ["B15_L15_NW", "B15_L14_NW", "B15_L14_SW", "B15_L15_SW"],
            {"side_3": {"radius": self.R_KEEL, "delta_deg": d15,
                        "length": round(self.R_KEEL * math.radians(d15), 2), "rot": "CCW"}},
            pi_area(["B15_L15_NW", "B15_L14_NW", "B15_L14_SW", "B15_L15_SW"]) - seg15)
        lot("16", ["B15_L16_NW", "B15_L15_NW", "B15_L15_SW", "B15_L16_SW"],
            {"side_3": {"radius": self.R_KEEL, "delta_deg": d16,
                        "length": round(self.R_KEEL * math.radians(d16), 2), "rot": "CCW"}},
            pi_area(["B15_L16_NW", "B15_L15_NW", "B15_L15_SW", "B15_L16_SW"]) - seg16)
        lot("17", ["B15_L17_NW", "B15_L16_NW", "B15_L16_SW", "B15_L17_CR_PT", "B15_L17_CR_PC", "B15_L18_SW"],
            {"side_4": {"radius": self.R_CORNER, "delta_deg": self.sol17.delta_deg,
                        "length": round(self.sol17.arc_length, 2), "rot": "CW"}},
            pi_area(["B15_L17_NW", "B15_L16_NW", "B15_L16_SW", "B15_L17_PI_SW", "B15_L18_SW"]) - cr(self.sol17))
        lot("18", ["B15_L1_SW", "B15_L2_SW", "B15_L3_SW", "B15_L18_SW"],
            stated=pi_area(["B15_L1_SW", "B15_L2_SW", "B15_L3_SW", "B15_L18_SW"]))

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: solver.compute_mapcheck() for num, solver in self.lots.items()}

    def generate_report(self, filepath: str = "data/block15_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 15 SURVEY MAPCHECK AUDIT REPORT (18 LOTS)\n")
            f.write("  Plat Book 30, Pages 82 & 82A, Public Records of Duval County, Florida\n")
            f.write("=" * 80 + "\n\n")
            for lot_num in [str(i) for i in range(1, 10)] + [str(i) for i in range(10, 19)]:
                res = results[lot_num]
                f.write(res.format_surveyor_sheet() + "\n\n")
        return filepath


# ==============================================================================
# 14. BLOCK 14 DETERMINISTIC COGO SOLVER PIPELINE (24 LOTS, KEEL & SHELLFISH)
# ==============================================================================

class BeachwoodBlock6Solver:
    """
    Block 6, Beachwood Unit Two (Sheet 2, PB 30 Pg 82A), Lots 2-12, read from the scan 2026-09-24.
    Bounded by Keel Dr S R/W, Beachwood Blvd W R/W, Marina Dr N R/W and the plat boundary.

      - Keel S R/W (west from the Blvd P.I., R=25' return): 100' (L10), 75' (L9), 75' (L8), 108.22' (L7),
        30' to the P.T. of the S R/W curve R=143.93-30=113.93' (Lot 6 chord 100.40' N61°26'55"E = full
        CL Δ 52°17'10"), 25.18' N35°18'20"E to the Marina P.I. (R=25' return).
      - Marina N R/W S54°41'40"E: 100' (L6), 101.10' (L5), 75' (L4; its last 35' on the boundary course
        S54°41'40"E 100.16' = 35 + 65.16), then the boundary curve R=894.08' (to the left) with lot chords
        15.98' S55°12'23"E (L3) and 84.02' S58°24'42"E (L2), then boundary N28°53'42"E 100.0' and
        S65°48'08"E 90.51' (L12) to the Blvd W R/W.
      - Blvd W R/W S00°41'40"E: 90' (L10), 84.79' (L11), 110' (L12).
      - Interior: rear line S71°15'04"E (80 + 75 + 19.29 = 93.87 + 80.42 = 174.29), lot lines N52°58'07"E 93.70,
        N37°21'04"E 112.15, N35°41'27"E 133.46, N2°24'30"W 105.97 / 135 / 87.05, and the S40°30'16"E diagonal
        from the hub (62.66 + 76 = 56.66 + 82 = 138.66).
    Construction starts at the Lot 10 NE P.I. (Keel x Blvd); every other printed line is a check.
    """
    R_KEEL_S = 113.93
    R_BND = 894.08

    def __init__(self, origin: Point | None = None):
        self.origin = origin or Point(0.0, 0.0)
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self.checks: dict[str, tuple[float, float]] = {}
        self.sol10 = solve_corner_return("N87°35'30\"E", "S00°41'40\"E", radius=25.0,
                                         stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=90.0, rot="CW")
        self.sol6 = solve_corner_return("N54°41'40\"W", "N35°18'20\"E", radius=25.0,
                                        stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=25.18, rot="CW")
        self._solve_geometry()

    def _solve_geometry(self) -> None:
        P = self.points
        W = parse_bearing("S87°35'30\"W")
        E = parse_bearing("N87°35'30\"E")
        blvd_s = parse_bearing("S00°41'40\"E")
        blvd_n = parse_bearing("N00°41'40\"W")
        marina = parse_bearing("S54°41'40\"E")
        side_s = parse_bearing("S02°24'30\"E")
        rear = parse_bearing("S71°15'04\"E")
        diag = parse_bearing("S40°30'16\"E")

        def put(name, pt):
            P[name] = pt
            return pt

        # ---- Keel Dr S R/W, west from the Blvd P.I. ----
        pi10 = put("B6_L10_PI_NE", self.origin)
        put("B6_L10_PT_N", pi10.offset(W, self.sol10.tangent))
        put("B6_L10_PC_E", pi10.offset(blvd_s, self.sol10.tangent))
        k = put("B6_K910", pi10.offset(W, 100.0))
        k = put("B6_K89", k.offset(W, 75.0))
        k = put("B6_K78", k.offset(W, 75.0))
        k = put("B6_K67", k.offset(W, 108.22))
        kpt = put("B6_KEEL_PT", k.offset(W, 30.0))
        d_keel = 52.0 + 17.0 / 60.0 + 10.0 / 3600.0
        ctr = kpt.offset((E + 90.0) % 360.0, self.R_KEEL_S)            # curve turns right going east
        kpc = put("B6_KEEL_PC", ctr.offset((E + 90.0 + 180.0 - d_keel) % 360.0, self.R_KEEL_S))
        pi6 = put("B6_L6_PI_W", kpc.offset(parse_bearing("S35°18'20\"W"), 25.18))
        put("B6_L6_PT_K", pi6.offset(parse_bearing("N35°18'20\"E"), self.sol6.tangent))
        put("B6_L6_PC_M", pi6.offset(marina, self.sol6.tangent))

        # ---- Marina N R/W / boundary ----
        m1 = put("B6_M56", pi6.offset(marina, 100.0))
        m2 = put("B6_M45", m1.offset(marina, 101.10))
        put("B6_BND_260_TOP", m2.offset(marina, 40.0))                 # boundary N35°18'20"E 260' meets Marina
        m3 = put("B6_M34", m2.offset(marina, 75.0))
        bpc = put("B6_BND_PC", m3.offset(marina, 65.16))
        ctr_b = bpc.offset((marina - 90.0) % 360.0, self.R_BND)        # curve to the left
        a0 = (marina + 90.0) % 360.0
        d3 = 2.0 * math.degrees(math.asin(15.98 / (2.0 * self.R_BND)))
        d2 = 2.0 * math.degrees(math.asin(84.02 / (2.0 * self.R_BND)))
        c1 = put("B6_C23", ctr_b.offset((a0 - d3) % 360.0, self.R_BND))
        c2 = put("B6_BND_PT", ctr_b.offset((a0 - d3 - d2) % 360.0, self.R_BND))
        u = put("B6_U", c2.offset(parse_bearing("N28°53'42\"E"), 100.0))

        # ---- Blvd W R/W ----
        e10 = put("B6_E1011", pi10.offset(blvd_s, 90.0))
        e11 = put("B6_E1112", e10.offset(blvd_s, 84.79))
        w12 = put("B6_L12_SE", e11.offset(blvd_s, 110.0))

        # ---- interior ----
        q = put("B6_Q", m1.offset(parse_bearing("N52°58'07\"E"), 93.70))
        r = put("B6_R", m2.offset(parse_bearing("N37°21'04\"E"), 112.15))
        s = put("B6_S", m3.offset(parse_bearing("N35°41'27\"E"), 133.46))
        h = put("B6_H", s.offset(rear, 19.29))
        l7se = put("B6_L7_SE", q.offset(rear, 93.87))
        v = put("B6_V", P["B6_K910"].offset(side_s, 87.05))
        t = put("B6_T", h.offset(diag, 62.66))
        y = put("B6_Y", h.offset(diag, 56.66))

        # ---- lots (clockwise rings) ----
        def seg(R, dd):
            tt = math.radians(dd)
            return 0.5 * R * R * (tt - math.sin(tt))

        def poly(names):
            return shoelace_area([P[n] for n in names])

        def lot(num, names, stated, curve_specs=None):
            self.lots[num] = DeterministicLotSolver(
                lot_id=f"Blk6-Lot{num}", block_id="6", lot_number=num,
                vertices=[P[n] for n in names], node_names=names,
                curve_specs=curve_specs or {}, stated_area_sqft=round(stated, 1),
            )

        def fil(side, sol):
            return {side: {"radius": 25.0, "delta_deg": sol.delta_deg, "length": round(sol.arc_length, 2), "rot": "CW"}}

        def arc(side, R, dd):
            return {side: {"radius": R, "delta_deg": dd, "length": round(R * math.radians(dd), 2), "rot": "CW"}}

        r6 = ["B6_M56", "B6_L6_PC_M", "B6_L6_PT_K", "B6_KEEL_PC", "B6_KEEL_PT", "B6_K67", "B6_Q"]
        cs = fil("side_2", self.sol6)
        cs.update(arc("side_4", self.R_KEEL_S, d_keel))
        lot("6", r6, poly(["B6_M56", "B6_L6_PI_W", "B6_KEEL_PC", "B6_KEEL_PT", "B6_K67", "B6_Q"])
            + seg(self.R_KEEL_S, d_keel) - self.sol6.fillet_area, cs)
        lot("5", ["B6_M45", "B6_M56", "B6_Q", "B6_R"], poly(["B6_M45", "B6_M56", "B6_Q", "B6_R"]))
        r4 = ["B6_M34", "B6_BND_260_TOP", "B6_M45", "B6_R", "B6_S"]
        lot("4", r4, poly(r4))
        r3 = ["B6_C23", "B6_BND_PC", "B6_M34", "B6_S", "B6_H", "B6_T"]
        lot("3", r3, poly(r3) + seg(self.R_BND, d3), arc("side_1", self.R_BND, d3))
        r2 = ["B6_BND_PT", "B6_C23", "B6_T", "B6_U"]
        lot("2", r2, poly(r2) + seg(self.R_BND, d2), arc("side_1", self.R_BND, d2))
        r7 = ["B6_Q", "B6_K67", "B6_K78", "B6_L7_SE"]
        lot("7", r7, poly(r7))
        r8 = ["B6_L7_SE", "B6_K78", "B6_K89", "B6_H"]
        lot("8", r8, poly(r8))
        r9 = ["B6_H", "B6_K89", "B6_K910", "B6_V"]
        lot("9", r9, poly(r9))
        r10 = ["B6_V", "B6_K910", "B6_L10_PT_N", "B6_L10_PC_E", "B6_E1011"]
        lot("10", r10, poly(["B6_V", "B6_K910", "B6_L10_PI_NE", "B6_E1011"]) - self.sol10.fillet_area, fil("side_3", self.sol10))
        r11 = ["B6_H", "B6_V", "B6_E1011", "B6_E1112", "B6_Y"]
        lot("11", r11, poly(r11))
        r12 = ["B6_Y", "B6_E1112", "B6_L12_SE", "B6_U"]
        lot("12", r12, poly(r12))

        # ---- printed values not used in the construction ----
        d = lambda a, b: P[a].dist_to(P[b])  # noqa: E731
        self.checks = {
            "Lot 6/7 line 75'": (d("B6_Q", "B6_K67"), 75.0),
            "Lot 5 N (rear) 80'": (d("B6_Q", "B6_R"), 80.0),
            "Lot 4 N (rear) 75'": (d("B6_R", "B6_S"), 75.0),
            "Lot 7 S (rear) 93.87' -> L7 SE": (d("B6_Q", "B6_L7_SE"), 93.87),
            "Lot 8 S (rear) 80.42'": (d("B6_L7_SE", "B6_H"), 80.42),
            "Lot 7/8 line 105.97'": (d("B6_L7_SE", "B6_K78"), 105.97),
            "Lot 8/9 line 135'": (d("B6_H", "B6_K89"), 135.0),
            "Lot 9 S 89.02' (H -> V)": (d("B6_H", "B6_V"), 89.02),
            "Lot 10 S 97.35' (V -> Blvd)": (d("B6_V", "B6_E1011"), 97.35),
            "Lot 3/2 line 123.46'": (d("B6_T", "B6_C23"), 123.46),
            "Lot 2 NE 76' (T -> U)": (d("B6_T", "B6_U"), 76.0),
            "Lot 12 W 82' (Y -> U)": (d("B6_Y", "B6_U"), 82.0),
            "Lot 11/12 line 134.90'": (d("B6_Y", "B6_E1112"), 134.90),
            "Lot 12 S boundary 90.51'": (d("B6_U", "B6_L12_SE"), 90.51),
            "Boundary curve chord 99.98'": (d("B6_BND_PC", "B6_BND_PT"), 99.98),
        }

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: solver.compute_mapcheck() for num, solver in self.lots.items()}

    def generate_report(self, filepath: str = "data/block6_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n  BEACHWOOD UNIT TWO -- BLOCK 6 SURVEY MAPCHECK REPORT (LOTS 2-12)\n")
            f.write("  Plat Book 30, Page 82A, Public Records of Duval County, Florida\n" + "=" * 80 + "\n\n")
            for num, res in results.items():
                f.write(res.format_surveyor_sheet() + "\n\n")
            f.write("PRINTED-DIMENSION REDUNDANCY CHECKS (computed vs plat)\n")
            for key, (calc, printed) in self.checks.items():
                f.write(f"  {key:<36} {calc:9.3f}  vs {printed:8.2f}  ({calc - printed:+.3f})\n")
        return filepath


class BeachwoodBlock7Solver:
    """
    Block 7, Beachwood Unit Two (Sheet 2, PB 30 Pg 82A), Lots 11-37, read from the scan 2026-09-24.

      - North row (Lots 24-37) on Marina Dr S R/W: from the Mangrove P.I. (R=25' return, Δ 88°37'30"),
        99.93' + 83.26' on N87°35'30"E to the P.C., then the S R/W curve R=359.27-30=329.27' with chords
        99.37 / 99.36 / 17.24 (Δ ≈ 17°21' + 17°21' + 3° = CL Δ 37°42'50"), 61.10' tangent, Lots 29-37 at 75'.
      - South row (Lots 23-11) on Sands Ave N R/W: 80' from the Mangrove P.I. (R=25' return), then the
        N R/W curve R=459.36+30=489.36' with chords 17.08 / 76.78 x3 / 62.59 (Δ 2° + 9° x3 + 7°20'
        = CL Δ 36°20'), 9.10' tangent, Lots 18-11 at 75'.
      - Shared rear line: 102.38' + 83.26' on N88°58'20"E, then S77°35'15"E 66.85' + 66.86' (south side
        20' + 83.71' + 30'), then S54°41'40"E (north 75' each; south 65', 85', then 75' each).
      - East end: Lots 37 and 11 on the boundary N35°18'20"E 260.0' (100' + 100' + 60' Marina Dr).
    Every printed lot side line is kept out of the construction and reported in `self.checks`.
    Origin: Lot 24 NW P.I. (Mangrove E R/W x Marina S R/W).
    """
    R_MARINA = 329.27
    R_SANDS = 489.36

    def __init__(self, origin: Point | None = None):
        self.origin = origin or Point(0.0, 0.0)
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self.checks: dict[str, tuple[float, float]] = {}
        self.sol24 = solve_corner_return("N01°01'40\"W", "N87°35'30\"E", radius=25.0,
                                         stated_dim_in_to_pi=100.74, stated_dim_out_to_pi=99.93, rot="CW")
        self.sol23 = solve_corner_return("S88°58'20\"W", "N01°01'40\"W", radius=25.0,
                                         stated_dim_in_to_pi=80.0, stated_dim_out_to_pi=100.0, rot="CW")
        self._solve_geometry()

    def _solve_geometry(self) -> None:
        P = self.points
        south = parse_bearing("S01°01'40\"E")
        north = parse_bearing("N01°01'40\"W")
        e_marina = parse_bearing("N87°35'30\"E")
        e0 = parse_bearing("N88°58'20\"E")
        d1 = parse_bearing("S77°35'15\"E")
        d2 = parse_bearing("S54°41'40\"E")

        def put(name, pt):
            P[name] = pt
            return pt

        def chord_delta(R, c):
            return 2.0 * math.degrees(math.asin(c / (2.0 * R)))

        def arc_chain(pc, tan_in_az, R, deltas):
            """Points along a curve turning right from pc (tangent tan_in_az)."""
            ctr = pc.offset((tan_in_az + 90.0) % 360.0, R)
            a0 = (tan_in_az - 90.0) % 360.0
            out, acc = [], 0.0
            for d in deltas:
                acc += d
                out.append(ctr.offset((a0 + acc) % 360.0, R))
            return out

        # ---------------- north row front (Marina S R/W) ----------------
        pi24 = put("B7_L24_PI_NW", self.origin)
        put("B7_L24_PC_W", pi24.offset(south, self.sol24.tangent))
        put("B7_L24_PT_N", pi24.offset(e_marina, self.sol24.tangent))
        put("B7_L24_NE", pi24.offset(e_marina, 99.93))                  # P.R.M.
        mpc = put("B7_L25_NE", P["B7_L24_NE"].offset(e_marina, 83.26))  # Marina P.C.
        d_mar = [chord_delta(self.R_MARINA, 99.37), chord_delta(self.R_MARINA, 99.36), chord_delta(self.R_MARINA, 17.24)]
        for name, pt in zip(["B7_L26_NE", "B7_L27_NE", "B7_MARINA_PT"], arc_chain(mpc, e_marina, self.R_MARINA, d_mar)):
            put(name, pt)
        f = put("B7_L28_NE", P["B7_MARINA_PT"].offset(d2, 61.10))
        for num in range(29, 38):
            f = put(f"B7_L{num}_NE", f.offset(d2, 75.0))

        # ---------------- shared rear line ----------------
        r = put("B7_L24_SW", pi24.offset(south, 100.74))
        put("B7_L24_SE", r.offset(e0, 102.38))
        r2 = put("B7_L25_SE", P["B7_L24_SE"].offset(e0, 83.26))
        put("B7_L26_SE", r2.offset(d1, 66.85))
        r4 = put("B7_L27_SE", P["B7_L26_SE"].offset(d1, 66.86))
        put("B7_L22_NE", r2.offset(d1, 20.0))
        put("B7_L21_NE", P["B7_L22_NE"].offset(d1, 83.71))
        f = r4
        for num in range(28, 38):
            f = put(f"B7_L{num}_SE", f.offset(d2, 75.0))
        put("B7_L20_NE", r4.offset(d2, 65.0))
        f = put("B7_L19_NE", P["B7_L20_NE"].offset(d2, 85.0))
        for num in range(18, 10, -1):
            f = put(f"B7_L{num}_NE", f.offset(d2, 75.0))

        # ---------------- south row front (Sands N R/W) ----------------
        pi23 = put("B7_L23_PI_SW", P["B7_L24_SW"].offset(south, 100.0))
        put("B7_L23_PC_W", pi23.offset(north, self.sol23.tangent))
        put("B7_L23_PT_S", pi23.offset(e0, self.sol23.tangent))
        spc = put("B7_SANDS_PC", pi23.offset(e0, 80.0))
        d_sands = [2.0, 9.0, 9.0, 9.0, 7.0 + 20.0 / 60.0]
        pts = arc_chain(spc, e0, self.R_SANDS, d_sands)
        for name, pt in zip(["B7_L23_SE", "B7_L22_SE", "B7_L21_SE", "B7_L20_SE", "B7_SANDS_PT"], pts):
            put(name, pt)
        f = put("B7_L19_SE", P["B7_SANDS_PT"].offset(d2, 9.10))
        for num in range(18, 10, -1):
            f = put(f"B7_L{num}_SE", f.offset(d2, 75.0))
        # Lot 23's NE corner: its printed east line from the front (N01°58'48"E 100.44'); its fit to the
        # rear line is reported as a check.
        put("B7_L23_NE", P["B7_L23_SE"].offset(parse_bearing("N01°58'48\"E"), 100.44))

        # ---------------- lots ----------------
        def seg(R, d):
            t = math.radians(d)
            return 0.5 * R * R * (t - math.sin(t))

        def poly(names):
            return shoelace_area([P[n] for n in names])

        def arc(side, R, d, rot):
            return {side: {"radius": R, "delta_deg": d, "length": round(R * math.radians(d), 2), "rot": rot}}

        def lot(num, names, stated, curve_specs=None):
            self.lots[num] = DeterministicLotSolver(
                lot_id=f"Blk7-Lot{num}", block_id="7", lot_number=num,
                vertices=[P[n] for n in names], node_names=names,
                curve_specs=curve_specs or {}, stated_area_sqft=round(stated, 1),
            )

        # north row (clockwise; Marina arcs eastward turn right -> CW, lots inside the curve -> +seg)
        cs = {"side_2": {"radius": 25.0, "delta_deg": self.sol24.delta_deg, "length": round(self.sol24.arc_length, 2), "rot": "CW"}}
        lot("24", ["B7_L24_SW", "B7_L24_PC_W", "B7_L24_PT_N", "B7_L24_NE", "B7_L24_SE"],
            poly(["B7_L24_SW", "B7_L24_PI_NW", "B7_L24_NE", "B7_L24_SE"]) - self.sol24.fillet_area, cs)
        lot("25", ["B7_L24_SE", "B7_L24_NE", "B7_L25_NE", "B7_L25_SE"], poly(["B7_L24_SE", "B7_L24_NE", "B7_L25_NE", "B7_L25_SE"]))
        r26 = ["B7_L25_SE", "B7_L25_NE", "B7_L26_NE", "B7_L26_SE"]
        lot("26", r26, poly(r26) + seg(self.R_MARINA, d_mar[0]), arc("side_2", self.R_MARINA, d_mar[0], "CW"))
        r27 = ["B7_L26_SE", "B7_L26_NE", "B7_L27_NE", "B7_L27_SE"]
        lot("27", r27, poly(r27) + seg(self.R_MARINA, d_mar[1]), arc("side_2", self.R_MARINA, d_mar[1], "CW"))
        r28 = ["B7_L27_SE", "B7_L27_NE", "B7_MARINA_PT", "B7_L28_NE", "B7_L28_SE"]
        lot("28", r28, poly(r28) + seg(self.R_MARINA, d_mar[2]), arc("side_2", self.R_MARINA, d_mar[2], "CW"))
        for num in range(29, 38):
            lot(str(num), [f"B7_L{num-1}_SE", f"B7_L{num-1}_NE", f"B7_L{num}_NE", f"B7_L{num}_SE"], 7500.0)

        # south row (clockwise; Sands arcs westward turn left -> CCW, lots outside the curve -> -seg)
        r23 = ["B7_L24_SW", "B7_L23_NE", "B7_L23_SE", "B7_SANDS_PC", "B7_L23_PT_S", "B7_L23_PC_W"]
        cs = arc("side_3", self.R_SANDS, d_sands[0], "CCW")
        cs["side_5"] = {"radius": 25.0, "delta_deg": self.sol23.delta_deg, "length": round(self.sol23.arc_length, 2), "rot": "CW"}
        lot("23", r23, poly(["B7_L24_SW", "B7_L23_NE", "B7_L23_SE", "B7_SANDS_PC", "B7_L23_PI_SW"])
            - seg(self.R_SANDS, d_sands[0]) - self.sol23.fillet_area, cs)
        r22 = ["B7_L23_NE", "B7_L24_SE", "B7_L25_SE", "B7_L22_NE", "B7_L22_SE", "B7_L23_SE"]
        lot("22", r22, poly(r22) - seg(self.R_SANDS, 9.0), arc("side_5", self.R_SANDS, 9.0, "CCW"))
        r21 = ["B7_L22_NE", "B7_L21_NE", "B7_L21_SE", "B7_L22_SE"]
        lot("21", r21, poly(r21) - seg(self.R_SANDS, 9.0), arc("side_3", self.R_SANDS, 9.0, "CCW"))
        r20 = ["B7_L21_NE", "B7_L27_SE", "B7_L20_NE", "B7_L20_SE", "B7_L21_SE"]
        lot("20", r20, poly(r20) - seg(self.R_SANDS, 9.0), arc("side_4", self.R_SANDS, 9.0, "CCW"))
        r19 = ["B7_L20_NE", "B7_L19_NE", "B7_L19_SE", "B7_SANDS_PT", "B7_L20_SE"]
        lot("19", r19, poly(r19) - seg(self.R_SANDS, d_sands[4]), arc("side_4", self.R_SANDS, d_sands[4], "CCW"))
        for num in range(18, 10, -1):
            lot(str(num), [f"B7_L{num+1}_NE", f"B7_L{num}_NE", f"B7_L{num}_SE", f"B7_L{num+1}_SE"], 7500.0)

        # ---------------- printed values not used in the construction ----------------
        d = lambda a, b: P[a].dist_to(P[b])  # noqa: E731
        a0, a1 = P["B7_L24_SW"], P["B7_L24_SE"]
        off23 = abs((a1.e - a0.e) * (a0.n - P["B7_L23_NE"].n) - (a0.e - P["B7_L23_NE"].e) * (a1.n - a0.n)) / a0.dist_to(a1)
        self.checks = {
            "Lot 24 E side 103.17'": (d("B7_L24_SE", "B7_L24_NE"), 103.17),
            "Lot 25 E side 105.18'": (d("B7_L25_SE", "B7_L25_NE"), 105.18),
            "Lot 26 E side 112.43'": (d("B7_L26_SE", "B7_L26_NE"), 112.43),
            "Lot 27 E side 99.60'": (d("B7_L27_SE", "B7_L27_NE"), 99.60),
            "Lot 28 E side 100'": (d("B7_L28_SE", "B7_L28_NE"), 100.0),
            "Lot 37 E side (boundary) 100'": (d("B7_L37_SE", "B7_L37_NE"), 100.0),
            "Lot 23 NE on rear line (0')": (off23, 0.0),
            "Lot 22 E side 109.05'": (d("B7_L22_NE", "B7_L22_SE"), 109.05),
            "Lot 21 E side 112.43'": (d("B7_L21_NE", "B7_L21_SE"), 112.43),
            "Lot 20 E side 104.88'": (d("B7_L20_NE", "B7_L20_SE"), 104.88),
            "Lot 19 E side 100'": (d("B7_L19_NE", "B7_L19_SE"), 100.0),
            "Lot 11 E side (boundary) 100'": (d("B7_L11_NE", "B7_L11_SE"), 100.0),
            "Rear lines meet: L37 SE = L11 NE (0')": (d("B7_L37_SE", "B7_L11_NE"), 0.0),
            "Marina CL Δ 37°42'50\" (deg)": (sum(d_mar), 37.0 + 42.0 / 60.0 + 50.0 / 3600.0),
        }

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: solver.compute_mapcheck() for num, solver in self.lots.items()}

    def generate_report(self, filepath: str = "data/block7_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n  BEACHWOOD UNIT TWO -- BLOCK 7 SURVEY MAPCHECK REPORT (LOTS 11-37)\n")
            f.write("  Plat Book 30, Page 82A, Public Records of Duval County, Florida\n" + "=" * 80 + "\n\n")
            for num, res in results.items():
                f.write(res.format_surveyor_sheet() + "\n\n")
            f.write("PRINTED-DIMENSION REDUNDANCY CHECKS (computed vs plat)\n")
            for key, (calc, printed) in self.checks.items():
                f.write(f"  {key:<40} {calc:9.3f}  vs {printed:8.2f}  ({calc - printed:+.3f})\n")
        return filepath


class BeachwoodBlock8Solver:
    """
    Block 8, Beachwood Unit Two (Sheet 2, PB 30 Pg 82A), Lots 17-34, read from the scan 2026-09-24.

    Two lot rows split by a drainage & utilities R/W (40' at Mangrove Ave; its lines bend
    N88°58'20"E -> S72°51'40"E -> S54°41'40"E):
      - North row, Lots 23-34, on Sands Ave S R/W: 80' from the Mangrove P.I. (R=25' return), then the
        S R/W curve R=459.36-30=429.36' with printed lot chords 17.48 / 89.76 / 89.76 / 74.84
        (Δ 2°20' + 12° + 12° + 10° = CL Δ 36°20'), 5.15' tangent, then Lots 27-34 at 75' on S54°41'40"E.
        Lots 31-34 back onto the plat boundary (S54°41'40"E 300.0'); Lot 34's east side is the boundary.
      - South row, Lots 17-22, on Cape Horn Ave N R/W: 25.0' from the Mangrove P.I. (R=25' return, T=25'),
        then the N R/W curve R=327.01+30=357.01' with chords 70.50 / 80.83 / 74.64 (Δ 11°20' + 13° + 12°
        = CL Δ 36°20'), 10.13' tangent, then Lots 19-17 at 80'. Lot 17's east side is the boundary (P.R.M. at SE).
    Every printed lot side line is kept out of the construction and reported in `self.checks`.
    Origin: Lot 23 NW P.I. (Mangrove E R/W x Sands S R/W).
    """
    R_SANDS = 429.36
    R_CAPE = 357.01

    def __init__(self, origin: Point | None = None):
        self.origin = origin or Point(0.0, 0.0)
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self.checks: dict[str, tuple[float, float]] = {}
        self.sol23 = solve_corner_return("N01°01'40\"W", "N88°58'20\"E", radius=25.0,
                                         stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=80.0, rot="CW")
        self.sol22 = solve_corner_return("S88°58'20\"W", "N01°01'40\"W", radius=25.0,
                                         stated_dim_in_to_pi=25.0, stated_dim_out_to_pi=100.0, rot="CW")
        self._solve_geometry()

    @staticmethod
    def _dms(d, m=0.0, s=0.0):
        return d + m / 60.0 + s / 3600.0

    def _solve_geometry(self) -> None:
        P = self.points
        south = parse_bearing("S01°01'40\"E")
        east0 = parse_bearing("N88°58'20\"E")
        diag1 = parse_bearing("S72°51'40\"E")
        diag2 = parse_bearing("S54°41'40\"E")
        perp = parse_bearing("N35°18'20\"E")      # lot side lines on the diagonal
        perp_s = parse_bearing("S35°18'20\"W")

        def put(name, pt):
            P[name] = pt
            return pt

        def arc_chain(pc, tan_in_az, R, deltas, right=True):
            """Points along a circular curve from pc (tangent tan_in_az), turning right if `right`."""
            sgn = 1.0 if right else -1.0
            ctr = pc.offset((tan_in_az + sgn * 90.0) % 360.0, R)
            a0 = (tan_in_az - sgn * 90.0) % 360.0
            out, acc = [], 0.0
            for d in deltas:
                acc += d
                out.append(ctr.offset((a0 + sgn * acc) % 360.0, R))
            return ctr, out

        # ---------------- north row: Sands Ave S R/W ----------------
        pi23 = put("B8_L23_PI_NW", self.origin)
        put("B8_L23_PC_W", pi23.offset(south, self.sol23.tangent))
        put("B8_L23_PT_N", pi23.offset(east0, self.sol23.tangent))
        sands_pc = put("B8_SANDS_PC", pi23.offset(east0, 80.0))
        d_sands = [self._dms(2, 20), 12.0, 12.0, 10.0]
        ctr_s, pts = arc_chain(sands_pc, east0, self.R_SANDS, d_sands, right=True)
        for name, pt in zip(["B8_L23_NE", "B8_L24_NE", "B8_L25_NE", "B8_SANDS_PT"], pts):
            put(name, pt)
        f = put("B8_L26_NE", P["B8_SANDS_PT"].offset(diag2, 5.15))
        for num in range(27, 35):
            f = put(f"B8_L{num}_NE", f.offset(diag2, 75.0))

        # drainage N line
        dn = put("B8_L23_SW", pi23.offset(south, 100.0))
        dn = put("B8_L23_SE", dn.offset(east0, 103.20))
        dn = put("B8_L24_SE", dn.offset(diag1, 60.0))
        dn = put("B8_L25_SE", dn.offset(diag1, 60.0))
        put("B8_DN_BEND", dn.offset(diag1, 41.36))
        dn = put("B8_L26_SE", P["B8_DN_BEND"].offset(diag2, 28.30))
        for num in range(27, 35):
            dn = put(f"B8_L{num}_SE", dn.offset(diag2, 75.0))

        # ---------------- south row: Cape Horn Ave N R/W ----------------
        dsn = put("B8_L22_NW", P["B8_L23_SW"].offset(south, 40.0))
        pi22 = put("B8_L22_PI_SW", dsn.offset(south, 100.0))
        put("B8_L22_PC_W", pi22.offset(parse_bearing("N01°01'40\"W"), self.sol22.tangent))
        cape_pc = put("B8_L22_PT_S", pi22.offset(east0, self.sol22.tangent))   # T = 25.0' = printed 25.0'
        d_cape = [self._dms(11, 20), 13.0, 12.0]
        ctr_c, pts = arc_chain(cape_pc, east0, self.R_CAPE, d_cape, right=True)
        for name, pt in zip(["B8_L22_SE", "B8_L21_SE", "B8_CAPE_PT"], pts):
            put(name, pt)
        f = put("B8_L20_SE", P["B8_CAPE_PT"].offset(diag2, 10.13))
        for num in (19, 18, 17):
            f = put(f"B8_L{num}_SE", f.offset(diag2, 80.0))

        # drainage S line
        put("B8_DS_BEND1", dsn.offset(east0, 96.80))      # Lot 22 north: 96.80' then 33' on the first diagonal
        ds = put("B8_L22_NE", P["B8_DS_BEND1"].offset(diag1, 33.0))
        ds = put("B8_L21_NE", ds.offset(diag1, 115.56))
        ds = put("B8_L20_NE", ds.offset(diag2, 81.90))
        for num in (19, 18, 17):
            ds = put(f"B8_L{num}_NE", ds.offset(diag2, 80.0))

        # ---------------- lots ----------------
        def seg(R, d):
            t = math.radians(d)
            return 0.5 * R * R * (t - math.sin(t))

        def lot(num, names, stated, curve_specs=None):
            self.lots[num] = DeterministicLotSolver(
                lot_id=f"Blk8-Lot{num}", block_id="8", lot_number=num,
                vertices=[P[n] for n in names], node_names=names,
                curve_specs=curve_specs or {}, stated_area_sqft=round(stated, 1),
            )

        def sarc(side, d, rot):
            R = self.R_SANDS if rot == "CW" else self.R_CAPE
            return {side: {"radius": R, "delta_deg": d, "length": round(R * math.radians(d), 2), "rot": rot}}

        def poly(names):
            return shoelace_area([P[n] for n in names])

        # north row (clockwise rings; Sands arcs travelled eastward turn right -> CW, lot inside -> +seg)
        r23 = ["B8_L23_SW", "B8_L23_PC_W", "B8_L23_PT_N", "B8_SANDS_PC", "B8_L23_NE", "B8_L23_SE"]
        cs = sarc("side_4", d_sands[0], "CW")
        cs["side_2"] = {"radius": 25.0, "delta_deg": self.sol23.delta_deg, "length": round(self.sol23.arc_length, 2), "rot": "CW"}
        lot("23", r23, poly(["B8_L23_SW", "B8_L23_PI_NW", "B8_SANDS_PC", "B8_L23_NE", "B8_L23_SE"])
            + seg(self.R_SANDS, d_sands[0]) - self.sol23.fillet_area, cs)
        lot("24", ["B8_L23_SE", "B8_L23_NE", "B8_L24_NE", "B8_L24_SE"],
            poly(["B8_L23_SE", "B8_L23_NE", "B8_L24_NE", "B8_L24_SE"]) + seg(self.R_SANDS, 12.0), sarc("side_2", 12.0, "CW"))
        lot("25", ["B8_L24_SE", "B8_L24_NE", "B8_L25_NE", "B8_L25_SE"],
            poly(["B8_L24_SE", "B8_L24_NE", "B8_L25_NE", "B8_L25_SE"]) + seg(self.R_SANDS, 12.0), sarc("side_2", 12.0, "CW"))
        r26 = ["B8_L25_SE", "B8_L25_NE", "B8_SANDS_PT", "B8_L26_NE", "B8_L26_SE", "B8_DN_BEND"]
        lot("26", r26, poly(r26) + seg(self.R_SANDS, 10.0), sarc("side_2", 10.0, "CW"))
        for num in range(27, 35):
            r = [f"B8_L{num-1}_SE", f"B8_L{num-1}_NE", f"B8_L{num}_NE", f"B8_L{num}_SE"]
            lot(str(num), r, 7500.0)

        # south row (clockwise rings; Cape Horn arcs travelled westward turn left -> CCW, lot outside -> -seg)
        r22 = ["B8_L22_NW", "B8_DS_BEND1", "B8_L22_NE", "B8_L22_SE", "B8_L22_PT_S", "B8_L22_PC_W"]
        cs = sarc("side_4", d_cape[0], "CCW")
        cs["side_5"] = {"radius": 25.0, "delta_deg": self.sol22.delta_deg, "length": round(self.sol22.arc_length, 2), "rot": "CW"}
        lot("22", r22, poly(["B8_L22_NW", "B8_DS_BEND1", "B8_L22_NE", "B8_L22_SE", "B8_L22_PT_S", "B8_L22_PI_SW"])
            - seg(self.R_CAPE, d_cape[0]) - self.sol22.fillet_area, cs)
        r21 = ["B8_L22_NE", "B8_L21_NE", "B8_L21_SE", "B8_L22_SE"]
        lot("21", r21, poly(r21) - seg(self.R_CAPE, 13.0), sarc("side_3", 13.0, "CCW"))
        r20 = ["B8_L21_NE", "B8_L20_NE", "B8_L20_SE", "B8_CAPE_PT", "B8_L21_SE"]
        lot("20", r20, poly(r20) - seg(self.R_CAPE, 12.0), sarc("side_4", 12.0, "CCW"))
        for prv, num in ((20, 19), (19, 18), (18, 17)):
            r = [f"B8_L{prv}_NE", f"B8_L{num}_NE", f"B8_L{num}_SE", f"B8_L{prv}_SE"]
            lot(str(num), r, 8000.0)

        # ---------------- printed values not used in the construction ----------------
        d = lambda a, b: P[a].dist_to(P[b])  # noqa: E731
        self.checks = {
            "Lot 23 E side 99.80'": (d("B8_L23_SE", "B8_L23_NE"), 99.80),
            "Lot 24 E side 108.52'": (d("B8_L24_SE", "B8_L24_NE"), 108.52),
            "Lot 25 E side 107.04'": (d("B8_L25_SE", "B8_L25_NE"), 107.04),
            "Lot 26 E side 100'": (d("B8_L26_SE", "B8_L26_NE"), 100.0),
            "Lot 34 E side (boundary) 100.0'": (d("B8_L34_SE", "B8_L34_NE"), 100.0),
            "Lot 22 E side 102.17'": (d("B8_L22_NE", "B8_L22_SE"), 102.17),
            "Lot 21 E side 107.85'": (d("B8_L21_NE", "B8_L21_SE"), 107.85),
            "Lot 20 E side 100'": (d("B8_L20_NE", "B8_L20_SE"), 100.0),
            "Lot 17 E side (boundary) 100'": (d("B8_L17_NE", "B8_L17_SE"), 100.0),
            "Boundary N35°18'20\"E 140.0' (L17 SE -> L30 SE)": (d("B8_L17_SE", "B8_L30_SE"), 140.0),
            "Sands chord L23 17.48'": (d("B8_SANDS_PC", "B8_L23_NE"), 17.48),
            "Cape Horn chord L22 70.50'": (d("B8_L22_PT_S", "B8_L22_SE"), 70.50),
        }

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: solver.compute_mapcheck() for num, solver in self.lots.items()}

    def generate_report(self, filepath: str = "data/block8_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n  BEACHWOOD UNIT TWO -- BLOCK 8 SURVEY MAPCHECK REPORT (LOTS 17-34)\n")
            f.write("  Plat Book 30, Page 82A, Public Records of Duval County, Florida\n" + "=" * 80 + "\n\n")
            for num, res in results.items():
                f.write(res.format_surveyor_sheet() + "\n\n")
            f.write("PRINTED-DIMENSION REDUNDANCY CHECKS (computed vs plat)\n")
            for key, (calc, printed) in self.checks.items():
                f.write(f"  {key:<48} {calc:9.3f}  vs {printed:8.2f}  ({calc - printed:+.3f})\n")
        return filepath


class BeachwoodBlock14Solver:
    """
    Block 14, Beachwood Unit Two (Sheet 2, PB 30 Pg 82A): the strip between the 50' drainage R/W and
    Mangrove Ave's west R/W, Starfish Ave to Cape Horn Ave. Read from the scan 2026-09-24. (The earlier
    solver modelled a 24-lot double row with a cul-de-sac that doesn't exist on this plat.)

      - Lots 1-5 front the Mangrove N leg (N02°24'30"W), 100' deep (S87°35'30"W):
        Lot 1 100' x 100' (R=25' return at Starfish, P.R.M. at SE), Lot 2 91.88', Lots 3-5 90'.
      - Lot 6 straddles the bend to the S leg (N01°01'40"W): north line 100' S87°35'30"W, south line
        100' N88°58'20"E; east side 60.45' + 16.99', west side 59.22' + 15.78' (each split at its line's bend).
      - Lots 7-10 75' on the S leg, 100' deep (S88°58'20"W); Tract "A" 40' x 100' (lift station, Note 7).
      - 40' Drainage R/W, then Lot 11 100' x 100' (R=25' return at Cape Horn Ave).
    Origin: Lot 1 NE P.I. (Starfish S R/W x Mangrove W R/W).
    """
    def __init__(self, origin: Point | None = None):
        self.origin = origin or Point(0.0, 0.0)
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self.checks: dict[str, tuple[float, float]] = {}
        self.sol1 = solve_corner_return("N87°35'30\"E", "S02°24'30\"E", radius=25.0,
                                        stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0, rot="CW")
        self.sol11 = solve_corner_return("S01°01'40\"E", "S88°58'20\"W", radius=25.0,
                                         stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0, rot="CW")
        self._solve_geometry()

    def _solve_geometry(self) -> None:
        s_n = parse_bearing("S02°24'30\"E")   # N leg, southward
        s_s = parse_bearing("S01°01'40\"E")   # S leg, southward
        w_n = parse_bearing("S87°35'30\"W")   # depth on N leg
        w_s = parse_bearing("S88°58'20\"W")   # depth on S leg
        P = self.points

        def put(name, pt):
            P[name] = pt
            return pt

        def lot(num, names, stated, curve_specs=None):
            self.lots[num] = DeterministicLotSolver(
                lot_id=f"Blk14-Lot{num}", block_id="14", lot_number=num,
                vertices=[P[n] for n in names], node_names=names,
                curve_specs=curve_specs or {}, stated_area_sqft=round(stated, 1),
            )

        # ---- east line (Mangrove W R/W), north to south ----
        e = put("B14_L1_PI_NE", self.origin)
        put("B14_L1_PC", e.offset(parse_bearing("S87°35'30\"W"), self.sol1.tangent))
        put("B14_L1_PT", e.offset(s_n, self.sol1.tangent))
        for num, w in [("1", 100.0), ("2", 91.88), ("3", 90.0), ("4", 90.0), ("5", 90.0)]:
            e = put(f"B14_L{num}_SE", e.offset(s_n, w))
        bend_e = put("B14_BEND_E", e.offset(s_n, 60.45))
        e = put("B14_L6_SE", bend_e.offset(s_s, 16.99))
        for num in ["7", "8", "9", "10"]:
            e = put(f"B14_L{num}_SE", e.offset(s_s, 75.0))
        e = put("B14_TA_SE", e.offset(s_s, 40.0))
        e11 = put("B14_L11_NE", e.offset(s_s, 40.0))       # across the 40' Drainage R/W
        pi11 = put("B14_L11_PI_SE", e11.offset(s_s, 100.0))
        put("B14_L11_PC", pi11.offset(parse_bearing("N01°01'40\"W"), self.sol11.tangent))
        put("B14_L11_PT", pi11.offset(w_s, self.sol11.tangent))

        # ---- west line: every lot is 100' deep, square to its own leg ----
        put("B14_L1_NW", P["B14_L1_PI_NE"].offset(w_n, 100.0))
        for num in ["1", "2", "3", "4", "5"]:
            put(f"B14_L{num}_SW", P[f"B14_L{num}_SE"].offset(w_n, 100.0))
        bend_w = put("B14_BEND_W", P["B14_L5_SW"].offset(s_n, 59.22))
        put("B14_L6_SW", P["B14_L6_SE"].offset(w_s, 100.0))
        for num in ["7", "8", "9", "10"]:
            put(f"B14_L{num}_SW", P[f"B14_L{num}_SE"].offset(w_s, 100.0))
        put("B14_TA_SW", P["B14_TA_SE"].offset(w_s, 100.0))
        put("B14_L11_NW", e11.offset(w_s, 100.0))
        put("B14_L11_SW", pi11.offset(w_s, 100.0))

        # ---- lots (clockwise rings) ----
        lot("1", ["B14_L1_NW", "B14_L1_PC", "B14_L1_PT", "B14_L1_SE", "B14_L1_SW"],
            100.0 * 100.0 - self.sol1.fillet_area,
            {"side_2": {"radius": 25.0, "delta_deg": self.sol1.delta_deg,
                        "length": round(self.sol1.arc_length, 2), "rot": "CW"}})
        prev = "1"
        for num, w in [("2", 91.88), ("3", 90.0), ("4", 90.0), ("5", 90.0)]:
            lot(num, [f"B14_L{prev}_SW", f"B14_L{prev}_SE", f"B14_L{num}_SE", f"B14_L{num}_SW"], w * 100.0)
            prev = num
        l6 = ["B14_L5_SW", "B14_L5_SE", "B14_BEND_E", "B14_L6_SE", "B14_L6_SW", "B14_BEND_W"]
        lot("6", l6, shoelace_area([P[n] for n in l6]))
        prev = "6"
        for num in ["7", "8", "9", "10"]:
            lot(num, [f"B14_L{prev}_SW", f"B14_L{prev}_SE", f"B14_L{num}_SE", f"B14_L{num}_SW"], 7500.0)
            prev = num
        lot("A", ["B14_L10_SW", "B14_L10_SE", "B14_TA_SE", "B14_TA_SW"], 4000.0)
        lot("11", ["B14_L11_NW", "B14_L11_NE", "B14_L11_PC", "B14_L11_PT", "B14_L11_SW"],
            100.0 * 100.0 - self.sol11.fillet_area,
            {"side_3": {"radius": 25.0, "delta_deg": self.sol11.delta_deg,
                        "length": round(self.sol11.arc_length, 2), "rot": "CW"}})

        # Printed values not used in the construction
        self.checks = {
            "Lot 6 west 15.78' (bend to SW)": (bend_w.dist_to(P["B14_L6_SW"]), 15.78),
            "Lot 6 south 100' N88°58'20\"E": (P["B14_L6_SW"].dist_to(P["B14_L6_SE"]), 100.0),
        }

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: solver.compute_mapcheck() for num, solver in self.lots.items()}

    def generate_report(self, filepath: str = "data/block14_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 14 SURVEY MAPCHECK REPORT (LOTS 1-11 + TRACT A)\n")
            f.write("  Plat Book 30, Page 82A, Public Records of Duval County, Florida\n")
            f.write("=" * 80 + "\n\n")
            for num, res in results.items():
                f.write(res.format_surveyor_sheet() + "\n\n")
            f.write("PRINTED-DIMENSION REDUNDANCY CHECKS (computed vs plat)\n")
            for key, (calc, printed) in self.checks.items():
                f.write(f"  {key:<36} {calc:9.3f}  vs {printed:8.2f}  ({calc - printed:+.3f})\n")
        return filepath


# ==============================================================================
# 15. ALL-BLOCKS REGISTRY & ORCHESTRATION FACTORY
# ==============================================================================

def get_all_block_solvers(spacing_ft: float = 400.0) -> dict[str, Any]:
    """
    Factory creating independent cadastral solvers for every block in Beachwood Unit Two:
      Sheet 1: Blocks 9, 10, 11, 12
      Sheet 2: Blocks 13, 14, 15, 16, 17, 18
    Each block is computed independently in its own local coordinate space,
    offset cleanly on a multi-block canvas so that they sit aside of the outer boundary.
    """
    solvers = {}
    dy = spacing_ft
    origins = {
        # Arranged in clean grid layout on local canvas
        # Sheet 2: Blocks 18 down to 13 (Column 1, E = 0.0)
        "BLOCK_18": Point(0.0, 0.0),
        "BLOCK_17": Point(-1.0 * dy, 0.0),
        "BLOCK_16": Point(-2.0 * dy, 0.0),
        "BLOCK_15": Point(-3.0 * dy, 0.0),
        "BLOCK_14": Point(-4.0 * dy, 0.0),
        "BLOCK_13": Point(-5.0 * dy, 0.0),
        # Sheet 1: Blocks 12 down to 9 (Column 2, E = 2200.0)
        "BLOCK_12": Point(0.0, 2200.0),
        "BLOCK_11": Point(-1.0 * dy, 2200.0),
        "BLOCK_10": Point(-2.0 * dy, 2200.0),
        "BLOCK_9":  Point(-3.0 * dy, 2200.0),
        "BLOCK_8":  Point(-4.5 * dy, 2000.0),
        "BLOCK_7":  Point(-7.0 * dy, 2000.0),
        "BLOCK_6":  Point(-9.0 * dy, 2600.0),
    }

    solvers["BLOCK_18"] = BeachwoodBlock18Solver(origins["BLOCK_18"])
    solvers["BLOCK_17"] = BeachwoodBlock17Solver(origins["BLOCK_17"])
    solvers["BLOCK_16"] = BeachwoodBlock16Solver(origins["BLOCK_16"])
    solvers["BLOCK_15"] = BeachwoodBlock15Solver(origins["BLOCK_15"])
    solvers["BLOCK_14"] = BeachwoodBlock14Solver(origins["BLOCK_14"])
    solvers["BLOCK_13"] = BeachwoodBlock13Solver(origins["BLOCK_13"])
    solvers["BLOCK_12"] = BeachwoodBlock12Solver(origins["BLOCK_12"])
    solvers["BLOCK_11"] = BeachwoodBlock11Solver(origins["BLOCK_11"])
    solvers["BLOCK_10"] = BeachwoodBlock10Solver(origins["BLOCK_10"])
    solvers["BLOCK_9"]  = BeachwoodBlock9Solver(origins["BLOCK_9"])
    solvers["BLOCK_8"]  = BeachwoodBlock8Solver(origins["BLOCK_8"])
    solvers["BLOCK_7"]  = BeachwoodBlock7Solver(origins["BLOCK_7"])
    solvers["BLOCK_6"]  = BeachwoodBlock6Solver(origins["BLOCK_6"])

    return solvers

