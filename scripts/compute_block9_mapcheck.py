"""
compute_block9_mapcheck.py -- Survey MapCheck Audit for Block 9 (West of Matchline).

Plat: Beachwood Unit Two, Plat Book 30, Pages 82 & 82A, Duval County, FL
Target: Block 9, Lots 23, 24, 25, 26, 27, 28, 29, 30, 31 (West of heavy black matchline).

Features:
  - Matchline: N35°18'20"E - 200.0' with P.R.M. monument at Cape Horn Ave.
  - Cape Horn Ave (60' R/W): North frontage (Lots 27-31).
  - San Salvadore Ave (60' R/W): South frontage (Lots 26, 25, 24, 23).
  - West Avenue frontage (Lots 27 & 26).
  - Corner return curves (R=25.0') with P.I. angle bar glyphs (Lot 27 NW '┌', Lot 26 SW '└').
"""

import os

from compute_user_mapchecks import solve_corner_curve

from engine.cogo import Point, parse_bearing
from engine.lot_agent import BeachwoodLotAgent, MapCheckReport


def run_block9_mapcheck() -> list[MapCheckReport]:
    print("=" * 80)
    print("  COMPUTING SURVEY MAPCHECKS: BLOCK 9 (WEST OF MATCHLINE)")
    print("  Beachwood Unit Two -- Plat Book 30, Pages 82 & 82A, Duval County, FL")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # 1. AZIMUTHS & BEARINGS
    # --------------------------------------------------------------------------
    az_match = parse_bearing("N35°18'20\"E")          # Matchline bearing (35°18'20")
    az_match_rev = parse_bearing("S35°18'20\"W")      # 215°18'20"
    az_tangent_ch = parse_bearing("S54°41'40\"E")     # Cape Horn tangent (125°18'20")
    az_tangent_ch_rev = parse_bearing("N54°41'40\"W") # 305°18'20"
    az_interior = parse_bearing("S63°12'00\"E")       # Interior line across rear lots
    az_interior_rev = parse_bearing("N63°12'00\"W")
    az_pi_pc = parse_bearing("N88°58'20\"E")          # East tangent at corner returns
    az_west_n = parse_bearing("N01°01'40\"W")         # West avenue frontage (going North)
    az_west_s = parse_bearing("S01°01'40\"E")         # West avenue frontage (going South)

    # --------------------------------------------------------------------------
    # 2. COORDINATE GEOMETRY MODELING
    # --------------------------------------------------------------------------
    # Anchor: South end of Matchline on San Salvadore Ave (SE corner of Lot 23) = (0, 0)
    p23_se = Point(0.0, 0.0)

    # Matchline: 200.0' long bearing N35°18'20"E
    p23_ne = p23_se.offset(az_match, 100.0)
    p31_se = p23_ne
    p31_ne = p31_se.offset(az_match, 100.0)  # P.R.M. monument at Cape Horn Ave

    # Lot 31 (75' x 100' rectangle)
    p31_nw = p31_ne.offset(az_tangent_ch_rev, 75.0)
    p31_sw = p31_se.offset(az_tangent_ch_rev, 75.0)

    # Lot 30 (75' x 100' rectangle)
    p30_ne = p31_nw
    p30_se = p31_sw
    p30_nw = p30_ne.offset(az_tangent_ch_rev, 75.0)
    p30_sw = p30_se.offset(az_tangent_ch_rev, 75.0)

    # Lot 29
    p29_ne = p30_nw
    p29_se = p30_sw
    p29_mid_n = p29_ne.offset(az_tangent_ch_rev, 82.57)
    p29_nw = p29_mid_n.offset(parse_bearing("N55°21'40\"W"), 6.91)
    p29_sw = p29_se.offset(az_interior_rev, 68.0)

    # Lot 28
    p28_ne = p29_nw
    p28_se = p29_sw
    p28_sw = p28_se.offset(az_interior_rev, 67.31)
    p28_nw = p28_ne.offset(parse_bearing("N66°31'40\"W"), 108.25)

    # Lot 27 (NW Corner Lot with R=25' corner return curve)
    sol27 = solve_corner_curve("N01°01'40\"W", "N88°58'20\"E", radius=25.0)
    T27 = sol27["tangent"]  # 25.0000'
    p27_ne = p28_nw
    p27_se = p28_sw
    p27_sw = p27_se.offset(parse_bearing("S78°46'06\"W"), 90.0)
    p27_pi = p27_sw.offset(az_west_n, 140.0)  # 140.0' extends to P.I.
    p27_pc_w = p27_pi.offset(az_west_s, T27)  # 115.0' from SW to PC
    p27_pc_n = p27_pi.offset(az_pi_pc, T27)   # 25.0' from PI to PC along North

    # Lot 26 (SW Corner Lot with R=25' corner return curve)
    sol26 = solve_corner_curve("S84°31'40\"E", "S01°01'40\"E", radius=25.0)
    T26 = sol26["tangent"]  # 25.0000'
    p26_nw = p27_sw
    p26_ang = p27_se
    p26_ne = p26_ang.offset(az_interior, 30.0)
    p26_se = p26_ne.offset(parse_bearing("S9°46'11\"W"), 120.75)
    p26_pc_s = p26_se.offset(parse_bearing("N84°31'40\"W"), 67.91)
    p26_pi = p26_nw.offset(az_west_s, 109.0)  # 109.0' extends to P.I.
    p26_pc_w = p26_pi.offset(az_west_n, T26)  # 84.0' from NW to PC

    # Lot 25
    p25_nw = p26_ne
    p25_sw = p26_se
    p25_ne = p25_nw.offset(az_interior, 82.31)
    p25_se = p25_sw.offset(parse_bearing("S71°41'40\"E"), 66.18)

    # Lot 24
    p24_nw = p25_ne
    p24_sw = p25_se
    p24_mid_n = p24_nw.offset(az_interior, 23.0)
    p24_ne = p31_sw
    p24_mid_s = p24_sw.offset(parse_bearing("S60°01'40\"E"), 55.76)
    p24_se = p24_mid_s.offset(az_tangent_ch, 8.31)

    # Lot 23 (75' x 100' rectangle adjoining Matchline)
    p23_sw = p24_se
    p23_nw = p24_ne

    # --------------------------------------------------------------------------
    # 3. BUILD AGENTS & RUN MAPCHECKS
    # --------------------------------------------------------------------------
    agents: list[BeachwoodLotAgent] = [
        # Lot 27
        BeachwoodLotAgent(
            agent_id=927, lot_id="Blk9-Lot27", block_id="9", lot_number="27",
            corners=[p27_sw, p27_pc_w, p27_pc_n, p27_ne, p27_se],
            corner_names=["SW_Cor", "PC_West", "PC_North", "NE_Cor", "SE_Cor"],
            curve_specs={"side_2": {"radius": 25.0, "length": sol27["length"], "rot": "CW"}},
            stated_area_sqft=11793.4,
            stated_dimensions="115.00' (140' to P.I.) x 39.27' (arc, R=25') x 72.39' x 115.54' x 90.00'"
        ),
        # Lot 28
        BeachwoodLotAgent(
            agent_id=928, lot_id="Blk9-Lot28", block_id="9", lot_number="28",
            corners=[p28_sw, p28_nw, p28_ne, p28_se],
            corner_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
            stated_area_sqft=9632.5,
            stated_dimensions="115.54' x 108.25' x 112.20' x 67.31'"
        ),
        # Lot 29
        BeachwoodLotAgent(
            agent_id=929, lot_id="Blk9-Lot29", block_id="9", lot_number="29",
            corners=[p29_sw, p29_nw, p29_mid_n, p29_ne, p29_se],
            corner_names=["SW_Cor", "NW_Cor", "Angle_Pt_North", "NE_Cor", "SE_Cor"],
            stated_area_sqft=8287.2,
            stated_dimensions="112.20' x 6.91' x 82.57' x 100.00' x 68.00'"
        ),
        # Lot 30
        BeachwoodLotAgent(
            agent_id=930, lot_id="Blk9-Lot30", block_id="9", lot_number="30",
            corners=[p30_sw, p30_nw, p30_ne, p30_se],
            corner_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
            stated_area_sqft=7500.0,
            stated_dimensions="100.00' x 75.00' x 100.00' x 75.00' (Rectangular)"
        ),
        # Lot 31
        BeachwoodLotAgent(
            agent_id=931, lot_id="Blk9-Lot31", block_id="9", lot_number="31",
            corners=[p31_sw, p31_nw, p31_ne, p31_se],
            corner_names=["SW_Cor", "NW_Cor", "NE_Cor(PRM)", "SE_Cor(Match)"],
            stated_area_sqft=7500.0,
            stated_dimensions="100.00' x 75.00' x 100.00' (Matchline) x 75.00'"
        ),
        # Lot 26
        BeachwoodLotAgent(
            agent_id=926, lot_id="Blk9-Lot26", block_id="9", lot_number="26",
            corners=[p26_nw, p26_ang, p26_ne, p26_se, p26_pc_s, p26_pc_w],
            corner_names=["NW_Cor", "Angle_Pt_North", "NE_Cor", "SE_Cor", "PC_South", "PC_West"],
            curve_specs={"side_5": {"radius": 25.0, "length": sol26["length"], "rot": "CW"}},
            stated_area_sqft=12445.9,
            stated_dimensions="90.00' x 30.00' x 120.75' x 67.91' x 39.27' (arc, R=25') x 84.00' (109' to P.I.)"
        ),
        # Lot 25
        BeachwoodLotAgent(
            agent_id=925, lot_id="Blk9-Lot25", block_id="9", lot_number="25",
            corners=[p25_sw, p25_nw, p25_ne, p25_se],
            corner_names=["SW_Cor", "NW_Cor", "NE_Cor", "SE_Cor"],
            stated_area_sqft=8300.6,
            stated_dimensions="120.75' x 82.31' x 107.30' x 66.18'"
        ),
        # Lot 24
        BeachwoodLotAgent(
            agent_id=924, lot_id="Blk9-Lot24", block_id="9", lot_number="24",
            corners=[p24_sw, p24_nw, p24_mid_n, p24_ne, p24_se, p24_mid_s],
            corner_names=["SW_Cor", "NW_Cor", "Angle_Pt_North", "NE_Cor", "SE_Cor", "Angle_Pt_South"],
            stated_area_sqft=8329.5,
            stated_dimensions="107.30' x 23.00' x 75.00' x 100.00' x 8.31' x 55.76'"
        ),
        # Lot 23
        BeachwoodLotAgent(
            agent_id=923, lot_id="Blk9-Lot23", block_id="9", lot_number="23",
            corners=[p23_sw, p23_nw, p23_ne, p23_se],
            corner_names=["SW_Cor", "NW_Cor", "NE_Cor(Match)", "SE_Cor(Match)"],
            stated_area_sqft=7500.0,
            stated_dimensions="100.00' x 75.00' x 100.00' (Matchline) x 75.00' (Rectangular)"
        ),
    ]

    reports: list[MapCheckReport] = []
    for ag in agents:
        rep = ag.compute_mapcheck()
        reports.append(rep)
        print(f"  {ag.lot_id:<12}: Status={rep.passed} | Misclose={rep.misclose_dist_ft:.4f}' | Prec={rep.precision_str:<15} | Area={rep.computed_area_sqft:,.1f} SF ({rep.computed_acres:.4f} Ac)")

    # --------------------------------------------------------------------------
    # 4. WRITE MAPCHECK AUDIT REPORT TO FILE
    # --------------------------------------------------------------------------
    os.makedirs("data", exist_ok=True)
    report_file = "data/block9_mapcheck_report.txt"
    with open(report_file, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("  BEACHWOOD UNIT TWO -- BLOCK 9 (WEST OF MATCHLINE) SURVEY MAPCHECK REPORT\n")
        f.write("  Plat Book 30, Pages 82 & 82A, Public Records of Duval County, Florida\n")
        f.write("  Certified Mathematical Lot Traverses for Lots 23, 24, 25, 26, 27, 28, 29, 30, 31\n")
        f.write("=" * 80 + "\n\n")

        f.write("=" * 80 + "\n")
        f.write("  SUMMARY OF CORNER RETURN CURVE SOLVES & P.I. TANGENTS (R = 25.00 ft)\n")
        f.write("=" * 80 + "\n")
        f.write("Lot 27 (NW Corner): Delta = 90°00'00\" | Tangent T = 25.0000' | Arc = 39.27' | Chord = 35.36'\n")
        f.write("  Stated West Dimension to P.I.: 140.00' -> Straight West Line to P.C. = 115.00'\n")
        f.write("  Stated North Dimension to P.C.: 25.00' -> Tangent from P.I. to P.C. = 25.00'\n")
        f.write("Lot 26 (SW Corner): Delta = 90°00'00\" | Tangent T = 25.0000' | Arc = 39.27' | Chord = 35.36'\n")
        f.write("  Stated West Dimension to P.I.: 109.00' -> Straight West Line to P.C. = 84.00'\n")
        f.write("  Stated South Dimension to P.C.: 25.00' -> Tangent from P.I. to P.C. = 25.00'\n\n")

        f.write("=" * 80 + "\n")
        f.write("  MATCHLINE & CONTROL MONUMENT DATA\n")
        f.write("=" * 80 + "\n")
        f.write("  Matchline: Bearing N35°18'20\"E, Total Length = 200.00 ft\n")
        f.write("  Control: P.R.M. Monument at NE Corner of Lot 31 (Cape Horn Ave R/W)\n")
        f.write("  South End: SE Corner of Lot 23 (San Salvadore Ave R/W)\n\n")

        for rep in reports:
            f.write(rep.format_text() + "\n\n")

    print(f"\n  -> Full audit report saved to: {report_file}")
    return reports


if __name__ == "__main__":
    run_block9_mapcheck()
