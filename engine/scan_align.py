"""
scan_align.py -- register a scanned plat's skeleton onto the vector (COGO) plat
the way a surveyor would, with no hand-picked pixel landmarks.

  1. SCALE FIRST. The scan is converted to feet by the exact unit conversion
     (ft/px = scale_ft / dpi). Scale is never fitted; it is CHECKED, by measuring a
     long line whose length the plat states.
  2. ANCHOR. One corner of the vector plat is pinned to the same corner on the
     scan. The corner is where two fitted long lines cross, so it does not depend
     on a pixel read off a blob.
  3. BASELINE. The scan is rotated about that corner until a long scan line lies
     on the same long line of the vector plat (the bearing of one long course fixes
     the rotation; a second line at right angles cross-checks it).
  4. ADD AND ADJUST. Vector polylines are added a group at a time, nearest the
     anchor first. Each group is compared with the ink, and the alignment is
     corrected -- translation first, then rotation once a distant group is in --
     at most `max_adjustments` (three) times.

Why not fit a Helmert transform to four landmarks (iterative_align_raster_to_cogo)?
That is only as good as the landmarks. On Beachwood the four pixels named POB,
Block 18 Lot 1, Starfish/Mangrove and the north-line end were not on those
features (hundreds of feet off), so the fit returned a 0.9553 "scale" and a
56.8 ft residual for one build and a meaningless 0.05 ft for the other -- a
perfect fit to made-up points. A fixed scale, one corner and one baseline leave
nothing to fit wrongly.

Frames: the scan is in scan feet, (Northing = up the image, Easting = right), from
px_to_feet_polylines. The alignment maps scan -> vector and is expressed in the
same terms as iterative_align_raster_to_cogo, so align_skeleton_to_vector() applies
it unchanged:

    vector = scale * R(rotation_deg) @ scan + (translation_n, translation_e)
    R(a) = [[cos a, -sin a], [sin a, cos a]]   (rotates an azimuth by +a)
"""
from __future__ import annotations
import math
from dataclasses import dataclass
import numpy as np

from .curve_follow import InkField, _OrientedDistance

_PI = math.pi


def _wrap180(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def _rot(deg: float) -> np.ndarray:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s], [s, c]])


# --------------------------------------------------------------------------- scan lines

@dataclass
class ScanLine:
    """A straight stroke fitted through the scan's ink, in scan feet (n, e)."""
    point: np.ndarray    # (2,) a point on the line (centroid of the ink used)
    direction: np.ndarray  # (2,) unit vector, oriented as fitted (see `az_deg`)
    a: np.ndarray        # (2,) one end of the ink extent
    b: np.ndarray        # (2,) the other end
    length_ft: float
    n_points: int
    rms_ft: float

    @property
    def az_deg(self) -> float:
        """Azimuth of `direction` (0 = up the image, 90 = right), in [0, 360)."""
        return math.degrees(math.atan2(self.direction[1], self.direction[0])) % 360.0


def dominant_axes(ink: InkField, bin_deg: float = 0.25) -> tuple[float, float]:
    """The two perpendicular directions most ink runs along (azimuth mod 180).

    A drawn plat is almost always laid out on a rectangular sheet; its ruled lines
    share two directions. Returns (near-vertical, near-horizontal) in degrees."""
    deg = np.degrees(ink.angles)
    h, edges = np.histogram(deg, bins=np.arange(0.0, 180.0 + bin_deg, bin_deg))
    first = int(np.argmax(h))
    a1 = edges[first] + bin_deg / 2
    perp = (a1 + 90.0) % 180.0
    lo = np.abs(((edges[:-1] + bin_deg / 2 - perp + 90.0) % 180.0) - 90.0) <= 3.0
    a2 = (edges[:-1] + bin_deg / 2)[lo][int(np.argmax(h[lo]))]
    return tuple(sorted((float(a1), float(a2)), key=lambda x: min(x, 180 - x)))


