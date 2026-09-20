"""
ticks.py -- find curve stations (P.C., P.T., P.R.C., P.C.C.) on a boundary
by detecting the surveyor's TICK MARKS.

Domain insight (from the user): small curves are hard to spot because the
arc barely departs from a straight line at plat scale, but the draftsman
ALWAYS marks the station -- a short stroke drawn across the boundary,
roughly perpendicular to it, making a little cross on the line, usually
with a P.C./P.T. label nearby.

That makes the station findable even when the curvature itself is invisible:
we are not looking for the curve, we are looking for the TICK.

Detection: a tick is a SHORT segment whose midpoint lies ON a long boundary
segment and whose direction is roughly PERPENDICULAR to it. Both conditions
matter -- lot side lines also meet the boundary perpendicularly, so length
is what separates a 3-5 ft tick from a 120 ft side line.
"""
from __future__ import annotations
import math


def _seg_len(s):
    return math.hypot(s[2] - s[0], s[3] - s[1])


def _seg_az(s):
    return math.degrees(math.atan2(s[3] - s[1], s[2] - s[0])) % 180


def _midpoint(s):
    return ((s[0] + s[2]) / 2.0, (s[1] + s[3]) / 2.0)


def _dist_pt_seg(pn, pe, s):
    n1, e1, n2, e2 = s
    dn, de = n2 - n1, e2 - e1
    L2 = dn * dn + de * de
    if L2 < 1e-12:
        return math.hypot(pn - n1, pe - e1), 0.0
    t = max(0.0, min(1.0, ((pn - n1) * dn + (pe - e1) * de) / L2))
    cn, ce = n1 + t * dn, e1 + t * de
    return math.hypot(pn - cn, pe - ce), t


def find_ticks(segments, boundary, min_len=1.0, max_len=8.0,
               perp_tol_deg=25.0, on_line_tol=1.5):
    """Find tick marks sitting on `boundary` (a single long segment).

    min_len/max_len are in PLAT FEET. Defaults target the 2-6 ft strokes
    typical at 1"=50'. Raising max_len starts catching real lot side lines;
    that is the main failure mode, so the caller should sanity-check the
    count against how many stations are plausible.
    """
    b_az = _seg_az(boundary)
    b_len = _seg_len(boundary)
    hits = []
    for s in segments:
        L = _seg_len(s)
        if not (min_len <= L <= max_len):
            continue
        d_az = abs(_seg_az(s) - b_az)
        d_az = min(d_az, 180 - d_az)
        if abs(d_az - 90.0) > perp_tol_deg:
            continue
        mn, me = _midpoint(s)
        dist, t = _dist_pt_seg(mn, me, boundary)
        if dist > on_line_tol:
            continue
        hits.append(dict(station_ft=t * b_len, t=t, offset=dist,
                         length=L, perp_err=abs(d_az - 90.0),
                         seg=s, point=(boundary[0] + t * (boundary[2] - boundary[0]),
                                       boundary[1] + t * (boundary[3] - boundary[1]))))
    hits.sort(key=lambda h: h["station_ft"])
    # merge ticks that are effectively the same mark found twice
    merged = []
    for h in hits:
        if merged and abs(h["station_ft"] - merged[-1]["station_ft"]) < 1.0:
            continue
        merged.append(h)
    return merged


def stations_to_segments(ticks, boundary_length, include_ends=True):
    """Turn detected tick stations into the run lengths between them --
    i.e. the candidate per-lot or per-curve segment lengths along the
    boundary, which is what gets compared against the recorded table."""
    st = [t["station_ft"] for t in ticks]
    if include_ends:
        st = [0.0] + st + [boundary_length]
    st = sorted(set(round(x, 3) for x in st))
    return [(st[i], st[i + 1], st[i + 1] - st[i]) for i in range(len(st) - 1)]


def match_runs_to_table(runs, table_lengths, tol=1.0):
    """Compare detected runs against recorded lengths (e.g. curve arc
    lengths C195..C201, or a row of lot frontages).

    Returns per-run best match so the caller can see whether the tick
    spacing actually reproduces the recorded subdivision -- the whole point
    of detecting ticks is to tie drawn stations to recorded values."""
    out = []
    for (a, b, length) in runs:
        best, best_d = None, None
        for name, L in table_lengths.items():
            d = abs(L - length)
            if best_d is None or d < best_d:
                best, best_d = name, d
        out.append(dict(start=a, end=b, detected=length,
                        match=best, recorded=table_lengths.get(best),
                        diff=best_d, ok=(best_d is not None and best_d <= tol)))
    return out


