"""
repair.py -- geometric error localization for OCR'd survey data.

The core technique (per surveyor practice): a corrupted value is recovered by
INVERSING it from the geometry that surrounds it, then confirming the solved
value is a plausible OCR corruption of what was read.

Why this beats a plain consistency check: L = R*delta and chord =
2R*sin(delta/2) tell you a curve row is *wrong*, but not *which field* is
wrong. Inversing does. Hold any two fields, solve the third; if exactly one
field's solved value is a single-digit edit away from the OCR reading, that
field is the error and the solved value is the fix -- and it is a derived,
checkable number rather than a guess.

Tiers of context, weakest to strongest:
  1. intra-row inverse   (L/R/delta/chord over-determination)
  2. radius consensus    (curves on one road centerline share a radius)
  3. tangency chain      (consecutive curves share a tangent bearing)
  4. traverse closure    (surrounding lot/boundary must close)
"""
from __future__ import annotations

import math

# OCR confusion sets observed on these plat scans
CONFUSE = {
    "0": "0O8o6D", "1": "17lI|", "2": "27Z", "3": "38B", "4": "41A",
    "5": "56S", "6": "608G", "7": "71T", "8": "830B", "9": "930g",
    "O": "O0", "S": "S5", "B": "B83",
}


def digit_edit_ok(read: float, solved: float, decimals=2) -> tuple[bool, str]:
    """Is `solved` reachable from `read` by ONE plausible OCR digit error?
    Handles substitution, single-digit insertion (dropout) and deletion."""
    a = f"{read:.{decimals}f}".rstrip("0").rstrip(".")
    b = f"{solved:.{decimals}f}".rstrip("0").rstrip(".")
    if a == b:
        return True, "identical"
    # same length -> substitution
    if len(a) == len(b):
        diff = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]
        if len(diff) == 1:
            i = diff[0]
            if a[i].isdigit() and b[i].isdigit():
                if b[i] in CONFUSE.get(a[i], "") or a[i] in CONFUSE.get(b[i], ""):
                    return True, f"substitution {a[i]}->{b[i]} at pos {i}"
                return True, f"digit change {a[i]}->{b[i]} at pos {i} (weak)"
        return False, "multi-digit difference"
    # length differs by 1 -> dropped or added digit
    if abs(len(a) - len(b)) == 1:
        longer, shorter = (b, a) if len(b) > len(a) else (a, b)
        for i in range(len(longer)):
            if longer[:i] + longer[i + 1:] == shorter:
                return True, f"digit {'dropout' if longer is b else 'insertion'} at pos {i}"
    return False, "not a single-digit edit"


def _solve_from_pair(which: str, a: float, b: float) -> dict | None:
    """Any TWO curve fields determine the whole curve. Returns full row."""
    try:
        if which == "R,D":
            R, D = a, b
        elif which == "R,L":
            R, L = a, b
            D = math.degrees(L / R)
        elif which == "R,C":
            R, C = a, b
            ratio = C / (2 * R)
            if not -1 <= ratio <= 1:
                return None
            D = 2 * math.degrees(math.asin(ratio))
        elif which == "L,D":
            L, D = a, b
            R = L / math.radians(D)
        elif which == "C,D":
            C, D = a, b
            R = C / (2 * math.sin(math.radians(D) / 2))
        elif which == "L,C":
            # L and chord alone: solve delta numerically (L/C = (D/2)/sin(D/2))
            L, C = a, b
            if C <= 0 or L < C:
                return None
            target = L / C
            lo, hi = 1e-6, math.pi * 0.999
            for _ in range(80):
                mid = (lo + hi) / 2
                val = mid / (2 * math.sin(mid / 2)) * 2 / 2  # (D/2)/sin(D/2)
                val = (mid / 2) / math.sin(mid / 2)
                if val < target:
                    lo = mid
                else:
                    hi = mid
            D = math.degrees((lo + hi) / 2)
            R = L / math.radians(D)
        else:
            return None
        if not (R > 0 and 0 < D < 360):
            return None
        return dict(radius=round(R, 2), delta=round(D, 4),
                    length=round(R * math.radians(D), 2),
                    chord=round(2 * R * math.sin(math.radians(D) / 2), 2))
    except (ZeroDivisionError, ValueError):
        return None


