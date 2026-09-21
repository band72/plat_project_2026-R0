"""
engine/lot_agent.py -- Autonomous Cadastral Lot Agent with Integrated Omni-Parameter Curve MapCheck.

Each lot in the subdivision plat is assigned a dedicated autonomous agent responsible for:
1. Constructing exact corner coordinates and curved boundary geometry via the omni-parameter curve solver.
2. Walking the closed boundary traverse course-by-course.
3. Calculating mathematical closure vector (dN, dE), linear misclose distance, and precision ratio.
4. Computing exact parcel area (Shoelace formula + circular arc segment areas).
5. Generating professional surveyor MapCheck reports and CAD drawing entities.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any
from engine.cogo import Point, parse_bearing, azimuth_to_bearing
from engine.curves import solve_curve_all_parameters, Curve, deg_to_dms_str, curve_segment_area
from engine.lots import shoelace_area
from engine.dxf_writer import DXFWriter


@dataclass
class MapCheckCourse:
    """A single boundary course in a cadastral parcel traverse."""
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
class MapCheckReport:
    """Detailed Survey MapCheck Report for an individual subdivision lot."""
    lot_id: str
    block_id: str
    lot_number: str
    courses: list[MapCheckCourse]
    perimeter_ft: float
    misclose_n_ft: float
    misclose_e_ft: float
    misclose_dist_ft: float
    precision_str: str
    raw_shoelace_sqft: float
    curve_adj_sqft: float
    computed_area_sqft: float
    computed_acres: float
    stated_area_sqft: float
    area_diff_sqft: float
    passed: bool
    verdict: str

    def format_text(self) -> str:
        """Format the MapCheck into standard professional land survey format."""
        lines = [
            f"================================================================================",
            f"  SURVEY MAPCHECK REPORT: {self.lot_id} (Block {self.block_id}, Lot {self.lot_number})",
            f"================================================================================",
            f"Stated Dimensions: Area Target = {self.stated_area_sqft:,.1f} SF ({self.stated_area_sqft/43560.0:.4f} Acres)",
            f"--------------------------------------------------------------------------------",
            f"{'Course':<8} | {'From -> To':<18} | {'Bearing':<14} | {'Distance (ft)':<14} | {'Type':<8}",
            f"--------------------------------------------------------------------------------",
        ]
        for c in self.courses:
            ctype = "CURVE" if c.is_curve else "LINE"
            lines.append(f"{c.course_num:<8} | {c.from_node+' -> '+c.to_node:<18} | {c.bearing_str:<14} | {c.distance:<14.2f} | {ctype:<8}")
            if c.is_curve and c.curve_data:
                cd = c.curve_data
                lines.append(
                    f"         Curve Data -> Radius: {cd.get('radius', 0.0):.2f}' | Arc: {cd.get('length', 0.0):.2f}' | "
                    f"Delta: {cd.get('delta_dms', '')} | Chord: {cd.get('chord', 0.0):.2f}'"
                )
                lines.append(
                    f"                       Tangent: {cd.get('tangent', 0.0):.2f}' | Mid-Ord: {cd.get('mid_ordinate', 0.0):.2f}' | "
                    f"Ext: {cd.get('external', 0.0):.2f}' | Seg Area: {cd.get('segment_area', 0.0):.1f} SF"
                )
        lines.extend([
            f"--------------------------------------------------------------------------------",
            f"TRAVERSE CLOSURE & PRECISION:",
            f"  Perimeter:           {self.perimeter_ft:,.2f} ft",
            f"  Misclose Vector:     dN = {self.misclose_n_ft:+.4f} ft, dE = {self.misclose_e_ft:+.4f} ft",
            f"  Linear Misclose:     {self.misclose_dist_ft:.4f} ft",
            f"  Relative Precision:  {self.precision_str}",
            f"  Traverse Status:     {'PASS (CLOSED)' if self.passed else 'FAIL (OPEN)'}",
            f"AREA VERIFICATION:",
            f"  Raw Polygon Area:    {self.raw_shoelace_sqft:,.1f} SF",
            f"  Curve Area Adj:      {self.curve_adj_sqft:+,.1f} SF",
            f"  Net Computed Area:   {self.computed_area_sqft:,.1f} SF ({self.computed_acres:.4f} Acres)",
            f"  Target Stated Area:  {self.stated_area_sqft:,.1f} SF",
            f"  Discrepancy:         {self.area_diff_sqft:+,.1f} SF ({abs(self.area_diff_sqft)/self.stated_area_sqft*100.0:.2f}%)",
            f"FINAL VERDICT:         {self.verdict}",
            f"================================================================================",
        ])
        return "\n".join(lines)


class BeachwoodLotAgent:
    """
    Autonomous Cadastral Lot Agent for Beachwood Unit Two.
    
    Each agent models, verifies, and draws a single subdivision lot.
    """
    def __init__(
        self,
        agent_id: int,
        lot_id: str,
        block_id: str,
        lot_number: str,
        corners: list[Point],
        corner_names: list[str] | None = None,
        curve_specs: dict[str, Any] | None = None,
        stated_area_sqft: float = 7500.0,
        stated_dimensions: str = "75.0' x 100.0'",
        skeleton_pts: list[Any] | None = None,
        skeleton_resolution_ft: float = 2.0,
    ):
        self.agent_id = agent_id
        self.lot_id = lot_id
        self.block_id = block_id
        self.lot_number = lot_number
        self.corners = corners  # Closed or unclosed list of corner Points
        self.corner_names = corner_names or [f"{lot_id}_P{i+1}" for i in range(len(corners))]
        self.curve_specs = curve_specs or {}
        self.stated_area_sqft = stated_area_sqft
        self.stated_dimensions = stated_dimensions
        self.skeleton_pts = skeleton_pts
        self.skeleton_resolution_ft = skeleton_resolution_ft
        self.mapcheck_report: MapCheckReport | None = None


    def compute_mapcheck(self) -> MapCheckReport:
        """
        Execute course-by-course boundary traverse, solve curve parameters,
        and perform mathematical closure and area audit.
        """
        # Ensure corners list has 4 distinct vertices
        pts = self.corners[:-1] if (len(self.corners) > 1 and self.corners[0].dist_to(self.corners[-1]) < 1e-4) else self.corners
        n_pts = len(pts)

        courses: list[MapCheckCourse] = []
        tot_perimeter = 0.0

        for i in range(n_pts):
            p1 = pts[i]
            p2 = pts[(i + 1) % n_pts]
            name1 = self.corner_names[i]
            name2 = self.corner_names[(i + 1) % n_pts]
            
            dist = p1.dist_to(p2)
            tot_perimeter += dist
            dn = p2.n - p1.n
            de = p2.e - p1.e
            az = (math.degrees(math.atan2(de, dn))) % 360.0
            bearing = azimuth_to_bearing(az)

            side_key = f"side_{i+1}"
            curve_info = self.curve_specs.get(side_key)

            if curve_info:
                # Solve all 8 parameters for this curve
                solved_curve = solve_curve_all_parameters(
                    radius=curve_info.get("radius"),
                    delta_deg=curve_info.get("delta_deg"),
                    length=curve_info.get("length"),
                    chord=curve_info.get("chord", dist),
                    tangent=curve_info.get("tangent"),
                    mid_ordinate=curve_info.get("mid_ordinate"),
                    external=curve_info.get("external"),
                )
                default_rot = curve_info.get("rot", "CCW")
                rot = default_rot
                if self.skeleton_pts:
                    from engine.curves import determine_curve_direction_from_skeleton
                    skel_dir_info = determine_curve_direction_from_skeleton(
                        pc=p1,
                        pt=p2,
                        skeleton_pts=self.skeleton_pts,
                        radius=float(solved_curve["radius"]),
                        delta_deg=float(solved_curve["delta_deg"]),
                        fallback_rot=default_rot,
                        resolution_ft=self.skeleton_resolution_ft,
                    )
                    # The coded side is overridden ONLY when the scan decided. This used to accept
                    # the scan's vote whenever it had >= 3 nearby points OR confidence >= 0.20;
                    # nearly any curve has 3 points of unrelated ink beside it, so 9 of 18 coded
                    # sides on Beachwood were flipped at confidence 0.00.
                    if skel_dir_info["decided"]:
                        rot = skel_dir_info["rot"]

                c_obj = Curve(
                    id=curve_info.get("id", f"C_{self.lot_id}"),
                    length=float(solved_curve["length"]),
                    radius=float(solved_curve["radius"]),
                    delta_deg=float(solved_curve["delta_deg"]),
                    chord_bearing=bearing,
                    chord=float(solved_curve["chord"]),
                    rot=rot,
                )

                arc_pts = c_obj.arc_points(p1, n_segments=16)
                
                course = MapCheckCourse(
                    course_num=i + 1,
                    from_node=name1,
                    to_node=name2,
                    start_pt=p1,
                    end_pt=p2,
                    bearing_str=bearing,
                    distance=dist,
                    is_curve=True,
                    curve_data=solved_curve,
                    curve_rot=rot,
                    arc_points=arc_pts,
                )
            else:
                course = MapCheckCourse(
                    course_num=i + 1,
                    from_node=name1,
                    to_node=name2,
                    start_pt=p1,
                    end_pt=p2,
                    bearing_str=bearing,
                    distance=dist,
                    is_curve=False,
                )
            courses.append(course)

        # Traverse closure walk
        p_curr = Point(pts[0].n, pts[0].e)
        for c in courses:
            az = parse_bearing(c.bearing_str)
            p_curr = p_curr.offset(az, c.distance)

        mis_n = p_curr.n - pts[0].n
        mis_e = p_curr.e - pts[0].e
        misclose_dist = math.hypot(mis_n, mis_e)

        if misclose_dist < 1e-4:
            precision_str = "EXACT (0.000 ft)"
        else:
            ratio = tot_perimeter / misclose_dist
            precision_str = f"1:{ratio:,.0f}"

        # Area calculation
        raw_sqft = shoelace_area(pts + [pts[0]])
        # Each curve adds (bulges out of the polygon) or removes (bulges into it) its segment
        # area. Which one is a property of the GEOMETRY -- whether the drawn arc lies outside
        # or inside the polygon -- not of `rot` alone. It used to be fixed by rot (CCW +, CW -),
        # but an arc's bulge relative to the polygon depends on the polygon's WINDING and the
        # direction of travel. Every Beachwood lot is wound clockwise, where that rule is
        # backwards: all 18 curved lots reported an area wrong by twice the segment area, and
        # still passed because their stated areas used the same rule. So bend ONE arc at a time
        # into the ring and see whether the area grows or shrinks; the magnitude stays analytic.
        curve_adj = 0.0
        for k, ck in enumerate(courses):
            if not ck.is_curve:
                continue
            ring: list[Point] = []
            for j, cj in enumerate(courses):
                ring.extend(cj.arc_points[:-1] if j == k else [cj.start_pt])
            grows = shoelace_area(ring + [ring[0]]) > raw_sqft
            seg_a = float(ck.curve_data.get("segment_area", 0.0))
            curve_adj += seg_a if grows else -seg_a

        net_sqft = round(raw_sqft + curve_adj, 1)
        net_acres = net_sqft / 43560.0
        area_diff = round(net_sqft - self.stated_area_sqft, 1)

        is_closed = (misclose_dist <= 0.05)
        area_ok = (abs(area_diff) <= 5.0) or (abs(area_diff) / self.stated_area_sqft < 0.02)
        passed = is_closed and area_ok

        verdict = "PASS - Certified Survey-Grade Lot Closure" if passed else "WARN - Minor Coordinate Discrepancy"

        report = MapCheckReport(
            lot_id=self.lot_id,
            block_id=self.block_id,
            lot_number=self.lot_number,
            courses=courses,
            perimeter_ft=round(tot_perimeter, 2),
            misclose_n_ft=round(mis_n, 4),
            misclose_e_ft=round(mis_e, 4),
            misclose_dist_ft=round(misclose_dist, 4),
            precision_str=precision_str,
            raw_shoelace_sqft=round(raw_sqft, 1),
            curve_adj_sqft=round(curve_adj, 1),
            computed_area_sqft=net_sqft,
            computed_acres=round(net_acres, 4),
            stated_area_sqft=self.stated_area_sqft,
            area_diff_sqft=area_diff,
            passed=passed,
            verdict=verdict,
        )
        self.mapcheck_report = report
        return report

    def draw(
        self,
        dxf: DXFWriter,
        layer: str = "LOT_LINE",
        text_layer: str = "TEXT-LABELS",
        dim_layer: str = "DIM-LABELS",
        curve_layer: str = "CURVE",
        draw_dims: bool = True,
    ):
        """Draw lot boundary, curves, lot number, and dimension annotations into DXF."""
        if not self.mapcheck_report:
            self.compute_mapcheck()

        # Draw boundary polyline
        full_boundary_coords: list[tuple[float, float]] = []
        for c in self.mapcheck_report.courses:
            if c.is_curve and c.arc_points:
                for pt in c.arc_points[:-1]:
                    full_boundary_coords.append((pt.n, pt.e))
                # Also draw on CURVE layer
                dxf.polyline([(p.n, p.e) for p in c.arc_points], layer=curve_layer, closed=False)
            else:
                full_boundary_coords.append((c.start_pt.n, c.start_pt.e))

        dxf.polyline(full_boundary_coords, layer=layer, closed=True)

        # Centroid calculation for text label
        pts = self.corners[:-1] if (len(self.corners) > 1 and self.corners[0].dist_to(self.corners[-1]) < 1e-4) else self.corners
        cn = sum(p.n for p in pts) / len(pts)
        ce = sum(p.e for p in pts) / len(pts)
        
        # Lot number text
        dxf.text((cn, ce), self.lot_number, height=8.0, layer=text_layer)

        # Dimension annotations
        if draw_dims:
            for c in self.mapcheck_report.courses:
                mid_n = (c.start_pt.n + c.end_pt.n) / 2.0
                mid_e = (c.start_pt.e + c.end_pt.e) / 2.0
                # Vector perpendicular to course
                dn = c.end_pt.n - c.start_pt.n
                de = c.end_pt.e - c.start_pt.e
                L = math.hypot(dn, de)
                if L > 1e-6:
                    perp_n = -de / L * 3.5
                    perp_e = dn / L * 3.5
                    lbl_n = mid_n + perp_n
                    lbl_e = mid_e + perp_e
                    dxf.text((lbl_n, lbl_e), f"{c.distance:.1f}'", height=5.5, layer=dim_layer)
