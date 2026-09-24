"""Score a vision extraction of Beachwood Unit Two Sheet 2 against the checked lots.

    python3 eval/score_extraction.py run   <plat.pdf> --page 2 --out eval/run.json   # calls the Claude API (costs money)
    python3 eval/score_extraction.py score eval/run.json                              # offline scoring

Metrics (per lot that exists in the ground truth):
  found       - the extraction has a lot with this block/lot number
  value_prec  - share of extracted distances that equal (within 0.01') one of the true course lengths of that lot.
                A misread digit (e.g. 194.90 for 134.90) lowers this -- it is the main accuracy number.
  value_rec   - share of true course lengths that were extracted. A LOWER BOUND: the truth includes derived segments
                (straights cut back to a curve P.C.) that are never printed.
  closes      - lots whose extracted ring closes in the deterministic check (after repair, if run).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
TRUTH = os.path.join(os.path.dirname(__file__), "beachwood_sheet2_truth.json")


def score(run: dict, truth: dict) -> dict:
    ext = {(l["block"].strip(), l["lot"].strip()): l for l in run["lots"]}
    rows, found, prec_n, prec_d, rec_n, rec_d, closes = [], 0, 0, 0, 0, 0, 0
    for t in truth["lots"]:
        key = (t["block"], t["lot"])
        e = ext.get(key)
        true_vals = [c["distance"] for c in t["courses"]]
        if e is None:
            rows.append({"block": t["block"], "lot": t["lot"], "found": False})
            rec_d += len(true_vals)
            continue
        found += 1
        got = [c["distance"] for c in e["courses"] if c["distance"]]
        ok = [v for v in got if any(abs(v - tv) <= 0.011 for tv in true_vals)]
        hit = [tv for tv in true_vals if any(abs(tv - v) <= 0.011 for v in got)]
        prec_n, prec_d = prec_n + len(ok), prec_d + len(got)
        rec_n, rec_d = rec_n + len(hit), rec_d + len(true_vals)
        closes += e.get("check", {}).get("status") == "PASS"
        rows.append({"block": t["block"], "lot": t["lot"], "found": True, "wrong_values": [v for v in got if v not in ok],
                     "check": e.get("check", {}).get("status")})
    n = len(truth["lots"])
    return {"lots_in_truth": n, "found": found, "found_pct": round(100 * found / n, 1),
            "value_precision_pct": round(100 * prec_n / max(prec_d, 1), 1),
            "value_recall_lower_bound_pct": round(100 * rec_n / max(rec_d, 1), 1),
            "lots_closing": closes, "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("pdf")
    r.add_argument("--page", type=int, default=2)
    r.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "run.json"))
    r.add_argument("--no-repair", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("run_json")
    a = ap.parse_args()
    if a.cmd == "run":
        from engine.vision_extract import extract_pdf_page
        res = extract_pdf_page(a.pdf, a.page, repair=not a.no_repair)
        json.dump(res, open(a.out, "w"), indent=1)
        print(f"wrote {a.out}  ({res['tiles']} tiles, {len(res['lots'])} lots)")
        a.run_json = a.out
    rep = score(json.load(open(a.run_json)), json.load(open(TRUTH)))
    print(json.dumps({k: v for k, v in rep.items() if k != "rows"}, indent=1))
    bad = [r for r in rep["rows"] if r.get("wrong_values")]
    for r in bad[:25]:
        print(f"  block {r['block']} lot {r['lot']}: values not in truth {r['wrong_values']}")


if __name__ == "__main__":
    main()
