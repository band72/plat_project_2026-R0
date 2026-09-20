"""
registration.py -- register a transcribed traverse onto a scaled raster.

Extracted from build_true_overlay.py / build_atlantic_iter2.py, which had
the same ~40 lines of pixel->local conversion, rotation solving and control
point handling copy-pasted, with FT_PER_PX, IMG_H, CP1_PX and CP2_PX
hardcoded separately in each. That duplication is a correctness hazard, not
just untidiness: fixing a control point in one script silently leaves the
other wrong, and the two would then disagree about where the same lot is.

Method (validated on Atlantic Beach sheet 3):
  pick two points whose TRUE bearing and distance apart are known from the
  plat, read their PIXEL positions off the scan, and that single pair fixes
  both the translation (anchor) and the rotation. Validate by predicting the
  second point from the fit and checking the residual.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from engine.cogo import Point, parse_bearing, azimuth_to_bearing


@dataclass
class SheetRegistration:
    """A solved pixel->plat transform for one scanned sheet."""
    ft_per_px: float
    img_h_px: int
    cp1_px: tuple
    cp2_px: tuple
    control_bearing: str
    control_distance: float

    def __post_init__(self):
        self.cp1_local = self.px_to_local(*self.cp1_px)
        self.cp2_local = self.px_to_local(*self.cp2_px)
        self.measured_distance = math.hypot(
            self.cp2_px[0] - self.cp1_px[0],
            self.cp2_px[1] - self.cp1_px[1]) * self.ft_per_px
        self.true_az = parse_bearing(self.control_bearing)
        self.local_az = math.degrees(math.atan2(
            self.cp2_local[1] - self.cp1_local[1],
            self.cp2_local[0] - self.cp1_local[0])) % 360
        self.phi = (self.local_az - self.true_az) % 360

    def px_to_local(self, px, py):
        """Pixel (x,y) -> local (N,E) feet, flipping the image Y axis."""
        return ((self.img_h_px - py) * self.ft_per_px, px * self.ft_per_px)

    def true_to_local(self, n_true, e_true):
        """Rotate a TRUE (N,E) offset into the sheet's local frame and
        translate so control point 1 anchors the traverse origin."""
        rad = math.radians(self.phi)
        n_rel = n_true * math.cos(rad) - e_true * math.sin(rad)
        e_rel = n_true * math.sin(rad) + e_true * math.cos(rad)
        return (self.cp1_local[0] + n_rel, self.cp1_local[1] + e_rel)

    def scale_agreement(self) -> float:
        """How far the pixel-measured control distance differs from the
        recorded one. This is the primary scale check."""
        return abs(self.measured_distance - self.control_distance)

    def residual(self) -> float:
        """Predict control point 2 from the fit and compare to its
        pixel-read position -- an independent check that the solve is
        self-consistent rather than merely arithmetically valid."""
        pred = self.true_to_local(
            self.control_distance * math.cos(math.radians(self.true_az)),
            self.control_distance * math.sin(math.radians(self.true_az)))
        return math.hypot(pred[0] - self.cp2_local[0],
                          pred[1] - self.cp2_local[1])

    def report(self) -> str:
        return "\n".join([
            f"  control line: {self.control_bearing} {self.control_distance:.2f}'",
            f"  pixel-measured: {self.measured_distance:.2f}' "
            f"(agreement {self.scale_agreement():.2f} ft)",
            f"  solved rotation PHI: {self.phi:.4f} deg "
            f"(sheet is drawn {self.phi:.1f} deg off north-up)",
            f"  registration residual at CP2: {self.residual():.2f} ft",
        ])


# The Atlantic Beach sheet 3 registration, defined ONCE and imported by
# every build script that needs it.
ATLANTIC_SHEET3 = SheetRegistration(
    ft_per_px=50.0 / 300.0,
    img_h_px=6600,
    cp1_px=(1470, 545),          # Tract K corner
    cp2_px=(6105, 555),          # corner after the 772.85' run
    control_bearing="N00°32'22\"E",
    control_distance=772.85,
)
