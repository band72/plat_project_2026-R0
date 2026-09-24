"""One image -> DXF + PNG render + overlay PNG + JSON report, and metrics."""
from __future__ import annotations

import json
import os
import time

import cv2
import numpy as np

from . import associate as A
from . import curvedata as CD
from . import export as X
from . import linework as LW
from . import text as T
from .preprocess import prepare


def reference_lines(prep, char_h):
    """Independent linework reference: long straight Hough segments on the
    raw ink skeleton (they cannot be text: >= 4 char heights long).  Used
    only for scoring so the metric is not circular with our own
    text/linework split."""
    from skimage.morphology import skeletonize
    sk = (skeletonize(prep.ink > 0) * 255).astype(np.uint8)
    L = int(max(4 * char_h, 30))
    segs = cv2.HoughLinesP(sk, 1, np.pi / 720, threshold=max(20, L // 2), minLineLength=L,
                           maxLineGap=max(2, int(prep.stroke_w)))
    ref = np.zeros_like(sk)
    if segs is not None:
        for x1, y1, x2, y2 in segs[:, 0]:
            cv2.line(ref, (x1, y1), (x2, y2), 255, 1)
    return cv2.bitwise_and(ref, cv2.dilate(sk, np.ones((3, 3), np.uint8)))


_TRUTH = None
_TRUTH_MON: dict = {}
_TRUTH_CURVES: dict = {}
NO_SCALE = "none"          # truth says the image has no dimensions to scale by


def _truth_scale(image_name: str):
    """Ground-truth ft/px from raster2dxf/truth.json (None if unknown)."""
    global _TRUTH
    global _TRUTH_MON
    if _TRUTH is None:
        p = os.path.join(os.path.dirname(__file__), "truth.json")
        raw = json.load(open(p)) if os.path.exists(p) else {}
        _TRUTH = raw.get("scales", {})
        _TRUTH_MON = raw.get("monuments", {})
        global _TRUTH_CURVES
        _TRUTH_CURVES = raw.get("curve_catalog", {})
    t = _TRUTH.get(image_name)
    if not t:
        return None
    return NO_SCALE if t.get("no_scale") else t["ft_per_px"]


def _truth_tol(image_name: str) -> float:
    _truth_scale(image_name)
    return (_TRUTH.get(image_name) or {}).get("tol", 0.03)


def _truth_monuments(image_name: str):
    _truth_scale(image_name)
    return _TRUTH_MON.get(image_name)


def monument_f1(found, truth, shape, tol=8.0, edge=20.0):
    """F1 of detected monument centres vs hand-verified ones (match within
    tol px); anything within `edge` px of the border is ignored both ways
    (symbols cut by the crop edge)."""
    h, w = shape[:2]
    inside = lambda p: edge <= p[0] <= w - edge and edge <= p[1] <= h - edge
    f = [np.asarray(p, float) for p in found if inside(p)]
    t = [np.asarray(p, float) for p in truth if inside(p)]
    used, tp = set(), 0
    for p in f:
        k = next((i for i, q in enumerate(t) if i not in used and np.hypot(*(p - q)) <= tol), None)
        if k is not None:
            used.add(k)
            tp += 1
    prec = tp / len(f) if f else (1.0 if not t else 0.0)
    rec = tp / len(t) if t else 1.0
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def curve_score(blocks, image_name: str):
    """(right, wrong) of dewarped curve reads vs the plat's curve catalog;
    None if the image isn't covered by the catalog."""
    _truth_scale(image_name)
    cat = _TRUTH_CURVES
    if not cat or image_name not in cat.get("images", []):
        return None
    right = wrong = 0
    for b in blocks:
        if b.get("source") != "dewarp" or not b.get("R"):
            continue
        ok = False
        for c in cat["curves"].values():
            if abs(b["R"] / c["R"] - 1) <= 0.01:
                t = b["fields"].get("T")
                ok = t is None or abs(t / c["T"] - 1) <= 0.01
                if ok:
                    break
        right += ok
        wrong += not ok
    return right, wrong


def metrics(prep, linework, labels, tmask, cal, char_h, blocks=()) -> dict:
    sw = prep.stroke_w
    vec = T.rasterize(linework, prep.ink.shape, thick=1)
    tol = max(2, int(round(1.5 * sw)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tol + 1, 2 * tol + 1))
    ref = reference_lines(prep, char_h) > 0
    recall = float((cv2.dilate(vec, k)[ref] > 0).mean()) if ref.any() else 1.0
    vsel = vec > 0
    # nothing drawn is right when the independent reference finds no lines
    precision = float((cv2.dilate(prep.ink, k)[vsel] > 0).mean()) if vsel.any() else \
        (1.0 if not ref.any() else 0.0)
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    dims = [l for l in labels if l.kind in ("bearing", "distance")]
    assoc = sum(1 for l in dims if l.assoc) / len(dims) if dims else None
    read = [l for l in labels if l.text]
    classified = sum(1 for l in read if l.kind not in ("text", "empty")) / len(read) if read else 0.0
    sc = None
    truth = _truth_scale(prep.name)
    f = cal["ft_per_px"]
    correct = None
    if truth == NO_SCALE:
        correct = not f
        sc = 1.0 if correct else 0.0
    elif truth:
        # ground truth known: reward being right, punish being wrong, and
        # rate "no scale reported" in between (honest abstention)
        correct = None if not f else abs(f / truth - 1) <= _truth_tol(prep.name)
        sc = 0.5 if not f else (1.0 if correct else 0.0)
    elif cal["ft_per_px"]:
        sc = cal["scale_inliers"] / max(1, cal["scale_votes"])
    score = 0.55 * f1 + 0.2 * (assoc if assoc is not None else f1) + 0.1 * classified \
        + 0.15 * (sc if sc is not None else (0.5 if not dims else 0.0))
    mon_truth = _truth_monuments(prep.name)
    mon = None
    if mon_truth is not None:
        mon = monument_f1([m.center for m in getattr(linework, "monuments", [])], mon_truth, prep.ink.shape)
        score = 0.9 * score + 0.1 * mon
    cs = curve_score(blocks, prep.name)
    if cs and sum(cs):
        # wrong curves cost, right ones earn; abstaining is neutral
        score = 0.95 * score + 0.05 * (cs[0] / sum(cs))
    return dict(scale_truth=truth, scale_correct=correct, monument_f1=None if mon is None else round(mon, 4),
                curves_right=None if cs is None else cs[0], curves_wrong=None if cs is None else cs[1],
                line_recall=round(recall, 4), line_precision=round(precision, 4),
                line_f1=round(f1, 4), label_assoc=None if assoc is None else round(assoc, 4),
                label_classified=round(classified, 4),
                scale_consistency=None if sc is None else round(sc, 4),
                score=round(score, 4))


def process(path: str, out_dir: str) -> dict:
    t0 = time.time()
    name = os.path.splitext(os.path.basename(path))[0]
    prep = prepare(path)
    char_h = T.estimate_char_height(prep.ink, prep.stroke_w)
    lw = LW.extract(prep.ink, prep.stroke_w, char_h, prep.color)
    tmask = T.text_mask(prep.text_ink, lw, prep.stroke_w)
    labels = T.cluster_labels(tmask, char_h, prep.stroke_w, lw)
    # distances printed on the line cut it in two -- rejoin before calibrating
    boxes = [(l.center, l.angle, l.width, l.height) for l in labels]
    LW.bridge_label_gaps(lw, boxes, char_h, prep.stroke_w)
    # monuments: split courses at them so each lot course ends at its corner
    lw.monuments = LW.find_monuments(prep.ink, lw.lines, char_h, prep.stroke_w, boxes)
    if lw.monuments:
        lw.lines = LW.split_at_points(lw.lines, [m.center for m in lw.monuments],
                                      max(2.0, prep.stroke_w))
    # OCR on the image with linework whited out so lines don't become glyphs
    clean = prep.gray.copy()
    lwmask = T.rasterize(lw, prep.ink.shape, thick=max(2, int(round(prep.stroke_w * 1.6)) + 2))
    clean[(lwmask > 0) & (tmask == 0)] = 255
    T.ocr_labels(clean, labels, char_h)
    # curve-data blocks (Δ / R / T / L stacked beside a curve)
    blocks = CD.group_blocks(labels, char_h)
    CD.attach(blocks, lw.arcs, char_h)
    # single-field "blocks" are too weak to re-kind (a stray "4°" is not a Δ)
    in_block = {i for b in blocks if len(b["fields"]) >= 2 for i in b["labels"]}
    for l in labels:
        if l.id in in_block and l.kind in ("text", "empty", "lot"):
            l.kind = "curve_data"
    A.mark_table_cells(labels, lw, char_h)
    cal = A.reconcile(labels, lw, char_h,
                      A.SCAN_SCALE_TOL if prep.kind == "scan" else A.DIGITAL_SCALE_TOL)
    table = A.parse_curve_rows(labels, char_h)
    curve_links = A.link_curve_ids(labels, lw, table, cal["ft_per_px"])
    # "℄ Curve Data" blocks: unwrap along the arc, re-read, verify
    dw = CD.dewarp_blocks(prep.gray, labels, lw.arcs, char_h, cal["ft_per_px"])
    if dw:
        blocks = [b for b in blocks if min(np.hypot(*(b["center"] - d["center"])) for d in dw)
                  > 6 * char_h] + dw
    # text-only images (notes panels): paragraph OCR -> MTEXT
    notes = None
    if not lw.lines and not lw.arcs:
        notes = T.ocr_block(prep.gray)
    for d in ("dxf", "png", "overlay", "json"):
        os.makedirs(os.path.join(out_dir, d), exist_ok=True)
    doc = X.write_dxf(os.path.join(out_dir, "dxf", name + ".dxf"), prep, lw, labels, cal, table, char_h,
                      notes=notes, curve_blocks=blocks)
    X.render_png(doc, os.path.join(out_dir, "png", name + ".png"))
    X.render_overlay(os.path.join(out_dir, "overlay", name + ".png"), prep, lw, labels)
    m = metrics(prep, lw, labels, tmask, cal, char_h, blocks)
    rep = dict(
        image=os.path.basename(path), kind=prep.kind, size=list(prep.ink.shape[:2][::-1]),
        stroke_w=round(prep.stroke_w, 2), char_h=round(char_h, 1),
        n_monuments=len(lw.monuments), n_lines=len(lw.lines), n_dashed=sum(l.dashed for l in lw.lines), n_arcs=len(lw.arcs),
        n_labels=len(labels), n_verified=sum(l.verified for l in labels),
        kinds={k: sum(1 for l in labels if l.kind == k) for k in
               ("bearing", "distance", "curve_id", "curve_data", "lot", "area", "table", "text", "empty")},
        calibration={k: v for k, v in cal.items() if k != "qa"}, qa=cal["qa"],
        curve_table=table, curve_blocks=[{k: v for k, v in b.items() if k != 'center'} | {'center': [round(float(x), 1) for x in b['center']]} for b in blocks],
        curve_links=curve_links, notes=notes, metrics=m, seconds=round(time.time() - t0, 1),
        labels=[dict(id=l.id, text=l.text, kind=l.kind, conf=round(l.conf, 1),
                     center=[round(float(v), 1) for v in l.center], angle=round(l.angle, 1),
                     assoc=l.assoc or None) for l in labels],
    )
    with open(os.path.join(out_dir, "json", name + ".json"), "w") as f:
        json.dump(rep, f, indent=1, default=str)
    return rep
