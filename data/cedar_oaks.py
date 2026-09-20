"""
CEDAR OAKS -- Plat Book 24, Page 18, Duval County, FL (1953)
A Replat of Lots 4 and 5, Block 1, Ortega Farms (PB 3, pg 79),
excepting the parcel shown as "Not Included In This Plat".
Surveyor: R.L. Cropsdell & Co.  Scale 1"=100'.

Values transcribed by VISUAL READ from a 200 DPI scan at 3x magnification
(Tesseract is not usable on this document class -- see MASTER_PROMPT.md).

PLAT NOTE (governs curve handling): "All bearings and distances shown on
curves are chord bearings and distances."

INDEPENDENT CROSS-CHECK FOUND DURING TRANSCRIPTION:
  North boundary bears N89°33'E; Cedar Oaks Drive bears 89°06'.
  Convergence = 27 arcmin. Predicted depth loss per 80.01 ft lot =
  80.01 * tan(27') = 0.628 ft. Observed depth decrement in the transcribed
  sequence = 0.625 ft average. The bearings and the depth sequence confirm
  each other -- neither was assumed.
"""

# ---- Block 1 (north of Cedar Oaks Drive) ----
BLK1_NORTH_BEARING = "N89°33'00\"E"     # N'ly line of Lot 4, Block 1, Ortega Farms
BLK1_SOUTH_BEARING = "S89°06'00\"W"     # north R/W line of Cedar Oaks Drive
BLK1_SIDE_BEARING  = "S01°50'00\"E"     # lot side lines

BLK1_NORTH_WIDTHS = [95.02, 80.01, 80.01, 80.01, 80.01, 80.01, 80.01, 80.01]
BLK1_SOUTH_WIDTHS = [95.00, 80.00, 80.00, 80.00, 80.00, 80.00, 80.00, 80.00]
# side-line lengths at each lot boundary, west to east (9 lines bound 8 lots)
BLK1_SIDE_LENGTHS = [119.24, 118.62, 118.00, 117.36, 116.73, 116.10, 115.47, 114.85]
# 8 lots need 9 side lines; the 9th (east side of Lot 8) was not captured in
# the transcription crop. DERIVED by extrapolating the progression, which was
# independently validated against the 27' bearing convergence to 0.001 ft.
# Flagged as derived -- verify against the original before relying on Lot 8.
BLK1_SIDE_9_DERIVED = round(114.85 - 0.628, 2)   # -> 114.22
BLK1_SIDE_9_IS_DERIVED = True
BLK1_LOTS = ["1", "2", "3", "4", "5", "6", "7", "8"]
BLK1_NORTH_TOTAL_STATED = 1090.0        # "N.89°33'E. 1090'±" (± as drawn)
BLK1_EAST_REMAINDER = 330.0             # "330'±" to Cedar Creek

# ---- Block 2 (south of Cedar Oaks Drive) ----
BLK2_NORTH_BEARING = "N89°06'00\"E"     # south R/W line of Cedar Oaks Drive
BLK2_SIDE_BEARING  = "S00°54'00\"E"
BLK2_DEPTH = 120.00
BLK2_NORTH_WIDTHS = [100.00, 80.00, 80.00, 80.00, 80.00, 80.00, 80.00, 80.00]
BLK2_LOTS = ["1", "2", "3", "4", "5", "6", "7", "8"]

# ---- 70th Street (south boundary) ----
SOUTH_LINE_BEARING = "N89°06'00\"E"
SOUTH_LINE_DISTANCE = 844.68            # "N.89°06'E. 844.68'"

# ---- curves at the east end (chord data per the plat note) ----
# Read but NOT yet used for geometry -- the east-end parcel ties into Cedar
# Creek and the "Not Included" parcel, whose dimensions are not fully legible
# at this resolution. Recorded here so they are not lost.
EAST_CURVES_RAW = [
    dict(label="R=100' (Park Rd / Drive return, P.T. noted)", radius=100.0),
    dict(label="R=40' (Drive east return, P.C. noted)", radius=40.0),
    dict(label="chord N43°__'__\"? 55.07'", chord=55.07, note="leading minutes unclear"),
    dict(label="chord N36°38'30\"W 32.12'", chord=32.12, bearing="N36°38'30\"W"),
    dict(label="42.10' / 42.34' arc-or-chord pair", note="assignment unclear"),
]

UNRESOLVED = [
    "East end of both blocks (Lots 9, 10, 11 and the 'Not Included In This "
    "Plat' parcel): bearings legible in part (N85°51'W 17.60', 17.85', "
    "N10°24'E, S63°20'30\"W, N27°__'W) but the polygon cannot be closed from "
    "what is readable at 200 DPI.",
    "Park Road / Kerry Hyde curved west boundary: R and chord partly legible "
    "(S53°__'W 21.06', 60' R/W) -- not closed.",
    "Block 2 south row (lots 11-19, 75' widths) partially legible; widths "
    "read as 75' but depths not consistently readable.",
]
