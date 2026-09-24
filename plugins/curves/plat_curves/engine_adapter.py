"""plat_curves.engine_adapter -- Bridge adapter between plat_curves toolkit and engine COGO.

Provides utilities to:
1. Access stated plat centerline curve definitions directly from plat data.
2. Build PlacedCurve objects for any subdivision curve.
3. Convert between PlacedCurve and engine-compatible dictionary/dataclass structures.
4. Generate analytical concentric right-of-way edges, corner return fillets, and cul-de-sacs.
"""

from __future__ import annotations

from typing import Any

from plat_curves.compound import (
    corner_return,
    cul_de_sac,
    row_edges,
)
from plat_curves.core import (
    Curve,
    PlacedCurve,
    Pt,
    dms_to_deg,
)

# Stated plat centerline curve definitions from Plat Book 30, Pages 82 & 82A
# Only Delta, R, T are printed in the plat curve data blocks.
STATED_PLAT_CURVES: dict[str, dict[str, Any]] = {
    "C_SANSALVADORE_CL": {
        "sheet": 1,
        "street_name": "San Salvadore Avenue",
        "delta_dms": "36°20'00\"",
        "delta_deg": dms_to_deg(36, 20, 0),
        "radius": 269.96,
        "tangent": 88.59,
        "direction": "CW",
        "notes": "Sheet 1 Centerline block: Delta=36°20'00\", R=269.96', T=88.59'. R/W edges at 239.96' and 299.96'.",
    },
    "C_CAPEHORN_CL": {
        "sheet": 1,
        "street_name": "Cape Horn Avenue",
        "delta_dms": "36°20'00\"",
        "delta_deg": dms_to_deg(36, 20, 0),
        "radius": 327.01,
        "tangent": 107.31,
        "direction": "CCW",
        "notes": "Sheet 1 Centerline block: Delta=36°20'00\", R=327.01', T=107.31'.",
    },
    "C_MARINA_CL": {
        "sheet": 2,
        "street_name": "Marina Avenue",
        "delta_dms": "37°42'50\"",
        "delta_deg": dms_to_deg(37, 42, 50),
        "radius": 359.27,
        "tangent": 122.70,
        "direction": "CW",
        "notes": "Sheet 2 Centerline block: Delta=37°42'50\", R=359.27', T=122.70'. North R/W edge is outer at 389.27'.",
    },
    "C_SANDS_CL": {
        "sheet": 2,
        "street_name": "Sands Avenue",
        "delta_dms": "36°20'00\"",
        "delta_deg": dms_to_deg(36, 20, 0),
        "radius": 459.36,
        "tangent": 150.73,
        "direction": "CCW",
        "notes": "Sheet 2 Centerline block: Delta=36°20'00\", R=459.36', T=150.73'.",
    },
    "C_KEEL_CL": {
        "sheet": 2,
        "street_name": "Keel Drive",
        "delta_dms": "52°17'10\"",
        "delta_deg": dms_to_deg(52, 17, 10),
        "radius": 143.93,
        "tangent": 70.65,
        "direction": "CW",
        "notes": "Sheet 2 Centerline block: Delta=52°17'10\", R=143.93', T=70.65'.",
    },
    "C_SHELLFISH_CL": {
        "sheet": 2,
        "street_name": "Shellfish Drive",
        "delta_dms": "52°17'10\"",
        "delta_deg": dms_to_deg(52, 17, 10),
        "radius": 167.95,
        "tangent": 82.35,
        "direction": "CW",
        "notes": "Sheet 2 7th Centerline block: Delta=52°17'10\", R=167.95', T=82.35'.",
    },
}


def build_placed_curve_from_plat(
    curve_id: str,
    pc: Pt,
    back_az: float,
    direction: str | None = None,
) -> PlacedCurve:
    """Build an analytical PlacedCurve from stated plat data for a given curve ID."""
    if curve_id not in STATED_PLAT_CURVES:
        raise KeyError(f"Unknown plat curve ID: {curve_id}")
    spec = STATED_PLAT_CURVES[curve_id]
    d = direction if direction is not None else spec["direction"]
    curve = Curve.from_params(
        direction=d,
        radius=spec["radius"],
        delta_deg=spec["delta_deg"],
    )
    return PlacedCurve(curve=curve, pc=pc, back_az=back_az)