def _dms_edit_ok(read_deg: float, solved_deg: float) -> tuple[bool, str]:
    """Delta is written dd-mm-ss on the plat, so corruption happens per
    component (30-22-36 misread as 3-22-36). Compare in DMS space."""
    def dms(x):
        d = int(x)
        m_f = (x - d) * 60
        m = int(round(m_f, 4))
        s = round((m_f - m) * 60)
        if s >= 60:
            s -= 60
            m += 1
        if m >= 60:
            m -= 60
            d += 1
        return d, m, s
    # Fast path: if the difference is (near) a whole number of degrees, the
    # minutes/seconds are identical and ONLY the degrees component is
    # corrupted -- the classic "30 deg read as 3 deg" dropout. Comparing
    # component-by-component fails here because a solved delta inherits
    # rounding noise from 2-decimal inputs (observed: 7 arcsec of drift).
    d = solved_deg - read_deg
    if abs(d - round(d)) < 0.01 and abs(round(d)) >= 1:
        ok, why = digit_edit_ok(float(int(read_deg)), float(int(solved_deg)), decimals=0)
        if ok:
            return True, f"degrees {int(read_deg)}->{int(solved_deg)} ({why}); minutes+seconds identical"
    rd, rm, rs = dms(read_deg)
    sd, sm, ss = dms(solved_deg)
    # tolerant component compare: seconds within 30" is rounding noise
    same = [rd == sd, rm == sm or abs(rm - sm) <= 1, abs(rs - ss) <= 30]
    diffs = [i for i, ok_ in enumerate(same) if not ok_]
    if not diffs:
        return True, "identical within rounding"
    if len(diffs) == 1:
        names = ["degrees", "minutes", "seconds"]
        i = diffs[0]
        rv = [rd, rm, rs][i]
        sv = [sd, sm, ss][i]
        ok, why = digit_edit_ok(float(rv), float(sv), decimals=0)
        if ok:
            return True, f"{names[i]} {rv}->{sv} ({why})"
    return False, "multi-component DMS difference"


def _field_edit_ok(field: str, read: float, solved: float) -> tuple[bool, str]:
    if field == "delta":
        ok, why = _dms_edit_ok(read, solved)
        if ok:
            return ok, why
        return digit_edit_ok(read, solved, decimals=4)
    # compare at survey precision, and also as a whole number (radii are
    # usually round) -- comparing raw floats fails valid edits on noise
    for dec in (2, 1, 0):
        ok, why = digit_edit_ok(round(read, dec), round(solved, dec), decimals=dec)
        if ok:
            return True, why
    return False, "not a single-digit edit"


def inverse_solve_curve(rec: dict, tol=0.05, rel=0.01) -> list[dict]:
    """Enumerate every pair of fields as a hypothesis (each pair determines
    the full curve), score by how many of the REMAINING read fields it
    reproduces, and return ranked corrections.

    The scoring is the key idea: if three fields mutually agree, the fourth
    is determined by redundancy and can be corrected with confidence even
    when the corruption is gross (a column-leak, say) rather than a tidy
    single-digit typo. If no hypothesis is corroborated by a third field,
    the row is genuinely ambiguous and is refused rather than guessed."""
    fields = ("length", "radius", "delta", "chord")
    read = {f: rec.get(f) for f in fields}
    if not all(isinstance(v, (int, float)) and v > 0 for v in read.values()):
        return []

    pairs = [("R,D", "radius", "delta"), ("R,L", "radius", "length"),
             ("R,C", "radius", "chord"), ("L,D", "length", "delta"),
             ("C,D", "chord", "delta"), ("L,C", "length", "chord")]

    def agrees(f, val):
        r = read[f]
        t = 0.01 if f == "delta" else max(tol, abs(r) * rel)
        return abs(val - r) <= t

    hyps = []
    for key, fa, fb in pairs:
        sol = _solve_from_pair(key, read[fa], read[fb])
        if not sol:
            continue
        others = [f for f in fields if f not in (fa, fb)]
        support = sum(1 for f in others if agrees(f, sol[f]))
        wrong = [f for f in others if not agrees(f, sol[f])]
        hyps.append(dict(basis=(fa, fb), sol=sol, support=support, wrong=wrong))

    if not hyps:
        return []
    best = max(h["support"] for h in hyps)
    if best < 1:
        return []  # nothing corroborates anything -> ambiguous, refuse

    out = []
    seen = set()
    for h in sorted(hyps, key=lambda x: -x["support"]):
        if h["support"] < best or len(h["wrong"]) != 1:
            continue
        f = h["wrong"][0]
        solved = h["sol"][f]
        if (f, round(solved, 2)) in seen:
            continue
        seen.add((f, round(solved, 2)))
        ok, why = _field_edit_ok(f, read[f], solved)
        # 3 agreeing fields => determined by redundancy; a tidy digit-edit is
        # a bonus, not a requirement
        # support>=1 with exactly one disagreeing field means THREE fields
        # are mutually consistent -- the fourth is over-determined, so it is
        # solved, not guessed. A tidy digit-edit raises confidence but is not
        # required; gross corruption (a column leak) is still recoverable
        # when three independent fields agree on the answer.
        conf = "high" if ok else "medium"
        out.append(dict(field=f, read=read[f], solved=solved, why=why if ok else
                        "gross error (column leak?) -- determined by redundancy",
                        corroboration=f"{h['basis'][0]}+{h['basis'][1]} reproduce "
                                      f"{h['support']} other field(s)",
                        confidence=conf))
    order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda d: order.get(d["confidence"], 9))
    return out


