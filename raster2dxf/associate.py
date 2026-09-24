"""Label -> geometry association, scale & rotation calibration, curve tables.

Scale: every distance label that sits parallel to a straight line piece
votes value_ft / length_px; the densest +/-1.5% cluster of votes wins.
Rotation (basis of bearings): each bearing label votes the angle between
the line's image azimuth and its written bearing; the mode is the
rotation that turns the drawing to grid north.  Both calibrations then
flag labels that disagree with the measured geometry (QA layer).
"""
from __future__ import annotations

import itertools
import math
import re

import numpy as np

from .text import apply_alt, bearing_azimuth, bearing_readings, normalize


def _line_frame(l):
    d = l.p2 - l.p1
    L = float(np.hypot(*d))
    u = d / L if L else np.array([1.0, 0.0])
    return u, np.array([-u[1], u[0]]), L


def _ang_diff180(a, b):
    d = abs((a - b) % 180.0)
    return min(d, 180 - d)


def associate(labels, linework, char_h: float, skip=()) -> None:
    lines, arcs = linework.lines, linework.arcs
    taken: dict[tuple, int] = {}
    for lab in labels:
        if lab.id in skip and lab.assoc:
            taken[(lab.assoc['geom'], lab.kind)] = lab.id
    cands = []
    if lines:
        P1 = np.array([l.p1 for l in lines])
        P2 = np.array([l.p2 for l in lines])
        LL = np.hypot(*(P2 - P1).T)
        U = (P2 - P1) / np.maximum(LL, 1e-9)[:, None]
        N = np.stack([-U[:, 1], U[:, 0]], axis=1)
        line_arr = (P1, U, N, LL, np.array([l.angle for l in lines]))
    for lab in labels:
        if lab.id in skip or lab.kind not in ("bearing", "distance", "curve_id", "curve_data"):
            continue
        la = lab.angle % 180.0
        if lines:
            P1, U, N, LL, ANG = line_arr
            w = lab.center - P1
            t = (w * U).sum(1)
            off = (w * N).sum(1)
            ad = np.abs((la - ANG) % 180.0)
            ad = np.minimum(ad, 180 - ad)
            margin = 0.15 * LL + 0.5 * char_h
            ok = (LL >= 1) & (ad <= 12) & (np.abs(off) <= 2.6 * char_h + 0.5 * lab.height) \
                & (t >= -margin) & (t <= LL + margin)
            for k in np.flatnonzero(ok):
                outside = max(0.0, -t[k], t[k] - LL[k])
                score = abs(off[k]) / char_h + ad[k] / 6 + outside / char_h
                cands.append((float(score), lab.id, ("L", lines[k].id), float(t[k] / LL[k]), float(off[k])))
        for a in arcs:
            v = lab.center - a.center
            rr = float(np.hypot(*v))
            off = rr - a.r
            # curve numbers ("C3: 85.24'") label the curve from further in
            reach = (6.0 if lab.kind == "curve_id" else 2.6) * char_h
            if abs(off) > reach + 0.5 * lab.height:
                continue
            ang = math.atan2(v[1], v[0])
            t = ((ang - a.a0) / a.sweep) if a.sweep else 0.0
            # unwrap into the arc's parameter range
            per = 2 * math.pi / abs(a.sweep) if a.sweep else 1
            while t < -0.5:
                t += per
            while t > 1.5:
                t -= per
            if t < -0.25 or t > 1.25:
                continue
            tang = (math.degrees(ang) + 90) % 180
            ad = _ang_diff180(lab.angle % 180, tang)
            if lab.kind in ("bearing", "distance") and ad > 20:
                continue
            score = abs(off) / char_h + (ad / 10 if lab.kind in ("bearing", "distance") else 0) - 0.3
            cands.append((score, lab.id, ("A", a.id), t, off))
    cands.sort(key=lambda c: c[0])
    by_id = {l.id: l for l in labels}
    for score, lid, geom, t, off in cands:
        lab = by_id[lid]
        if lab.assoc:
            continue
        # one bearing / distance per course, but several curve numbers may
        # share one drawn arc (C3, C4 = lot portions of the same curve)
        slot = (geom, lab.kind) if lab.kind != "curve_id" else (geom, lab.kind, lab.value)
        if slot in taken:
            continue
        taken[slot] = lid
        lab.assoc = dict(geom=geom, t=float(t), offset=float(off), score=float(score))


