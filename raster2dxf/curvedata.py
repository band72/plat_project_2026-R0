"""Curve-data blocks ("℄ Curve Data  Δ=36°20'00"  T=107.31'  R=327.01'").

Plats label curves either by number (C1 → curve table) or with a stacked
curve-data block beside the curve.  OCR of the latter is fragmentary and
misreads the keys (Δ → A / 4 / D, "=" → > : .), so:
  1. parse_fields: tolerant KEY value extraction from each label
  2. group_blocks: fields within ~4 char heights form one block
  3. solve: fill/verify with circular-curve identities
       T = R·tan(Δ/2)   L = R·Δ   CH = 2R·sin(Δ/2)
     -- a value derived from two others is marked derived, and a block is
     "consistent" when an over-determined identity holds within 1%
  4. attach: block → nearest arc (|dist(c, centre) − r| ≤ 8 char_h)
"""
from __future__ import annotations

import math
import re

import cv2
import numpy as np

_DELTA = re.compile(r"(?:^|[^A-Z])(?:Δ|A|D|4|DELTA)\s*[=>:.\-_]*\s*(\d{1,3})\s*[°O*º]\s*(\d{1,2})?\s*['’`°]?\s*(\d{1,2})?")
_NUMF = r"(\d{1,5}(?:\s?[._]\s?\d{1,2})?)"
# R's key is often misread (&, B, P, 8) -- only accepted with the ".=" /
# "=" punctuation that follows keys in a curve-data block
_KEYS = {"R": re.compile(r"(?:^|[^A-Z])(?:R|RAD|RADIUS|[&BP8](?=\s*\.?\s*=))\s*[=>:.\-_]+\s*" + _NUMF),
         "T": re.compile(r"(?:^|[^A-Z])(?:T|TAN)\s*[=>:.\-_]+\s*" + _NUMF),
         "L": re.compile(r"(?:^|[^A-Z])(?:L|ARC)\s*[=>:.\-_]+\s*" + _NUMF),
         "CH": re.compile(r"(?:^|[^A-Z])(?:CH|CHD|CHORD)\s*[=>:.\-_]+\s*" + _NUMF)}


def parse_fields(text: str) -> dict:
    """{'delta': deg, 'R': ft, 'T': ft, 'L': ft, 'CH': ft} found in a string."""
    s = " " + text.upper().replace(",", ".") + " "
    out = {}
    m = _DELTA.search(s)
    if m:
        d, mi, se = m.groups()
        d = int(d)
        mi = int(mi) if mi else 0
        se = int(se) if se else 0
        if 0 < d < 180 and mi < 60 and se < 60:
            out["delta"] = d + mi / 60 + se / 3600
    for k, rx in _KEYS.items():
        m = rx.search(s)
        if m:
            try:
                v = float(m.group(1).replace(" ", "").replace("_", "."))
            except ValueError:
                continue
            if v > 0:
                out[k] = v
    return out


