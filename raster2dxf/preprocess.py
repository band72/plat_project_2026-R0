"""Polarity- and illumination-independent ink extraction.

Works for both black-ink-on-paper scans and our own dark-background,
colored-stroke mapcheck renders: ink is anything that differs strongly
from its *local* background (a median filter a few stroke-widths wide),
so large flat fills (lot shading, paper tone, tape stains) are not ink but
thin strokes and glyphs are.
"""
from __future__ import annotations

from dataclasses import dataclass

import os

import cv2
import numpy as np


RENDER_INK_THRESHOLD = 35.0
RENDER_TEXT_THRESHOLD = 80.0


@dataclass
class Prepared:
    color: np.ndarray        # BGR, original
    gray: np.ndarray         # uint8, "ink dark" normalized (ink ~0, paper ~255)
    ink: np.ndarray          # uint8 {0,255} ink mask (linework)
    text_ink: np.ndarray     # uint8 {0,255} ink used for the text mask (stricter on renders)
    stroke_w: float          # median stroke width in px
    dark_bg: bool            # True for rendered dark-theme drawings
    kind: str                # "scan" | "render" | "screenshot"
    name: str = ""           # image file name (for ground-truth lookup)


def _local_diff(img: np.ndarray, k: int) -> np.ndarray:
    """max over channels of |img - medianBlur(img, k)|, computed at reduced
    resolution for large kernels (median of a downscaled image is a close
    and much faster approximation)."""
    h, w = img.shape[:2]
    scale = 1
    while k // scale > 31:
        scale *= 2
    if scale > 1:
        small = cv2.resize(img, (max(1, w // scale), max(1, h // scale)),
                           interpolation=cv2.INTER_AREA)
        kk = max(3, (k // scale) | 1)
        bg = cv2.resize(cv2.medianBlur(small, kk), (w, h),
                        interpolation=cv2.INTER_LINEAR)
    else:
        bg = cv2.medianBlur(img, max(3, k | 1))
    d = cv2.absdiff(img, bg)
    if d.ndim == 3:
        d = d.max(axis=2)
    return d


def _stroke_width(mask: np.ndarray) -> float:
    """2 x median distance-transform value on the skeleton ~= stroke width."""
    from skimage.morphology import skeletonize
    if mask.sum() == 0:
        return 2.0
    dt = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
    sk = skeletonize(mask > 0)
    vals = dt[sk]
    if vals.size == 0:
        return 2.0
    return float(max(1.0, 2.0 * np.median(vals)))


def classify(color: np.ndarray) -> tuple[str, bool]:
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    dark_bg = float(np.median(gray)) < 110
    hsv = cv2.cvtColor(color, cv2.COLOR_BGR2HSV)
    colorful = float(np.mean(hsv[..., 1] > 80))
    if dark_bg:
        return "render", True
    if colorful > 0.02:
        return "screenshot", False
    return "scan", False


def prepare(path: str) -> Prepared:
    color = cv2.imread(path, cv2.IMREAD_COLOR)
    if color is None:
        raise FileNotFoundError(path)
    kind, dark_bg = classify(color)
    # pass 1: generous kernel to estimate stroke width
    d = _local_diff(color, 31)
    t = max(30.0, cv2.threshold(d, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[0])
    ink0 = ((d > t) * 255).astype(np.uint8)
    sw = _stroke_width(ink0)
    # pass 2: kernel ~ 7 stroke widths, big enough that a stroke is minority
    k = int(max(15, min(101, 7 * sw))) | 1
    d = _local_diff(color, k)
    t_otsu = max(30.0, cv2.threshold(d, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[0] * 0.8)
    if kind == "scan":
        t = t_otsu
    else:
        # digital renders are noise-free (flat fills differ by exactly 0), so
        # Otsu -- dominated by bright text -- is far too high and drops
        # low-contrast strokes (blue lot lines on navy fill: diff ~66 vs t=79).
        # 35 keeps those and still rejects faint chart gridlines (~27).
        t = RENDER_INK_THRESHOLD
    def _mask(th):
        m = ((d > th) * 255).astype(np.uint8)
        # remove single-pixel speckle (scan noise) without eroding thin strokes
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        small = stats[:, cv2.CC_STAT_AREA] < max(3, int(0.6 * sw * sw))
        small[0] = False
        m[small[lab]] = 0
        return m

    ink = _mask(t)
    # renders: low threshold finds faint linework, but for *text* it turns
    # anti-alias fringes into hundreds of junk clusters -- use Otsu there
    # (floor 80: rendered text differs by 150-220, lot lines by ~66, and Otsu
    # can land right on a faint stroke's level when text is sparse)
    text_ink = ink if kind == "scan" else _mask(max(t_otsu, RENDER_TEXT_THRESHOLD))
    sw = _stroke_width(ink)
    gray = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    norm = 255 - np.clip(d.astype(np.int32) * 255 // max(1, int(d.max())), 0, 255).astype(np.uint8)
    return Prepared(name=os.path.basename(path), color=color, gray=norm if dark_bg else gray, ink=ink, text_ink=text_ink,
                    stroke_w=sw, dark_bg=dark_bg, kind=kind)