def scan_boundary_profile(mask, boundary_px, step_px=2, probe_min=6,
                          probe_max=22, ink_frac=0.45):
    """Walk a boundary in PIXEL space and classify what attaches at each
    station, by probing perpendicular to the line on BOTH sides.

    This replaces Hough for short marks. Ticks are attached to the
    boundary's own connected component, so they cannot be isolated as
    separate components, and they are far too short to survive the
    minLineLength a clean vectorization needs. Probing sidesteps both
    problems.

    Discriminator (the useful part):
        ink on BOTH sides  -> TICK  (a stroke drawn ACROSS the line, i.e.
                              a curve station: P.C./P.T./P.R.C.)
        ink on ONE side    -> JUNCTION (a lot side line, easement, or any
                              line meeting the boundary and stopping)
        ink on neither     -> plain boundary
    """
    import numpy as np
    x1, y1, x2, y2 = boundary_px
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L < 1:
        return []
    ux, uy = dx / L, dy / L
    px, py = -uy, ux                      # perpendicular unit
    H, W = mask.shape
    out = []
    n_steps = int(L // step_px)
    for k in range(n_steps + 1):
        s = k * step_px
        cx, cy = x1 + ux * s, y1 + uy * s
        sides = []
        for sign in (+1, -1):
            hits = 0
            total = 0
            for r in range(probe_min, probe_max + 1):
                sx = int(round(cx + px * r * sign))
                sy = int(round(cy + py * r * sign))
                if 0 <= sx < W and 0 <= sy < H:
                    total += 1
                    if mask[sy, sx] > 0:
                        hits += 1
            sides.append(hits / total if total else 0.0)
        both = sides[0] >= ink_frac and sides[1] >= ink_frac
        one = (sides[0] >= ink_frac) != (sides[1] >= ink_frac)
        out.append(dict(station_px=s, pos=(cx, cy),
                        left=sides[0], right=sides[1],
                        kind="TICK" if both else ("JUNCTION" if one else "-")))
    return out


def cluster_stations(profile, kind, min_gap_px=8):
    """Collapse consecutive same-kind samples into single stations."""
    runs = []
    cur = None
    for p in profile:
        if p["kind"] == kind:
            if cur is None:
                cur = [p]
            elif p["station_px"] - cur[-1]["station_px"] <= min_gap_px:
                cur.append(p)
            else:
                runs.append(cur); cur = [p]
        else:
            if cur is not None:
                runs.append(cur); cur = None
    if cur is not None:
        runs.append(cur)
    return [dict(station_px=sum(q["station_px"] for q in r) / len(r),
                 width_px=r[-1]["station_px"] - r[0]["station_px"] + 1,
                 n=len(r)) for r in runs]


def find_monuments(gray, region=None, min_r=4, max_r=14, param2=22):
    """Find circled monument symbols (P.R.M. / P.C.P.) via Hough circles.

    Monuments are the strongest anchors on a plat: they mark points that
    are RECORDED, not derived. Anchoring a derived station sequence to a
    monument beats any distance-threshold filter, because a monument is a
    real surveyed point rather than a guess about which detection is noise.

    NOTE: naive Hough circle detection on a full plat sheet returns many
    false positives (the letter 'O' is the main offender -- measured 166 on
    one sheet). Always restrict `region` to a boundary corridor, and treat
    results as CANDIDATES to be confirmed against an expected station.
    """
    import cv2
    img = gray if region is None else gray[region[1]:region[1]+region[3],
                                           region[0]:region[0]+region[2]]
    circles = cv2.HoughCircles(img, cv2.HOUGH_GRADIENT, dp=1, minDist=20,
                               param1=80, param2=param2,
                               minRadius=min_r, maxRadius=max_r)
    out = []
    if circles is not None:
        ox, oy = (region[0], region[1]) if region else (0, 0)
        for cx, cy, r in circles[0]:
            out.append(dict(x=float(cx) + ox, y=float(cy) + oy, r=float(r)))
    return out


def anchor_stations(stations_ft, stated_total=None, anchors_ft=None,
                    anchor_tol=4.0, total_tol=3.0):
    """Select the station subset that is CONSISTENT WITH RECORDED FACTS,
    instead of filtering detections by isolated distance thresholds.

    Threshold filtering failed repeatedly (three tolerance settings tried,
    none converged) because it judges each detection in isolation. A
    station sequence is not right or wrong individually -- it is right if
    the WHOLE sequence reproduces something recorded: the stated front run,
    or a monument at a known station.

    Returns (kept_stations, report).
    """
    st = sorted(stations_ft)
    report = {"input": len(st)}

    # snap to monument anchors first: any detection near a recorded
    # monument station is trusted and never dropped
    anchored = set()
    if anchors_ft:
        for a in anchors_ft:
            near = [s for s in st if abs(s - a) <= anchor_tol]
            if near:
                anchored.add(min(near, key=lambda s: abs(s - a)))
    report["anchored"] = len(anchored)

    if stated_total is None:
        return st, report

    # choose the contiguous subset whose span best matches the stated run
    best, best_err = st, None
    for i in range(len(st)):
        for j in range(i + 1, len(st) + 1):
            subset = st[i:j]
            if anchored and not anchored.issubset(set(subset)):
                continue
            span = subset[-1] if subset else 0.0
            err = abs(span - stated_total)
            if best_err is None or err < best_err:
                best, best_err = subset, err
    report["span_error"] = best_err
    report["kept"] = len(best)
    report["accepted"] = best_err is not None and best_err <= total_tol
    return best, report
