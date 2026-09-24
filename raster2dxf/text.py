"""Text/linework separation, oriented label clustering, batched OCR and
survey-label classification.

Batched OCR: every label crop is rotated to horizontal, height-normalized
and stacked into one tall strip; tesseract (psm 6) runs once per strip per
orientation and words are mapped back to their crop by y. That is ~50x
fewer tesseract process launches than per-label OCR on a big sheet.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytesseract

TARGET_H = 54          # px crop height fed to tesseract
SHEARS = (0.0, 0.3)    # italic de-slant variants (hand-lettered plats slant ~17 deg)
STRIP_PAD = 18


@dataclass
class Label:
    id: int
    center: np.ndarray            # px
    angle: float                  # reading direction, deg, image coords (x right, y down), CCW-negative
    width: float                  # along reading direction, px
    height: float                 # text height, px
    text: str = ""
    conf: float = -1.0
    kind: str = "text"            # bearing|distance|curve_id|curve_data|lot|area|text
    value: object = None
    box: np.ndarray = None        # 4x2 corners px
    assoc: dict = field(default_factory=dict)
    alts: list = field(default_factory=list)   # every OCR variant: (score, rot, text, conf, kind, value)
    angle0: float = 0.0           # cluster direction before choosing a reading variant
    verified: bool = False        # reading confirmed by measured geometry


def estimate_char_height(ink: np.ndarray, stroke_w: float) -> float:
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if n <= 1:
        return 12.0
    w, h, a = st[1:, 2], st[1:, 3], st[1:, 4]
    m = np.maximum(w, h)
    sel = (m >= 3 * stroke_w) & (m <= 40 * stroke_w) & (a >= 2 * stroke_w ** 2) \
        & (a <= 0.75 * w * h + 1) & (np.minimum(w, h) >= 1.5 * stroke_w)
    if sel.sum() < 5:
        return float(max(10.0, 6 * stroke_w))
    return float(np.median(m[sel]))


def rasterize(linework, shape, thick: int) -> np.ndarray:
    m = np.zeros(shape[:2], np.uint8)
    for l in linework.lines:
        cv2.line(m, tuple(np.round(l.p1).astype(int)), tuple(np.round(l.p2).astype(int)),
                 255, thick, cv2.LINE_8)
    for a in linework.arcs:
        pts = np.round(a.sample()).astype(np.int32)
        cv2.polylines(m, [pts], False, 255, thick, cv2.LINE_8)
    return m


def text_mask(ink: np.ndarray, linework, stroke_w: float) -> np.ndarray:
    lw = rasterize(linework, ink.shape, thick=max(2, int(round(stroke_w * 1.6)) + 2))
    return cv2.bitwise_and(ink, cv2.bitwise_not(lw))


def _glyph_dirs(centers, linework, char_h):
    """Undirected unit direction of the nearest line/arc (tangent) for each
    glyph centre, or None when nothing is within 2.5 char heights."""
    from scipy.spatial import cKDTree
    pts, dirs = [], []
    step = max(2.0, char_h / 2)
    for l in linework.lines:
        d = l.p2 - l.p1
        L = float(np.hypot(*d))
        if L < 1:
            continue
        u = d / L
        for t in np.arange(0, L + step, step):
            pts.append(l.p1 + u * min(t, L))
            dirs.append(u)
    for a in linework.arcs:
        for t in np.linspace(0, 1, max(3, int(a.length / step) + 1)):
            p = a.point(t)
            v = p - a.center
            v = v / (np.hypot(*v) or 1)
            pts.append(p)
            dirs.append(np.array([-v[1], v[0]]))
    out = [None] * len(centers)
    if not pts or not len(centers):
        return out
    tree = cKDTree(np.array(pts))
    dist, idx = tree.query(np.asarray(centers), distance_upper_bound=2.5 * char_h)
    for k, (dd, ii) in enumerate(zip(dist, idx)):
        if np.isfinite(dd):
            out[k] = dirs[ii]
    return out


def cluster_labels(tmask: np.ndarray, char_h: float, stroke_w: float, linework=None) -> list[Label]:
    """Group glyphs into labels.  Two glyphs join when they are close
    *along* the local text direction (the nearest line/arc -- plat labels
    run parallel to the course they describe) and nearly on the same
    baseline across it; leftover single glyphs may then join horizontally
    (lot numbers, notes).  This keeps adjacent parallel label columns
    (bearing | distance | lot no.) apart where isotropic dilation fuses them."""
    from scipy.spatial import cKDTree
    n, lab, st, cen = cv2.connectedComponentsWithStats(tmask, connectivity=8)
    gl = []
    for k in range(1, n):
        w, h, a = st[k, 2], st[k, 3], st[k, 4]
        m = max(w, h)
        if a < 0.5 * stroke_w ** 2 or m < 0.12 * char_h or m > 4.5 * char_h:
            continue
        gl.append(k)
    if not gl:
        return []
    C = cen[gl]
    WH = st[gl][:, 2:4].astype(float)
    dirs = _glyph_dirs(C, linework, char_h) if linework is not None else [None] * len(gl)
    parent = list(range(len(gl)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def ext(i, u):
        return (WH[i, 0] * abs(u[0]) + WH[i, 1] * abs(u[1])) / 2

    tree = cKDTree(C)
    pairs = tree.query_pairs(r=1.8 * char_h)
    hx = np.array([1.0, 0.0])
    deferred = []
    for i, j in pairs:
        di, dj = dirs[i], dirs[j]
        if di is not None and dj is not None and abs(float(di @ dj)) > math.cos(math.radians(15)):
            u = di
            v = C[j] - C[i]
            nrm = np.array([-u[1], u[0]])
            gap = abs(float(v @ u)) - ext(i, u) - ext(j, u)
            perp = abs(float(v @ nrm))
            if gap <= 0.7 * char_h and perp <= 0.5 * char_h:
                parent[find(i)] = find(j)
                continue
        deferred.append((i, j))
    sizes = {}
    for k in range(len(gl)):
        sizes[find(k)] = sizes.get(find(k), 0) + 1
    for i, j in deferred:
        if sizes.get(find(i), 1) > 1 and dirs[i] is not None and abs(dirs[i][1]) > 0.26:
            continue
        if sizes.get(find(j), 1) > 1 and dirs[j] is not None and abs(dirs[j][1]) > 0.26:
            continue
        v = C[j] - C[i]
        gap = abs(v[0]) - ext(i, hx) - ext(j, hx)
        if gap <= 0.6 * char_h and abs(v[1]) <= 0.45 * char_h:
            parent[find(i)] = find(j)
    groups: dict = {}
    for k in range(len(gl)):
        groups.setdefault(find(k), []).append(k)
    labels = []
    for ks in groups.values():
        mask_ids = np.array([gl[k] for k in ks])
        x0 = int(min(st[g, 0] for g in mask_ids)); y0 = int(min(st[g, 1] for g in mask_ids))
        x1 = int(max(st[g, 0] + st[g, 2] for g in mask_ids)); y1 = int(max(st[g, 1] + st[g, 3] for g in mask_ids))
        sub = np.isin(lab[y0:y1, x0:x1], mask_ids)
        ys, xs = np.nonzero(sub)
        if len(xs) < 4:
            continue
        pts = np.stack([xs + x0, ys + y0], axis=1).astype(np.float64)
        # direction: common line direction if the glyphs agreed on one,
        # else principal axis of the pixels (multi-glyph) or horizontal
        ds = [dirs[k] for k in ks if dirs[k] is not None]
        if len(ks) >= 2 and ds and _joined_along(ks, C, ds[0]):
            u = ds[0]
        elif len(ks) >= 2:
            c = pts.mean(axis=0)
            _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
            u = vt[0]
        else:
            u = hx
        ang = math.degrees(math.atan2(u[1], u[0]))
        c = pts.mean(axis=0)
        nrm = np.array([-u[1], u[0]])
        ta, tn = (pts - c) @ u, (pts - c) @ nrm
        w, h = ta.max() - ta.min() + 1, tn.max() - tn.min() + 1
        cc = c + u * (ta.max() + ta.min()) / 2 + nrm * (tn.max() + tn.min()) / 2
        if h < 0.3 * char_h and w < 1.2 * char_h:
            continue
        box = cv2.boxPoints(((cc[0], cc[1]), (w, h), ang))
        labels.append(Label(id=len(labels), center=cc, angle=ang % 360, width=w, height=h,
                            box=box))
    return labels


def _joined_along(ks, C, u):
    """True if the cluster is elongated along u (spread along >> across)."""
    P = C[ks]
    c = P.mean(axis=0)
    a = np.abs((P - c) @ u).max()
    b = np.abs((P - c) @ np.array([-u[1], u[0]])).max()
    return a >= b


def _crop(img: np.ndarray, lab: Label, rot_extra: float, char_h: float, shear: float = 0.0) -> np.ndarray:
    pad = 0.35 * char_h
    w, h = lab.width + 2 * pad, lab.height + 2 * pad
    if rot_extra % 180 == 90:
        w, h = h, w
    ang = lab.angle + rot_extra
    M = cv2.getRotationMatrix2D((float(lab.center[0]), float(lab.center[1])), ang, 1.0)
    M[0, 2] += w / 2 - lab.center[0]
    M[1, 2] += h / 2 - lab.center[1]
    out = cv2.warpAffine(img, M, (max(2, int(w)), max(2, int(h))),
                         flags=cv2.INTER_CUBIC, borderValue=255)
    s = TARGET_H / max(1.0, min(h, 1.6 * lab.height + 2 * pad))
    s = min(s, 6.0)
    out = cv2.resize(out, (max(2, int(out.shape[1] * s)), max(2, int(out.shape[0] * s))),
                     interpolation=cv2.INTER_CUBIC)
    if shear:
        hh, ww = out.shape
        M = np.float32([[1, shear, 0], [0, 1, 0]])
        out = cv2.warpAffine(out, M, (ww + int(shear * hh), hh), borderValue=255)
    _, out = cv2.threshold(out, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return out


def _ocr_strip(crops: list[np.ndarray]) -> list[tuple[str, float]]:
    """OCR a list of single-line crops in one tesseract call."""
    if not crops:
        return []
    W = max(c.shape[1] for c in crops) + 2 * STRIP_PAD
    ys, rows = [], []
    y = STRIP_PAD
    for c in crops:
        ys.append((y, y + c.shape[0]))
        y += c.shape[0] + STRIP_PAD
    strip = np.full((y, W), 255, np.uint8)
    for (y0, y1), c in zip(ys, crops):
        strip[y0:y1, STRIP_PAD:STRIP_PAD + c.shape[1]] = c
    d = pytesseract.image_to_data(strip, config="--psm 6 --oem 1",
                                  output_type=pytesseract.Output.DICT)
    words = [[] for _ in crops]
    for i, t in enumerate(d["text"]):
        t = t.strip()
        if not t:
            continue
        cy = d["top"][i] + d["height"][i] / 2
        for k, (y0, y1) in enumerate(ys):
            if y0 - STRIP_PAD / 2 <= cy <= y1 + STRIP_PAD / 2:
                words[k].append((d["left"][i], t, float(d["conf"][i])))
                break
    out = []
    for ws in words:
        ws.sort()
        if not ws:
            out.append(("", -1.0))
            continue
        out.append((" ".join(w[1] for w in ws), float(np.mean([w[2] for w in ws]))))
    return out


def ocr_labels(gray_clean: np.ndarray, labels: list[Label], char_h: float, chunk=80) -> None:
    """Fill label.text/conf, trying both reading directions (and the two
    perpendicular ones for near-square blobs such as lot numbers)."""
    variants = [(r, sh) for r in (0, 180, 90, 270) for sh in SHEARS]
    results = {v: {} for v in variants}
    for v in variants:
        rot, sh = v
        todo = [l for l in labels if rot in (0, 180) or l.width < 1.8 * l.height]
        for i in range(0, len(todo), chunk):
            part = todo[i:i + chunk]
            crops = [_crop(gray_clean, l, rot, char_h, sh) for l in part]
            for l, r in zip(part, _ocr_strip(crops)):
                results[v][l.id] = r
    for l in labels:
        l.angle0 = l.angle
        alts = []
        for v in variants:
            if l.id not in results[v]:
                continue
            txt, conf = results[v][l.id]
            kind, val = classify(txt, l.height, char_h)
            score = conf + (40 if kind in ("bearing", "distance", "curve_id", "curve_data") else 0) \
                + (15 if kind in ("lot", "area") else 0)
            alts.append((score, v[0], txt, conf, kind, val))
        alts.sort(key=lambda a: -a[0])
        l.alts = alts
        if alts:
            apply_alt(l, alts[0])


def apply_alt(l: Label, alt) -> None:
    _, rot, l.text, l.conf, l.kind, l.value = alt
    l.angle = (l.angle0 + rot) % 360


# ------------------------------------------------------------- classification
_BRG = re.compile(r"^([NS])(\d{1,2})[°o*º•]?(\d{1,2})['’`]?(\d{1,2}(?:\.\d+)?)?[\"”]?([EW])$")
_DIST = re.compile(r"^(\d{1,4}\.\d{1,2}|\d{1,4})(['’`]|FT)?$")
# combined course call "N87°35'30"E - 1453.5'" (normalize() drops spaces)
_COURSE = re.compile(r"^([NS][0-9°'\"*oOº•’`.]+[EW])\.?[-=~_]+(\d{1,5}(?:\.\d{1,2})?)['’`\"]?$")
_CID = re.compile(r"^C-?(\d{1,3})$")
_CDATA = re.compile(r"(^|[^A-Z])(R|L|T|A|D|Δ|CH|CB|LC|ARC|RAD|DELTA|CHORD)\s*=", re.I)


def normalize(t: str) -> str:
    t = t.strip().upper().replace(" ", "")
    t = t.replace("“", '"').replace("”", '"').replace("''", '"').replace("’", "'").replace("‘", "'")
    t = t.replace(",", ".").replace("—", "-").replace("–", "-")
    # an italic hand-lettered "1" is often read as "/" -- before a digit and
    # not after one (so 1/2 fractions survive): "/02.38'" -> "102.38'"
    t = re.sub(r"(?<![0-9])/(?=[0-9])", "1", t)
    # leading/trailing junk (leader ticks, line stubs, stray quote marks)
    t = re.sub(r"^[^A-Z0-9]+", "", t)
    t = re.sub(r"[^A-Z0-9'\"°]+$", "", t)
    # a distance's foot mark is often read as a degree sign / quote / "!"
    t = re.sub(r"^(\d{1,4}\.\d{1,2})[°\"!’`]+$", r"\1'", t)
    t = re.sub(r"^(\d{2,4})[°\"’`]$", r"\1'", t)
    return t


def parse_bearing(t: str):
    s = normalize(t).replace(".", "") if re.search(r"[NS].*[EW]", normalize(t)) else normalize(t)
    s = re.sub(r"(?<=\d)[O](?=\d)", "0", s)
    m = _BRG.match(s)
    if not m:
        return None
    ns, d, mi, se, ew = m.groups()
    d, mi = int(d), int(mi)
    se = float(se) if se else 0.0
    if d > 90 or mi >= 60 or se >= 60:
        return None
    return dict(ns=ns, deg=d, min=mi, sec=se, ew=ew,
                text=f"{ns} {d:02d}°{mi:02d}'{int(round(se)):02d}\" {ew}",
                decimal=d + mi / 60 + se / 3600)


def bearing_readings(t: str) -> list[tuple[int, dict]]:
    """Strict readings first; if none, quadrant-letter repairs (cost +2):
    '$'->S, a digit misread for the leading N/S ('187°35'30"E' -> N87...),
    or a trailing E/W lost to a cluster split.  Geometry then chooses (and
    readings costing >= 2 must match within 0.35 deg)."""
    out = _bearing_readings(t)
    if out:
        return out
    s = normalize(t.replace("$", "S"))
    heads = [s] if s[:1] in ("N", "S") else \
        [q + s for q in "NS"] + ([q + s[1:] for q in "NS"] if s[:1] in "17" else [])
    cands = []
    for h in heads:
        cands.append(h)
        if not re.search(r"[EW]\.?$", h):
            cands.extend(h + q for q in "EW")
    if "°" not in s and len(re.sub(r"\D", "", s)) < 4:
        return []
    best: dict = {}
    for c in cands:
        for cost, b in _bearing_readings(c):
            if cost + 2 <= 3 and (b["text"] not in best or cost + 2 < best[b["text"]][0]):
                best[b["text"]] = (cost + 2, b)
    return sorted(best.values(), key=lambda cb: cb[0])


def _bearing_readings(t: str) -> list[tuple[int, dict]]:
    """All plausible bearings in an OCR string, as (edit_cost, bearing).
    Cost 0 = the direct parse; cost 1 = one character dropped from the digit
    run (a degree/minute mark misread as a digit: N2024'30"W -> 2°24'30").
    Geometry decides between them (see associate.reconcile)."""
    s = normalize(t)
    dist = None
    mc = _COURSE.match(s)
    if mc:
        s, dist = mc.group(1), float(mc.group(2))
    s = s.replace(".", "")
    m = re.match(r"^([NS])(.*?)([EW])$", s)
    if not m:
        return []
    if dist is not None:
        return [(c, dict(b, dist=dist)) for c, b in _bearing_readings(s)]
    out = []
    b = parse_bearing(s)
    if b:
        out.append((0, b))
    ns, mid, ew = m.groups()
    # inside a numeric run, a stray letter is a digit misread
    # (N1°S8'48"E = N1°58'48"E) -- but only when the run is already mostly
    # digits, or words like "NORTH LINE" (N·ORTHLIN·E) turn into bearings
    lookalike = {"O": "0", "S": "5", "B": "8", "I": "1", "L": "1", "Z": "2"}
    n_real = sum(ch.isdigit() for ch in mid)
    n_map = sum(ch in lookalike for ch in mid)
    if n_real >= 3 and n_map <= 2 and n_map <= n_real // 2:
        mid = mid.translate(str.maketrans(lookalike))
    digits = re.sub(r"[^0-9]", "", mid)
    seen = {b["text"]} if b else set()

    def add(cost, d, mi, se):
        if d > 90 or mi >= 60 or se >= 60:
            return
        txt = f"{ns} {d:02d}°{mi:02d}'{se:02d}\" {ew}"
        if txt in seen:
            return
        seen.add(txt)
        out.append((cost, dict(ns=ns, deg=d, min=mi, sec=float(se), ew=ew, text=txt,
                               decimal=d + mi / 60 + se / 3600)))

    for skip in [None] + list(range(len(digits))):
        ds = digits if skip is None else digits[:skip] + digits[skip + 1:]
        for dl in (1, 2):
            # the degree mark (right after the degree digits) is the usual
            # misread; any other dropped digit is less plausible
            cost = 0 if skip is None else (1 if skip == dl else 2)
            if len(ds) == dl + 4:
                add(cost, int(ds[:dl]), int(ds[dl:dl + 2]), int(ds[dl + 2:]))
            elif len(ds) == dl + 2:
                add(cost + 1, int(ds[:dl]), int(ds[dl:]), 0)
    return out


def bearing_azimuth(b: dict) -> float:
    q = b["decimal"]
    if b["ns"] == "N":
        return q if b["ew"] == "E" else (360 - q) % 360
    return 180 - q if b["ew"] == "E" else 180 + q


def classify(txt: str, height: float, char_h: float):
    s = normalize(txt)
    if not s:
        return "empty", None
    m = _COURSE.match(s)
    if m:
        b = parse_bearing(m.group(1))
        if b:
            return "bearing", dict(b, dist=float(m.group(2)))
    b = parse_bearing(s)
    if b:
        return "bearing", b
    m = _CID.match(s)
    if m:
        return "curve_id", f"C{int(m.group(1))}"
    if _CDATA.search(s):
        return "curve_data", s
    if re.search(r"(SF|SQ\.?FT|AC\.?|ACRES?)$", s):
        return "area", s
    if re.match(r"^LOT\d{1,3}[A-Z]?$", s):
        return "lot", s[3:]
    m = _DIST.match(s)
    if m:
        num, ft = m.groups()
        v = float(num)
        if "." in num or ft:
            if 0.5 <= v <= 5000:
                return "distance", v
        if re.match(r"^\d{1,3}[A-Z]?$", s) and height >= 1.15 * char_h:
            return "lot", s
        if re.match(r"^\d{2,4}$", s):
            return "distance", v
        return "lot", s
    return "text", s


def ocr_block(gray: np.ndarray, shears=(0.0, 0.2, 0.3)) -> tuple[str, float]:
    """Paragraph OCR of a whole text-only image (notes panels).  Tries the
    italic de-slant variants and keeps the most confident; returns
    (text, mean word confidence).  Hand-lettered notes: shear 0.3 lifts
    mean confidence ~40 -> ~60 on plat_notes."""
    best = ("", -1.0)
    for sh in shears:
        h, w = gray.shape
        x = cv2.warpAffine(gray, np.float32([[1, sh, 0], [0, 1, 0]]), (w + int(sh * h), h),
                           borderValue=255) if sh else gray
        d = pytesseract.image_to_data(x, config="--psm 6", output_type=pytesseract.Output.DICT)
        words = [(t, float(c)) for t, c in zip(d["text"], d["conf"]) if t.strip()]
        if not words:
            continue
        conf = float(np.mean([c for _, c in words]))
        if conf > best[1]:
            txt = pytesseract.image_to_string(x, config="--psm 6")
            lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
            best = ("\n".join(lines), conf)
    return best
