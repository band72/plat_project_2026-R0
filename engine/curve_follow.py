"""
curve_follow.py -- decide WHICH SIDE a plat curve bulges, and follow it, using
the scanned linework (the skeleton polylines) as independent evidence.

WHY THIS EXISTS
A curve-table row (radius, delta, chord bearing) plus a P.C. fixes the arc only
up to a mirror image: with the chord fixed, the arc can bulge to either side of
it, and Curve.rot (CW / CCW) is the caller's guess. Closure, chord length and
every internal check are IDENTICAL for both choices -- the same trap as the
Iter 22 side-line flip in MASTER_PROMPT.md, where only the scan could tell. Until
now every rot in the repo was typed by hand and never checked against the drawing.

METHOD: oriented chamfer matching with a translation search
The scan is never registered perfectly (on Beachwood the ink sits 20-35 ft from
the COGO linework, more than the 19-23 ft mid-ordinate of the curves being
tested), so position alone cannot decide the side. Instead, for each candidate
side (CW, CCW) the arc is slid over every translation within a search window and
scored by how much of it lands on ink:

  * ORIENTED: a sample only counts if the ink there runs PARALLEL to the arc's
    tangent. A lot line crossing the arc, or a straight line that happens to be
    near it, is not evidence. The tolerance scales with the arc's own turning
    (a 37 deg arc has tangents from -19 to +19 deg, so a straight line can only
    cover a slice of it) but never drops below the vectorizer's own chord error.
  * TRANSLATION, not offset: registration error is a rigid shift of the whole arc.
    (A constant NORMAL offset is a different curve -- a concentric arc -- and
    penalises the true side when the arc is large.)
  * CONSENSUS: the side's score is the fraction of the arc explained by the ONE
    best translation. The mirror-image arc bows away from the ink by up to twice
    the mid-ordinate, so no single translation explains more than a slice of it;
    clutter at scattered offsets cannot outvote a consistent stroke.

WHAT IT WILL NOT DO
When the two candidate arcs differ by less than the scan can resolve (small
delta or huge radius -- the mid-ordinate is a few feet), the answer is
INDETERMINATE rather than a coin flip. When neither side is followed by ink it
says NO_INK, and when the evidence is not clear-cut, AMBIGUOUS. A confidently
wrong side is worse than no answer, so DECIDED is deliberately hard to earn.

Coordinates are (Northing, Easting) in feet, like the rest of the engine.
"""
from __future__ import annotations
import math
from collections import defaultdict
from dataclasses import dataclass, replace
import cv2
import numpy as np

from .cogo import Point
from .curves import Curve

_PI = math.pi


class InkField:
    """Scanned linework as oriented sample points in plat feet (Northing, Easting).

    Each point carries the direction of the stroke it lies on, so callers can
    ask for ink that runs PARALLEL to something, not just ink that is near it."""

    def __init__(self, points, angles, cell_ft: float = 10.0):
        self.points = np.asarray(points, dtype=float).reshape(-1, 2)
        self.angles = np.asarray(angles, dtype=float)  # radians in [0, pi): stroke direction
        self.cell = float(cell_ft)
        cells = defaultdict(list)
        keys = np.floor(self.points / self.cell).astype(np.int64)
        for idx, (i, j) in enumerate(keys.tolist()):
            cells[(i, j)].append(idx)
        self._cells = {k: np.asarray(v) for k, v in cells.items()}

    @classmethod
    def from_polylines(cls, polylines, step_ft: float = 0.5, min_seg_ft: float = 1.5,
                       cell_ft: float = 10.0) -> "InkField":
        """Build from skeleton polylines in feet, e.g. vectorize_plat_sheet()'s
        'polylines_ft'. Segments are densified to step_ft so distances to the ink
        are accurate to about step_ft / 2; segments shorter than min_seg_ft are
        skipped -- their direction is pixel noise."""
        pts, ang = [], []
        for poly in polylines:
            P = np.asarray(poly, dtype=float)
            for a, b in zip(P[:-1], P[1:]):
                d = b - a
                length = math.hypot(d[0], d[1])
                if length < min_seg_ft:
                    continue
                k = max(1, int(math.ceil(length / step_ft)))
                pts.append(a + d * (np.arange(k)[:, None] / k))
                ang.append(np.full(k, math.atan2(d[1], d[0]) % _PI))
        if not pts:
            return cls(np.empty((0, 2)), np.empty(0), cell_ft)
        return cls(np.vstack(pts), np.concatenate(ang), cell_ft)

    def __len__(self) -> int:
        return len(self.points)

    def near(self, p, radius: float) -> np.ndarray:
        """Indices of ink points in the grid cells covering `radius` around p."""
        r = int(math.ceil(radius / self.cell))
        ci, cj = int(math.floor(p[0] / self.cell)), int(math.floor(p[1] / self.cell))
        found = [self._cells[(i, j)]
                 for i in range(ci - r, ci + r + 1) for j in range(cj - r, cj + r + 1)
                 if (i, j) in self._cells]
        return np.concatenate(found) if found else np.empty(0, dtype=int)


