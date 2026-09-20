import cv2
import numpy as np
import easyocr
import math
import os

import pytesseract

# Initialize EasyOCR reader as optional fallback
try:
    reader = easyocr.Reader(['en'])
except Exception as e:
    reader = None

def apply_clahe(img: np.ndarray) -> np.ndarray:
    """Apply Contrast Limited Adaptive Histogram Equalization."""
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    return clahe.apply(gray)

def get_highlight_mask(img: np.ndarray) -> np.ndarray:
    """
    Color & Green Highlight Masking:
    Isolate highlighted text regions where g - r > 25 & g - b > 25.
    Only returns a restricting mask if significant highlight (>1000 pixels) is present.
    """
    if len(img.shape) != 3:
        return np.ones(img.shape[:2], dtype=np.uint8) * 255
        
    b, g, r = cv2.split(img.astype(np.int16))
    mask1 = (g - r) > 25
    mask2 = (g - b) > 25
    combined = (mask1 & mask2).astype(np.uint8) * 255
    
    kernel = np.ones((5,5), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)
    
    # If highlight covers significant area, use it; otherwise preserve full image
    if cv2.countNonZero(combined) > 1000:
        return combined
    return np.ones(img.shape[:2], dtype=np.uint8) * 255

def rotate_image(image: np.ndarray, angle: float) -> tuple[np.ndarray, np.ndarray]:
    """Rotate image by angle degrees and return rotated image and rotation matrix."""
    if angle == 0:
        return image.copy(), np.eye(3)[:2]
    elif angle == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), None
    elif angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180), None
    elif angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), None

    h, w = image.shape[:2]
    center = (w / 2, h / 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = np.abs(M[0, 0])
    sin = np.abs(M[0, 1])
    nW = int((h * sin) + (w * cos))
    nH = int((h * cos) + (w * sin))
    M[0, 2] += (nW / 2) - center[0]
    M[1, 2] += (nH / 2) - center[1]
    rotated = cv2.warpAffine(image, M, (nW, nH), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated, M

def extract_streets(img_path: str) -> dict:
    """
    4-Orientation OCR Pass (0°, 90°, 270°, 45°) with CLAHE contrast enhancement.
    Complies with permanent agent rules.
    """
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(img_path)
        
    enhanced = apply_clahe(img)
    mask = get_highlight_mask(img)
    if cv2.countNonZero(mask) > 1000 and len(img.shape) == 3:
        enhanced = cv2.bitwise_and(enhanced, enhanced, mask=mask)
        
    angles = {
        "0": 0.0,
        "90": 90.0,
        "270": 270.0,
        "45": 45.0
    }
    
    results = {}
    
    # Scale down for OCR if image is massive (>3500px)
    h, w = enhanced.shape[:2]
    scale = 1.0
    if max(h, w) > 3500:
        scale = 3500.0 / max(h, w)
        proc_base = cv2.resize(enhanced, (int(w * scale), int(h * scale)))
    else:
        proc_base = enhanced

    for name, angle in angles.items():
        rot_img, _ = rotate_image(proc_base, angle)
        # Try Tesseract first
        try:
            txt = pytesseract.image_to_string(rot_img, config='--psm 11')
            lines = [l.strip() for l in txt.split('\n') if len(l.strip()) > 3]
            results[name] = lines
        except Exception:
            if reader is not None:
                res = reader.readtext(rot_img, detail=0, paragraph=False)
                results[name] = [r for r in res if len(r) > 3]
            else:
                results[name] = []
                
    return results

def pair_intersections(extracted: dict) -> list[tuple[str, str]]:
    """
    Dual-Axis Intersection Consensus:
    Pair horizontal street candidates with vertical street candidates.
    """
    horiz = extracted.get("0", [])
    vert_90 = extracted.get("90", [])
    vert_270 = extracted.get("270", [])
    angled = extracted.get("45", [])
    
    horiz_candidates = set(horiz)
    vert_candidates = set(vert_90 + vert_270)
    
    street_keywords = [
        "STREET", "DRIVE", "BOULEVARD", "AVENUE", "LANE", "ROAD", 
        "COURT", "WAY", "PL", "BLVD", "AVE", "ST", "RD", "DR", "CT", "LN"
    ]
    
    def clean_street(s):
        s_upper = s.upper()
        # Look for presence of keyword as a whole word
        tokens = s_upper.split()
        for i, tok in enumerate(tokens):
            if tok in street_keywords or any(tok.endswith(kw) for kw in street_keywords):
                # Extract street phrase around this token
                start = max(0, i - 2)
                candidate = " ".join(tokens[start:i+1])
                # Remove common survey non-street words
                for bad in ["PLAT", "BOOK", "PAGE", "RIGHT", "OF", "WAY", "SUITE", "FEET", "THE"]:
                    candidate = candidate.replace(f"{bad} ", "").replace(f" {bad}", "")
                candidate = "".join(c for c in candidate if c.isalnum() or c in " -").strip()
                if len(candidate) > 4:
                    return candidate
        return None
        
    h_streets = set()
    for s in horiz_candidates:
        cs = clean_street(s)
        if cs:
            h_streets.add(cs)
            
    v_streets = set()
    for s in vert_candidates:
        cs = clean_street(s)
        if cs:
            v_streets.add(cs)
            
    pairs = []
    for h in sorted(list(h_streets)):
        for v in sorted(list(v_streets)):
            if h != v:
                pairs.append((h, v))
                
    return pairs
