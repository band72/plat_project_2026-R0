"""
blunder.py -- use the scanned plat as an independent check on transcription.

The user's insight, implemented: the scan and the transcription are two
INDEPENDENT representations of the same geometry. The transcription can be
internally perfect (closes exactly, bearings exactly complementary) and
still be wrong, if the recorded dimension itself is wrong -- a scrivener's
error on the original plat -- or if a digit was misread consistently.
Internal checks cannot catch either case. Comparing against the drawn
linework can, because the draftsman drew what was MEANT even when the
lettered dimension was mistyped.

Method: for each transcribed course, sample points along it, and measure
the perpendicular distance from each sample to the nearest scaled raster
segment. A correctly transcribed course hugs the drawn line (within the
~1 ft scale accuracy plus registration residual). A course that drifts
away from the ink is a blunder candidate -- and the SHAPE of the drift
distinguishes the cause:

  - constant offset along the whole course  -> registration/systematic
  - drift growing linearly from one end     -> wrong DISTANCE
  - drift growing from the middle outward   -> wrong BEARING
  - one course fine, the next one displaced -> blunder in the course between

This is the classic "plot it and look" check a surveyor does by eye,
made quantitative and repeatable.
"""
from __future__ import annotations
import math
from engine.cogo import Point


def _point_seg_distance(pn, pe, seg):
    """Perpendicular distance from point (pn,pe) to segment seg=(n1,e1,n2,e2)."""
    n1, e1, n2, e2 = seg
    dn, de = n2 - n1, e2 - e1
    L2 = dn * dn + de * de
    if L2 < 1e-12:
        return math.hypot(pn - n1, pe - e1)
    t = max(0.0, min(1.0, ((pn - n1) * dn + (pe - e1) * de) / L2))
    cn, ce = n1 + t * dn, e1 + t * de
    return math.hypot(pn - cn, pe - ce)


def course_deviation(a: tuple, b: tuple, raster_segs, samples=12,
                     search_radius=25.0):
    """Sample a transcribed course and measure its distance from the
    nearest drawn linework at each sample.

    search_radius caps how far we will look for 'the' matching drawn line,
    so an unrelated line clear across the sheet cannot masquerade as a
    match for a course whose real counterpart is missing from the raster."""
    devs = []
    for i in range(samples + 1):
        t = i / samples
        pn = a[0] + (b[0] - a[0]) * t
        pe = a[1] + (b[1] - a[1]) * t
        best = min((_point_seg_distance(pn, pe, s) for s in raster_segs),
                   default=float("inf"))
        devs.append(best if best <= search_radius else None)
    present = [d for d in devs if d is not None]
    if not present:
        return dict(status="NO_MATCHING_INK", samples=devs,
                    detail="no drawn line within the search radius anywhere "
                           "along this course")
    return dict(
        status="ok",
        samples=devs,
        mean=sum(present) / len(present),
        max=max(present),
        start_dev=devs[0],
        end_dev=devs[-1],
        mid_dev=devs[len(devs) // 2],
        unmatched=sum(1 for d in devs if d is None),
    )


def classify(dev: dict, tol_ok=2.0, tol_flag=4.0) -> tuple[str, str]:
    """Turn a deviation profile into a verdict plus a likely cause."""
    if dev["status"] == "NO_MATCHING_INK":
        return "MISSING", ("course has no counterpart in the drawn linework "
                           "-- either transcribed from the wrong part of the "
                           "sheet, or the raster lost that line")
    mx, mean = dev["max"], dev["mean"]
    if mx <= tol_ok:
        return "OK", "tracks the drawn line within scale accuracy"
    s, m, e = dev["start_dev"], dev["mid_dev"], dev["end_dev"]
    s = s if s is not None else mx
    m = m if m is not None else mx
    e = e if e is not None else mx
    spread = max(s, m, e) - min(s, m, e)
    verdict = "FLAG" if mx > tol_flag else "WATCH"
    if spread < tol_ok * 0.5:
        cause = ("roughly constant offset -- systematic: registration shift "
                 "or a whole-block placement error, NOT a single bad dimension")
    elif abs(e - s) > tol_ok and m < max(s, e):
        cause = ("drift grows from one end -- consistent with a wrong "
                 "DISTANCE on this course or an accumulated error arriving "
                 "from an earlier course")
    elif m > s and m > e:
        cause = ("bows out at the middle -- consistent with a wrong BEARING "
                 "(endpoints anchored, line swings between them)")
    else:
        cause = "irregular deviation -- inspect this course against the scan"
    return verdict, cause


def report(courses, raster_segs, tol_ok=2.0, tol_flag=4.0):
    """courses: list of dict(label, a=(n,e), b=(n,e), bearing, distance)."""
    out = []
    for c in courses:
        dev = course_deviation(c["a"], c["b"], raster_segs)
        verdict, cause = classify(dev, tol_ok, tol_flag)
        out.append(dict(label=c["label"], bearing=c.get("bearing"),
                        distance=c.get("distance"), verdict=verdict,
                        cause=cause,
                        mean=dev.get("mean"), max=dev.get("max")))
    return out
