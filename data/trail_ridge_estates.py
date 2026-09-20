"""
Trail Ridge Estates -- PB 82, Pg 35-40, Clay County, FL
CFN 1000001532, recorded 8/5/2026. Perret & Associates, Inc.

Transcribed from Sheets 1, 2, 3, 4, 5 of 6 (Sheet 6 / Pg 40 NOT YET SUPPLIED --
see MASTER_PROMPT.md open items). All bearings/distances below are as shown
on the plat sheets; nothing here is estimated or interpolated.
"""

# --- Sheet 2, State Plane Coordinates Table (anchors the whole plat in real
# space; NAD83(2011), Florida East Zone 0901, US survey feet) ---
STATE_PLANE_POINTS = {
    1: dict(desc="POINT OF BEGINNING", n=2109242.6727, e=390364.4882),
    2: dict(desc='SOUTHWEST CORNER OF TRACT "H"', n=2107916.3070, e=389373.8430),
}

# --- Sheet 1 Caption: overall parent-tract boundary, closed traverse ---
# Point of Commencement -> POB -> 4 boundary courses -> back to POB.
COMMENCEMENT_TO_POB = dict(
    label="C->POB", bearing="S89°42'22\"W", distance=334.57,
    note="along S'ly R/W line of Trail Ridge Road (60' R/W) from intersection "
         "with E line of SE1/4 of SW1/4 Sec 19-4S-25E to E line of ORB 1842/1624",
)

BOUNDARY_COURSES = [
    dict(label="POB->1", bearing="S00°36'13\"E", distance=1318.85,
         note="along E line of ORB1842/1624 & W line of E1/2 of SE1/4 SW1/4 Sec19, to S line of Sec19"),
    dict(label="1->2", bearing="S89°34'08\"W", distance=1004.57,
         note="along S line of Sec19 to SW corner of SE1/4 of SW1/4 Sec19"),
    dict(label="2->3", bearing="N00°33'19\"W", distance=1321.28,
         note="along W line of SE1/4 of SW1/4 Sec19 to S'ly R/W line Trail Ridge Rd"),
    dict(label="3->POB", bearing="N89°42'22\"E", distance=1003.47,
         note="along S'ly R/W line Trail Ridge Rd back to POB"),
]
BOUNDARY_ACREAGE_STATED = 30.4  # "more or less", per Sheet 1 Caption

# --- Master Line Table (plat-wide numbering, L2-L14 seen so far on Sheets 3-5;
# L1 not shown on any sheet supplied -- likely on missing Sheet 6) ---
LINE_TABLE = {
    "L2":  dict(length=35.27, bearing="S44°51'09\"W"),
    "L3":  dict(length=9.93,  bearing="S00°00'00\"E"),
    "L4":  dict(length=9.16,  bearing="N00°00'01\"E"),
    "L5":  dict(length=35.26, bearing="N45°08'51\"W"),
    "L6":  dict(length=11.54, bearing="S67°38'48\"E"),
    "L7":  dict(length=17.71, bearing="S67°35'48\"E"),
    "L8":  dict(length=26.27, bearing="S85°45'41\"E"),
    "L9":  dict(length=51.13, bearing="N77°47'52\"W"),
    "L10": dict(length=53.37, bearing="S72°42'36\"W"),
    "L11": dict(length=53.72, bearing="N80°26'48\"W"),
    "L12": dict(length=57.15, bearing="S84°35'10\"W"),
    "L13": dict(length=49.60, bearing="S77°25'16\"W"),
    "L14": dict(length=29.25, bearing="S67°38'48\"E"),
    "L24": dict(length=35.72, bearing="S84°35'10\"W"),
}

