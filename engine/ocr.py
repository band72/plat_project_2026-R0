"""
ocr.py -- REAL OCR pipeline for scanned plat sheets.

This replaces the hand-transcription approach. Pipeline:
  1. load image (bitonal/grayscale), upscale if needed for small text
  2. detect candidate table regions via morphological line detection
     (curve tables and line tables are ruled grids -- they're the most
     reliably machine-readable content on any plat sheet)
  3. run tesseract on each region with a whitelist tuned for survey data
  4. regex-parse rows into structured curve/line records
  5. validate every parsed curve against L=R*delta and chord=2R*sin(delta/2)
     -- this is the killer feature: bad OCR is *self-detecting* on curve
     tables, because the geometry must be internally consistent.

Requires: tesseract binary, opencv, pillow, numpy. No network.
"""
from __future__ import annotations
import re
import subprocess
import tempfile
import os
import math
import cv2
import numpy as np


# ---------- preprocessing ----------

def load_gray(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(path)
    return img


def deskew(img: np.ndarray) -> tuple[np.ndarray, float]:
    """Estimate and correct small scan rotation using dominant line angles."""
    inv = cv2.bitwise_not(img)
    thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    lines = cv2.HoughLinesP(thr, 1, np.pi / 1800, threshold=400,
                            minLineLength=img.shape[1] // 8, maxLineGap=20)
    if lines is None:
        return img, 0.0
    angs = []
    for x1, y1, x2, y2 in lines[:, 0]:
        a = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if abs(a) < 15:            # near-horizontal only
            angs.append(a)
    if not angs:
        return img, 0.0
    angle = float(np.median(angs))
    if abs(angle) < 0.05:
        return img, angle
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rot = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_REPLICATE)
    return rot, angle


def find_table_regions(img: np.ndarray, min_w=300, min_h=200) -> list[tuple]:
    """Find ruled-grid regions (curve/line tables). Detect horizontal and
    vertical rules separately, take their UNION (not intersection -- an
    intersection yields only sparse corner dots), close gaps, and keep large
    connected components that contain rules in BOTH directions."""
    inv = cv2.bitwise_not(img)
    thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    h, w = thr.shape
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(30, w // 150), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, h // 150)))
    horiz = cv2.morphologyEx(thr, cv2.MORPH_OPEN, hk, iterations=1)
    vert = cv2.morphologyEx(thr, cv2.MORPH_OPEN, vk, iterations=1)
    grid = cv2.bitwise_or(horiz, vert)
    grid = cv2.morphologyEx(grid, cv2.MORPH_CLOSE,
                            np.ones((15, 15), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < min_w or ch < min_h:
            continue
        # require meaningful rule content in BOTH directions inside the box
        hsub = horiz[y:y + ch, x:x + cw]
        vsub = vert[y:y + ch, x:x + cw]
        if (hsub > 0).sum() < cw * 2 or (vsub > 0).sum() < ch * 2:
            continue
        # a real table is mostly rules+text, not a big empty map area:
        density = (thr[y:y + ch, x:x + cw] > 0).mean()
        if density < 0.01:
            continue
        out.append((x, y, cw, ch))
    out.sort(key=lambda r: (r[1], r[0]))
    return out


# ---------- tesseract ----------

def ocr_region(img: np.ndarray, rect=None, psm=6, whitelist=None,
               upscale=2) -> str:
    """OCR a region. psm 6 = uniform block of text (right for table bodies)."""
    if rect is not None:
        x, y, w, h = rect
        crop = img[y:y + h, x:x + w]
    else:
        crop = img
    if upscale != 1:
        crop = cv2.resize(crop, None, fx=upscale, fy=upscale,
                          interpolation=cv2.INTER_CUBIC)
    # NOTE: no median blur here. On small table cells it erodes thin digit
    # strokes and was a contributor to leading-digit dropout. Add a white
    # margin instead -- tesseract needs quiet space around glyphs.
    crop = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "c.png")
        cv2.imwrite(p, crop)
        cmd = ["tesseract", p, "stdout", "--psm", str(psm), "-l", "eng"]
        if whitelist:
            cmd += [f"-c", f"tessedit_char_whitelist={whitelist}"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.stdout


# survey-data whitelist: digits, degree/minute/second marks, NSEW, punctuation
SURVEY_WHITELIST = "0123456789NSEWCLcl#.,'\"*°-/ ()"


def ocr_best(img: np.ndarray, rect=None, psm=6, whitelist=SURVEY_WHITELIST, upscale=2) -> str:
    """OCR a region with optimal survey table defaults."""
    return ocr_region(img, rect=rect, psm=psm, whitelist=whitelist, upscale=upscale)


# ---------- parsing ----------

def _pre_normalize(text: str) -> str:
    """Fix common OCR character confusions seen on survey tables BEFORE
    regex parsing. '$'->'S' is the big one (bearing prefix), plus the
    various unicode quote/degree lookalikes tesseract emits."""
    reps = {
        "$": "S", "§": "S", "5°": "S°",
        "”": '"', "“": '"', "’": "'", "‘": "'", "`": "'", "''": '"',
        "º": "°", "o°": "°", "0°": "°", "*": "°", "—": " ", "–": " ",
        "|": " ", "!": "1",
    }
    for a, b in reps.items():
        text = text.replace(a, b)
    return text


# tolerate OCR confusions: ° vs * vs 0 vs o, " vs '' , O vs 0, I/l vs 1
BEARING_PAT = re.compile(
    r"([NS])\s*([0-9OIl]{1,3})\s*[°*o0]?\s*([0-9OIl]{1,2})\s*['`]?\s*"
    r"([0-9OIl]{1,2})?\s*[\"']{0,2}\s*([EW])",
    re.IGNORECASE)

NUM_PAT = re.compile(r"\d{1,4}\.\d{1,2}")
CURVE_ID_PAT = re.compile(r"\bC\s?(\d{1,3})\b", re.IGNORECASE)
LINE_ID_PAT = re.compile(r"\bL\s?(\d{1,3})\b", re.IGNORECASE)
DELTA_PAT = re.compile(r"(\d{1,3})\s*[°*o0]\s*(\d{1,2})\s*['`]\s*(\d{1,2})")


def _fix_digits(s: str) -> str:
    return (s.replace("O", "0").replace("o", "0")
             .replace("I", "1").replace("l", "1")
             .replace("|", "1"))


def normalize_bearing(m) -> str | None:
    """Rebuild a canonical bearing string from a regex match."""
    try:
        ns, d, mi, se, ew = m.groups()
        d = _fix_digits(d or "0"); mi = _fix_digits(mi or "0")
        se = _fix_digits(se or "0")
        di, mii, sei = int(d), int(mi), int(se)
        if di > 90 or mii > 59 or sei > 59:
            return None
        return f"{ns.upper()}{di:02d}°{mii:02d}'{sei:02d}\"{ew.upper()}"
    except Exception:
        return None


def parse_curve_rows(text: str) -> dict:
    """Parse curve-table rows: C# | Length | Radius | Delta | ChordBrg | Chord.

    Rows whose C# column was clipped/misread still get captured as
    provisional entries (keyed '_row<n>') as long as the *geometry* is
    complete -- the caller can re-key them by sequence or drop them. Losing
    a row entirely because one label smudged would throw away good data."""
    text = _pre_normalize(text)
    out = {}
    anon = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        nums = [float(x) for x in NUM_PAT.findall(line)]
        brg = BEARING_PAT.search(line)
        brg_s = normalize_bearing(brg) if brg else None
        dm = DELTA_PAT.search(line)
        delta = None
        if dm:
            a, b, c = (int(_fix_digits(g)) for g in dm.groups())
            if a <= 360 and b <= 59 and c <= 59:
                delta = a + b / 60 + c / 3600
        if not (len(nums) >= 3 and delta is not None and brg_s):
            continue
        rec = dict(length=nums[0], radius=nums[1], delta=delta,
                   chord_bearing=brg_s, chord=nums[-1], raw=line)
        cid = CURVE_ID_PAT.search(line)
        if cid:
            out[f"C{int(cid.group(1))}"] = rec
        else:
            anon += 1
            rec["id_missing"] = True
            out[f"_row{anon}"] = rec
    return out


def parse_line_rows(text: str) -> dict:
    """Parse line-table rows: L# | Length | Direction."""
    text = _pre_normalize(text)
    out = {}
    anon = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        nums = [float(x) for x in NUM_PAT.findall(line)]
        brg = BEARING_PAT.search(line)
        brg_s = normalize_bearing(brg) if brg else None
        if not (nums and brg_s):
            continue
        # a curve row also has a bearing+numbers; skip anything with a delta
        if DELTA_PAT.search(line) and len(nums) >= 3:
            continue
        rec = dict(length=nums[0], bearing=brg_s, raw=line)
        lid = LINE_ID_PAT.search(line)
        if lid:
            out[f"L{int(lid.group(1))}"] = rec
        else:
            anon += 1
            rec["id_missing"] = True
            out[f"_lrow{anon}"] = rec
    return out


def rule_positions(bin_img: np.ndarray, axis: int, min_frac=0.55) -> list[int]:
    """Find positions of ruled lines by projection profile.
    axis=0 -> horizontal rules (row separators, returns y positions)
    axis=1 -> vertical rules (column separators, returns x positions)"""
    if axis == 0:
        proj = (bin_img > 0).sum(axis=1)
        length = bin_img.shape[1]
    else:
        proj = (bin_img > 0).sum(axis=0)
        length = bin_img.shape[0]
    thresh = length * min_frac
    hits = np.where(proj >= thresh)[0]
    if len(hits) == 0:
        return []
    # collapse runs of adjacent hits into single positions
    groups, cur = [], [hits[0]]
    for p in hits[1:]:
        if p - cur[-1] <= 3:
            cur.append(p)
        else:
            groups.append(int(np.mean(cur)))
            cur = [p]
    groups.append(int(np.mean(cur)))
    return groups


def extract_table_cells(img: np.ndarray, rect: tuple,
                        min_cell_w=18, min_cell_h=12) -> list[list[tuple]]:
    """Given a table bounding box, recover its cell grid from the ruled
    lines. Returns rows of (x, y, w, h) in FULL-IMAGE coordinates.

    Cell-level extraction is what makes column identity reliable: the curve
    number lives in its own cell, so it cannot be swallowed by, or
    misaligned against, neighbouring columns the way it is when you OCR the
    whole table as flowing text.

    The rule-detection threshold is AUTO-TUNED: scanned rules vary in
    darkness and continuity, and a fixed threshold silently returns an empty
    grid on perfectly good tables (observed: a 6-column curve table yielding
    0 columns at 0.5 but a correct 7 separators at 0.3)."""
    x, y, w, h = rect
    sub = img[y:y + h, x:x + w]
    inv = cv2.bitwise_not(sub)
    thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, w // 12), 1))
    # Vertical kernel is CAPPED. A kernel scaled to a tall table (h//20 was
    # 132 px on a 59-row curve table) erodes column rules that are thin or
    # gappy -- exactly what happens on anisotropic scans where the vertical
    # resolution is half the horizontal. Columns then vanish entirely.
    vk_len = max(10, min(40, h // 20))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, vk_len))
    horiz = cv2.morphologyEx(thr, cv2.MORPH_OPEN, hk, iterations=1)
    vert = cv2.morphologyEx(thr, cv2.MORPH_OPEN, vk, iterations=1)

    # Pick the threshold that recovers the MOST column separators (subject to
    # a sane row count). Breaking at the first threshold that "works" returns
    # a coarse 2-3 column grid that merges real columns together -- observed
    # collapsing a 6-column curve table into 2 cells.
    best, best_cols = None, 0
    for frac in (0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.12, 0.09):
        ys = rule_positions(horiz, axis=0, min_frac=frac)
        xs = rule_positions(vert, axis=1, min_frac=frac)
        if len(ys) >= 3 and len(xs) >= 3 and len(xs) <= 15:
            if len(xs) > best_cols:
                best, best_cols = (ys, xs), len(xs)
    if best is None:
        return []
    ys, xs = best

    rows = []
    for i in range(len(ys) - 1):
        y0, y1 = ys[i], ys[i + 1]
        if y1 - y0 < min_cell_h:
            continue
        row = []
        for j in range(len(xs) - 1):
            x0, x1 = xs[j], xs[j + 1]
            if x1 - x0 < min_cell_w:
                continue
            # Inset just enough to exclude the ruled border (which tesseract
            # otherwise reads as glyphs) but not so much that the first digit
            # is clipped. Tuned empirically: outward padding tanked recall
            # from 10 rows to 1; a 3px inset plus the white margin added in
            # ocr_region() is the best balance found.
            row.append((x + x0 + 3, y + y0 + 3, (x1 - x0) - 6, (y1 - y0) - 6))
        if row:
            rows.append(row)
    return rows


def ocr_cell(img: np.ndarray, cell: tuple, numeric=False, upscale=4) -> str:
    """OCR a single table cell. psm 7 = treat as one text line."""
    wl = "0123456789.'\"°NSEWCL#-/ " if not numeric else "0123456789.'\"°-"
    t = ocr_region(img, cell, psm=7, whitelist=wl, upscale=upscale)
    return _pre_normalize(t).strip()


def parse_table_by_cells(img: np.ndarray, rect: tuple) -> tuple[dict, dict]:
    """Cell-accurate table read. Returns (curves, lines) keyed by their own
    ID column -- no sequence guessing, no anonymous rows."""
    curves, lines = {}, {}
    for row in extract_table_cells(img, rect):
        texts = [ocr_cell(img, c) for c in row]
        joined = " ".join(texts)
        idm = CURVE_ID_PAT.search(texts[0]) if texts else None
        lidm = LINE_ID_PAT.search(texts[0]) if texts else None
        if texts:
            texts = list(texts)
            texts[0] = CURVE_ID_PAT.sub(" ", texts[0])
            texts[0] = LINE_ID_PAT.sub(" ", texts[0])
        nums, brg, delta = [], None, None
        # scan every cell: if column rules were partly missed, the first cell
        # can hold the ID *and* the first numeric columns
        for t in texts:
            nums += [float(v) for v in NUM_PAT.findall(t)]
            b = BEARING_PAT.search(t)
            if b and not brg:
                brg = normalize_bearing(b)
            d = DELTA_PAT.search(t)
            if d and delta is None:
                a, bb, cc = (int(_fix_digits(g)) for g in d.groups())
                if a <= 360 and bb <= 59 and cc <= 59:
                    delta = a + bb / 60 + cc / 3600
        if idm and len(nums) >= 3 and delta is not None and brg:
            curves[f"C{int(idm.group(1))}"] = dict(
                length=nums[0], radius=nums[1], delta=delta,
                chord_bearing=brg, chord=nums[-1], raw=joined, by_cell=True)
        elif lidm and nums and brg and delta is None:
            lines[f"L{int(lidm.group(1))}"] = dict(
                length=nums[0], bearing=brg, raw=joined, by_cell=True)
    return curves, lines


def find_table_regions_inside_border(img: np.ndarray, **kw) -> list[tuple]:
    """Sheet borders connect every table into one giant component. Strip the
    outer frame first, then detect tables within."""
    regs = find_table_regions(img, **kw)
    if not regs:
        return regs
    H, W = img.shape
    page = max(regs, key=lambda r: r[2] * r[3])
    if page[2] > W * 0.7 and page[3] > H * 0.7:
        inner = [r for r in regs if r is not page]
        return inner if inner else regs
    return regs


# ---------- self-validation ----------

def validate_curve(rec: dict, tol=0.15) -> tuple[bool, str]:
    """A curve row is internally over-determined, so OCR errors are
    self-detecting. Returns (ok, message)."""
    R, L, D, C = rec["radius"], rec["length"], rec["delta"], rec["chord"]
    if R <= 0 or D <= 0:
        return False, "nonpositive R or delta"
    cl = R * math.radians(D)
    cc = 2 * R * math.sin(math.radians(D) / 2)
    dl, dc = abs(cl - L), abs(cc - C)
    if dl < tol and dc < tol:
        return True, "ok"
    return False, f"L off {dl:.2f}, chord off {dc:.2f} (calc L={cl:.2f} C={cc:.2f})"


def repair_curve(rec: dict, max_err=3.0) -> dict | None:
    """If a row fails validation, try single-field repair: assume R and delta
    are correct (most OCR-robust: R is usually a round number, delta has 3
    separated groups) and recompute L and chord.

    CRITICAL GATE: only repair when the discrepancy is small enough to be a
    plausible OCR digit error (default 3 ft). A row that is off by tens or
    hundreds of feet is not a typo -- it is a misparsed row (wrong columns
    captured), and "repairing" it would fabricate authoritative-looking
    numbers from garbage. Those must be rejected, not fixed."""
    R, D = rec["radius"], rec["delta"]
    if R <= 0 or D <= 0:
        return None
    calc_L = R * math.radians(D)
    calc_C = 2 * R * math.sin(math.radians(D) / 2)
    if (abs(calc_L - rec["length"]) > max_err
            and abs(calc_C - rec["chord"]) > max_err):
        return None  # too far off to be a typo -- refuse to "repair"
    fixed = dict(rec)
    fixed["length"] = round(calc_L, 2)
    fixed["chord"] = round(calc_C, 2)
    fixed["repaired"] = True
    return fixed


# ---------- header-driven column mapping ----------

HEADER_ALIASES = {
    "curve": "id", "curve #": "id", "curve#": "id", "no": "id", "line": "id",
    "length": "length", "arc": "length", "arc length": "length",
    "radius": "radius", "rad": "radius",
    "delta": "delta", "central angle": "delta", "ca": "delta",
    "chord": "chord", "chord length": "chord", "ch": "chord",
    "bearing": "chord_bearing", "chord bearing": "chord_bearing",
    "chd bearing": "chord_bearing", "cb": "chord_bearing",
    "direction": "chord_bearing",
    "tangent": "tangent", "tan": "tangent", "t": "tangent",
    "distance": "length",
}


def map_header(cells_text: list[str]) -> dict[int, str]:
    """Map column index -> canonical field name using the table's own header.

    CRITICAL: curve-table column ORDER IS NOT STANDARD between plats.
      Trail Ridge (Clay Co 2026): CURVE|LENGTH|RADIUS|DELTA|CHORD BEARING|CHORD
      Atlantic Beach (Duval 2014): CURVE|LENGTH|RADIUS|BEARING|CHORD|DELTA|TANGENT
    A positional parser silently mis-assigns every value -- chord read as
    delta, delta read as chord -- and the geometry check then fails for a
    reason that looks like OCR noise. Always read the header."""
    out = {}
    for i, t in enumerate(cells_text):
        k = re.sub(r"[^a-z# ]", "", t.lower()).strip()
        k = re.sub(r"\s+", " ", k)
        if k in HEADER_ALIASES:
            out[i] = HEADER_ALIASES[k]
            continue
        for alias, field in HEADER_ALIASES.items():
            if alias and alias in k:
                out[i] = field
                break
    return out


def parse_table_with_header(img: np.ndarray, rect: tuple,
                            min_cols=3) -> tuple[dict, dict, dict]:
    """Cell-read a ruled table, using its header row to map columns.
    Returns (curves, lines, header_map)."""
    rows = extract_table_cells(img, rect)
    curves, lines, header = {}, {}, {}
    for row in rows:
        texts = [ocr_cell(img, c) for c in row]
        if len(texts) < min_cols:
            continue
        if not header:
            m = map_header(texts)
            # a header row maps most of its cells and carries no numbers
            if len(m) >= min_cols and not any(NUM_PAT.search(t) for t in texts):
                header = m
            continue
        rec = {}
        for i, t in enumerate(texts):
            f = header.get(i)
            if not f:
                continue
            t = _pre_normalize(t)
            if f == "id":
                m = CURVE_ID_PAT.search(t) or LINE_ID_PAT.search(t)
                if m:
                    rec["id"] = m.group(0).replace(" ", "").upper()
            elif f == "chord_bearing":
                b = BEARING_PAT.search(t)
                if b:
                    rec["chord_bearing"] = normalize_bearing(b)
            elif f == "delta":
                d = DELTA_PAT.search(t)
                if d:
                    a, bb, cc = (int(_fix_digits(g)) for g in d.groups())
                    if a <= 360 and bb <= 59 and cc <= 59:
                        rec["delta"] = a + bb/60 + cc/3600
            else:
                n = NUM_PAT.search(t)
                if n:
                    rec[f] = float(n.group(0))
        rid = rec.pop("id", None)
        if not rid:
            continue
        if "radius" in rec and "delta" in rec:
            curves[rid] = rec
        elif "length" in rec and "chord_bearing" in rec:
            lines[rid] = dict(length=rec["length"], bearing=rec["chord_bearing"])
    return curves, lines, header


def infer_curve_columns(rows_text: list[list[str]], tol=0.05) -> dict:
    """Infer which column is which by testing the CURVE IDENTITIES.

    Header text is often unreadable (split title rows, merged cells), and
    column ORDER differs between plats. But a curve row is over-determined:
    given delta, the true assignment of the numeric columns is the only one
    that satisfies, across many rows,
        length  = R * delta_rad
        chord   = 2R sin(delta/2)
        tangent = R tan(delta/2)
    So the table tells us its own schema. This needs no header at all and
    cannot be fooled by a plat that reorders its columns."""
    # locate the structural columns first
    id_col = bear_col = delta_col = None
    ncol = max(len(r) for r in rows_text)
    for c in range(ncol):
        col = [_pre_normalize(r[c]) if c < len(r) else "" for r in rows_text]
        if id_col is None and sum(1 for t in col if CURVE_ID_PAT.fullmatch(t.strip())) >= len(col) * 0.5:
            id_col = c
        if bear_col is None and sum(1 for t in col if BEARING_PAT.search(t)) >= len(col) * 0.5:
            bear_col = c
        # A bearing string contains a dd-mm-ss group too (N89d38'53"W), so a
        # naive DELTA_PAT scan latches onto the BEARING column and mislabels
        # it as delta. Require the delta column to be free of N/S..E/W.
        if (delta_col is None and c != bear_col
                and sum(1 for t in col if DELTA_PAT.search(t)
                        and not BEARING_PAT.search(t)) >= len(col) * 0.5):
            delta_col = c
    if delta_col is None:
        return {}
    num_cols = [c for c in range(ncol) if c not in (id_col, bear_col, delta_col)]

    # gather numeric values and deltas per row
    data = []
    for r in rows_text:
        if delta_col >= len(r):
            continue
        dm = DELTA_PAT.search(_pre_normalize(r[delta_col]))
        if not dm:
            continue
        a, b, c2 = (int(_fix_digits(g)) for g in dm.groups())
        if a > 360 or b > 59 or c2 > 59:
            continue
        D = a + b / 60 + c2 / 3600
        vals = {}
        for c in num_cols:
            if c < len(r):
                m = NUM_PAT.search(_pre_normalize(r[c]))
                if m:
                    vals[c] = float(m.group(0))
        if len(vals) >= 2:
            data.append((D, vals))
    if len(data) < 5:
        return {}

    best, best_score = None, -1
    from itertools import permutations
    roles = ["length", "radius", "chord", "tangent"][:len(num_cols)]
    for perm in permutations(num_cols, len(roles)):
        assign = dict(zip(roles, perm))
        score = 0
        for D, vals in data:
            R = vals.get(assign.get("radius"))
            if not R or R <= 0:
                continue
            rad = math.radians(D)
            ok = 0
            if "length" in assign and assign["length"] in vals:
                ok += abs(vals[assign["length"]] - R * rad) < max(tol, 0.02 * R * rad)
            if "chord" in assign and assign["chord"] in vals:
                ok += abs(vals[assign["chord"]] - 2 * R * math.sin(rad / 2)) < max(tol, 0.02 * R)
            if "tangent" in assign and assign["tangent"] in vals:
                ok += abs(vals[assign["tangent"]] - R * math.tan(rad / 2)) < max(tol, 0.02 * R)
            score += ok
        if score > best_score:
            best, best_score = assign, score
    out = {v: k for k, v in (best or {}).items()}
    if id_col is not None:
        out[id_col] = "id"
    if bear_col is not None:
        out[bear_col] = "chord_bearing"
    out[delta_col] = "delta"
    return dict(mapping=out, confidence=best_score, rows_tested=len(data))
