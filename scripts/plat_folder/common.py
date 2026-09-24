"""Shared helpers for the faithful Plat/ folder reconstructions.

Every build_*.py in this package reconstructs ONE plat sheet from Plat/*.pdf
using only dimensions read off the scan, writes its outputs under
Plat/output/<plat_id>/, and records a metrics.json that
scripts/plat_folder/scorecard.py aggregates.  Anything not printed on the
plat is recorded in metrics["assumptions"] -- never silently invented.
"""
import json
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT_ROOT = os.path.join(ROOT, "Plat", "output")
SQFT_PER_ACRE = 43560.0


def out_dir(plat_id):
    d = os.path.join(OUT_ROOT, plat_id)
    os.makedirs(d, exist_ok=True)
    return d


def shoelace(pts):
    """Unsigned area of a closed ring of (E, N) points."""
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def fit_circle(pts):
    """Algebraic (Kasa) least-squares circle through (x, y) points -> (cx, cy, r)."""
    import numpy as np
    A = np.array([[x, y, 1.0] for x, y in pts])
    b = np.array([-(x * x + y * y) for x, y in pts])
    (D, E, F), *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = -D / 2, -E / 2
    return cx, cy, math.sqrt(cx * cx + cy * cy - F)


def arc_points(cx, cy, r, p0, p1, n=48):
    """Densify the minor arc of circle (cx, cy, r) from p0 to p1 (both ~on the circle)."""
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    return [(cx + r * math.cos(a0 + d * i / n), cy + r * math.sin(a0 + d * i / n)) for i in range(n + 1)]


def write_dxf(path, layers, rings, lines, texts):
    """rings/lines: [(layer, [(E, N), ...])]; texts: [(layer, (E, N), str, height)]."""
    from engine.dxf_writer import DXFWriter
    dxf = DXFWriter()
    for name, color, lt in layers:
        dxf.add_layer(name, color, lt)
    for layer, pts in rings:
        dxf.polyline([(n, e) for e, n in pts], layer, closed=True)
    for layer, pts in lines:
        dxf.polyline([(n, e) for e, n in pts], layer, closed=False)
    for layer, (e, n), s, h in texts:
        dxf.text((n, e), s, h, layer, halign=1, valign=2)
    dxf.save(path)


def render_png(path, title, rings, lines, texts, flagged=()):
    fig, ax = plt.subplots(figsize=(14, 14 * 0.75))
    for layer, pts in lines:
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color="#888", lw=0.8, ls="-." if "ROW" in layer else "-")
    for layer, pts in rings:
        xs, ys = zip(*(pts + pts[:1]))
        ax.plot(xs, ys, color="#c00" if layer in flagged else "#111", lw=1.2 if layer == "BOUNDARY" else 0.8)
    for _layer, (e, n), s, h in texts:
        ax.text(e, n, s, ha="center", va="center", fontsize=max(5, h / 3))
    ax.set_aspect("equal")
    ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def save_metrics(plat_id, metrics):
    path = os.path.join(out_dir(plat_id), "metrics.json")
    with open(path, "w") as f:
        json.dump(metrics, f, indent=2)
    return path