def _mode_cluster(vals, rel_tol=None, abs_tol=None, circular=None):
    vals = np.asarray(vals, float)
    if len(vals) == 0:
        return None, np.zeros(0, bool)
    best = None
    for v in vals:
        if circular:
            d = np.abs((vals - v + circular / 2) % circular - circular / 2)
            m = d <= abs_tol
        elif rel_tol:
            m = np.abs(vals / v - 1) <= rel_tol
        else:
            m = np.abs(vals - v) <= abs_tol
        if best is None or m.sum() > best[1].sum():
            best = (v, m)
    v, m = best
    if circular:
        d = (vals[m] - v + circular / 2) % circular - circular / 2
        return float((v + np.median(d)) % circular), m
    return float(np.median(vals[m])), m


def calibrate(labels, linework, scale_hint=None, rot_hint=None, decided=False,
              scale_tol: float = 0.015, to_pi=None) -> dict:
    """Scale/rotation stats + QA.  With hints (from reconcile's joint vote)
    the hint is authoritative and only inliers/QA are computed from it;
    decided=True means a None hint is a rejection, not "work it out"."""
    lines = {l.id: l for l in linework.lines}
    arcs = {a.id: a for a in linework.arcs}
    votes, owners = [], []
    for lab in labels:
        if lab.assoc and lab.assoc["geom"][0] == "L":
            dist = lab.value if lab.kind == "distance" else (
                lab.value.get("dist") if lab.kind == "bearing" else None)
            l = lines[lab.assoc["geom"][1]]
            if dist and l.length > 3 and dist > 0:
                L = l.length
                if scale_hint and to_pi and l.id in to_pi:
                    # count the label against whichever length it matches:
                    # drawn line or line-to-P.I. of a corner return
                    L = min((l.length, to_pi[l.id]), key=lambda x: abs(dist / (scale_hint * x) - 1))
                votes.append(dist / L)
                owners.append((lab, L))
    cal = dict(ft_per_px=None, scale_votes=len(votes), scale_inliers=0,
               rotation_deg=0.0, rot_votes=0, rot_inliers=0, qa=[])
    if votes:
        if scale_hint:
            s = scale_hint
            m = np.abs(np.asarray(votes) / s - 1) <= scale_tol
            need = 0
        elif decided:
            s, m, need = None, np.zeros(len(votes), bool), 1
        else:
            s, m = _mode_cluster(votes, rel_tol=scale_tol)
            need = 2 if len(votes) <= 3 else max(3, int(0.25 * len(votes)))
        if m.sum() >= need:
            cal["ft_per_px"] = s
            cal["scale_inliers"] = int(m.sum())
            for (lab, L), ok, v in zip(owners, m, votes):
                if not ok and _qa_worthy(lab, L * s, scale_tol):
                    meas = L * s
                    wr = lab.value if lab.kind == "distance" else lab.value["dist"]
                    cal["qa"].append(dict(label=lab.id, kind="distance", text=lab.text,
                                          measured=round(meas, 2), written=wr,
                                          diff=round(meas - wr, 2)))
    # rotation: image azimuth (clockwise from up, y down) vs written azimuth
    rv, rown = [], []
    for lab in labels:
        if lab.kind == "bearing" and lab.assoc and lab.assoc["geom"][0] == "L":
            l = lines[lab.assoc["geom"][1]]
            d = l.p2 - l.p1
            img_az = math.degrees(math.atan2(d[0], -d[1])) % 180
            rv.append((bearing_azimuth(lab.value) - img_az) % 180)
            rown.append((lab, img_az))
    cal["rot_votes"] = len(rv)
    if rv:
        if rot_hint is not None:
            r = rot_hint % 180
            m = np.abs((np.asarray(rv) - r + 90) % 180 - 90) <= 1.0
            need = 0
        elif decided:
            r, m, need = 0.0, np.zeros(len(rv), bool), 1
        else:
            r, m = _mode_cluster(rv, abs_tol=1.0, circular=180.0)
            need = 2 if len(rv) <= 3 else 3
        if m.sum() >= need:
            r = r if r <= 90 else r - 180
            cal["rotation_deg"] = r
            cal["rot_inliers"] = int(m.sum())
            for (lab, img_az), ok in zip(rown, m):
                if not ok:
                    meas = (img_az + r) % 180
                    cal["qa"].append(dict(label=lab.id, kind="bearing", text=lab.text,
                                          measured_az=round(meas, 2),
                                          written_az=round(bearing_azimuth(lab.value) % 180, 2)))
    # curve radii from labeled arcs (only a QA hint -- arc labels may be L or CH)
    return cal


