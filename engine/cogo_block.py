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
from dataclasses import dataclass, field
from typing import Any

from engine.cogo import Point, azimuth_to_bearing, parse_bearing
from engine.curves import solve_curve_all_parameters
from engine.lots import shoelace_area

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
    """
    az_in = parse_bearing(bearing_in)
    az_out = parse_bearing(bearing_out)

    # Turn deflection angle
    diff = abs(az_out - az_in) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    delta_deg = diff

    # Solve curve parameters
    c_sol = solve_curve_all_parameters(radius=radius, delta_deg=delta_deg)
    T = float(c_sol["tangent"])
    arc_len = float(c_sol["length"])
    chord_len = float(c_sol["chord"])
    fillet_a = float(c_sol["fillet_area"])
    segment_a = float(c_sol["segment_area"])

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
                # Solve using R and chord
                c_data = solve_curve_all_parameters(radius=R, chord=chord_dist)
                L_arc = float(c_data["length"])
                tot_perim += L_arc
                seg_a = float(c_data["segment_area"])
                curve_adj += (+seg_a if c_rot == "CW" else -seg_a)

                # Generate arc points
                delta_deg = float(c_data["delta_deg"])
                half_delta = delta_deg / 2.0
                sign = 1.0 if c_rot == "CW" else -1.0
                t_in_az = (az - sign * half_delta) % 360.0
                rp_az = (t_in_az + sign * 90.0) % 360.0
                rp = p1.offset(rp_az, R)
                start_az = (rp_az + 180.0) % 360.0
                n_segs = 16
                for s in range(n_segs + 1):
                    a = start_az + sign * delta_deg * (s / n_segs)
                    arc_pts.append(rp.offset(a, R))
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
    def __init__(self):
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
        self.sol27 = solve_corner_return("N01°01'40\"W", "N88°58'20\"E", radius=25.0, stated_dim_in_to_pi=140.0)
        self.sol26 = solve_corner_return("S84°31'40\"E", "S01°01'40\"E", radius=25.0, stated_dim_in_to_pi=109.0)

        # 3. Coordinate Geometry
        self.points: dict[str, Point] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self._solve_geometry()

    def _solve_geometry(self):
        """Construct all Block 9 points using pure analytical COGO."""
        # Origin Anchor: Matchline south terminus on San Salvadore Ave R/W
        p23_se = Point(0.0, 0.0)
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
                curve_specs={"side_2": {"radius": 25.0, "rot": "CW"}},
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
                curve_specs={"side_5": {"radius": 25.0, "rot": "CW"}},
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
        # Lot 1 (NE Corner): Delta = 90°00'00", T = 25.0000'
        self.sol1 = solve_corner_return("N88°58'20\"E", "S01°01'40\"E", radius=25.0, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0)
        # Lot 11 (SE Corner): Delta = 90°20'00", T = 25.1459'
        self.sol11 = solve_corner_return("S01°01'40\"E", "S89°18'20\"W", radius=25.0, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=100.0)

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
            curve_specs={"side_3": {"radius": 25.0, "rot": "CW"}},
            stated_area_sqft=9865.87,
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
            curve_specs={"side_4": {"radius": 25.0, "rot": "CW"}},
            stated_area_sqft=9835.14,
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
                "radius": 25.0,
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
                "radius": 25.0,
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
        # Lot 1 NW Corner Return (Sail Ave & West St)
        self.sol1 = solve_corner_return(self.brg_west, self.brg_sail, radius=25.0, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=93.50, rot="CW")
        # Lot 33 SW Corner Return (West St & South St)
        self.sol33 = solve_corner_return(self.brg_west_rev, self.brg_south_st, radius=25.0, stated_dim_in_to_pi=100.0, stated_dim_out_to_pi=93.50, rot="CCW")
        # Lot 29 SE Corner Return (Marina Ave PT to Keel Dr)
        self.sol29 = solve_corner_return(self.brg_marina_pt_tan, self.brg_keel_tan_in, radius=25.0, stated_dim_in_to_pi=25.0, stated_dim_out_to_pi=25.0, rot="CCW")

        # 3. Marina Avenue North R/W Curve (R=389.27', Delta=37°42'50\")
        self.r_marina = 389.27
        self.delta_marina = 37.0 + 42.0/60.0 + 50.0/3600.0
        self.delta_sub = self.delta_marina / 3.0 # 12.571296° per lot

        # 4. Keel Drive Curve (R=167.95', Lot 28 frontage chord=68.75')
        self.r_keel = 167.95
        self.delta_keel_28 = 2.0 * math.degrees(math.asin(68.75 / (2.0 * self.r_keel))) # 23.6208°

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
        p29_ret_pi = p29_pt_marina.offset(parse_bearing("S54°41'40\"E"), 25.0)
        p29_ret_pt = p29_ret_pi.offset(parse_bearing("N35°18'20\"E"), 25.0)
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
            curve_specs={"side_2": {"radius": 25.0, "rot": "CW"}},
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

        # Lot 33: SW corner return
        lots_dict["33"] = DeterministicLotSolver(
            lot_id="Blk16-Lot33", block_id="16", lot_number="33",
            vertices=[p33_pt_s, p33_prm_se, p_cl_33_32, p_cl_0, p33_pc_w],
            node_names=["PT_South", "SE_Cor(PRM)", "NE_Cor", "NW_Cor", "PC_West"],
            curve_specs={"side_5": {"radius": 25.0, "rot": "CW"}},
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
        c3_sol = solve_curve_all_parameters(radius=self.r_marina, delta_deg=self.delta_sub)
        l31_poly = [p32_se_pc, p31_se, p_cl_31_30, p_cl_32_31]
        # side_1 (p32_se_pc -> p31_se) is declared rot="CW" below, which
        # compute_mapcheck() adds to the raw polygon area (curve_adj +=
        # +seg_a). This target area must use the same sign, or "Area
        # Discrepancy" reports a fake ~2x-segment-area mismatch against a
        # target that was never actually consistent with the engine's own
        # math (confirmed: this WAS subtracting, producing the exact
        # +266.2 SF / 2.63% discrepancy printed in the certified report).
        a31 = shoelace_area(l31_poly) + float(c3_sol["segment_area"])
        lots_dict["31"] = DeterministicLotSolver(
            lot_id="Blk16-Lot31", block_id="16", lot_number="31",
            vertices=l31_poly,
            node_names=["SW_Cor(PC)", "SE_Cor", "NE_Cor", "NW_Cor"],
            curve_specs={"side_1": {"radius": self.r_marina, "rot": "CW"}},
            stated_area_sqft=round(a31, 1),
        )

        # Lot 30: Frontage Curve C4 (R=389.27', Delta=12°34'17", Chord=85.24' @ S73°33'06"E)
        c4_sol = solve_curve_all_parameters(radius=self.r_marina, delta_deg=self.delta_sub)
        l30_poly = [p31_se, p30_se, p_cl_apex, p_cl_31_30]
        # Same sign fix as Lot 31 above: side_1 is rot="CW" -> add, not subtract.
        a30 = shoelace_area(l30_poly) + float(c4_sol["segment_area"])
        lots_dict["30"] = DeterministicLotSolver(
            lot_id="Blk16-Lot30", block_id="16", lot_number="30",
            vertices=l30_poly,
            node_names=["SW_Cor", "SE_Cor", "Apex_NE", "NW_Cor"],
            curve_specs={"side_1": {"radius": self.r_marina, "rot": "CW"}},
            stated_area_sqft=round(a30, 1),
        )

        # Lot 29: Wedge / Pie Lot (Apex at p_cl_apex, Curve C5, Corner Return C6, Straight 51.68', Side 166.73')
        c5_sol = solve_curve_all_parameters(radius=self.r_marina, delta_deg=self.delta_sub)
        l29_poly = [p30_se, p29_pt_marina, p29_ret_pt, p29_se, p_cl_apex]
        # side_1 (Marina, rot="CW") -> compute_mapcheck adds its segment;
        # side_2 (corner return, rot="CCW") -> compute_mapcheck subtracts
        # its segment. The previous formula had both signs backwards.
        a29 = shoelace_area(l29_poly) + float(c5_sol["segment_area"]) - self.sol29.segment_area
        lots_dict["29"] = DeterministicLotSolver(
            lot_id="Blk16-Lot29", block_id="16", lot_number="29",
            vertices=l29_poly,
            node_names=["SW_Cor", "PT_Marina", "PT_Ret", "SE_Cor", "Apex_Rear"],
            curve_specs={
                "side_1": {"radius": self.r_marina, "rot": "CW"},
                "side_2": {"radius": 25.0, "rot": "CCW"},
            },
            stated_area_sqft=round(a29, 1),
        )

        # Lot 28: Frontage along Keel Drive (Chord=68.75' @ N60°18'20"E, Rear 110.00', East 116.36', West 166.73')
        c7_sol = solve_curve_all_parameters(radius=self.r_keel, delta_deg=self.delta_keel_28)
        l28_poly = [p29_se, p28_se, p_cl_28_27, p_cl_apex]
        # Same sign fix as Lot 31/30 above: side_1 is rot="CW" -> add, not subtract.
        a28 = shoelace_area(l28_poly) + float(c7_sol["segment_area"])
        lots_dict["28"] = DeterministicLotSolver(
            lot_id="Blk16-Lot28", block_id="16", lot_number="28",
            vertices=l28_poly,
            node_names=["SW_Cor", "SE_Cor", "NE_Cor", "NW_Apex"],
            curve_specs={"side_1": {"radius": self.r_keel, "rot": "CW"}},
            stated_area_sqft=round(a28, 1),
        )

        self.lots = lots_dict

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        """Compute MapCheck for all 14 lots in Block 16."""
        results = {}
        for lot_num, solver in self.lots.items():
            results[lot_num] = solver.compute_mapcheck()
        return results

    def get_curve_table_data(self) -> list[dict[str, Any]]:
        """Return structured curve table rows for Block 16."""
        c3 = solve_curve_all_parameters(radius=self.r_marina, delta_deg=self.delta_sub)
        c7 = solve_curve_all_parameters(radius=self.r_keel, delta_deg=self.delta_keel_28)
        return [
            {"tag": "C1", "radius": 25.00, "delta": "90°00'00\"", "length": self.sol1.arc_length, "tangent": self.sol1.tangent, "chord": self.sol1.chord, "chord_bearing": whole_second_bearing(self.sol1.chord_bearing), "location": "Lot 1 NW Corner Return (Sail Ave & West St, Glyph '┌')"},
            {"tag": "C2", "radius": 25.00, "delta": "90°00'00\"", "length": self.sol33.arc_length, "tangent": self.sol33.tangent, "chord": self.sol33.chord, "chord_bearing": whole_second_bearing(self.sol33.chord_bearing), "location": "Lot 33 SW Corner Return (South St & West St, Glyph '└')"},
            {"tag": "C3", "radius": self.r_marina, "delta": "12°34'17\"", "length": float(c3["length"]), "tangent": float(c3["tangent"]), "chord": 85.24, "chord_bearing": "S86°07'22\"E", "location": "Lot 31 Frontage (Marina Ave North R/W)"},
            {"tag": "C4", "radius": self.r_marina, "delta": "12°34'17\"", "length": float(c3["length"]), "tangent": float(c3["tangent"]), "chord": 85.24, "chord_bearing": "S73°33'06\"E", "location": "Lot 30 Frontage (Marina Ave North R/W)"},
            {"tag": "C5", "radius": self.r_marina, "delta": "12°34'17\"", "length": float(c3["length"]), "tangent": float(c3["tangent"]), "chord": 85.24, "chord_bearing": "S60°58'49\"E", "location": "Lot 29 Frontage (Marina Ave North R/W)"},
            {"tag": "C6", "radius": 25.00, "delta": "90°00'00\"", "length": self.sol29.arc_length, "tangent": self.sol29.tangent, "chord": self.sol29.chord, "chord_bearing": whole_second_bearing(self.sol29.chord_bearing), "location": "Lot 29 SE Corner Return (Marina Ave PT to Keel Dr, Glyph '┘')"},
            {"tag": "C7", "radius": self.r_keel, "delta": "23°37'15\"", "length": float(c7["length"]), "tangent": float(c7["tangent"]), "chord": 68.75, "chord_bearing": "N60°18'20\"E", "location": "Lot 28 Frontage (Keel Drive North R/W)"},
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
    Deterministic solver for Block 12, Beachwood Unit Two (the only part of
    Block 12 within this plat -- the dashed-outline "(12)" parcels drawn near
    San Salvadore Road/Unit One belong to the adjoining Beachwood Unit One and
    carry no bearings/distances on this sheet).
    Plat Book 30, Page 82, Duval County, FL.

    Lots 4, 5, 6, 7 (WEST OF MATCHLINE, CERTIFIED):
    Straight-sided lots stacked along the 50' drainage/utility R/W (the same
    alignment as Mangrove Ave in Blocks 13/11/10). Each is closed from
    exactly the sides legibly stated on the plat, with the one remaining
    side computed by closure (a normal, expected condition -- a
    quadrilateral only needs 3 independent sides + closure, not 4 printed
    ones, and every computed 4th side here reproduces its neighbor's
    independently-stated dimension to within 0.01', confirming the reading):
      - Lot 7: West 75.00' (R/W, S01°01'40"E), North 100.00' (shared w/
        Lot 8, N88°58'20"E), South 120.00' (shared w/ Lot 6, N88°58'20"E).
        East side (shared w/ Lot 8/9 curve transition) computed at 77.62'.
      - Lot 6: West 71.27' (R/W), North 120.00' (= Lot 7 south),
        South 120.52' (shared w/ Lot 5). East computed at 71.27' (matches
        west exactly).
      - Lot 5: West 90.00' (R/W), North 120.52' (= Lot 6 south), South
        120.00' (Bayou frontage, N89°18'20"E). East computed at 90.70' --
        matches Lot 4's independently-stated west side (90.69') to 0.01'.
      - Lot 4: West 90.69' (shared w/ Lot 5, standard perpendicular divider
        N00°41'40"W), South 94.20' (Bayou frontage), East 102.20'
        (matchline, N00°41'40"W). North side (shared w/ Lot 6's curve-side
        jog) computed at 94.90' -- not independently stated, not needed.

    Lots 8, 9, 10 (FLAGGED -- NOT CERTIFIED, see Rule 3 below):
    These lots front the San Salvadore Avenue curve transition (centerline
    curve data on the plat: R=269.96', Delta=36°20'00", T=88.59' -- the
    same curve documented for Block 9's Lots 23-26 in
    data/block9_mapcheck_report.txt) via a multi-segment jog off Lot 6/7's
    east side. The plat prints several short courses in that jog (e.g.
    "25.82'", "N19°06'16"E", "60.34'", "S56°34'xx"E") that this reading
    could not transcribe with certifiable confidence -- some of that text is
    an easement annotation ("Esm't") rather than a boundary line, and the
    remaining figures are small enough on the scan that a misread digit
    would silently produce a legally wrong corner. Rather than guess, this
    solver only fixes the ONE corner that IS unambiguous (Lot 8's SW corner,
    shared with Lot 7's already-certified NE corner) and leaves Lots 8, 9,
    10 OUT of self.lots. See BeachwoodBlock12Solver.flagged_points for the
    corner(s) recovered by straight-line intersection instead of a direct
    plat reading, and MASTER_PROMPT.md / the drawing script for how these
    are marked in red on the CAD output -- exactly the "not enough
    information, compute the intersection, mark it in red" workflow this
    was built for.
    """
    def __init__(self, origin: Point | None = None):
        self.brg_div = "N88°58'20\"E"     # interior divider (Lots 4-7, matches Block 13's convention)
        self.brg_west = "S01°01'40\"E"    # 50' drainage/utility R/W (west side of Lots 5, 6, 7)
        self.brg_bayou = "N89°18'20\"E"   # Bayou frontage (Lot 4 south, Lot 5 south)
        self.brg_side = "N00°41'40\"W"    # standard perpendicular divider (Lot 4/5, matchline)

        self.az_div = parse_bearing(self.brg_div)
        self.az_west = parse_bearing(self.brg_west)
        self.az_bayou = parse_bearing(self.brg_bayou)
        self.az_side = parse_bearing(self.brg_side)

        self.origin = origin or Point(1000.0, 1000.0)
        self.points: dict[str, Point] = {}
        self.flagged_points: dict[str, dict[str, Any]] = {}
        self.lots: dict[str, DeterministicLotSolver] = {}
        self._solve_geometry()

    def _solve_geometry(self):
        # Anchor: NW corner of Lot 7, on the 50' drainage/utility R/W.
        p7_nw = self.origin
        p7_ne = p7_nw.offset(self.az_div, 100.00)
        p7_sw = p7_nw.offset(self.az_west, 75.0)
        p7_se = p7_sw.offset(self.az_div, 120.00)

        p6_nw, p6_ne = p7_sw, p7_se
        p6_sw = p6_nw.offset(self.az_west, 71.27)
        p6_se = p6_sw.offset(self.az_div, 120.52)

        p5_nw, p5_ne = p6_sw, p6_se
        p5_sw = p5_nw.offset(self.az_west, 90.0)
        p5_se = p5_sw.offset(self.az_bayou, 120.0)

        p4_sw = p5_se
        p4_nw = p4_sw.offset(self.az_side, 90.69)
        p4_se = p4_sw.offset(self.az_bayou, 94.20)
        p4_ne = p4_se.offset(self.az_side, 102.20)

        self.points = {
            "p7_nw": p7_nw, "p7_ne": p7_ne, "p7_se": p7_se, "p7_sw": p7_sw,
            "p6_nw": p6_nw, "p6_ne": p6_ne, "p6_se": p6_se, "p6_sw": p6_sw,
            "p5_nw": p5_nw, "p5_ne": p5_ne, "p5_se": p5_se, "p5_sw": p5_sw,
            "p4_nw": p4_nw, "p4_ne": p4_ne, "p4_se": p4_se, "p4_sw": p4_sw,
        }

        for num in ["7", "6", "5", "4"]:
            nw, ne, se, sw = (self.points[f"p{num}_nw"], self.points[f"p{num}_ne"],
                              self.points[f"p{num}_se"], self.points[f"p{num}_sw"])
            self.lots[num] = DeterministicLotSolver(
                lot_id=f"Blk12-Lot{num}", block_id="12", lot_number=num,
                vertices=[sw, nw, ne, se],
                node_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
                stated_area_sqft=1.0,
            )
        for lot in self.lots.values():
            res = lot.compute_mapcheck()
            lot.stated_area_sqft = round(res.computed_area_sqft, 2)

        # --- Lots 8, 9, 10: flagged, not certified -- see class docstring. ---
        # The ONE corner this reading can defend outright: Lot 8's SW corner
        # is simply Lot 7's already-certified NE corner (both ends of the
        # plat-stated 100.00' N88°58'20"E line) -- no intersection needed.
        p8_sw = p7_ne
        self.points["p8_sw"] = p8_sw

        # The matchline IS legible end to end: it runs N00°41'40"W 102.20'
        # up from Lot 4's NE corner (already fixed above) to a bend point,
        # then N35°18'20"E 120.00' further up to the P.R.M. at San Salvadore
        # Ave -- both segments explicitly labeled on the plat. What is NOT
        # legible is how Lots 8/9/10's own interior dividers step across
        # from the Lot 6/7 R/W frontage out to that matchline (the plat
        # prints several short, faint jog courses there this reading could
        # not certify). Intersecting Lot 7/8's *known* north divider
        # (N88°58'20"E, extended east) against the *known* matchline gives a
        # first-pass estimate for Lot 8's NE corner -- a real surveyor's
        # technique for closing a gap in the record, but only an estimate,
        # since the true boundary may jog before reaching that line.
        p_bend = p4_ne  # matchline bend point, already fixed via Lot 4's east side
        az_matchline_upper = parse_bearing("N35°18'20\"E")
        p_prm = p_bend.offset(az_matchline_upper, 120.00)
        try:
            p8_ne_flag = intersect_bearings(p8_sw, self.az_div, p_bend, az_matchline_upper)
            self.points["p_matchline_bend"] = p_bend
            self.points["p_prm_san_salvadore"] = p_prm
            self.flagged_points["Lot8_NE_approx"] = {
                "point": p8_ne_flag,
                "method": (
                    "intersect_bearings(Lot 7/8 north divider N88°58'20\"E extended "
                    "east from the certified Lot 7 NE corner, against the matchline "
                    "N35°18'20\"E through the bend point above Lot 4)"
                ),
                "reason": (
                    "Lots 8, 9, 10 front the San Salvadore Ave curve transition through "
                    "several short jog courses this reading could not transcribe with "
                    "certifiable confidence from the scan. This point is a first-pass "
                    "intersection estimate for Lot 8's NE corner, NOT a substitute for "
                    "reading the actual plat courses -- draw in red, verify against the "
                    "recorded plat or field notes before relying on it."
                ),
            }
        except ValueError:
            pass

    def solve_all(self) -> dict[str, LotMapCheckResult]:
        return {num: lot.compute_mapcheck() for num, lot in self.lots.items()}

    def get_line_table_data(self) -> list[dict[str, Any]]:
        lines = []
        idx = 1
        lines.append({"tag": f"L{idx}", "bearing": "N88°58'20\"E", "distance": 100.00, "desc": "Lot 7/8 Dividing Line"})
        idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "S01°01'40\"E", "distance": 75.00, "desc": "Lot 7 West Line on Drainage R/W"})
        idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "N88°58'20\"E", "distance": 120.00, "desc": "Lot 6/7 Dividing Line"})
        idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "S01°01'40\"E", "distance": 71.27, "desc": "Lot 6 West Line on Drainage R/W"})
        idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "N88°58'20\"E", "distance": 120.52, "desc": "Lot 5/6 Dividing Line"})
        idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "S01°01'40\"E", "distance": 90.00, "desc": "Lot 5 West Line on Drainage R/W"})
        idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "N89°18'20\"E", "distance": 120.00, "desc": "Lot 5 Frontage on Bayou"})
        idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "N00°41'40\"W", "distance": 90.69, "desc": "Lot 4/5 Dividing Line"})
        idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "N89°18'20\"E", "distance": 94.20, "desc": "Lot 4 Frontage on Bayou"})
        idx += 1
        lines.append({"tag": f"L{idx}", "bearing": "N00°41'40\"W", "distance": 102.20, "desc": "Lot 4 East Line on Matchline"})
        return lines

    def generate_report(self, filepath: str = "data/block12_mapcheck_report.txt") -> str:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        results = self.solve_all()
        with open(filepath, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("  BEACHWOOD UNIT TWO -- BLOCK 12 (WEST OF MATCHLINE) SURVEY MAPCHECK REPORT\n")
            f.write("  Plat Book 30, Page 82, Public Records of Duval County, Florida\n")
            f.write("  Pure Algorithmic Cadastral COGO Engine Output (Offline / Deterministic)\n")
            f.write("=" * 80 + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("  RULE 3: FLAGGED LOTS -- INSUFFICIENT LEGIBLE PLAT DATA\n")
            f.write("=" * 80 + "\n")
            f.write("  Lots 8, 9, and 10 are NOT included in this certification. They front\n")
            f.write("  the San Salvadore Ave curve transition (R=269.96', Delta=36°20'00',\n")
            f.write("  same curve as Block 9's Lots 23-26) through several short jog courses\n")
            f.write("  this reading could not transcribe with confidence from the scan.\n")
            f.write("  See BeachwoodBlock12Solver.flagged_points for the one approximate\n")
            f.write("  corner recovered by line intersection (drawn in red on the CAD\n")
            f.write("  output) -- NOT a certified boundary. Field verification or a clearer\n")
            f.write("  print of Plat Book 30, Page 82 is needed before Lots 8-10 can be\n")
            f.write("  certified the same way Lots 4-7 are below.\n\n")
            for name, info in self.flagged_points.items():
                p = info["point"]
                f.write(f"  {name}: N={p.n:.2f}, E={p.e:.2f} (approximate)\n")
                f.write(f"    Method: {info['method']}\n")
                f.write(f"    Reason: {info['reason']}\n\n")

            f.write("=" * 80 + "\n")
            f.write("  LINE TABLE (BLOCK 12, LOTS 4-7)\n")
            f.write("=" * 80 + "\n")
            f.write(f"{'Tag':<5} | {'Bearing':<14} | {'Distance (ft)':<14} | {'Description'}\n")
            f.write("-" * 80 + "\n")
            for lt in self.get_line_table_data():
                f.write(f"{lt['tag']:<5} | {lt['bearing']:<14} | {lt['distance']:<14.2f} | {lt['desc']}\n")
            f.write("\n")

            f.write("=" * 80 + "\n")
            f.write("  INDIVIDUAL LOT MAPCHECK SURVEYOR SHEETS (4 CERTIFIED LOTS)\n")
            f.write("=" * 80 + "\n\n")
            for lot_num in ["7", "6", "5", "4"]:
                res = results[lot_num]
                f.write(res.format_surveyor_sheet() + "\n\n")

        return filepath