def fit_scan_line(ink: InkField, hint_a, hint_b, corridor_ft: float = 8.0,
                  dir_tol_deg: float = 3.0, gap_ft: float = 20.0) -> ScanLine:
    """Least-squares straight line through the ink around a rough (a, b) hint.

    Only ink running parallel to the hint (within dir_tol_deg) and inside a
    corridor of +-corridor_ft counts. The fit is total least squares with the
    worst residuals trimmed twice, so a lot line meeting the stroke or a tick
    mark does not tilt it. The direction is good to about 0.01 deg over a
    1,600 ft stroke -- the accuracy a baseline needs."""
    a, b = np.asarray(hint_a, float), np.asarray(hint_b, float)
    length = float(np.hypot(*(b - a)))
    u = (b - a) / length
    nrm = np.array([-u[1], u[0]])
    hint_phi = math.atan2(u[1], u[0]) % _PI
    rel = ink.points - a
    along, perp = rel @ u, rel @ nrm
    dphi = np.abs(((ink.angles - hint_phi + _PI / 2) % _PI) - _PI / 2)
    m = ((np.abs(perp) <= corridor_ft) & (along >= -corridor_ft) & (along <= length + corridor_ft)
         & (dphi <= math.radians(dir_tol_deg)))
    Q = ink.points[m]
    if len(Q) < 20:
        raise ValueError(f"no straight stroke found near the hint (only {len(Q)} ink points in the corridor)")
    for _ in range(3):
        c = Q.mean(axis=0)
        d = np.linalg.svd(Q - c, full_matrices=False)[2][0]
        if d @ u < 0:
            d = -d
        res = (Q - c) @ np.array([-d[1], d[0]])
        keep = np.abs(res) <= max(0.75, 2.5 * float(res.std()))
        if keep.all():
            break
        Q = Q[keep]
    t = (Q - c) @ d
    order = np.argsort(t)
    ts = t[order]
    cuts = np.flatnonzero(np.diff(ts) > gap_ft)                # longest gap-free run of the stroke
    runs = list(zip(np.r_[0, cuts + 1], np.r_[cuts, len(ts) - 1]))
    s, e = max(runs, key=lambda r: ts[r[1]] - ts[r[0]])
    res = (Q - c) @ np.array([-d[1], d[0]])
    return ScanLine(c, d, c + d * ts[s], c + d * ts[e], float(ts[e] - ts[s]), len(Q), float(res.std()))


def intersect(l1: ScanLine, l2: ScanLine) -> np.ndarray:
    """Where two fitted lines cross (scan feet)."""
    A = np.array([l1.direction, -l2.direction]).T
    if abs(np.linalg.det(A)) < 1e-6:
        raise ValueError("lines are parallel")
    t = np.linalg.solve(A, l2.point - l1.point)
    return l1.point + l1.direction * t[0]


def _axis_toward(axes, az_deg: float) -> float:
    """The scan axis (as a direction, 0-360) pointing the way vector azimuth az_deg points."""
    best = None
    for ax in axes:
        for cand in (ax % 360.0, (ax + 180.0) % 360.0):
            d = abs(_wrap180(cand - az_deg))
            if best is None or d < best[0]:
                best = (d, cand)
    return best[1]


