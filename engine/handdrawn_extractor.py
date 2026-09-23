"""
engine/handdrawn_extractor.py -- Image Normalization, Dual-Stream Linework/Text
Separation, Skeletonization, and Callout Extraction for Historical Plats.

Designed for historical hand-drawn plats (e.g., Beverly Isle, 1959-1968) that may
be captured as 24-bit RGB photos with non-uniform lighting, tape stains, and
creases, as well as standard 1-bit or 8-bit monochrome/grayscale archival scans.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import pytesseract
from skimage.morphology import skeletonize as sk_skeletonize


@dataclass
class PlatCallout:
    """Extracted text callout with spatial bounding box, angle, and parsed value."""
    text: str
    box: tuple[int, int, int, int]  # (x, y, w, h)
    angle_deg: float
    confidence: float
    category: str  # 'BEARING', 'DISTANCE', 'CURVE_PARAM', 'LOT_NUM', 'NOTE'
    parsed_value: Any = None


@dataclass
class SkeletonEdge:
    """Vectorized edge traced along skeleton centerline."""
    points: list[tuple[float, float]]  # [(x, y), ...] in pixel coordinates
    length_px: float
    angle_deg: float
    start_node: int
    end_node: int


class PlatImageNormalizer:
    """Universal illumination flattening and binarization engine.
    
    Seamlessly handles both:
    1. 24-bit RGB photographs with lighting gradients, yellowed vellum, and tape stains.
    2. 1-bit / 8-bit clean monochrome scans without unnecessary distortion.
    """

    def __init__(self, bg_sigma: int = 25, bilateral_d: int = 7):
        self.bg_sigma = bg_sigma
        self.bilateral_d = bilateral_d

    def is_rgb_photo(self, img: np.ndarray) -> bool:
        """Detect whether the image is a color photograph with chromatic variation."""
        if len(img.shape) < 3 or img.shape[2] < 3:
            return False
        # Sample down to assess color channel differences
        small = cv2.resize(img, (256, 256), interpolation=cv2.INTER_AREA)
        b, g, r = small[:, :, 0], small[:, :, 1], small[:, :, 2]
        diff_rg = np.mean(np.abs(r.astype(float) - g.astype(float)))
        diff_rb = np.mean(np.abs(r.astype(float) - b.astype(float)))
        return (diff_rg + diff_rb) > 8.0  # Noticeable color cast (e.g. amber tape/yellowed paper)

    def normalize(self, img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Normalize illumination and binarize.
        
        Returns:
            clean_gray: 8-bit normalized grayscale image with uniform background.
            binary_mask: 8-bit binary mask (255 = ink/strokes, 0 = background).
        """
        if len(img.shape) == 3 and img.shape[2] >= 3:
            is_color = self.is_rgb_photo(img)
            if is_color:
                # Use green or red channel to minimize amber tape stain visibility
                # Tape stains are yellow/amber (high red & green, low blue).
                # Combining red and green suppresses amber darkness.
                b, g, r = cv2.split(img)
                gray = cv2.addWeighted(r, 0.5, g, 0.5, 0)
            else:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
            is_color = False

        if is_color:
            # Flat-field illumination correction via background division
            ksize = 2 * int(2.5 * self.bg_sigma) + 1
            bg = cv2.GaussianBlur(gray, (ksize, ksize), self.bg_sigma)
            flat = cv2.normalize(gray.astype(float) / (bg.astype(float) + 1e-5),
                                 None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            # Bilateral filter to smooth paper grain while retaining crisp stroke edges
            filtered = cv2.bilateralFilter(flat, self.bilateral_d, 50, 50)
            # Adaptive local thresholding
            bin_mask = cv2.adaptiveThreshold(
                filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 25, 11
            )
            # Remove isolated single-pixel noise
            clean_mask = cv2.morphologyEx(
                bin_mask, cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            )
            return filtered, clean_mask
        else:
            # Monochrome / Grayscale scan
            # Standard Otsu or gentle adaptive threshold
            inv = cv2.bitwise_not(gray)
            _, bin_mask = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            clean_mask = cv2.morphologyEx(
                bin_mask, cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            )
            return gray, clean_mask


class DualStreamSeparator:
    """Separates continuous linework geometry from compact text callouts."""

    def __init__(self, min_line_span: int = 120, max_char_dim: int = 90, max_char_area: int = 2500):
        self.min_line_span = min_line_span
        self.max_char_dim = max_char_dim
        self.max_char_area = max_char_area

    def separate(self, binary_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Decompose binary ink mask into Linework Mask and Text Callout Mask.
        
        Returns:
            mask_lines: binary mask of boundary lines, curves, centerlines.
            mask_text: binary mask of characters, numerals, and annotations.
        """
        n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary_mask, 8)
        mask_lines = np.zeros_like(binary_mask)
        mask_text = np.zeros_like(binary_mask)

        for i in range(1, n_labels):
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]
            area = stats[i, cv2.CC_STAT_AREA]
            diag = math.hypot(w, h)

            # Text components are small, compact characters
            if diag < self.min_line_span and w <= self.max_char_dim and h <= self.max_char_dim and area <= self.max_char_area:
                mask_text[labels == i] = 255
            else:
                # Linework strokes (boundaries, section lines, road curves)
                mask_lines[labels == i] = 255

        # Morphological bridge on linework to repair small breaks across characters
        line_kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
        line_kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
        mask_lines = cv2.morphologyEx(mask_lines, cv2.MORPH_CLOSE, line_kernel_h)
        mask_lines = cv2.morphologyEx(mask_lines, cv2.MORPH_CLOSE, line_kernel_v)

        return mask_lines, mask_text


class PlatSkeletonGraph:
    """Skeletonizes drawn strokes and extracts topological vector graph."""

    def __init__(self, spur_len_thresh: int = 12):
        self.spur_len_thresh = spur_len_thresh

    def skeletonize(self, mask_lines: np.ndarray) -> np.ndarray:
        """Produce 1-pixel-wide centerline skeleton."""
        skel = (sk_skeletonize(mask_lines > 0) * 255).astype(np.uint8)
        return skel

    def extract_segments(self, skel: np.ndarray, min_len_px: int = 30, max_gap: int = 12) -> list[tuple[int, int, int, int]]:
        """Extract linear segments from skeleton mask."""
        lines = cv2.HoughLinesP(
            skel, 1, np.pi / 720, threshold=25,
            minLineLength=min_len_px, maxLineGap=max_gap
        )
        if lines is None:
            return []
        return [tuple(int(v) for v in row) for row in lines[:, 0]]


class PlatCalloutExtractor:
    """Extracts and parses surveyor bearings, distances, and curve parameters."""

    # Survey regex patterns
    BEARING_REGEX = re.compile(
        r"([NS])\s*(\d{1,2})[°\s\.\-O]+(\d{1,2})['\s\.\-]+(?:(\d{1,2})[\"'\s]*)?([EW])",
        re.IGNORECASE
    )
    DISTANCE_REGEX = re.compile(
        r"(\d{1,4}\.\d{1,2})['\s]*",
        re.IGNORECASE
    )
    CURVE_TABLE_ROW_REGEX = re.compile(
        r"([abc])\s+(\d{1,3}\.\d{1,2})['\s]+(\d{1,3}\.\d{1,2})['\s]+(\d{1,3})[°\s]+(\d{1,2})['\s]*",
        re.IGNORECASE
    )
    LOT_NUM_REGEX = re.compile(
        r"(?:LOT|PARCEL|NO\.?)\s*(\d{1,2})",
        re.IGNORECASE
    )

    @classmethod
    def parse_bearing(cls, text: str) -> str | None:
        """Extract normalized quadrant bearing from OCR text string."""
        m = cls.BEARING_REGEX.search(text)
        if not m:
            return None
        ns = m.group(1).upper()
        deg = int(m.group(2))
        minute = int(m.group(3))
        sec = int(m.group(4)) if m.group(4) else 0
        ew = m.group(5).upper()
        if deg > 90 or minute >= 60 or sec >= 60:
            return None
        return f"{ns} {deg:02d}°{minute:02d}'{sec:02d}\" {ew}"

    @classmethod
    def parse_distance(cls, text: str) -> float | None:
        """Extract distance in feet from OCR text string."""
        m = cls.DISTANCE_REGEX.search(text)
        if not m:
            return None
        try:
            val = float(m.group(1))
            if 0.5 <= val <= 5000.0:
                return val
        except ValueError:
            pass
        return None

    @classmethod
    def parse_curve_row(cls, text: str) -> dict | None:
        """Parse curve data row (Curve name, Radius, Tangent, Delta)."""
        m = cls.CURVE_TABLE_ROW_REGEX.search(text)
        if not m:
            return None
        name = m.group(1).lower()
        rad = float(m.group(2))
        tan = float(m.group(3))
        deg = int(m.group(4))
        minute = int(m.group(5))
        delta_deg = deg + minute / 60.0
        return {
            "name": name,
            "radius": rad,
            "tangent": tan,
            "delta_deg": delta_deg,
            "delta_str": f"{deg}°{minute:02d}'"
        }

    def ocr_region(self, gray_crop: np.ndarray, angles: tuple[int, ...] = (0, 90, 180, 270)) -> list[tuple[str, float]]:
        """Run multi-orientation Tesseract OCR on a cropped region."""
        results = []
        for angle in angles:
            if angle == 0:
                rot = gray_crop
            elif angle == 90:
                rot = cv2.rotate(gray_crop, cv2.ROTATE_90_CLOCKWISE)
            elif angle == 180:
                rot = cv2.rotate(gray_crop, cv2.ROTATE_180)
            elif angle == 270:
                rot = cv2.rotate(gray_crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
            else:
                h, w = gray_crop.shape[:2]
                mat = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
                rot = cv2.warpAffine(gray_crop, mat, (w, h), borderValue=(255, 255, 255))

            data = pytesseract.image_to_data(rot, output_type=pytesseract.Output.DICT, config="--psm 6")
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                txt = data['text'][i].strip()
                conf = float(data['conf'][i])
                if txt and conf > 30.0:
                    results.append((txt, conf))
        return results
