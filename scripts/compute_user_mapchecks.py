"""
compute_user_mapchecks.py -- Survey MapCheck Audit for Lots in User Plat Screenshots.

Plat Book 30, Pages 82 & 82A, Duval County, FL (Beachwood Unit Two):
  Image 1: Block 14 (Lots 7, 8, 9, 10, Tract A, 40' R/W Strip, Lot 11) along Mangrove Ave
  Image 2: Block 15 (Lots 9, 10) along Shellfish Dr, Beachwood Blvd (Curve C2), and Keel Dr
  Image 3: Block 14 (Lots 24, 23) along Shellfish Dr, Mangrove Ave, and South 60' Street R/W
"""
import math
import os
from engine.cogo import Point, parse_bearing
from engine.curves import solve_curve_all_parameters
from engine.lot_agent import BeachwoodLotAgent, MapCheckReport


def solve_corner_curve(b_in: str, b_out: str, radius: float = 25.0) -> dict:
    """
    Determine the delta angle between incoming and outgoing tangents meeting at the P.I.
    and use solve_curve_all_parameters(radius, delta_deg) to solve for:
      - Tangent distance T = R * tan(Delta / 2)
      - Arc length L = R * Delta_rad
      - Chord distance C = 2 * R * sin(Delta / 2)
      - All auxiliary circular curve parameters
    """
    az_in = parse_bearing(b_in)
    az_out = parse_bearing(b_out)
    diff = abs(az_out - az_in) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    delta_deg = diff
    return solve_curve_all_parameters(radius=radius, delta_deg=delta_deg)