def align_from_corner(ink: InkField, corner_hint, anchor_vec, baseline_vec_az: float,
                      baseline_len_ft: float, cross_vec_az: float, cross_len_ft: float = 600.0,
                      corridor_ft: float = 12.0, max_scale_correction_pct: float = 1.0) -> dict:
    """Anchor + baseline alignment from one corner of the plat.

    corner_hint: roughly where that corner is on the scan (scan feet, +-corridor_ft is
    plenty). anchor_vec: the same corner in the vector plat. baseline_vec_az: azimuth,
    in the vector plat, of the long line leaving the corner (its stated length is
    baseline_len_ft); cross_vec_az: the azimuth of the second line leaving the corner
    (roughly at right angles). The scan is assumed already in feet (scale first).

    Both lines are fitted through all the ink along them, the corner is where the fits
    cross, and the baseline sets the rotation. The result carries its own checks:

      cross_check_deg  the rotation the SECOND line implies minus the baseline's. A
                       drafted corner is square to a few hundredths of a degree; if this
                       is large the wrong lines were fitted.
      far_corner_ft    distance from the corner to where the baseline meets the line at
                       its far end, vs the stated baseline_len_ft -- the scale check.

    Scale starts as the exact unit conversion the scan was made with. If the measured
    corner-to-corner length is within max_scale_correction_pct of the stated one, the
    stated length sets the scale (a print shrinks and a scanner is never exactly its
    nominal dpi); a bigger disagreement means the wrong line was measured, and the
    nominal scale is kept."""
    axes = dominant_axes(ink)
    hint = np.asarray(corner_hint, float)
    az_b = _axis_toward(axes, baseline_vec_az)
    az_c = _axis_toward(axes, cross_vec_az)
    ub = np.array([math.cos(math.radians(az_b)), math.sin(math.radians(az_b))])
    uc = np.array([math.cos(math.radians(az_c)), math.sin(math.radians(az_c))])
    base = fit_scan_line(ink, hint - ub * 8.0, hint + ub * baseline_len_ft, corridor_ft=corridor_ft)
    cross = fit_scan_line(ink, hint - uc * 8.0, hint + uc * cross_len_ft, corridor_ft=corridor_ft)
    corner = intersect(base, cross)
    ub_fit = base.direction if base.direction @ ub > 0 else -base.direction
    uc_fit = cross.direction if cross.direction @ uc > 0 else -cross.direction
    az_base = math.degrees(math.atan2(ub_fit[1], ub_fit[0])) % 360.0
    az_cross = math.degrees(math.atan2(uc_fit[1], uc_fit[0])) % 360.0
    theta = _wrap180(baseline_vec_az - az_base)
    theta_cross = _wrap180(cross_vec_az - az_cross)
    out = dict(corner_scan=corner, baseline=base, cross=cross, baseline_scan_az=az_base,
               cross_scan_az=az_cross, cross_check_deg=theta_cross - theta, far_corner_ft=None,
               scale_error_pct=None, scale_source="nominal")
    # SCALE: measure the baseline corner to corner (the line at its far end, square to it)
    # and compare with the length the plat states.
    scale = 1.0
    far_hint = corner + ub_fit * baseline_len_ft
    try:
        far = fit_scan_line(ink, far_hint - uc * 8.0, far_hint + uc * cross_len_ft, corridor_ft=corridor_ft)
        far_pt = intersect(base, far)
        out["far_corner_ft"] = float(np.hypot(*(far_pt - corner)))
        out["scale_error_pct"] = 100.0 * (out["far_corner_ft"] / baseline_len_ft - 1.0)
        if abs(out["scale_error_pct"]) <= max_scale_correction_pct:
            scale = baseline_len_ft / out["far_corner_ft"]      # the plat's own stated length sets the scale
            out["scale_source"] = "baseline"
    except ValueError:
        pass
    out["params"] = anchor_baseline_alignment(corner, anchor_vec, az_base, baseline_vec_az, scale)
    return out


# --------------------------------------------------------------------------- alignment

def anchor_baseline_alignment(anchor_scan, anchor_vec, baseline_scan_az: float,
                              baseline_vec_az: float, scale: float = 1.0) -> dict:
    """Alignment from ONE corner and ONE baseline (scale given, default 1).

    anchor_scan: the corner on the scan (scan feet); anchor_vec: the same corner in
    the vector plat. baseline_scan_az / baseline_vec_az: the azimuth of the same long
    line leaving that corner, measured on the scan and in the vector plat. Returns
    params in the iterative_align_raster_to_cogo / align_skeleton_to_vector form."""
    theta = _wrap180(baseline_vec_az - baseline_scan_az)
    t = np.asarray(anchor_vec, float) - scale * (_rot(theta) @ np.asarray(anchor_scan, float))
    return {"scale": float(scale), "rotation_deg": theta, "translation_n": float(t[0]), "translation_e": float(t[1])}