# ---------------------------------------------------------------- curve tables
_NUM = re.compile(r"\d+\.\d+|\d+")
_DEL = re.compile(r"(\d{1,3})[°o*º](\d{1,2})['’]?(\d{1,2}(?:\.\d+)?)?")


def _dms(m):
    d, mi, s = m.groups()
    return int(d) + int(mi) / 60 + (float(s) if s else 0) / 3600


def parse_curve_rows(labels, char_h: float) -> dict:
    """Group near-horizontal OCR'd words into rows; rows led by a curve id
    and carrying >=2 numbers are curve-table rows.  Column meaning is
    inferred from internal consistency (L = R*Delta, CH = 2R sin(D/2),
    T = R tan(D/2)) rather than trusted to OCR'd headers."""
    horiz = [l for l in labels if l.text and (l.angle % 360 < 8 or l.angle % 360 > 352)]
    horiz.sort(key=lambda l: l.center[1])
    rows, cur = [], []
    for l in horiz:
        if cur and abs(l.center[1] - np.mean([c.center[1] for c in cur])) > 0.6 * char_h:
            rows.append(cur)
            cur = []
        cur.append(l)
    if cur:
        rows.append(cur)
    table = {}
    for row in rows:
        row.sort(key=lambda l: l.center[0])
        s = normalize(" ".join(l.text for l in row).replace(" ", "|"))
        m = re.match(r"^\|?C-?(\d{1,3})\|", s + "|")
        if not m:
            continue
        rest = s[m.end():]
        delta = None
        dm = _DEL.search(rest)
        if dm:
            delta = _dms(dm)
            rest = rest[:dm.start()] + "|" + rest[dm.end():]
        rest = re.sub(r"[NS]\d.*?[EW]", "|", rest)
        nums = [float(x) for x in _NUM.findall(rest)]
        nums = [x for x in nums if x > 0]
        if len(nums) < 2:
            continue
        rec = dict(id=f"C{int(m.group(1))}", raw=s, delta=delta)
        rec.update(_infer_columns(nums[:4], delta))
        table[rec["id"]] = rec
    return table


def _infer_columns(nums, delta):
    names = ["R", "L", "CH", "T"]
    best = None
    for k in range(2, min(4, len(nums)) + 1):
        for perm in itertools.permutations(names, k):
            rec = dict(zip(perm, nums[:k]))
            if "R" not in rec:
                continue
            R = rec["R"]
            D = math.radians(delta) if delta else None
            if D is None and "L" in rec:
                D = rec["L"] / R
            if not D or D <= 0 or D > 2 * math.pi:
                continue
            err = 0.0
            if "L" in rec:
                err += abs(rec["L"] - R * D) / max(1, rec["L"])
            if "CH" in rec:
                err += abs(rec["CH"] - 2 * R * math.sin(D / 2)) / max(1, rec["CH"])
            if "T" in rec:
                err += abs(rec["T"] - R * math.tan(D / 2)) / max(1, rec["T"])
            err /= (k - (0 if delta else 1)) or 1
            if best is None or err < best[0] - 1e-9 or (abs(err - best[0]) < 1e-9 and k > len(best[1])):
                best = (err, rec)
    if best is None:
        return dict(R=nums[0], consistency=None)
    rec = dict(best[1])
    rec["consistency"] = round(best[0], 4)
    return rec


# ------------------------------------------------ geometry-constrained decoding
def _line_arrays(lines):
    P1 = np.array([l.p1 for l in lines])
    P2 = np.array([l.p2 for l in lines])
    LL = np.hypot(*(P2 - P1).T)
    U = (P2 - P1) / np.maximum(LL, 1e-9)[:, None]
    return P1, U, LL, np.array([l.angle for l in lines])