def group_blocks(labels, char_h: float) -> list[dict]:
    """Group labels carrying curve fields into blocks (single-link, 4 char_h)."""
    items = [(l, parse_fields(l.text)) for l in labels if l.text]
    items = [(l, f) for l, f in items if f]
    parent = list(range(len(items)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if np.hypot(*(items[i][0].center - items[j][0].center)) <= 4 * char_h:
                parent[find(i)] = find(j)
    blocks: dict = {}
    for k, (l, f) in enumerate(items):
        b = blocks.setdefault(find(k), dict(labels=[], fields={}))
        b["labels"].append(l.id)
        for key, v in f.items():
            b["fields"].setdefault(key, v)
    out = []
    for b in blocks.values():
        cs = np.array([next(l.center for l in labels if l.id == i) for i in b["labels"]])
        b["center"] = cs.mean(axis=0)
        b.update(solve(b["fields"]))
        out.append(b)
    return out


def solve(f: dict) -> dict:
    """Complete a curve from any two of (Δ, R, T, L) and check the rest."""
    D = math.radians(f["delta"]) if "delta" in f else None
    R, T, L = f.get("R"), f.get("T"), f.get("L")
    derived = {}
    if D and not R:
        if T:
            R = T / math.tan(D / 2); derived["R"] = R
        elif L:
            R = L / D; derived["R"] = R
    if R and not D:
        if L:
            D = L / R; derived["delta"] = math.degrees(D)
        elif T:
            D = 2 * math.atan(T / R); derived["delta"] = math.degrees(D)
    checks = []
    if R and D:
        if T and "R" not in derived and "delta" not in derived:
            checks.append(abs(T / (R * math.tan(D / 2)) - 1))
        if L and "R" not in derived and "delta" not in derived:
            checks.append(abs(L / (R * D) - 1))
        if not T:
            derived["T"] = R * math.tan(D / 2)
        if not L:
            derived["L"] = R * D
        derived.setdefault("CH", 2 * R * math.sin(D / 2))
    consistent = bool(checks) and max(checks) <= 0.01
    return dict(R=R, delta=math.degrees(D) if D else None, derived={k: round(v, 3) for k, v in derived.items()},
                consistent=consistent, check=None if not checks else round(max(checks), 4))


def attach(blocks, arcs, char_h: float) -> None:
    for b in blocks:
        best = None
        for a in arcs:
            d = abs(float(np.hypot(*(b["center"] - a.center))) - a.r)
            if d <= 8 * char_h and (best is None or d < best[0]):
                best = (d, a.id)
        b["arc"] = None if best is None else best[1]


# ---------------------------------------------------------- dewarped re-read
# ℄ data sits beside R/W arcs at R ± ~30 ft, long flat arcs fit loosely and
# hand drafting is ~5% to scale: geometry can't pin R to a few %, but it
# cleanly rejects digit flips (page1 Sands: 459 is 13% off the drawn arc,
# a 1->4 flip giving 1374 is 238% off)
GEO_TOL = 0.25
MAX_ANCHORS = 6


def unwrap(gray, center, r0, r1, t0, t1, ra, outward_up: bool, forward: bool):
    """Polar unwrap of the annulus sector (r0..r1, t0..t1) about `center`
    into a straight strip: columns follow the arc (1 px ≈ 1 px at radius
    ra), rows follow radius, oriented so the text reads upright."""
    rs = np.arange(r0, r1, 1.0)
    ts = np.linspace(t0, t1, max(8, int((t1 - t0) * ra)))
    if not forward:
        ts = ts[::-1]
    if outward_up:
        rs = rs[::-1]
    R, Tt = np.meshgrid(rs, ts, indexing="ij")
    mx = (center[0] + R * np.cos(Tt)).astype(np.float32)
    my = (center[1] + R * np.sin(Tt)).astype(np.float32)
    return cv2.remap(gray, mx, my, cv2.INTER_LINEAR, borderValue=255)


def _vote(readings):
    """Per-field majority over window readings (values rounded to 0.01)."""
    from collections import Counter
    out = {}
    for key in ("delta", "R", "T", "L", "CH"):
        vals = [round(f[key], 2) for f in readings if key in f]
        if vals:
            v, n = Counter(vals).most_common(1)[0]
            out[key] = v
    return out


def dewarp_blocks(gray, labels, arcs, char_h: float, ft_per_px) -> list[dict]:
    """Re-read "℄ Curve Data" blocks by unwrapping the text along the
    nearest drawn arc (rotated rectangles failed: arc-following text read
    right at 14.0° and wrong at 13.8°).  Anchored on OCR'd "Curve" titles;
    several windows either side of the arc, per-field vote, then kept only
    if verified by identity (over-determined & consistent) or by the drawn
    arc (derived/read R within GEO_TOL of arc radius × ft/px)."""
    from .text import normalize, ocr_block
    out = []
    # anchors: "Curve" titles first, then curve-field fragments ("A= 269",
    # "R.=4", "T.2") -- capped, and one anchor per 12 char heights
    frag = re.compile(r"^[\(\[]?[ΔA4DRTL&]\s*[.:]?\s*[=>]")
    cand = [l for l in labels if l.text and "CURV" in normalize(l.text)] + \
           [l for l in labels if l.text and frag.match(normalize(l.text))]
    anchors = []
    for l in cand:
        if all(np.hypot(*(l.center - m.center)) > 12 * char_h for m in anchors):
            anchors.append(l)
    for a in anchors[:MAX_ANCHORS]:
        near = [x for x in arcs if x.r >= 5 * char_h and
                abs(float(np.hypot(*(a.center - x.center))) - x.r) <= 8 * char_h]
        if not near:
            continue
        arc = min(near, key=lambda x: abs(float(np.hypot(*(a.center - x.center))) - x.r))
        c = arc.center
        v = a.center - c
        ra = float(np.hypot(*v))
        th = math.atan2(v[1], v[0])
        rr = math.radians(a.angle)
        u = np.array([math.cos(rr), math.sin(rr)])          # reading direction
        up = np.array([math.sin(rr), -math.cos(rr)])        # text "up" (y down)
        tangent = np.array([-math.sin(th), math.cos(th)])   # d/dθ at the anchor
        forward = float(u @ tangent) >= 0
        outward_up = float(up @ (v / ra)) > 0
        reads = []
        for dr in ((-6, 2), (-7, 1), (-2, 6), (-1, 7)):
            for back, ahead in ((8, 16), (6, 14)):
                t0, t1 = (th - back * char_h / ra, th + ahead * char_h / ra) if forward else \
                         (th - ahead * char_h / ra, th + back * char_h / ra)
                img = unwrap(gray, c, ra + dr[0] * char_h, ra + dr[1] * char_h, t0, t1, ra,
                             outward_up, forward)
                txt, conf = ocr_block(img)
                f = parse_fields(txt.replace("\n", " "))
                if f:
                    reads.append(f)
        if not reads:
            continue
        f = _vote(reads)
        if len(f) < 2:
            continue
        sol = solve(f)
        if not sol["consistent"] and "R" in f and "delta" in f:
            # R and Δ read: a T / L disagreeing > 5% with them is a misread
            D = math.radians(f["delta"])
            want = {"T": f["R"] * math.tan(D / 2), "L": f["R"] * D, "CH": 2 * f["R"] * math.sin(D / 2)}
            f = {k: v for k, v in f.items() if k not in want or abs(v / want[k] - 1) <= 0.05}
            sol = solve(f)
        how = "identity" if sol["consistent"] else None
        if not how and sol["R"] and ft_per_px:
            if abs(sol["R"] / (arc.r * ft_per_px) - 1) <= GEO_TOL:
                how = "arc"
        if how:
            out.append(dict(labels=[a.id], fields=f, center=a.center.copy(), source="dewarp",
                            verified_by=how, n_reads=len(reads), arc=arc.id, **sol))
    return out