class _OrientedDistance:
    """Distance-to-ink rasters over a local window, one per stroke-direction bin.

    A sample whose tangent falls in bin b is looked up in raster b, which measures
    the distance to the nearest ink stroke running within `member_deg` of that
    bin's direction. Rasters are built lazily, so only the directions a given arc
    actually turns through are ever computed. Feet throughout."""

    def __init__(self, ink: InkField, lo, hi, res_ft: float, width_deg: float, member_deg: float):
        self.n0, self.e0, self.res = float(lo[0]), float(lo[1]), float(res_ft)
        self.H = int(math.ceil((hi[0] - lo[0]) / res_ft)) + 1
        self.W = int(math.ceil((hi[1] - lo[1]) / res_ft)) + 1
        pts = ink.points
        keep = ((pts[:, 0] >= lo[0]) & (pts[:, 0] <= hi[0]) &
                (pts[:, 1] >= lo[1]) & (pts[:, 1] <= hi[1]))
        self._ang = ink.angles[keep]
        self._ii = np.round((pts[keep, 0] - self.n0) / res_ft).astype(int)
        self._jj = np.round((pts[keep, 1] - self.e0) / res_ft).astype(int)
        self.width = math.radians(width_deg)
        self.member = math.radians(member_deg)
        self.n_bins = max(1, int(round(_PI / self.width)))
        self._cache: dict[int, np.ndarray] = {}

    def bin_of(self, phi: float) -> int:
        return int(round(phi / self.width)) % self.n_bins

    def raster(self, b: int) -> np.ndarray:
        if b not in self._cache:
            centre = b * self.width
            near = np.abs((self._ang - centre + _PI / 2) % _PI - _PI / 2) <= self.member
            if near.any():
                img = np.full((self.H, self.W), 255, np.uint8)
                img[self._ii[near], self._jj[near]] = 0
                self._cache[b] = cv2.distanceTransform(img, cv2.DIST_L2, cv2.DIST_MASK_5) * self.res
            else:
                self._cache[b] = np.full((self.H, self.W), 1e6, np.float32)
        return self._cache[b]

    def lookup(self, b: int, n, e) -> np.ndarray:
        """Distance (ft) from points (n, e) to ink of direction bin b; inf outside the window."""
        ii = np.round((np.asarray(n) - self.n0) / self.res).astype(int)
        jj = np.round((np.asarray(e) - self.e0) / self.res).astype(int)
        inside = (ii >= 0) & (ii < self.H) & (jj >= 0) & (jj < self.W)
        out = np.full(ii.shape, np.inf)
        out[inside] = self.raster(b)[ii[inside], jj[inside]]
        return out