def apply_alignment(params: dict, pts) -> np.ndarray:
    """scan -> vector for an (N, 2) array of (n, e)."""
    pts = np.asarray(pts, float).reshape(-1, 2)
    return params["scale"] * (pts @ _rot(params["rotation_deg"]).T) + [params["translation_n"], params["translation_e"]]


def invert_alignment(params: dict, pts) -> np.ndarray:
    """vector -> scan."""
    pts = np.asarray(pts, float).reshape(-1, 2) - [params["translation_n"], params["translation_e"]]
    return (pts @ _rot(-params["rotation_deg"]).T) / params["scale"]


def sample_polylines(polylines, step_ft: float = 2.0, min_len_ft: float = 10.0):
    """Points along vector polylines every step_ft, with each one's direction (mod pi)."""
    P, D = [], []
    for poly in polylines:
        V = np.asarray(poly, float)
        for a, b in zip(V[:-1], V[1:]):
            L = float(np.hypot(*(b - a)))
            if L < min_len_ft:
                continue
            k = max(2, int(L / step_ft))
            t = (np.arange(k) + 0.5) / k
            P.append(a + (b - a) * t[:, None])
            D.append(np.full(k, math.atan2(b[1] - a[1], b[0] - a[0]) % _PI))
    if not P:
        return np.empty((0, 2)), np.empty(0)
    return np.vstack(P), np.concatenate(D)


def _tiles(P, D, anchor, size_ft: float, min_samples: int = 20):
    """Split samples into square tiles of size_ft so one long group gives several
    measurements at different positions (a long strip's west and east ends can then
    disagree, which is how a rotation shows up)."""
    key = np.floor((P - anchor) / size_ft).astype(int)
    out = []
    for k in {tuple(r) for r in key}:
        m = (key[:, 0] == k[0]) & (key[:, 1] == k[1])
        if m.sum() >= min_samples:
            out.append((P[m], D[m]))
    return out


def _observable_normals(D, dominant_frac: float = 0.8, tol_deg: float = 15.0):
    """Unit vectors along which a tile's measured shift is actually determined.

    A tile whose lines all run one way can slide ALONG them and still match perfectly, so
    only its shift across the lines means anything: one normal. A tile with lines in two
    directions (a grid crossing) is pinned in both: the two axes."""
    deg = np.degrees(D) % 180.0
    h, edges = np.histogram(deg, bins=np.arange(0.0, 190.0, 10.0))
    centre = edges[int(np.argmax(h))] + 5.0
    off = ((deg - centre + 90.0) % 180.0) - 90.0
    near = np.abs(off) <= tol_deg
    if near.mean() >= dominant_frac:
        phi = math.radians(centre + float(np.median(off[near])))
        return [np.array([-math.sin(phi), math.cos(phi)])]
    return [np.array([1.0, 0.0]), np.array([0.0, 1.0])]


class _Comparator:
    """Scores how well vector samples land on parallel ink, under any alignment."""

    def __init__(self, ink: InkField, res_ft: float = 1.0, tol_ft: float = 2.0):
        lo = ink.points.min(axis=0) - 5.0
        hi = ink.points.max(axis=0) + 5.0
        self.od = _OrientedDistance(ink, lo, hi, res_ft, width_deg=8.0, member_deg=10.0)
        self.tol = tol_ft

    def distances(self, params: dict, P, D, shift=(0.0, 0.0)) -> np.ndarray:
        scan = invert_alignment(params, P + np.asarray(shift))
        phi = (D - math.radians(params["rotation_deg"])) % _PI
        bins = np.round(phi / self.od.width).astype(int) % self.od.n_bins
        out = np.empty(len(P))
        for b in np.unique(bins):
            m = bins == b
            out[m] = self.od.lookup(int(b), scan[m, 0], scan[m, 1])
        return out

    def agreement(self, params: dict, P, D, shift=(0.0, 0.0)) -> float:
        """Fraction of the samples within tol_ft of ink running the same way."""
        return float(np.mean(self.distances(params, P, D, shift) <= self.tol)) if len(P) else 0.0