def placed_to_engine_curve_dict(
    placed: PlacedCurve,
    curve_id: str,
    street_name: str,
    right_of_way_width: float = 60.0,
    is_assumed: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    """
    Convert a PlacedCurve into a dictionary compatible with CenterlineCurve initialization.
    Guarantees that all 10 analytical geometric identities hold to float precision.
    """
    return {
        "id": curve_id,
        "street_name": street_name,
        "center_point": placed.rp,
        "pc_point": placed.pc,
        "pt_point": placed.pt,
        "pi_point": placed.pi,
        "radius": placed.curve.radius,
        "delta_deg": placed.curve.delta_deg,
        "arc_length": placed.curve.arc_length,
        "tangent": placed.curve.tangent,
        "chord_length": placed.curve.chord,
        "chord_bearing": placed.chord_bearing,
        "direction": placed.direction,
        "right_of_way_width": right_of_way_width,
        "is_assumed": is_assumed,
        "notes": notes,
    }


def compute_concentric_row_edges(
    placed: PlacedCurve,
    row_width: float = 60.0,
) -> dict[str, PlacedCurve]:
    """Compute inner and outer concentric right-of-way edges using plat_curves.compound."""
    return row_edges(placed, row_width)


def compute_corner_return(
    corner: Pt,
    az_in: float,
    az_out: float,
    radius: float = 25.0,
) -> PlacedCurve:
    """Compute a 25' (or custom) corner return fillet at an intersection corner."""
    return corner_return(corner=corner, az_in=az_in, az_out=az_out, radius=radius)


def compute_open_cul_de_sac(
    center: Pt,
    bulb_radius: float,
    throat_half_width: float,
    fillet_radius: float = 25.0,
    axis_az: float = 0.0,
) -> dict[str, Any]:
    """Compute open-ended cul-de-sac turnaround bulb + reverse fillet geometry."""
    res = cul_de_sac(
        center=center,
        bulb_radius=bulb_radius,
        throat_half_width=throat_half_width,
        fillet_radius=fillet_radius,
        axis_az=axis_az,
    )
    # Add engine-compatible key aliases
    res["throat_distance_yf_ft"] = res["yf"]
    res["corridor_half_width_ft"] = res["throat_half_width"]
    res["bulb_radius_ft"] = res["bulb_radius"]
    res["fillet_radius_ft"] = res["fillet_radius"]
    res["delta_bulb_deg"] = res["bulb_sweep_deg"]
    return res


# Stated plat corner return curve definitions from Beachwood Unit Two
# Plat Book 30, Pages 82 & 82A, Duval County, FL (1960).
STATED_BLOCK_CORNER_RETURNS: dict[str, dict[str, Any]] = {
    "CR_BLK18_L19": {
        "block": "18", "lot": "19", "corner": "SE", "radius": 25.0,
        "delta_dms": "88°17'10\"", "delta_deg": dms_to_deg(88, 17, 10),
        "tangent": 24.2631, "arc_length": 38.52, "direction": "CW",
        "notes": "Block 18 Lot 19 SE corner return into Beachwood Blvd.",
    },
    "CR_BLK17_L1": {
        "block": "17", "lot": "1", "corner": "NW", "radius": 25.0,
        "delta_dms": "90°00'00\"", "delta_deg": 90.0,
        "tangent": 25.0000, "arc_length": 39.27, "direction": "CW",
        "notes": "Block 17 Lot 1 NW corner return: Mangrove Ave to Starfish Ave.",
    },
    "CR_BLK17_L34": {
        "block": "17", "lot": "34", "corner": "SW", "radius": 25.0,
        "delta_dms": "90°00'00\"", "delta_deg": 90.0,
        "tangent": 25.0000, "arc_length": 39.27, "direction": "CCW",
        "notes": "Block 17 Lot 34 SW corner return: Mangrove Ave to Sail Ave.",
    },
    "CR_BLK16_L1": {
        "block": "16", "lot": "1", "corner": "NW", "radius": 25.0,
        "delta_dms": "90°00'00\"", "delta_deg": 90.0,
        "tangent": 25.0000, "arc_length": 39.27, "direction": "CW",
        "notes": "Block 16 Lot 1 NW corner return: West St to Sail Ave.",
    },
    "CR_BLK16_L33": {
        "block": "16", "lot": "33", "corner": "SW", "radius": 25.0,
        "delta_dms": "90°00'00\"", "delta_deg": 90.0,
        "tangent": 25.0000, "arc_length": 39.27, "direction": "CW",
        "notes": "Block 16 Lot 33 SW corner return: West St to South St.",
    },
    "CR_BLK16_L29": {
        "block": "16", "lot": "29", "corner": "SE", "radius": 25.0,
        "delta_dms": "90°00'00\"", "delta_deg": 90.0,
        "tangent": 25.0000, "arc_length": 39.27, "direction": "CCW",
        "notes": "Block 16 Lot 29 SE corner return: Marina Ave PT to Keel Dr.",
    },
    "CR_BLK13_L1": {
        "block": "13", "lot": "1", "corner": "NE", "radius": 25.0,
        "delta_dms": "90°00'00\"", "delta_deg": 90.0,
        "tangent": 25.0000, "arc_length": 39.27, "direction": "CW",
        "notes": "Block 13 Lot 1 NE corner return: North cross street to Mangrove Ave.",
    },
    "CR_BLK13_L11": {
        "block": "13", "lot": "11", "corner": "SE", "radius": 25.0,
        "delta_dms": "90°20'00\"", "delta_deg": dms_to_deg(90, 20, 0),
        "tangent": 25.1459, "arc_length": 39.42, "direction": "CW",
        "notes": "Block 13 Lot 11 SE corner return: Mangrove Ave to Surfwood Ave (20' skew).",
    },
    "CR_BLK9_L27": {
        "block": "9", "lot": "27", "corner": "NW", "radius": 25.0,
        "delta_dms": "90°00'00\"", "delta_deg": 90.0,
        "tangent": 25.0000, "arc_length": 39.27, "direction": "CW",
        "notes": "Block 9 Lot 27 NW corner return: West Ave to North street line.",
    },
    "CR_BLK9_L26": {
        "block": "9", "lot": "26", "corner": "SW", "radius": 25.0,
        "delta_dms": "83°30'00\"", "delta_deg": dms_to_deg(83, 30, 0),
        "tangent": 22.3134, "arc_length": 36.72, "direction": "CW",
        "notes": "Block 9 Lot 26 SW corner return: West Ave to South street line.",
    },
}


def get_block_corner_returns(block: str | None = None) -> dict[str, dict[str, Any]]:
    """Return stated block corner returns, optionally filtered by block ID."""
    if block is None:
        return dict(STATED_BLOCK_CORNER_RETURNS)
    b_str = str(block).upper().replace("BLOCK_", "").replace("BLK", "")
    return {k: v for k, v in STATED_BLOCK_CORNER_RETURNS.items() if v["block"] == b_str}


# Stated plat interior and frontage lot curve definitions from Beachwood Unit Two
# Plat Book 30, Pages 82 & 82A, Duval County, FL (1960).
STATED_BLOCK_FRONTAGE_CURVES: dict[str, dict[str, Any]] = {
    "CURVE_BLK16_MARINA_NORTH_RW": {
        "block": "16",
        "lots": ["31", "30", "29"],
        "street": "Marina Avenue",
        "radius": 389.27,
        "delta_dms": "37°42'50\"",
        "delta_deg": dms_to_deg(37, 42, 50),
        "total_arc_length": 256.24,
        "lot_arc_length": 85.41,
        "direction": "CW",
        "notes": "Marina Ave North R/W curve outer edge (R=389.27'), equally divided across Lots 31, 30, and 29.",
    },
    "CURVE_BLK16_KEEL_L28": {
        "block": "16",
        "lots": ["28"],
        "street": "Keel Drive",
        "radius": 167.95,
        "stated_chord": 68.75,
        "delta_deg": 23.6208,
        "arc_length": 69.24,
        "direction": "CW",
        "notes": "Keel Drive North R/W curve fronting Block 16 Lot 28.",
    },
    "CURVE_BLK15_SHELLFISH_L1": {
        "block": "15",
        "lots": ["1"],
        "street": "Shellfish Drive",
        "radius": 137.95,
        "delta_dms": "52°17'10\"",
        "delta_deg": dms_to_deg(52, 17, 10),
        "arc_length": 125.89,
        "chord": 121.56,
        "chord_bearing": "N61°26'55\"E",
        "direction": "CW",
        "notes": "Shellfish Drive S R/W curve (CL R=167.95' - 30') fronting Block 15 Lot 1; "
                 "tangent N35°18'20\"E in, N87°35'30\"E out. Chord/bearing printed on plat.",
    },
    "CURVE_BLK15_KEEL_L15": {
        "block": "15",
        "lots": ["15"],
        "street": "Keel Drive",
        "radius": 173.93,
        "stated_chord": 75.29,
        "delta_deg": 25.0,
        "arc_length": 75.89,
        "direction": "CW",
        "notes": "Keel Drive outer North R/W curve fronting Block 15 Lot 15.",
    },
    "CURVE_BLK15_KEEL_L16": {
        "block": "15",
        "lots": ["16"],
        "street": "Keel Drive",
        "radius": 173.93,
        "stated_chord": 82.45,
        "delta_deg": 27.4214,
        "arc_length": 83.24,
        "direction": "CW",
        "notes": "Keel Drive outer North R/W curve fronting Block 15 Lot 16.",
    },
    "CURVE_BLK15_EAST_BOUNDARY": {
        "block": "15",
        "lots": ["9", "10"],
        "street": "East Plat Boundary / Course 21",
        "radius": 1959.86,
        "arc_length": 200.08,
        "lot_arc_length": 100.04,
        "direction": "CW",
        "notes": "East boundary curve (Course 21) forming east rear line of Lots 9 and 10.",
    },
    "CURVE_BLK14_CULDESAC_BULB": {
        "block": "14",
        "lots": ["1", "8", "9", "10", "11", "24"],
        "street": "Keel Drive Turnaround Bulb",
        "bulb_radius": 50.0,
        "throat_half_width": 30.0,
        "fillet_radius": 25.0,
        "notes": "Block 14 West terminus cul-de-sac turnaround bulb on Keel Drive.",
    },
}


def get_block_frontage_curves(block: str | None = None) -> dict[str, dict[str, Any]]:
    """Return stated block frontage and interior curves, optionally filtered by block ID."""
    if block is None:
        return dict(STATED_BLOCK_FRONTAGE_CURVES)
    b_str = str(block).upper().replace("BLOCK_", "").replace("BLK", "")
    return {k: v for k, v in STATED_BLOCK_FRONTAGE_CURVES.items() if v["block"] == b_str}