def _as_array(points) -> np.ndarray:
    return np.array([(p.n, p.e) for p in points], dtype=float)


@dataclass
class SideFit:
    """How well one candidate side (CW or CCW) matches the scan."""
    rot: str
    cover: float         # fraction of arc samples explained by the ONE best translation
    shift: np.ndarray    # (2,) that translation (dn, de), ft = the registration error; nan if none
    bias_ft: float       # its length
    arc: np.ndarray      # (K, 2) sampled candidate arc, feet (before the shift)
    matched: np.ndarray  # (K,) bool -- sample lands on parallel ink at that shift
    hits: np.ndarray     # (K, 2) the ink point it lands on, NaN where unmatched


@dataclass
class SideResult:
    """Outcome of choose_curve_side(). `side` is 'CW' / 'CCW' only when DECIDED."""
    side: str | None
    verdict: str         # DECIDED | INDETERMINATE | AMBIGUOUS | NO_INK
    mid_ordinate_ft: float
    expected_gap_ft: float  # how far apart the two sides' shapes are (RMS) -- what the scan must resolve
    fits: dict           # {'CW': SideFit, 'CCW': SideFit}
    reason: str

    def agrees_with(self, rot: str) -> bool | None:
        """True/False if the scan decided the side, None if it could not."""
        return None if self.side is None else self.side == rot


def _direction_tolerance_deg(curve: Curve, ink_eps_ft: float) -> float:
    """How far a matching stroke's direction may stray from the arc tangent.

    Two things bound it. It must be TIGHT relative to the arc's own turning, or a
    straight lot line would 'match' the flat part of any arc. But it cannot be
    tighter than the vectorizer's own error: approxPolyDP replaces an arc by
    chords whose direction is off by up to sqrt(2*eps/R), large for small radii."""
    turning = 0.18 * curve.delta_deg
    vectorizer = 1.2 * math.degrees(math.sqrt(2.0 * ink_eps_ft / curve.radius))
    return min(20.0, max(4.0, turning, vectorizer))


def _tangent_angles(pts: np.ndarray) -> np.ndarray:
    tang = np.gradient(pts, axis=0)
    return np.arctan2(tang[:, 1], tang[:, 0]) % _PI


def _fit_side(curve: Curve, pc: Point, rot: str, od: _OrientedDistance, ink: InkField,
              shifts: np.ndarray, n_samples: int, tol_in_ft: float, trim_ends: float,
              min_cover: float) -> SideFit:
    cand = replace(curve, rot=rot)
    full = _as_array(cand.arc_points(pc, n_segments=n_samples))
    lo = int(round(trim_ends * n_samples))
    pts = full[lo:len(full) - lo] if lo else full
    K = len(pts)
    bins = [od.bin_of(a) for a in _tangent_angles(pts)]
    dist = np.empty((K, len(shifts)), dtype=np.float32)
    for i in range(K):
        dist[i] = od.lookup(bins[i], pts[i, 0] + shifts[:, 0], pts[i, 1] + shifts[:, 1])
    agree = dist <= tol_in_ft
    frac = agree.mean(axis=0)
    fmax = float(frac.max())
    nan_hit = np.full((K, 2), np.nan)
    if fmax < min_cover:
        return SideFit(rot, fmax, np.full(2, np.nan), float("nan"), pts,
                       np.zeros(K, dtype=bool), nan_hit)
    # Every shift within tolerance of the ink ties for the best cover, so the winner
    # must be picked INSIDE that plateau. Taking the smallest shift (as first tried)
    # parks the answer on the plateau's edge, up to a tolerance-width off the ink;
    # the mean distance to the ink finds its centre.
    best = np.flatnonzero(frac >= fmax - 1e-9)
    j = best[np.argmin(np.minimum(dist[:, best], 2.0 * tol_in_ft).mean(axis=0))]
    shift = shifts[j]
    matched = agree[:, j]
    hits = nan_hit.copy()
    tol_dir = od.member
    tang = _tangent_angles(pts)
    for i in np.flatnonzero(matched):
        idx = ink.near(pts[i] + shift, 2.0 * tol_in_ft)
        if idx.size == 0:
            continue
        d = np.hypot(*(ink.points[idx] - (pts[i] + shift)).T)
        ok = np.abs((ink.angles[idx] - tang[i] + _PI / 2) % _PI - _PI / 2) <= 2 * tol_dir
        if ok.any():
            hits[i] = ink.points[idx][ok][np.argmin(d[ok])]
    return SideFit(rot, fmax, shift.copy(), float(np.hypot(*shift)), pts, matched, hits)