def measure_group(cmp: _Comparator, params: dict, P, D, window_ft: float = 25.0, step_ft: float = 0.5):
    """How far the ink sits from a group of vector lines: the (dn, de) shift of the
    vector samples that lands the most of them on ink, with its agreement and the
    agreement with no shift. Ties are broken by the smallest mean distance, so the
    answer sits in the middle of the plateau, not on its edge."""
    g = np.arange(-window_ft, window_ft + 1e-9, step_ft)
    dn, de = np.meshgrid(g, g, indexing="ij")
    shifts = np.stack([dn.ravel(), de.ravel()], axis=1)
    shifts = shifts[np.hypot(shifts[:, 0], shifts[:, 1]) <= window_ft]
    sub = slice(None, None, max(1, len(P) // 1500))               # 1,500 samples is plenty for the search
    Ps, Ds = P[sub], D[sub]
    frac = np.empty(len(shifts))
    dist = np.empty((len(shifts), len(Ps)), dtype=np.float32)
    for i, s in enumerate(shifts):
        dist[i] = cmp.distances(params, Ps, Ds, s)
    frac = (dist <= cmp.tol).mean(axis=1)
    best = np.flatnonzero(frac >= frac.max() - 1e-9)
    j = best[np.argmin(np.minimum(dist[best], 2 * cmp.tol).mean(axis=1))]
    return shifts[j].copy(), float(frac[j]), cmp.agreement(params, Ps, Ds)


def _correct(params: dict, anchor_vec, dt, dtheta_deg: float) -> dict:
    """Move the ink by -(dt + dtheta about the anchor) so it lands on the vector plat."""
    a = np.asarray(anchor_vec, float)
    t = np.array([params["translation_n"], params["translation_e"]])
    t_new = _rot(-dtheta_deg) @ (t - a) + a - np.asarray(dt, float)
    return {"scale": params["scale"], "rotation_deg": params["rotation_deg"] - dtheta_deg,
            "translation_n": float(t_new[0]), "translation_e": float(t_new[1])}


def refine_alignment(params: dict, groups, ink: InkField, anchor_vec, tol_ft: float = 2.0,
                     window_ft: float = 25.0, min_agreement: float = 0.6, min_shift_ft: float = 1.0,
                     min_spread_ft: float = 300.0, max_adjustments: int = 3, tile_ft: float = 350.0) -> tuple[dict, list[dict]]:
    """Add vector polylines a group at a time and correct the alignment, at most
    `max_adjustments` times.

    groups: list of (name, [polylines]) in the vector frame, taken nearest the anchor
    first. Each group is measured against the ink: the shift of the vector lines that
    lands the most of them on parallel ink. A group is TRUSTED only if at its best
    shift at least min_agreement of it is on ink -- a block the vector plat models
    differently from the drawing (Beachwood's diagonal blocks agree 0-9%) cannot pull
    the alignment around. When a trusted group is off by min_shift_ft or more, ONE
    adjustment is made from ALL trusted groups so far, re-measured under the current
    alignment (in tile_ft tiles, so each group's west and east ends report separately). Only the
    part of each tile's shift that its lines determine counts (across them, not along them),
    and those are combined by least squares into a translation, plus a
    rotation about the anchor once the measured tiles are min_spread_ft apart. Groups are
    never chased one at a time -- that lets each fight the last. Returns
    (params, history)."""
    cmp = _Comparator(ink, tol_ft=tol_ft)
    a = np.asarray(anchor_vec, float)
    samples = {name: sample_polylines(polys) for name, polys in groups}
    ordered = sorted((g for g in groups if len(samples[g[0]][0]) >= 20),
                     key=lambda g: float(np.hypot(*(samples[g[0]][0].mean(axis=0) - a))))
    trusted, history, adjustments = [], [], 0
    for name, _ in ordered:
        P, D = samples[name]
        shift, best, base = measure_group(cmp, params, P, D, window_ft)
        rec = dict(group=name, samples=len(P), agreement_before=round(base, 3),
                   shift=tuple(float(x) for x in np.round(shift, 2)), agreement_at_shift=round(best, 3), action="none")
        if best < min_agreement:
            rec["action"] = "skipped (drawing does not agree well enough to steer by)"
            history.append(rec)
            continue
        trusted.append(name)
        if adjustments >= max_adjustments:
            rec["action"] = "checked only (adjustment budget spent)"
            history.append(rec)
            continue
        # Re-measure every trusted group -- in tiles, so a long strip carries positional leverage --
        # under the CURRENT alignment, and keep only what each tile can actually determine: its
        # shift across its own lines (see _observable_normals). Then solve once.
        rows, ys, pos = [], [], []
        for tn in trusted:
            for Pt, Dt in _tiles(*samples[tn], a, tile_ft):
                s_t, best_t, _ = measure_group(cmp, params, Pt, Dt, window_ft if adjustments == 0 else 12.0)
                if best_t < min_agreement:
                    continue
                x = Pt.mean(axis=0) - a
                for nu in _observable_normals(Dt):
                    rows.append((nu, x))
                    ys.append(float(nu @ s_t))
                    pos.append(x)
        if not rows:
            rec["action"] = "no tile agreed well enough to steer by"
            history.append(rec)
            continue
        y = np.array(ys)
        if float(np.max(np.abs(y))) < min_shift_ft:
            rec["action"] = "within tolerance"
            history.append(rec)
            continue
        A2 = np.array([[nu[0], nu[1]] for nu, _ in rows])
        pos_a = np.array(pos)
        spread = max((float(np.hypot(*(pos_a[i] - pos_a[j]))) for i in range(len(pos_a)) for j in range(i)), default=0.0)
        dt, dtheta = None, 0.0
        if spread >= min_spread_ft:
            # d = dt + delta * (-x_e, x_n); the rotation column is scaled to a 1,000 ft lever arm
            # so it is conditioned like the translation columns
            A3 = np.column_stack([A2, [float(nu @ np.array([-x[1], x[0]])) / 1000.0 for nu, x in rows]])
            if np.linalg.matrix_rank(A3) >= 3:
                sol = np.linalg.lstsq(A3, y, rcond=None)[0]
                dt, dtheta = sol[:2], math.degrees(sol[2] / 1000.0)
                rec["action"] = f"translation + rotation ({dtheta:+.4f} deg) from {len(rows)} constraints"
        if dt is None:
            dt = np.linalg.lstsq(A2, y, rcond=None)[0]
            rec["action"] = f"translation from {len(rows)} constraint(s)"
        params = _correct(params, anchor_vec, dt, dtheta)
        adjustments += 1
        rec["adjustment"] = adjustments
        history.append(rec)
    return params, history


def alignment_agreement(params: dict, groups, ink: InkField, tol_ft: float = 2.0) -> dict:
    """Independent check: what fraction of each group's line length lands within
    tol_ft of parallel ink, and overall, under `params`. This is the number that
    says whether an alignment is correct -- it never sees the landmarks or the
    corner the alignment was built from."""
    cmp = _Comparator(ink, tol_ft=tol_ft)
    per, tot_n, tot_hit = {}, 0, 0.0
    for name, polylines in groups:
        P, D = sample_polylines(polylines)
        if not len(P):
            continue
        f = cmp.agreement(params, P, D)
        per[name] = f
        tot_n += len(P); tot_hit += f * len(P)
    return {"overall": tot_hit / tot_n if tot_n else 0.0, "groups": per}