# --- Master Curve Table (plat-wide numbering C2-C59 seen so far; gaps like
# C1, C7-C13, C39-C42, C50-C51, C53-C56 not shown on supplied sheets -- likely
# on missing Sheet 6, OR simply not all curve numbers are used) ---
CURVE_TABLE = {
    # id:  length, radius, delta_deg, chord_bearing, chord
    "C2":  dict(length=172.88, radius=110.00, delta=90.0483,  chord_bearing="N45°34'46\"W", chord=155.63),
    "C3":  dict(length=172.69, radius=110.00, delta=89.9517,  chord_bearing="N44°25'14\"E", chord=155.50),
    "C4":  dict(length=15.25,  radius=118.00, delta=7.4025,   chord_bearing="S03°42'04\"W", chord=15.23),
    "C5":  dict(length=19.97,  radius=118.00, delta=9.6981,   chord_bearing="S12°15'05\"W", chord=19.95),
    "C6":  dict(length=25.34,  radius=82.00,  delta=17.7042,  chord_bearing="S08°14'54\"W", chord=25.24),
    "C14": dict(length=39.27,  radius=25.00,  delta=90.0,     chord_bearing="N45°36'13\"W", chord=35.36),
    "C15": dict(length=50.59,  radius=140.00, delta=20.7053,  chord_bearing="N80°15'04\"W", chord=50.32),
    "C16": dict(length=71.85,  radius=140.00, delta=29.4033,  chord_bearing="N55°11'49\"E", chord=71.06),
    "C17": dict(length=72.81,  radius=140.00, delta=29.7972,  chord_bearing="N25°35'48\"E", chord=71.99),
    "C18": dict(length=24.78,  radius=140.00, delta=10.1425,  chord_bearing="N05°37'36\"W", chord=24.75),
    "C19": dict(length=51.35,  radius=140.00, delta=21.0144,  chord_bearing="N09°57'07\"E", chord=51.06),
    "C20": dict(length=76.09,  radius=140.00, delta=31.1400,  chord_bearing="N36°01'45\"E", chord=75.16),
    "C21": dict(length=74.22,  radius=140.00, delta=30.3767,  chord_bearing="N66°47'15\"E", chord=73.36),
    "C22": dict(length=18.13,  radius=140.00, delta=7.4222,   chord_bearing="N85°41'10\"E", chord=18.12),
    "C23": dict(length=24.04,  radius=82.00,  delta=16.7978,  chord_bearing="N09°00'09\"W", chord=23.95),
    "C24": dict(length=19.95,  radius=118.00, delta=9.6864,   chord_bearing="N12°33'26\"W", chord=19.93),
    "C25": dict(length=15.89,  radius=118.00, delta=7.7133,   chord_bearing="N03°51'23\"W", chord=15.87),
    "C23b_note": "C23 appears twice on Sheet 3 curve table w/ different rows; kept as listed",
    "C26": dict(length=39.27,  radius=25.00,  delta=90.0,     chord_bearing="N44°23'47\"E", chord=35.36),
    "C27": dict(length=39.27,  radius=25.00,  delta=90.0,     chord_bearing="S45°36'13\"E", chord=35.36),
    "C28": dict(length=39.27,  radius=25.00,  delta=90.0,     chord_bearing="S44°23'47\"W", chord=35.36),
    "C29": dict(length=32.03,  radius=80.00,  delta=22.9467,  chord_bearing="N79°08'01\"W", chord=31.82),
    "C30": dict(length=93.70,  radius=80.00,  delta=67.1078,  chord_bearing="N34°06'34\"W", chord=88.44),
    "C31": dict(length=93.49,  radius=80.00,  delta=66.9589,  chord_bearing="N32°55'27\"E", chord=88.26),
    "C32": dict(length=32.10,  radius=80.00,  delta=22.9928,  chord_bearing="N77°54'00\"E", chord=31.89),
    "C33": dict(length=63.85,  radius=40.00,  delta=91.4592,  chord_bearing="N83°41'40\"E", chord=57.29),
    "C34": dict(length=92.42,  radius=274.00, delta=19.3256,  chord_bearing="S60°14'09\"E", chord=91.98),
    "C35": dict(length=75.86,  radius=274.00, delta=15.8628,  chord_bearing="S77°49'48\"E", chord=75.62),
    "C36": dict(length=20.83,  radius=1000.00,delta=1.1936,   chord_bearing="S86°21'30\"E", chord=20.83),
    "C37": dict(length=20.88,  radius=1000.00,delta=1.1964,   chord_bearing="S87°33'12\"E", chord=20.88),
    "C38": dict(length=27.23,  radius=25.00,  delta=62.4164,  chord_bearing="S56°56'35\"E", chord=25.91),
    "C43": dict(length=25.74,  radius=50.00,  delta=29.4922,  chord_bearing="S87°27'22\"W", chord=25.45),
    "C44": dict(length=23.43,  radius=50.00,  delta=26.8433,  chord_bearing="S86°07'54\"W", chord=23.21),
    "C45": dict(length=13.06,  radius=50.00,  delta=14.9672,  chord_bearing="N87°55'49\"W", chord=13.02),
    "C46": dict(length=44.76,  radius=25.00,  delta=102.5800, chord_bearing="N51°17'24\"W", chord=39.02),
    "C47": dict(length=26.50,  radius=40.00,  delta=37.9622,  chord_bearing="N18°58'52\"E", chord=26.02),
    "C48": dict(length=90.36,  radius=40.00,  delta=129.4258, chord_bearing="N64°42'48\"E", chord=72.33),
    "C49": dict(length=168.28, radius=274.00, delta=35.1883,  chord_bearing="S68°10'02\"E", chord=165.65),
    "C52": dict(length=41.71,  radius=1000.00,delta=2.39,     chord_bearing="S86°57'23\"E", chord=41.71),
    "C57": dict(length=20.59,  radius=40.00,  delta=29.4922,  chord_bearing="S87°27'22\"W", chord=20.36),
    "C58": dict(length=28.11,  radius=60.00,  delta=26.8433,  chord_bearing="S86°07'54\"W", chord=27.85),
    "C59": dict(length=10.45,  radius=40.00,  delta=14.9672,  chord_bearing="N87°55'49\"W", chord=10.42),
}

MISSING = {
    "sheet": "6 of 6 (Plat Book 82, Page 40)",
    "reason": "Not present in upload; file supplied for slot 2 duplicated sheet 1 instead.",
    "impact": "Tract A (lift station) and Tract B geometry, remaining lot fabric on the "
              "west side, and any curve/line table rows only referenced there (e.g. L1, "
              "and any C-numbers in the unused ranges) cannot be drawn yet.",
}