def choose_curve_side(curve: Curve, pc: Point, ink: InkField, tol_ft: float = 2.0,
                      search_ft: float | None = None, angle_tol_deg: float | None = None,
                      n_samples: int = 48, min_cover: float = 0.5, decide_cover: float = 0.7,
                      cover_margin: float = 0.25, trim_ends: float = 0.10,
                      ink_eps_ft: float = 0.75, res_ft: float = 0.5,
                      center_ft=(0.0, 0.0)) -> SideResult:
    """Decide from the scan whether `curve` bulges CW or CCW when placed at `pc`.

    Both candidate arcs share the chord and endpoints, so only the middle of the
    arc carries evidence; the outer `trim_ends` fraction is skipped.

    tol_ft is the scan + vectorization noise floor (the project measures about
    1-2 ft). Two arcs whose shapes differ by less than that cannot be told apart,
    and the result says so instead of guessing.

    A side is DECIDED only when (a) one translation explains at least
    `decide_cover` of the arc, (b) the other side is explained by at least
    `cover_margin` less, and (c) that translation is well inside the search
    window -- a 'match' at the window's edge is more likely a different stroke.

    center_ft is a coarse (dN, dE) registration guess to centre the search on. The
    window is +-search_ft around it, so a scan that is registered only roughly
    (Beachwood's Marina curves are hundreds of feet off) can still be searched
    without a huge, clutter-prone window: read the offset off one landmark."""
    M = curve.mid_ordinate
    center = np.asarray(center_ft, dtype=float)
    # The wrong side's shape bows away by up to 2M (RMS about 0.6M): that is how far
    # apart the two sides are, and what the scan has to resolve.
    expected_gap = 0.6 * M
    # Registration error is unknown and can exceed the sagitta (Beachwood's Marina
    # curves sit 20-35 ft off), so the window must be generous.
    search = search_ft if search_ft is not None else max(2.0 * M + 12.0, 60.0)
    tol_dir = angle_tol_deg if angle_tol_deg is not None else _direction_tolerance_deg(curve, ink_eps_ft)
    tol_in = 0.75 * tol_ft

    def result(side, verdict, reason, fits):
        return SideResult(side, verdict, M, expected_gap, fits, reason)

    both = np.vstack([_as_array(replace(curve, rot=r).arc_points(pc, n_segments=n_samples))
                      for r in ("CW", "CCW")])
    margin = search + 3.0 * tol_in
    lo, hi = both.min(axis=0) + center - margin, both.max(axis=0) + center + margin
    od = _OrientedDistance(ink, lo, hi, res_ft, width_deg=tol_dir / 2.0, member_deg=0.75 * tol_dir)
    g = np.arange(-search, search + 1e-9, res_ft)
    dn, de = np.meshgrid(g, g, indexing="ij")
    shifts = np.stack([dn.ravel(), de.ravel()], axis=1)
    shifts = shifts[np.hypot(shifts[:, 0], shifts[:, 1]) <= search] + center
    fits = {rot: _fit_side(curve, pc, rot, od, ink, shifts, n_samples, tol_in, trim_ends, min_cover)
            for rot in ("CW", "CCW")}
    best, other = sorted(fits.values(), key=lambda f: -f.cover)

    if expected_gap < 1.5 * tol_ft:
        return result(None, "INDETERMINATE",
                      f"mid-ordinate {M:.2f} ft: the two sides differ by only about "
                      f"{expected_gap:.1f} ft, under the {1.5 * tol_ft:.1f} ft the scan can resolve", fits)
    if best.cover < min_cover:
        return result(None, "NO_INK",
                      f"no parallel stroke follows either side along {min_cover:.0%}+ of the arc "
                      f"(CW {fits['CW'].cover:.0%}, CCW {fits['CCW'].cover:.0%})", fits)
    problems = []
    if best.cover < decide_cover:
        problems.append(f"{best.rot} is followed along only {best.cover:.0%} of the arc (needs {decide_cover:.0%})")
    if best.cover - other.cover < cover_margin:
        problems.append(f"{other.rot} is followed along {other.cover:.0%}, too close to {best.rot}'s "
                        f"{best.cover:.0%} (needs a {cover_margin:.0%} margin)")
    if best.cover >= min_cover and float(np.hypot(*(best.shift - center))) > 0.8 * search:
        problems.append(f"shift {best.bias_ft:.0f} ft is at the edge of the {search:.0f} ft window")
    if problems:
        return result(None, "AMBIGUOUS", "; ".join(problems), fits)
    return result(best.rot, "DECIDED",
                  f"{best.rot} followed along {best.cover:.0%} of the arc vs {other.cover:.0%} for "
                  f"{other.rot}; registration shift {best.shift[0]:+.1f} N, {best.shift[1]:+.1f} E ft", fits)


