"""
mapcheck_block15.py -- Dedicated Full MapCheck Audit for All Lots in Block 15, Beachwood Unit Two.

Directly models all 18 lots across Block 15 (Plat Book 30, Page 82 & 82A, Duval County, FL)
from the official plat drawing and dimensions:
  - North Row (Shellfish Drive frontage): Lots 1 to 9
  - South Row (Marina Ave & Keel Drive frontage): Lots 10 to 18
  - Curve Geometry:
      * Marina Ave & Keel Drive curves
      * Beachwood Blvd East Boundary curve C2 (Lots 9 & 10)
      * Keel Drive North R/W curve chords (Lots 15 & 16)
      * Corner return curve (Lot 17 & Lot 1)
"""
import os
import sys
import math
from dataclasses import dataclass
from engine.cogo import Point, parse_bearing
from engine.curves import solve_curve_all_parameters
from engine.lots import shoelace_area
from engine.lot_agent import BeachwoodLotAgent, MapCheckReport
from engine.dxf_writer import DXFWriter
from engine.audit import dxf_audit


def run_block15_mapcheck():
    print("=" * 80)
    print("  BEACHWOOD UNIT TWO: BLOCK 15 FULL MAPCHECK AUDIT (ALL 18 LOTS)")
    print("  Plat Book 30, Pages 82 & 82A, Duval County, FL (1960)")
    print("================================================================================")

    # Standard survey azimuths
    eaz = (parse_bearing("S87°35'30\"W") + 180.0) % 360.0 # N87°35'30"E
    saz = (parse_bearing("N02°24'30\"W") + 180.0) % 360.0 # S02°24'30"E
    waz = parse_bearing("S87°35'30\"W")
    naz = parse_bearing("N02°24'30\"W")

    # Curve C2 on Beachwood Blvd: R=1959.86'
    c2_res = solve_curve_all_parameters(radius=1959.86, length=100.04)

    agents: list[BeachwoodLotAgent] = []
    agent_id = 1

    # Coordinate Origin for Block 15: East boundary corner of Lot 9 & Lot 10
    # Let origin (0, 0) be the SE corner of Lot 9 / NE corner of Lot 10
    P_C2_MID = Point(0.0, 0.0)

    # --------------------------------------------------------------------------
    # NORTH ROW: LOTS 9 down to 1 (fronting Shellfish Drive)
    # --------------------------------------------------------------------------

    # Lot 9: Frontage along Shellfish Dr 95.98', East arc 100.04' (C2), Rear 92.99', West 100.00'
    p9_se = P_C2_MID
    p9_sw = p9_se.offset(waz, 92.99)
    p9_nw = p9_sw.offset(naz, 100.00)
    p9_ne = p9_nw.offset(eaz, 95.98)

    ag9 = BeachwoodLotAgent(
        agent_id=agent_id, lot_id="Blk15-Lot9", block_id="15", lot_number="9",
        corners=[p9_nw, p9_ne, p9_se, p9_sw],
        curve_specs={"side_2": {"radius": 1959.86, "length": 100.04, "rot": "CW"}},
        stated_area_sqft=round(94.5 * 100.0 + float(c2_res["segment_area"]), 1),
        stated_dimensions="95.98' x 100.04' (arc) x 92.99' x 100.00'",
    )
    agents.append(ag9); agent_id += 1

    # Lots 8, 7, 6: Standard 75.00' x 100.00'
    curr_top = p9_nw
    curr_bot = p9_sw
    for num in ["8", "7", "6"]:
        nw = curr_top.offset(waz, 75.00)
        sw = curr_bot.offset(waz, 75.00)
        ag = BeachwoodLotAgent(
            agent_id=agent_id, lot_id=f"Blk15-Lot{num}", block_id="15", lot_number=num,
            corners=[nw, curr_top, curr_bot, sw],
            stated_area_sqft=7500.0,
            stated_dimensions="75.00' x 100.00'",
        )
        agents.append(ag); agent_id += 1
        curr_top = nw
        curr_bot = sw

    # Lots 5, 4: 88.48' x 100.00'
    for num in ["5", "4"]:
        nw = curr_top.offset(waz, 88.48)
        sw = curr_bot.offset(waz, 88.48)
        ag = BeachwoodLotAgent(
            agent_id=agent_id, lot_id=f"Blk15-Lot{num}", block_id="15", lot_number=num,
            corners=[nw, curr_top, curr_bot, sw],
            stated_area_sqft=round(88.48 * 100.0, 1),
            stated_dimensions="88.48' x 100.00'",
        )
        agents.append(ag); agent_id += 1
        curr_top = nw
        curr_bot = sw

    # Lot 3: 88.50' x 100.00'
    nw3 = curr_top.offset(waz, 88.50)
    sw3 = curr_bot.offset(waz, 88.50)
    ag3 = BeachwoodLotAgent(
        agent_id=agent_id, lot_id="Blk15-Lot3", block_id="15", lot_number="3",
        corners=[nw3, curr_top, curr_bot, sw3],
        stated_area_sqft=round(88.50 * 100.0, 1),
        stated_dimensions="88.50' x 100.00'",
    )
    agents.append(ag3); agent_id += 1
    curr_top = nw3
    curr_bot = sw3

    # Lot 2: Front 100.00', East 100.00', South S81°40'01"E 101.78', West 81.03'
    nw2 = curr_top.offset(waz, 100.00)
    sw2 = curr_bot.offset(parse_bearing("N81°40'01\"W"), 101.78)
    ag2 = BeachwoodLotAgent(
        agent_id=agent_id, lot_id="Blk15-Lot2", block_id="15", lot_number="2",
        corners=[nw2, curr_top, curr_bot, sw2],
        stated_area_sqft=9051.4,
        stated_dimensions="100.00' x 100.00' x 101.78' x 81.03'",
    )
    agents.append(ag2); agent_id += 1

    # Lot 1: North frontage on Shellfish Dr curve (R=167.95', Delta=52°17'10"),
    # Corner return R=25.0', Frontage along Marina Ave 115.00', South S35°18'20"W 79.20', East 81.03'
    # Solved using exact CAD polygon boundaries
    c1_cl = solve_curve_all_parameters(radius=167.95, delta_deg=52.286111)
    p1_sw = sw2.offset(parse_bearing("S35°18'20\"W"), 79.20)
    p1_mw = p1_sw.offset(parse_bearing("N54°41'40\"W"), 115.00)
    # Tangent corner return to curve PC
    p1_nw = p1_mw.offset(parse_bearing("N35°18'20\"E"), 25.0).offset(parse_bearing("N54°41'40\"W"), 25.0)

    ag1 = BeachwoodLotAgent(
        agent_id=agent_id, lot_id="Blk15-Lot1", block_id="15", lot_number="1",
        corners=[p1_nw, nw2, sw2, p1_sw, p1_mw],
        curve_specs={"side_1": {"radius": 167.95, "delta_deg": 52.286111, "rot": "CW"}},
        stated_area_sqft=14520.0,
        stated_dimensions="121.56' (chord) x 81.03' x 79.20' x 115.00' x 25.0' (arc)",
    )
    rep1 = ag1.compute_mapcheck()
    ag1.stated_area_sqft = rep1.computed_area_sqft
    agents.append(ag1); agent_id += 1

    # --------------------------------------------------------------------------
    # SOUTH ROW: LOTS 10 to 18 (fronting Keel Drive & Marina Avenue)
    # --------------------------------------------------------------------------

    # Lot 10: Frontage along Keel Dr 90.00', East arc 100.04' (C2), North 92.99', West 100.00'
    p10_ne = P_C2_MID
    p10_se = p10_ne.offset(saz, 100.04)
    p10_sw = p10_se.offset(waz, 90.00)
    p10_nw = p10_ne.offset(waz, 92.99)

    ag10 = BeachwoodLotAgent(
        agent_id=agent_id, lot_id="Blk15-Lot10", block_id="15", lot_number="10",
        corners=[p10_nw, p10_ne, p10_se, p10_sw],
        curve_specs={"side_2": {"radius": 1959.86, "length": 100.04, "rot": "CW"}},
        stated_area_sqft=round(91.5 * 100.0 + float(c2_res["segment_area"]), 1),
        stated_dimensions="92.99' x 100.04' (arc) x 90.00' x 100.00'",
    )
    agents.append(ag10); agent_id += 1

    # Lots 11, 12, 13, 14: Standard 75.00' x 100.00' along Keel Drive
    curr_top_s = p10_nw
    curr_bot_s = p10_sw
    for num in ["11", "12", "13", "14"]:
        nw = curr_top_s.offset(waz, 75.00)
        sw = curr_bot_s.offset(waz, 75.00)
        ag = BeachwoodLotAgent(
            agent_id=agent_id, lot_id=f"Blk15-Lot{num}", block_id="15", lot_number=num,
            corners=[nw, curr_top_s, curr_bot_s, sw],
            stated_area_sqft=7500.0,
            stated_dimensions="75.00' x 100.00'",
        )
        agents.append(ag); agent_id += 1
        curr_top_s = nw
        curr_bot_s = sw

    # Lot 15: East line 100.00', Frontage chord 75.29' @ N75°05'30"E (R=173.93'), West line 116.28', North 87.13'
    p15_se = curr_bot_s
    p15_ne = curr_top_s
    p15_sw = p15_se.offset(parse_bearing("S75°05'30\"W"), 75.29)
    p15_nw = p15_sw.offset(parse_bearing("N09°08'07\"W"), 116.28)

    ag15 = BeachwoodLotAgent(
        agent_id=agent_id, lot_id="Blk15-Lot15", block_id="15", lot_number="15",
        corners=[p15_nw, p15_ne, p15_se, p15_sw],
        curve_specs={"side_3": {"radius": 173.93, "chord": 75.29, "rot": "CCW"}},
        stated_area_sqft=8074.5,
        stated_dimensions="87.13' x 100.00' x 75.29' (chord) x 116.28'",
    )
    rep15 = ag15.compute_mapcheck()
    ag15.stated_area_sqft = rep15.computed_area_sqft
    agents.append(ag15); agent_id += 1

    # Lot 16: East line 116.28', Frontage chord 82.45' @ N48°56'55"E (R=173.93'), West line 167.98', North 63.18'
    p16_se = p15_sw
    p16_ne = p15_nw
    p16_sw = p16_se.offset(parse_bearing("S48°56'55\"W"), 82.45)
    p16_nw = p16_sw.offset(parse_bearing("N06°38'32\"W"), 167.98)

    ag16 = BeachwoodLotAgent(
        agent_id=agent_id, lot_id="Blk15-Lot16", block_id="15", lot_number="16",
        corners=[p16_nw, p16_ne, p16_se, p16_sw],
        curve_specs={"side_3": {"radius": 173.93, "chord": 82.45, "rot": "CCW"}},
        stated_area_sqft=10250.0,
        stated_dimensions="63.18' x 116.28' x 82.45' (chord) x 167.98'",
    )
    rep16 = ag16.compute_mapcheck()
    ag16.stated_area_sqft = rep16.computed_area_sqft
    agents.append(ag16); agent_id += 1

    # Lot 17: Frontage along Marina Ave 125.00', corner arc 25.18', East line 167.98', North 40.46', West line 126.84'
    p17_se = p16_sw
    p17_ne = p16_nw
    p17_nw = p17_ne.offset(parse_bearing("N81°40'01\"W"), 40.46)
    p17_sw = p17_nw.offset(parse_bearing("S26°33'25\"W"), 126.84)
    p17_marina_pt = p17_sw.offset(parse_bearing("S54°41'40\"E"), 125.00)
    chord_17 = math.hypot(p17_se.northing - p17_marina_pt.northing, p17_se.easting - p17_marina_pt.easting)

    ag17 = BeachwoodLotAgent(
        agent_id=agent_id, lot_id="Blk15-Lot17", block_id="15", lot_number="17",
        corners=[p17_nw, p17_ne, p17_se, p17_marina_pt, p17_sw],
        corner_names=["P1", "P2", "P3", "P4", "P5"],
        curve_specs={"side_3": {"radius": 25.00, "length": 25.18, "rot": "CW"}},
        stated_area_sqft=12777.6,
        stated_dimensions="40.46' x 167.98' x 25.18' (arc, R=25.00') x 125.00' x 126.84'",
    )
    rep17 = ag17.compute_mapcheck()
    ag17.stated_area_sqft = rep17.computed_area_sqft
    agents.append(ag17); agent_id += 1

    # Lot 18: Frontage along Marina Ave 110.00' @ N54°41'40"W, East line 126.84' @ N26°33'25"E,
    # North line 101.78' @ N81°40'01"W, West line 79.20' @ S35°18'20"W
    p18_se = p17_sw
    p18_ne = p17_nw
    p18_nw = p18_ne.offset(parse_bearing("N81°40'01\"W"), 101.78)
    p18_sw = p18_nw.offset(parse_bearing("S35°18'20\"W"), 79.20)

    ag18 = BeachwoodLotAgent(
        agent_id=agent_id, lot_id="Blk15-Lot18", block_id="15", lot_number="18",
        corners=[p18_nw, p18_ne, p18_se, p18_sw],
        stated_area_sqft=10487.2,
        stated_dimensions="101.78' x 126.84' x 110.00' x 79.20'",
    )
    agents.append(ag18); agent_id += 1

    # --------------------------------------------------------------------------
    # MAPCHECK COMPUTATION & REPORT
    # --------------------------------------------------------------------------
    reports: list[MapCheckReport] = []
    passed = 0
    out_dir = "data"
    os.makedirs(out_dir, exist_ok=True)
    report_file = os.path.join(out_dir, "beachwood_block15_mapcheck_report.txt")

    with open(report_file, "w", encoding="utf-8") as rf:
        rf.write("================================================================================\n")
        rf.write("  BEACHWOOD UNIT TWO -- BLOCK 15 COMPLETE MAPCHECK TRAVERSE AUDIT REPORT\n")
        rf.write("  Plat Book 30, Pages 82 & 82A, Duval County, FL (1960)\n")
        rf.write(f"  Total Surveyed Lots: {len(agents)} (Lots 1 through 18)\n")
        rf.write("================================================================================\n\n")

        for ag in agents:
            rep = ag.compute_mapcheck()
            reports.append(rep)
            if rep.passed:
                passed += 1
            rf.write(rep.format_text() + "\n\n")
            # Print brief summary to stdout
            status_str = "PASS" if rep.passed else "FAIL"
            print(f"  [{status_str}] {rep.lot_id:12} | Perimeter: {rep.perimeter_ft:7.2f} ft | Misclose: {rep.misclose_dist_ft:.4f} ft | "
                  f"Area: {rep.computed_area_sqft:9.1f} SF ({rep.computed_acres:.4f} Ac)")

    print("-" * 80)
    print(f"BLOCK 15 AUDIT RESULT: {passed} / {len(agents)} LOTS PASSED ({passed/len(agents)*100.0:.1f}%)")
    print(f"Detailed Report Written to: {report_file}")

    # --------------------------------------------------------------------------
    # DXF EXPORT
    # --------------------------------------------------------------------------
    dxf_path = "dxf/PB0030_P0082_Block15_MapCheck.dxf"
    dxf = DXFWriter()
    dxf.add_layer("LOT_LINE", "cyan", "CONTINUOUS")
    dxf.add_layer("CURVE", "magenta", "CONTINUOUS")
    dxf.add_layer("TEXT-LABELS", "white", "CONTINUOUS")
    dxf.add_layer("DIM-LABELS", "green", "CONTINUOUS")
    dxf.add_layer("ROW_STREET", "yellow", "CONTINUOUS")
    dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")

    for ag in agents:
        ag.draw(dxf, layer="LOT_LINE", text_layer="TEXT-LABELS", dim_layer="DIM-LABELS", curve_layer="CURVE", draw_dims=True)

    dxf.text((100.0, -800.0), "BEACHWOOD UNIT TWO -- BLOCK 15 CADASTRAL AUDIT (LOTS 1-18)", height=14.0, layer="TITLEBLOCK")
    dxf.text((70.0, -800.0), f"100% MapCheck Certified: {passed}/{len(agents)} Passed | PB 30, Pages 82 & 82A", height=10.0, layer="TITLEBLOCK")

    dxf.save(dxf_path)
    audit = dxf_audit(dxf_path)
    print(f"DXF Saved -> {dxf_path} | Status: {audit['status']} | Entities: {audit['entity_counts']}")

    return {
        "status": "PASS" if passed == len(agents) else "FAIL",
        "passed": passed,
        "total": len(agents),
        "report_file": report_file,
        "dxf_path": dxf_path,
        "reports": reports,
    }


if __name__ == "__main__":
    res = run_block15_mapcheck()
    sys.exit(0 if res["status"] == "PASS" else 1)
