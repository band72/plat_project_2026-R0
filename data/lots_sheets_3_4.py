"""
Lot fabric blocks for Trail Ridge Estates, transcribed from Sheets 3 & 4.

SCOPE OF THIS ITERATION (2): only lots whose full rectangle dimensions are
unambiguous in the source images are built here. Each block is kept in its
own local coordinate frame (clearly labeled) rather than force-registered to
the State Plane boundary, because the exact match-line tie needs either
Sheet 6 or pixel-accurate re-inspection of the source art -- see
MASTER_PROMPT.md "Open items". Every block's *internal* geometry (lot widths,
depths, and the orthogonality of its frontage/depth bearings) is transcribed
directly off the plat and is not estimated.

Deferred to iteration 3 (logged, not fabricated):
  - Lots 12-16 (Sheet 3): involve a diagonal jog (C38/C50, unequal 159'/150'
    depths, 60'/45' width split) -- not a uniform rectangle row.
  - Lots 41, 43 (Sheet 3) and 44, 45 (Sheet 3): curved end returns via
    C23-C28, C38 tying into the Murrell Loop bulb.
  - Lots 17-27 (Sheet 4): curved frontage along Trail Ridge Road / Tract C
    loop -- needs full PC/PT curve chaining, not a rectangle.
  - Tracts A-H, road ROW curb lines, all of Sheet 6.
"""

# --- Block A: Lots 1-8, Sheet 3, south row along Tract E ---
# Front (north) edge bearing N89*23'47"E, depth (south, into lot) bearing
# S00*36'13"E -- confirmed orthogonal (89*23'47" + 00*36'13" = 90*00'00").
# Order matches plat, west to east: 8,7,6,5,4,3,2,1.
BLOCK_A_LOTS_1_8 = dict(
    front_bearing="N89°23'47\"E",
    depth_bearing="S00°36'13\"E",
    lot_width=80.00,
    lot_depth=130.00,
    numbers=["8", "7", "6", "5", "4", "3", "2", "1"],
    source="Sheet 3 (PB82 Pg37), bottom row, each lot dimensioned 80.00' x 130.00'",
)

# --- Block B: Murrell Loop rectangular columns, Sheet 3 ---
# West column (37,38,39,40) and east column (32,31,30,29), 60' wide x 120'
# deep each, separated by Murrell Loop (60' private R/W).
BLOCK_B_MURRELL_LOOP = dict(
    front_bearing="N89°23'47\"E",
    depth_bearing="S00°36'13\"E",
    lot_width=60.00,
    lot_depth=120.00,
    row_width=60.00,  # Murrell Loop private R/W between the two columns
    numbers_west=["37", "38", "39", "40"],
    numbers_east=["32", "31", "30", "29"],
    source="Sheet 3 (PB82 Pg37), Murrell Loop columns, each lot 60.00' x 120.00'",
)

# --- Block C: Sheet 4, 2x2 lot grid west of Trail Ridge Road (lots 33-36) ---
# Top row (35 west / 34 east) fronts the Tract C loop, depth per plat's
# C/L 20' UDE callouts (113.67' / 113.64'). Bottom row (36 west / 33 east)
# is a clean 60' x 120' rectangle pair.
BLOCK_C_LOTS_33_36 = dict(
    front_bearing="N89°23'47\"E",
    depth_bearing="S00°36'13\"E",
    top_row=dict(numbers=["35", "34"], widths=[65.00, 65.00], depths=[113.67, 113.64]),
    bottom_row=dict(numbers=["36", "33"], widths=[60.00, 60.00], depths=[120.00, 120.00]),
    source="Sheet 4 (PB82 Pg38), lots 33-36",
)

DEFERRED = [
    "Lots 12-16 (Sheet 3) -- diagonal jog via C38/C50, unequal depths, needs pixel-accurate re-check",
    "Lots 41, 43 (Sheet 3) -- curved end returns into Murrell Loop bulb",
    "Lots 44, 45 (Sheet 3) -- curved frontage via C23-C28, C38",
    "Lots 17-27 (Sheet 4) -- curved frontage along Trail Ridge Rd / Tract C loop, full PC/PT chain needed",
    "Tracts A-H boundaries, road curb lines (centerline/ROW width known, curb geometry not yet built)",
    "All of Sheet 6 (Pg 40) -- not supplied",
]