def _near_lines(center, angle, height, arr, char_h, top=3):
    """Indices of the few lines a label at (center, angle) could describe."""
    P1, U, LL, ANG = arr
    w = center - P1
    t = (w * U).sum(1)
    off = w[:, 0] * -U[:, 1] + w[:, 1] * U[:, 0]
    ad = np.abs((angle % 180 - ANG) % 180.0)
    ad = np.minimum(ad, 180 - ad)
    ok = (LL >= 3) & (ad <= 12) & (np.abs(off) <= 2.6 * char_h + 0.5 * height) \
        & (t >= -0.15 * LL) & (t <= 1.15 * LL)
    idx = np.flatnonzero(ok)
    sc = np.abs(off[idx]) / char_h + ad[idx] / 6
    return [int(k) for k in idx[np.argsort(sc)][:top]]


def _img_az(l):
    d = l.p2 - l.p1
    return math.degrees(math.atan2(d[0], -d[1])) % 180


def _readings(lab):
    """(alt, kind, value, cost) for every survey-grammar reading of a label."""
    out = []
    for alt in lab.alts:
        _, rot, txt, conf, kind, val = alt
        if kind == "distance":
            out.append((alt, "distance", val, 0))
        for cost, b in bearing_readings(txt):
            out.append((alt, "bearing", b, cost))
    return out


def _consensus(votes, tol, circular=None, rel=False):
    """votes: list of (value, label_id, weight). Returns (center, set(label_ids))
    maximizing the number of *distinct labels* agreeing within tol."""
    if not votes:
        return None, set()
    vals = np.array([v[0] for v in votes])
    ids = [v[1] for v in votes]
    wts = np.array([v[2] for v in votes])
    best = None
    for v in vals:
        if circular:
            d = np.abs((vals - v + circular / 2) % circular - circular / 2)
        elif rel:
            d = np.abs(vals / v - 1)
        else:
            d = np.abs(vals - v)
        m = d <= tol
        labs = {ids[k] for k in np.flatnonzero(m)}
        key = (len(labs), float(wts[m].sum()))
        if best is None or key > best[0]:
            best = (key, v, m, labs)
    _, v, m, labs = best
    if circular:
        d = (vals[m] - v + circular / 2) % circular - circular / 2
        return float((v + np.median(d)) % circular), labs
    return float(np.median(vals[m])), labs


SMALL_ROT_DEG = 5.0
STRONG_CONF = 70.0


def _strong(alt) -> bool:
    """A distance read with real evidence: decimal point, foot mark, or a
    confident OCR read."""
    txt, conf = alt[2], alt[3]
    return "." in txt or "'" in txt or "’" in txt or conf >= STRONG_CONF


QA_MIN_CONF = 60.0


def _qa_worthy(lab, measured: float, scale_tol: float) -> bool:
    """Flag a distance/geometry disagreement only when it can mean something:
    a confident, strong read (after normalizing, so 80° counts as 80'),
    off by more than 2x the scale tolerance (beyond ordinary drafting
    error) but by less than 100% (a 7x mismatch is a misread, not a
    finding)."""
    written = lab.value if lab.kind == "distance" else (lab.value or {}).get("dist")
    if not written or lab.conf < QA_MIN_CONF:
        return False
    if not _strong((None, None, normalize(lab.text), lab.conf)):
        return False
    r = abs(measured / written - 1)
    return 2 * scale_tol < r < 1.0


def _junk_scale(svotes, scale, ok_ids, tol=0.015) -> bool:
    """Reject a scale supported only by identical, weak reads (three
    low-confidence "20"s on a grid agree by chance -> 0.034 ft/px).  Equal
    values are fine when any read is strong (three 75' frontages)."""
    inl = [v for v in svotes if v[1] in ok_ids and abs(v[0] / scale - 1) <= tol]
    if not inl:
        return True
    same = len({round(v[3], 2) for v in inl}) == 1
    return same and not any(v[4] for v in inl)


SCAN_SCALE_TOL = 0.04      # hand-drafted plats are only ~±5% to scale
DIGITAL_SCALE_TOL = 0.015  # renders/CAD are exact


