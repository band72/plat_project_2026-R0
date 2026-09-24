"""plat_curves -- stdlib-only horizontal-curve toolkit for plat reading / COGO (see SPEC.md).

Submodules ``compound`` and ``plat_notation`` are imported explicitly by callers
(``from plat_curves.compound import ...``); this package root re-exports the ``core`` API.
"""

from __future__ import annotations

from .core import (
    DEGREE_ARC_CONST,
    PLAT_TOL_FT,
    Curve,
    PlacedCurve,
    Pt,
    az,
    az_to_bearing,
    bearing_to_az,
    deg_to_dms,
    dist,
    dms_to_deg,
    offset,
)

__all__ = [
    "DEGREE_ARC_CONST",
    "PLAT_TOL_FT",
    "Curve",
    "PlacedCurve",
    "Pt",
    "az",
    "az_to_bearing",
    "bearing_to_az",
    "deg_to_dms",
    "dist",
    "dms_to_deg",
    "offset",
]