def run_all_mapchecks():
    # Azimuths for Block 14 along Mangrove
    eaz14 = parse_bearing('N88°58\'20\"E')
    saz14 = parse_bearing('S01°01\'40\"E')
    waz14 = parse_bearing('S88°58\'20\"W')
    naz14 = parse_bearing('N01°01\'40\"W')

    # Azimuths for Block 15 along Shellfish & Beachwood Blvd
    eaz15 = parse_bearing('N87°35\'30\"E')
    saz15 = parse_bearing('S02°24\'30\"E')
    waz15 = parse_bearing('S87°35\'30\"W')
    naz15 = parse_bearing('N02°24\'30\"W')

    reports: list[MapCheckReport] = []
    curve_solves: list[dict] = []

    # ==============================================================================
    # IMAGE 1: BLOCK 14 LOTS ALONG MANGROVE AVENUE
    # ==============================================================================

    # Lot 7 (Block 14)
    p7_nw = Point(0.0, 0.0)
    p7_ne = p7_nw.offset(eaz14, 100.0)
    p7_se = p7_ne.offset(saz14, 75.0)
    p7_sw = p7_se.offset(waz14, 100.0)
    ag7 = BeachwoodLotAgent(
        agent_id=1407, lot_id='Blk14-Lot7', block_id='14', lot_number='7',
        corners=[p7_nw, p7_ne, p7_se, p7_sw],
        corner_names=['NW_Cor', 'NE_Cor', 'SE_Cor', 'SW_Cor'],
        stated_area_sqft=7500.0, stated_dimensions='100.00\' x 75.00\''
    )
    reports.append(ag7.compute_mapcheck())

    # Lot 8 (Block 14)
    p8_nw = p7_sw
    p8_ne = p7_se
    p8_se = p8_ne.offset(saz14, 75.0)
    p8_sw = p8_se.offset(waz14, 100.0)
    ag8 = BeachwoodLotAgent(
        agent_id=1408, lot_id='Blk14-Lot8', block_id='14', lot_number='8',
        corners=[p8_nw, p8_ne, p8_se, p8_sw],
        corner_names=['NW_Cor', 'NE_Cor', 'SE_Cor', 'SW_Cor'],
        stated_area_sqft=7500.0, stated_dimensions='100.00\' x 75.00\' (5\' West Utility Easement)'
    )
    reports.append(ag8.compute_mapcheck())

    # Lot 9 (Block 14)
    p9_nw = p8_sw
    p9_ne = p8_se
    p9_se = p9_ne.offset(saz14, 75.0)
    p9_sw = p9_se.offset(waz14, 100.0)
    ag9 = BeachwoodLotAgent(
        agent_id=1409, lot_id='Blk14-Lot9', block_id='14', lot_number='9',
        corners=[p9_nw, p9_ne, p9_se, p9_sw],
        corner_names=['NW_Cor', 'NE_Cor', 'SE_Cor', 'SW_Cor'],
        stated_area_sqft=7500.0, stated_dimensions='100.00\' x 75.00\''
    )
    reports.append(ag9.compute_mapcheck())

    # Lot 10 (Block 14)
    p10_nw = p9_sw
    p10_ne = p9_se
    p10_se = p10_ne.offset(saz14, 75.0)
    p10_sw = p10_se.offset(waz14, 100.0)
    ag10 = BeachwoodLotAgent(
        agent_id=1410, lot_id='Blk14-Lot10', block_id='14', lot_number='10',
        corners=[p10_nw, p10_ne, p10_se, p10_sw],
        corner_names=['NW_Cor', 'NE_Cor', 'SE_Cor', 'SW_Cor'],
        stated_area_sqft=7500.0, stated_dimensions='100.00\' x 75.00\''
    )
    reports.append(ag10.compute_mapcheck())

    # Tract "A" (Block 14)
    pta_nw = p10_sw
    pta_ne = p10_se
    pta_se = pta_ne.offset(saz14, 40.0)
    pta_sw = pta_se.offset(waz14, 100.0)
    ag_ta = BeachwoodLotAgent(
        agent_id=1400, lot_id='Blk14-TractA', block_id='14', lot_number='Tract A',
        corners=[pta_nw, pta_ne, pta_se, pta_sw],
        corner_names=['NW_Cor', 'NE_Cor', 'SE_Cor', 'SW_Cor'],
        stated_area_sqft=4000.0, stated_dimensions='100.00\' x 40.00\' (Tract A Lift Station)'
    )
    reports.append(ag_ta.compute_mapcheck())

    # 40' Right of Way / Drainage Strip (Block 14)
    prow_nw = pta_sw
    prow_ne = pta_se
    prow_se = prow_ne.offset(saz14, 40.0)
    prow_sw = prow_se.offset(waz14, 100.0)
    ag_row = BeachwoodLotAgent(
        agent_id=1401, lot_id='Blk14-40ft-ROW', block_id='14', lot_number='40ft R/W',
        corners=[prow_nw, prow_ne, prow_se, prow_sw],
        corner_names=['NW_Cor', 'NE_Cor', 'SE_Cor', 'SW_Cor'],
        stated_area_sqft=4000.0, stated_dimensions='100.00\' x 40.00\' (Dedicated Right-of-Way)'
    )
    reports.append(ag_row.compute_mapcheck())

    # Lot 11 (Block 14) - SE Corner Curve Solver
    # Tangents meeting at SE P.I.: S01°01'40"E (East line) and S88°58'20"W (South line)
    sol11 = solve_corner_curve('S01°01\'40\"E', 'S88°58\'20\"W', radius=25.0)
    curve_solves.append({
        'lot': 'Block 14, Lot 11 (SE Corner)',
        'tangent1': 'S01°01\'40\"E', 'tangent2': 'S88°58\'20\"W',
        'delta': sol11['delta_dms'], 'radius': sol11['radius'],
        'tangent': sol11['tangent'], 'length': sol11['length'], 'chord': sol11['chord'],
        'stated_pi_dist': '100.00\' East line, 100.00\' South line',
        'cut_back_dist': f"{100.0 - sol11['tangent']:.2f}' to PC, {100.0 - sol11['tangent']:.2f}' from PT"
    })
    T11 = sol11['tangent']
    p11_nw = prow_sw
    p11_ne = prow_se
    p11_pc = p11_ne.offset(saz14, 100.0 - T11)
    chord_bearing = parse_bearing('S43°58\'20\"W')
    p11_pt = p11_pc.offset(chord_bearing, sol11['chord'])
    p11_sw = p11_pt.offset(waz14, 100.0 - T11)
    ag11 = BeachwoodLotAgent(
        agent_id=1411, lot_id='Blk14-Lot11', block_id='14', lot_number='11',
        corners=[p11_nw, p11_ne, p11_pc, p11_pt, p11_sw],
        corner_names=['NW_Cor', 'NE_Cor', 'PC', 'PT', 'SW_Cor'],
        curve_specs={'side_3': {'radius': 25.0, 'length': sol11['length'], 'rot': 'CW'}},
        stated_area_sqft=round(10000.0 - 25.0**2 * (1.0 - math.pi / 4.0), 1),
        stated_dimensions=f"100.00\' x {100.0-T11:.2f}\' x {sol11['length']:.2f}\' (arc, R=25\') x {100.0-T11:.2f}\' x 100.00\'"
    )
    reports.append(ag11.compute_mapcheck())

    # Lot 11 (Block 14) - Rectangular (Uncurved)
    p11_sq_se = p11_ne.offset(saz14, 100.0)
    p11_sq_sw = p11_sq_se.offset(waz14, 100.0)
    ag11_sq = BeachwoodLotAgent(
        agent_id=1412, lot_id='Blk14-Lot11-Rectangular', block_id='14', lot_number='11 (Uncurved)',
        corners=[p11_nw, p11_ne, p11_sq_se, p11_sq_sw],
        corner_names=['NW_Cor', 'NE_Cor', 'SE_Cor', 'SW_Cor'],
        stated_area_sqft=10000.0,
        stated_dimensions='100.00\' x 100.00\' (Rectangular)'
    )
    reports.append(ag11_sq.compute_mapcheck())

    # ==============================================================================
    # IMAGE 2: BLOCK 15 LOTS 9 & 10 ALONG BEACHWOOD BOULEVARD
    # Both have 25' corner return curves at the street intersections (NE & SE)
    # The plat dimensions extend to the P.I. (indicated by the corner angle bar glyph)
    # ==============================================================================

    # Lot 9 Block 15 (NE corner curve R=25.0')
    # Tangents meeting at NE P.I.: N87°35'30"E (Shellfish Dr) and S00°41'45"E (Beachwood Blvd)
    sol9 = solve_corner_curve('N87°35\'30\"E', 'S00°41\'45\"E', radius=25.0)
    T9 = sol9['tangent']
    curve_solves.append({
        'lot': 'Block 15, Lot 9 (NE Corner)',
        'tangent1': 'N87°35\'30\"E', 'tangent2': 'S00°41\'45\"E',
        'delta': sol9['delta_dms'], 'radius': sol9['radius'],
        'tangent': sol9['tangent'], 'length': sol9['length'], 'chord': sol9['chord'],
        'stated_pi_dist': '95.98\' North line to P.I., 100.04\' East line to P.I.',
        'cut_back_dist': f"{95.98 - T9:.2f}' to PC, {100.04 - T9:.2f}' from PT"
    })

    p15_9_nw = Point(100.0, 380.0)
    p15_9_pi = p15_9_nw.offset(eaz15, 95.98) # 95.98' extends to P.I.
    p15_9_pc = p15_9_pi.offset(waz15, T9)
    p15_9_pt = p15_9_pi.offset(parse_bearing('S00°41\'45\"E'), T9)
    p15_9_se = p15_9_pt.offset(parse_bearing('S00°41\'45\"E'), 100.04 - T9) # 100.04' extends to P.I.
    p15_9_sw = p15_9_se.offset(waz15, 92.99)

    ag15_9 = BeachwoodLotAgent(
        agent_id=1509, lot_id='Blk15-Lot9', block_id='15', lot_number='9',
        corners=[p15_9_nw, p15_9_pc, p15_9_pt, p15_9_se, p15_9_sw],
        corner_names=['NW_Cor', 'PC', 'PT', 'SE_Cor', 'SW_Cor'],
        curve_specs={'side_2': {'radius': 25.0, 'length': sol9['length'], 'rot': 'CW'}},
        stated_area_sqft=round(9491.1 - 25.0**2 * (1.0 - math.pi / 4.0), 1),
        stated_dimensions=f"{95.98 - T9:.2f}\' (95.98\' to P.I.) x {sol9['length']:.2f}\' (arc, R=25\') x {100.04 - T9:.2f}\' x 92.99\' x 100.00\'"
    )
    reports.append(ag15_9.compute_mapcheck())

    # Lot 10 Block 15 (SE corner curve R=25.0')
    # Tangents meeting at SE P.I.: S00°41'45"E (Beachwood Blvd) and S87°35'30"W (Keel Dr)
    sol10 = solve_corner_curve('S00°41\'45\"E', 'S87°35\'30\"W', radius=25.0)
    T10 = sol10['tangent']
    curve_solves.append({
        'lot': 'Block 15, Lot 10 (SE Corner)',
        'tangent1': 'S00°41\'45\"E', 'tangent2': 'S87°35\'30\"W',
        'delta': sol10['delta_dms'], 'radius': sol10['radius'],
        'tangent': sol10['tangent'], 'length': sol10['length'], 'chord': sol10['chord'],
        'stated_pi_dist': '100.04\' East line to P.I., 90.00\' South line to P.I.',
        'cut_back_dist': f"{100.04 - T10:.2f}' to PC, {90.00 - T10:.2f}' from PT"
    })

    p15_10_nw = p15_9_sw
    p15_10_ne = p15_9_se
    p15_10_sw = p15_10_nw.offset(saz15, 100.00)
    p15_10_pi = p15_10_sw.offset(eaz15, 90.00) # 90.00' extends to P.I.
    p15_10_pc = p15_10_ne.offset(parse_bearing('S00°41\'45\"E'), 100.04 - T10) # 100.04' extends to P.I.
    p15_10_pt = p15_10_pi.offset(waz15, T10)

    ag15_10 = BeachwoodLotAgent(
        agent_id=1510, lot_id='Blk15-Lot10', block_id='15', lot_number='10',
        corners=[p15_10_nw, p15_10_ne, p15_10_pc, p15_10_pt, p15_10_sw],
        corner_names=['NW_Cor', 'NE_Cor', 'PC', 'PT', 'SW_Cor(PRM)'],
        curve_specs={'side_3': {'radius': 25.0, 'length': sol10['length'], 'rot': 'CW'}},
        stated_area_sqft=round(9192.1 - 25.0**2 * (1.0 - math.pi / 4.0), 1),
        stated_dimensions=f"92.99\' x {100.04 - T10:.2f}\' (100.04\' to P.I.) x {sol10['length']:.2f}\' (arc, R=25\') x {90.00 - T10:.2f}\' (90\' to P.I.) x 100.00\'"
    )
    reports.append(ag15_10.compute_mapcheck())

    # ==============================================================================
    # IMAGE 3: BLOCK 14 LOTS 24 & 23 ALONG SHELLFISH & MANGROVE
    # Lot 24 has NW corner curve (R=25')
    # Lot 23 has SW corner curve (R=25')
    # Both have corner angle bar glyphs indicating dimensions extend to P.I.
    # ==============================================================================

    # Lot 24 Block 14
    # Tangents meeting at NW P.I.: N01°01'40"W (Mangrove Ave) and N87°35'30"E (Shellfish Dr)
    sol24 = solve_corner_curve('N01°01\'40\"W', 'N87°35\'30\"E', radius=25.0)
    T24 = sol24['tangent']
    curve_solves.append({
        'lot': 'Block 14, Lot 24 (NW Corner)',
        'tangent1': 'N01°01\'40\"W', 'tangent2': 'N87°35\'30\"E',
        'delta': sol24['delta_dms'], 'radius': sol24['radius'],
        'tangent': sol24['tangent'], 'length': sol24['length'], 'chord': sol24['chord'],
        'stated_pi_dist': '100.74\' West line to P.I., 99.93\' North line to P.I.',
        'cut_back_dist': f"{100.74 - T24:.2f}' to PC, {99.93 - T24:.2f}' from PT"
    })

    p24_pi = Point(0.0, 700.0) # NW P.I.
    p24_pt = p24_pi.offset(eaz15, T24)
    p24_ne = p24_pi.offset(eaz15, 99.93) # 99.93' extends to P.I.
    p24_se = p24_ne.offset(saz15, 103.17)
    p24_sw = p24_pi.offset(parse_bearing('S01°01\'40\"E'), 100.74) # 100.74' extends to P.I.
    p24_pc = p24_pi.offset(parse_bearing('S01°01\'40\"E'), T24)

    ag24 = BeachwoodLotAgent(
        agent_id=1424, lot_id='Blk14-Lot24', block_id='14', lot_number='24',
        corners=[p24_pt, p24_ne, p24_se, p24_sw, p24_pc],
        corner_names=['PT', 'NE_Cor(PRM)', 'SE_Cor', 'SW_Cor', 'PC'],
        curve_specs={'side_5': {'radius': 25.0, 'length': sol24['length'], 'rot': 'CW'}},
        stated_area_sqft=round(10312.1 - 25.0**2 * (1.0 - math.pi / 4.0), 1),
        stated_dimensions=f"{99.93 - T24:.2f}\' (99.93\' to P.I.) x 103.17\' x 102.39\' x {100.74 - T24:.2f}\' (100.74\' to P.I.) x {sol24['length']:.2f}\' (arc, R=25\')"
    )
    reports.append(ag24.compute_mapcheck())

    # Lot 23 Block 14
    # Tangents meeting at SW P.I.: S01°02'47"E (Mangrove Ave) and N88°58'20"E (South line / 60' Street)
    sol23 = solve_corner_curve('S01°02\'47\"E', 'N88°58\'20\"E', radius=25.0)
    T23 = sol23['tangent']
    curve_solves.append({
        'lot': 'Block 14, Lot 23 (SW Corner)',
        'tangent1': 'S01°02\'47\"E', 'tangent2': 'N88°58\'20\"E',
        'delta': sol23['delta_dms'], 'radius': sol23['radius'],
        'tangent': sol23['tangent'], 'length': sol23['length'], 'chord': sol23['chord'],
        'stated_pi_dist': '100.00\' West line to P.I., 80.00\' South line to P.I.',
        'cut_back_dist': f"{100.00 - T23:.2f}' to PC, {80.00 - T23:.2f}' from PT"
    })

    p23_sw_pi = p24_sw.offset(parse_bearing('S01°01\'40\"E'), 100.0) # SW P.I. (100' to P.I.)
    p23_pc = p23_sw_pi.offset(parse_bearing('N01°02\'47\"W'), T23)
    p23_pt = p23_sw_pi.offset(eaz14, T23)
    p23_ang = p23_sw_pi.offset(eaz14, 80.0) # 80' to P.I.
    p23_se = p23_ang.offset(parse_bearing('N89°58\'20\"E'), 17.08)
    p23_ne = p24_se
    p23_nw = p24_sw

    ag23 = BeachwoodLotAgent(
        agent_id=1423, lot_id='Blk14-Lot23', block_id='14', lot_number='23',
        corners=[p23_nw, p23_ne, p23_se, p23_ang, p23_pt, p23_pc],
        corner_names=['NW_Cor', 'NE_Cor', 'SE_Cor', 'Angle_Pt', 'PT', 'PC'],
        curve_specs={'side_5': {'radius': 25.0, 'length': sol23['length'], 'rot': 'CW'}},
        stated_area_sqft=round(9976.6 - 25.0**2 * (1.0 - math.pi / 4.0), 1),
        stated_dimensions=f"102.38\' x 100.44\' x 17.08\' x {80.0 - T23:.2f}\' (80\' to P.I.) x {sol23['length']:.2f}\' (arc, R=25\') x {100.0 - T23:.2f}\' (100\' to P.I.)"
    )
    reports.append(ag23.compute_mapcheck())

    # Write output to data/user_lots_mapcheck_report.txt
    report_path = 'data/user_lots_mapcheck_report.txt'
    with open(report_path, 'w') as f:
        f.write('=' * 80 + '\n')
        f.write('  BEACHWOOD UNIT TWO -- SURVEY MAPCHECK AUDIT REPORT\n')
        f.write('  Plat Book 30, Pages 82 & 82A, Public Records of Duval County, Florida\n')
        f.write('  Complete Analysis for All Lots in Attached User Screenshots:\n')
        f.write('    - Image 1: Block 14 (Lots 7, 8, 9, 10, Tract A, 40\' R/W, Lot 11)\n')
        f.write('    - Image 2: Block 15 (Lots 9, 10)\n')
        f.write('    - Image 3: Block 14 (Lots 24, 23)\n')
        f.write('=' * 80 + '\n\n')

        f.write('=' * 80 + '\n')
        f.write('  CORNER RETURN CURVE SOLVER AUDIT -- TANGENT DERIVATION FROM DELTA ANGLE\n')
        f.write('  Rule: Stated plat dimensions with corner tick/angle bar glyph go to the P.I.\n')
        f.write('  Formula: Tangent T = R * tan(Delta / 2), with R = 25.00 ft per Plat Note 2\n')
        f.write('=' * 80 + '\n')
        f.write(f"{'Corner / Lot Location':<32} | {'Delta Angle':<12} | {'Radius':<7} | {'Tangent (T)':<11} | {'Arc (L)':<8} | {'Chord (C)':<8}\n")
        f.write('-' * 88 + '\n')
        for cs in curve_solves:
            f.write(f"{cs['lot']:<32} | {cs['delta']:<12} | {cs['radius']:<7.2f} | {cs['tangent']:<11.4f} | {cs['length']:<8.2f} | {cs['chord']:<8.2f}\n")
            f.write(f"  Tangents: {cs['tangent1']} and {cs['tangent2']}\n")
            f.write(f"  Plat Dimensions to P.I.: {cs['stated_pi_dist']}\n")
            f.write(f"  Cut-back straight courses: {cs['cut_back_dist']}\n")
            f.write('-' * 88 + '\n')
        f.write('\n\n')

        for rep in reports:
            f.write(rep.format_text() + '\n\n')

    print(f'Successfully wrote {len(reports)} mapcheck reports to {report_path}')
    return reports


if __name__ == '__main__':
    run_all_mapchecks()