def reconcile(labels, linework, char_h: float, scale_tol: float = DIGITAL_SCALE_TOL) -> dict:
    """Choose each label's reading using geometry, then associate + calibrate.

    1. every distance reading of every label x each nearby parallel line
       votes a scale; the scale agreed by the most distinct labels wins
       (needs >= 3, or 2 when that's all there is);
    2. same for bearings (incl. digit-split alternatives) -> rotation;
    3. each label takes the reading its geometry confirms (distance within
       1.5% of scale x length, bearing within 1 deg of rotated azimuth),
       lowest edit cost / highest OCR confidence first -- it is then pinned
       to that line and marked verified;
    4. the ordinary nearest-parallel association handles the rest, and
       calibrate() recomputes stats + QA from the final state."""
    lines = linework.lines
    if not lines:
        associate(labels, linework, char_h)
        return calibrate(labels, linework)
    arr = _line_arrays(lines)
    # also offer each line's length to the P.I. of a corner-return arc
    from .linework import course_lengths
    to_pi = course_lengths(linework, max(3.0, 0.4 * char_h))
    lens = lambda k: [lines[k].length] + ([to_pi[lines[k].id]] if lines[k].id in to_pi else [])
    cand = {}
    svotes, rvotes = [], []
    for lab in labels:
        if lab.kind == "table":          # table cells don't describe a course
            continue
        for alt, kind, val, cost in _readings(lab):
            ang = (lab.angle0 + alt[1]) % 360
            for k in _near_lines(lab.center, ang, lab.height, arr, char_h):
                cand.setdefault(lab.id, []).append((alt, kind, val, cost, k))
                w = alt[3] / 100.0 - 0.3 * cost
                if cost >= 2:          # repairs may be verified, never vote
                    continue
                if kind == "distance" and val > 0:
                    for L in lens(k):
                        svotes.append((val / L, lab.id, w, val, _strong(alt)))
                elif kind == "bearing":
                    rvotes.append(((bearing_azimuth(val) - _img_az(lines[k])) % 180, lab.id, w))
                    if val.get("dist"):             # combined course call votes scale too
                        svotes.append((val["dist"] / lines[k].length, lab.id, w, val["dist"], True))
    scale, s_ok = _consensus(svotes, scale_tol, rel=True)
    rot, r_ok = _consensus(rvotes, 1.0, circular=180.0)
    n_s = len({v[1] for v in svotes})
    n_r = len({v[1] for v in rvotes})
    if len(s_ok) < (2 if n_s <= 3 else 3):
        scale = None
    elif _junk_scale(svotes, scale, s_ok, scale_tol):
        scale = None
    # rotation turns the whole output drawing, so demand real agreement:
    # >= 3 distinct labels and >= 25% of voters -- except a small rotation
    # (scan skew, <= SMALL_ROT_DEG), which is low-risk and needs only 2
    small = rot is not None and abs((rot + 90) % 180 - 90) <= SMALL_ROT_DEG
    if len(r_ok) < (2 if small else max(3, 0.25 * n_r)):
        rot = None
    by_id = {l.id: l for l in labels}
    taken = set()
    choices = []
    for lid, cs in cand.items():
        for alt, kind, val, cost, k in cs:
            l = lines[k]
            if kind == "distance" and scale:
                err = min(abs(val / (scale * L) - 1) for L in lens(k))
                if err <= scale_tol:
                    choices.append((cost, -alt[3], err, lid, alt, kind, val, k))
            elif kind == "bearing" and rot is not None:
                d = abs(((bearing_azimuth(val) - _img_az(l) - rot) + 90) % 180 - 90)
                # raster geometry pins a bearing to ~1 deg only, so readings
                # that needed >= 2 edits must agree much more tightly
                if d <= (1.0 if cost <= 1 else 0.35):
                    choices.append((cost, -alt[3], d / 60, lid, alt, kind, val, k))
    choices.sort(key=lambda c: c[:3])
    done = set()
    for cost, _, err, lid, alt, kind, val, k in choices:
        if lid in done or (k, kind) in taken:
            continue
        lab = by_id[lid]
        apply_alt(lab, alt)
        lab.kind, lab.value = kind, val
        if kind == "bearing":
            lab.text = val["text"]
        lab.verified = True
        l = lines[k]
        u = (l.p2 - l.p1) / l.length
        w = lab.center - l.p1
        lab.assoc = dict(geom=("L", l.id), t=float(w @ u / l.length),
                         offset=float(w[0] * -u[1] + w[1] * u[0]), score=0.0)
        done.add(lid)
        taken.add((k, kind))
    associate(labels, linework, char_h, skip=done)
    cal = calibrate(labels, linework, scale_hint=scale, rot_hint=rot, decided=True,
                    scale_tol=scale_tol, to_pi=to_pi)
    cal["verified"] = len(done)
    return cal


