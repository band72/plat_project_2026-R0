"""Batch driver:  python3 -m raster2dxf.run [IN_DIR] [OUT_DIR] [--only a,b] [-j N]

Writes OUT_DIR/{dxf,png,overlay,json}/<name>.* and OUT_DIR/summary.{json,md}.
summary.json keeps the previous run's scores so each refinement tick can
see per-image regressions (a change that lowers the mean score is reverted).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed

DEFAULT_IN = "Plat/training/drawings"
DEFAULT_OUT = "Plat/training/output"


def _one(args):
    path, out = args
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    from .pipeline import process
    try:
        r = process(path, out)
        r.pop("labels", None)
        return r
    except Exception as e:  # noqa: BLE001 -- report and keep the batch going
        return dict(image=os.path.basename(path), error=f"{type(e).__name__}: {e}",
                    trace=traceback.format_exc()[-1500:])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("in_dir", nargs="?", default=DEFAULT_IN)
    ap.add_argument("out_dir", nargs="?", default=DEFAULT_OUT)
    ap.add_argument("--only", default="")
    ap.add_argument("-j", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args(argv)
    files = sorted(glob.glob(os.path.join(a.in_dir, "*.png")) + glob.glob(os.path.join(a.in_dir, "*.jpg")))
    if a.only:
        keep = set(a.only.split(","))
        files = [f for f in files if os.path.splitext(os.path.basename(f))[0] in keep]
    os.makedirs(a.out_dir, exist_ok=True)
    summ_path = os.path.join(a.out_dir, "summary.json")
    prev = {}
    if os.path.exists(summ_path):
        with open(summ_path) as f:
            old = json.load(f)
        prev = {r["image"]: r for r in old.get("images", [])}
    results = {}
    # biggest first so the long poles start early
    files.sort(key=lambda f: -os.path.getsize(f))
    with ProcessPoolExecutor(max_workers=a.j) as ex:
        futs = {ex.submit(_one, (f, a.out_dir)): f for f in files}
        for fu in as_completed(futs):
            r = fu.result()
            results[r["image"]] = r
            s = r.get("metrics", {}).get("score")
            print(f"{r['image']:45s} {'ERR ' + r['error'] if 'error' in r else s}", flush=True)
    merged = dict(prev)
    merged.update(results)
    rows = sorted(merged.values(), key=lambda r: r["image"])
    ok = [r for r in rows if "metrics" in r]
    mean = lambda k: round(sum((r["metrics"][k] or 0) for r in ok) / max(1, len(ok)), 4)
    agg = dict(n=len(rows), errors=len(rows) - len(ok),
               mean_score=mean("score"), mean_line_f1=mean("line_f1"),
               mean_label_assoc=mean("label_assoc"),
               scaled=sum(1 for r in ok if r["calibration"]["ft_per_px"]),
               # against raster2dxf/truth.json: right / wrong / abstained
               scale_truth=dict(
                   right=sum(1 for r in ok if r["metrics"].get("scale_correct") is True),
                   wrong=sum(1 for r in ok if r["metrics"].get("scale_correct") is False),
                   abstained=sum(1 for r in ok if r["metrics"].get("scale_truth")
                                 and r["metrics"].get("scale_correct") is None)))
    prev_agg = None
    if os.path.exists(summ_path):
        prev_agg = old.get("aggregate")
    for r in rows:
        p = prev.get(r["image"])
        if p and "metrics" in p and "metrics" in r:
            r["prev_score"] = p["metrics"]["score"]
    with open(summ_path, "w") as f:
        json.dump(dict(aggregate=agg, previous_aggregate=prev_agg, images=rows), f, indent=1, default=str)
    with open(os.path.join(a.out_dir, "summary.md"), "w") as f:
        f.write("# raster2dxf training-set summary\n\n")
        f.write(f"aggregate: {agg}\n\nprevious: {prev_agg}\n\n")
        f.write("| image | kind | score | prev | line F1 | assoc | scale ft/px (inl/votes) | rot | lines | arcs | labels | brg | dist | C# | QA |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            if "metrics" not in r:
                f.write(f"| {r['image']} | ERROR | {r.get('error')} |\n")
                continue
            m, c, k = r["metrics"], r["calibration"], r["kinds"]
            sc = f"{c['ft_per_px']:.4f} ({c['scale_inliers']}/{c['scale_votes']})" if c["ft_per_px"] else f"- (0/{c['scale_votes']})"
            f.write(f"| {r['image']} | {r['kind']} | {m['score']} | {r.get('prev_score', '')} | {m['line_f1']} | "
                    f"{m['label_assoc']} | {sc} | {c['rotation_deg']:.2f} ({c['rot_inliers']}/{c['rot_votes']}) | "
                    f"{r['n_lines']} | {r['n_arcs']} | {r['n_labels']} | {k['bearing']} | {k['distance']} | "
                    f"{k['curve_id']} | {len(r['qa'])} |\n")
    print("AGG", agg, "PREV", prev_agg)


if __name__ == "__main__":
    main()