@dataclass
class TracedCurve:
    """A curve placed on the side the scan supports, shifted onto the drawn line."""
    rot: str
    verdict: str
    shift: np.ndarray       # (2,) translation that was applied (registration error), ft
    registered_arc: np.ndarray  # (K, 2) candidate arc moved by `shift` onto the ink
    traced: np.ndarray      # (K, 2) measured ink where found, registered arc elsewhere
    measured: np.ndarray    # (K,) bool -- True where `traced` is an actual ink measurement


def follow_curve(curve: Curve, pc: Point, ink: InkField,
                 result: SideResult | None = None, **kw) -> TracedCurve:
    """Follow a curve along the scan on the side the scan supports.

    If the scan could not decide the side (INDETERMINATE / AMBIGUOUS / NO_INK), the
    curve's own `rot` is kept and the verdict says so, so callers can tell a
    scan-confirmed trace from a fallback. The returned polyline is what a tick /
    junction probe should walk instead of a straight chord."""
    result = result or choose_curve_side(curve, pc, ink, **kw)
    rot = result.side or curve.rot
    fit = result.fits[rot]
    shift = fit.shift if np.all(np.isfinite(fit.shift)) else np.zeros(2)
    registered = fit.arc + shift
    traced = registered.copy()
    got = np.isfinite(fit.hits[:, 0])
    traced[got] = fit.hits[got]
    return TracedCurve(rot, result.verdict, shift, registered, traced, got)


def verify_curve_sides(specs, ink: InkField, **kw) -> list[dict]:
    """Check hand-set sides against the scan.

    specs: iterable of (label, Curve, pc). Each row reports the scan's verdict and
    whether the curve's own `rot` is CONFIRMED, CONTRADICTED, or UNDECIDED."""
    rows = []
    for label, curve, pc in specs:
        res = choose_curve_side(curve, pc, ink, **kw)
        agree = res.agrees_with(curve.rot)
        status = "UNDECIDED" if agree is None else ("CONFIRMED" if agree else "CONTRADICTED")
        rows.append(dict(label=label, coded=curve.rot, scan_side=res.side, status=status,
                         verdict=res.verdict, mid_ordinate_ft=res.mid_ordinate_ft,
                         shift_ft=res.fits[res.side or curve.rot].bias_ft, reason=res.reason))
    return rows