def mark_table_cells(labels, linework, char_h: float) -> int:
    """Re-kind distance/bearing labels that are table cells as "table".

    A cell is a strong numeric read (bearing / decimal distance -- bare
    integers are lot numbers or fragments), sits far from every line
    (> TABLE_FAR·char_h), and shares its row with >= 2 other text labels,
    at least one of them another strong numeric read (|dy| < 0.5·char_h
    within 15·char_h; table text OCRs in fragments, so the rest may be
    anything).  On
    block13 78 of 106 "dimensions" were Line/Curve-table cells, which can
    never associate with a course and aren't dimensions of the drawing.
    Returns the number re-kinded."""
    dims = [l for l in labels if l.kind in ("distance", "bearing", "curve_id")]
    if not dims:
        return 0
    lines = linework.lines
    if lines:
        P1 = np.array([l.p1 for l in lines])
        D = np.array([l.p2 - l.p1 for l in lines])
        L2 = np.maximum((D * D).sum(1), 1e-9)
    # table cells are strong numeric reads (bearing, or distance with a
    # decimal point); bare integers are lot numbers or misread fragments
    def strong_num(l):
        return l.kind == "bearing" or (l.kind in ("distance", "table") and "." in normalize(l.text))

    def cell_like(l):          # a curve table's first column is its C-numbers
        return l.kind == "curve_id" or strong_num(l)
    texts = [l for l in labels if l.text]
    tc = np.array([l.center for l in texts]) if texts else np.zeros((0, 2))
    strong = np.array([strong_num(l) for l in texts], bool)
    n = 0
    for lab in dims:
        if not cell_like(lab):
            continue
        if lines:
            t = np.clip(((lab.center - P1) * D).sum(1) / L2, 0, 1)
            far = np.hypot(*(P1 + D * t[:, None] - lab.center).T).min()
        else:
            far = np.inf
        if far <= TABLE_FAR * char_h:
            continue
        dy = np.abs(tc[:, 1] - lab.center[1])
        dx = np.abs(tc[:, 0] - lab.center[0])
        in_row = (dy < 0.5 * char_h) & (dx < 15 * char_h) & (dx > 0.5 * char_h)
        # a table row has several numeric columns: >= 2 neighbours, >= 1 of
        # them another strong numeric read (a lone decimal among words is a
        # dimension that failed to associate, not a table cell)
        if int(in_row.sum()) >= 2 and bool((in_row & strong).any()):
            lab.kind = "table"
            lab.assoc = {}
            n += 1
    return n


TABLE_FAR = 3.0


def link_curve_ids(labels, linework, curve_table, ft_per_px, tol=0.03) -> list[dict]:
    """C-number on the drawing -> its arc -> the curve table row.  A link is
    verified when the table's R matches the arc radius x ft/px (tol)."""
    arcs = {a.id: a for a in linework.arcs}
    out = []
    for lab in labels:
        if lab.kind != "curve_id" or not lab.assoc or lab.assoc["geom"][0] != "A":
            continue
        a = arcs[lab.assoc["geom"][1]]
        rec = curve_table.get(lab.value)
        r_ft = a.r * ft_per_px if ft_per_px else None
        ok = None
        if rec and rec.get("R") and r_ft:
            ok = abs(rec["R"] / r_ft - 1) <= tol
        out.append(dict(id=lab.value, arc=a.id, arc_R_ft=None if r_ft is None else round(r_ft, 2),
                        table=rec, verified=ok))
    return out