def radius_consensus(curves: dict, min_support=2) -> dict:
    """Curves along one road centerline share a radius. A radius value that
    appears once, but is a single-digit edit from a radius appearing several
    times, is almost certainly an OCR error -- this is the 'surrounding
    geometry' check applied across the curve table."""
    counts = {}
    for cid, r in curves.items():
        rr = r.get("radius")
        if rr:
            counts.setdefault(round(rr, 2), []).append(cid)
    findings = {}
    for val, ids in counts.items():
        if len(ids) >= min_support:
            continue
        for other, oids in counts.items():
            if other == val or len(oids) < min_support:
                continue
            ok, why = digit_edit_ok(val, other)
            if ok:
                findings[ids[0]] = dict(field="radius", read=val, solved=other,
                                        why=why,
                                        corroboration=f"{len(oids)} other curves use R={other}",
                                        confidence="medium")
                break
    return findings


def plausible_radius(curves: dict, r: float, tol_factor=3.0) -> bool:
    """Is a radius in family with the rest of the table? A misparsed row can
    corroborate itself (two garbage fields agreeing), so redundancy alone is
    not enough -- observed: R=1148 'confirmed' a delta correction that was
    wholly wrong. Radii on a subdivision plat cluster in a narrow band."""
    vals = sorted(v["radius"] for v in curves.values()
                  if isinstance(v.get("radius"), (int, float)) and v["radius"] > 0)
    if len(vals) < 3:
        return True
    med = vals[len(vals) // 2]
    return (med / tol_factor) <= r <= (med * tol_factor)


def apply_corrections(curves: dict, corrections: dict,
                      auto_only_high=True) -> tuple[dict, list, list]:
    """Apply corrections and re-verify. Returns (fixed, applied, review).

    Only HIGH-confidence corrections (the solved value is a plausible
    single-digit OCR edit of what was read) are applied automatically.
    Corrections justified purely by redundancy -- where the corrupted field
    is grossly wrong, e.g. a column leak -- are correct often enough to be
    worth surfacing, but they can also be produced by a self-corroborating
    misparse, so they are FLAGGED for a human rather than written in
    silently. Refusing to auto-apply these is the difference between a tool
    that finds errors and one that invents data."""
    fixed, applied, review = dict(curves), [], []
    for cid, corr in corrections.items():
        if cid not in fixed:
            continue
        rec = dict(fixed[cid])
        # Plausibility of the radius is informational context for the
        # reviewer. It must NOT gate a radius correction -- the read radius
        # is the corrupt value being fixed, so testing it against the table
        # would block exactly the repairs we want.
        check_r = corr["solved"] if corr["field"] == "radius" else rec.get("radius", 0)
        radius_ok = plausible_radius(curves, check_r)
        high = corr.get("confidence") == "high"
        entry = dict(curve=cid, field=corr["field"], read=corr["read"],
                     solved=corr["solved"], why=corr["why"],
                     corroboration=corr["corroboration"],
                     radius_in_family=radius_ok)
        if auto_only_high and not high:
            entry["action"] = "FLAGGED for review (not auto-applied)"
            review.append(entry)
            continue
        rec[corr["field"]] = corr["solved"]
        R, D = rec["radius"], rec["delta"]
        rec["length"] = round(R * math.radians(D), 2)
        rec["chord"] = round(2 * R * math.sin(math.radians(D) / 2), 2)
        rec["corrected"] = corr
        fixed[cid] = rec
        entry["action"] = "auto-applied"
        applied.append(entry)
    return fixed, applied, review
