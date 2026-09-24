"""Skeleton graph -> straight segments + circular arcs.

Steps:
  1. skeletonize the ink mask, find nodes (endpoints and junction clusters)
  2. trace every node-to-node pixel path exactly once (plus pure cycles)
  3. greedy primitive fitting along each path: at each position take the
     longest prefix that fits a line or a circle within tolerance (arc must
     clearly out-reach the line) -- this splits line-arc-line corner returns
     at their tangent points instead of chopping arcs in half (RDP does)
  4. global collinear merge (bridges junction gaps, text breaks and dashes;
     coverage < 0.8 marks the result dashed)
  5. endpoint snapping: L-corners to the true intersection of the two
     infinite lines, T-junctions projected onto the through line, arc ends
     onto the adjoining tangent line
  6. planarize: split lines at interior junctions so each lot course is one
     entity (what a surveyor expects: one bearing/distance per entity)
All coordinates are image pixels (x right, y down).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from skimage.morphology import skeletonize


@dataclass
class Line:
    p1: np.ndarray
    p2: np.ndarray
    coverage: float = 1.0          # fraction of length backed by ink
    color: tuple = (0, 0, 0)       # BGR sample
    kind: str = "line"
    id: int = -1

    @property
    def length(self) -> float:
        return float(np.hypot(*(self.p2 - self.p1)))

    @property
    def angle(self) -> float:
        """Undirected angle in [0,180) deg, image coords."""
        d = self.p2 - self.p1
        return math.degrees(math.atan2(d[1], d[0])) % 180.0

    @property
    def dashed(self) -> bool:
        return self.coverage < 0.8


@dataclass
class Arc:
    center: np.ndarray
    r: float
    a0: float                      # start angle, rad, image coords (y down)
    sweep: float                   # signed sweep, rad
    color: tuple = (0, 0, 0)
    kind: str = "arc"
    id: int = -1
    coverage: float = 1.0

    def point(self, t: float) -> np.ndarray:
        a = self.a0 + self.sweep * t
        return self.center + self.r * np.array([math.cos(a), math.sin(a)])

    @property
    def p1(self):
        return self.point(0.0)

    @property
    def p2(self):
        return self.point(1.0)

    @property
    def length(self) -> float:
        return abs(self.sweep) * self.r

    def sample(self, n=None) -> np.ndarray:
        n = n or max(8, int(abs(math.degrees(self.sweep)) / 3))
        return np.array([self.point(t) for t in np.linspace(0, 1, n)])


# ----------------------------------------------------------------- tracing
_NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def trace_paths(skel: np.ndarray) -> list[np.ndarray]:
    """Return ordered pixel paths (arrays of (x,y)) between skeleton nodes."""
    sk = (skel > 0).astype(np.uint8)
    sk = np.pad(sk, 1)
    nb = cv2.filter2D(sk, -1, np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], np.float32),
                      borderType=cv2.BORDER_CONSTANT).astype(np.int32) * sk
    H, W = sk.shape
    flat = sk.ravel().astype(bool)
    nbf = nb.ravel()
    offs = [dy * W + dx for dy, dx in _NB]
    is_node = flat & (nbf != 2)
    visited = np.zeros_like(flat)
    paths: list[list[int]] = []

    def walk(start: int, nxt: int) -> list[int]:
        path = [start, nxt]
        prev, cur = start, nxt
        while not is_node[cur]:
            visited[cur] = True
            step = None
            for o in offs:
                c = cur + o
                if flat[c] and c != prev and not (visited[c] and not is_node[c]):
                    # prefer 4-neighbours to avoid diagonal shortcuts
                    if step is None or abs(o) in (1, W):
                        step = c
                        if abs(o) in (1, W):
                            break
            if step is None:
                break
            prev, cur = cur, step
            path.append(cur)
        return path

    node_idx = np.flatnonzero(is_node)
    for s in node_idx:
        for o in offs:
            c = s + o
            if flat[c] and not visited[c]:
                if is_node[c]:
                    if c > s:            # node-node adjacency, keep once
                        paths.append([s, c])
                    continue
                paths.append(walk(s, c))
    # pure cycles (no nodes)
    rest = np.flatnonzero(flat & ~visited & ~is_node)
    for s in rest:
        if visited[s]:
            continue
        visited[s] = True
        for o in offs:
            c = s + o
            if flat[c] and not visited[c]:
                p = walk(s, c)
                p.append(s)
                paths.append(p)
                break
    out = []
    for p in paths:
        a = np.array(p, dtype=np.int64)
        ys, xs = np.divmod(a, W)
        out.append(np.stack([xs - 1, ys - 1], axis=1).astype(np.float64))
    return out


# ----------------------------------------------------------------- fitting
def fit_line(pts: np.ndarray):
    c = pts.mean(axis=0)
    u, s, vt = np.linalg.svd(pts - c, full_matrices=False)
    d = vt[0]
    n = np.array([-d[1], d[0]])
    dev = np.abs((pts - c) @ n)
    t = (pts - c) @ d
    return c + d * t.min(), c + d * t.max(), float(dev.max()), d, t


def fit_circle(pts: np.ndarray):
    x, y = pts[:, 0], pts[:, 1]
    A = np.stack([x, y, np.ones_like(x)], axis=1)
    b = -(x * x + y * y)
    try:
        (D, E, F), *_ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return None
    cx, cy = -D / 2, -E / 2
    r2 = cx * cx + cy * cy - F
    if r2 <= 0:
        return None
    r = math.sqrt(r2)
    dev = np.abs(np.hypot(x - cx, y - cy) - r)
    return np.array([cx, cy]), r, float(dev.max())


def _arc_from(pts, center, r) -> Arc:
    ang = np.unwrap(np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0]))
    return Arc(center=center, r=r, a0=float(ang[0]), sweep=float(ang[-1] - ang[0]))


def _longest(fits, i, n, min_len):
    """Largest j in (i+min_len, n] with fits(i, j) true (grow x2, then bisect)."""
    lo = min(n, i + min_len)
    if lo <= i + 1 or not fits(i, lo):
        return None
    step = max(2, min_len)
    hi = lo
    while hi < n:
        nxt = min(n, hi + step)
        if fits(i, nxt):
            hi = nxt
            step *= 2
        else:
            # bisect between hi (ok) and nxt (bad)
            a, b = hi, nxt
            while b - a > 1:
                m = (a + b) // 2
                if fits(i, m):
                    a = m
                else:
                    b = m
            return a
    return hi


def fit_path(pts: np.ndarray, tol: float, min_arc_px: float, max_r: float):
    """Greedy line/arc decomposition of an ordered pixel path."""
    n = len(pts)
    prims = []
    if n < 2:
        return prims
    line_ok = lambda i, j: fit_line(pts[i:j])[2] <= tol

    def arc_ok(i, j):
        # a near-straight span is arc-compatible (radius -> inf); counting it
        # keeps reach monotonic so short unstable circle fits don't stop growth
        if j - i < 6 or fit_line(pts[i:j])[2] <= tol * 0.5:
            return True
        f = fit_circle(pts[i:j])
        return f is not None and f[2] <= tol * 0.9 and f[1] <= max_r

    i = 0
    while i < n - 1:
        jl = _longest(line_ok, i, n, 2) or min(n, i + 2)
        ja = _longest(arc_ok, i, n, 8) if n - i >= 8 else None
        use_arc = False
        if ja is not None and (ja - i) > 1.3 * (jl - i) and (ja - i) >= min_arc_px:
            seg = pts[i:ja]
            f = fit_circle(seg)
            if f is not None and f[2] <= tol:
                arc = _arc_from(seg, f[0], f[1])
                if abs(math.degrees(arc.sweep)) >= 12 and f[1] >= 2 * tol:
                    use_arc = True
        if use_arc:
            prims.append(arc)
            i = ja - 1
        else:
            seg = pts[i:jl]
            if len(seg) >= 2:
                a, b, _, _, _ = fit_line(seg)
                # orient along the path direction
                if np.dot(b - a, seg[-1] - seg[0]) < 0:
                    a, b = b, a
                prims.append(Line(a, b))
            i = jl - 1
    return prims


# ----------------------------------------------------------------- merging
def _dir(l: Line):
    d = l.p2 - l.p1
    L = np.hypot(*d)
    return d / L if L > 0 else np.array([1.0, 0.0])


def merge_collinear(lines: list[Line], ang_tol=1.5, off_tol=2.0, gap_tol=20.0) -> list[Line]:
    """Union-find merge of collinear segments; coverage tracks ink support."""
    if not lines:
        return []
    lines = [l for l in lines if l.length > 0]
    n = len(lines)
    ang = np.array([l.angle for l in lines])
    order = np.argsort(ang)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    # candidate pairs: angle-sorted sweep (plus wraparound near 0/180),
    # each segment tested against its whole angle window at once (numpy)
    P1 = np.array([l.p1 for l in lines])
    P2 = np.array([l.p2 for l in lines])
    LEN = np.hypot(*(P2 - P1).T)
    D = (P2 - P1) / np.maximum(LEN, 1e-9)[:, None]
    ext = np.concatenate([order, order[ang[order] < ang_tol]])
    angs = np.concatenate([ang[order], ang[order][ang[order] < ang_tol] + 180])
    hi_idx = np.searchsorted(angs, angs + ang_tol, side="right")
    for a_pos in range(len(ext)):
        lo, hi = a_pos + 1, hi_idx[a_pos]
        if hi <= lo:
            continue
        a = ext[a_pos]
        bs = ext[lo:hi]
        bs = bs[bs != a]
        if not len(bs):
            continue
        # direction of the longer member of each pair
        d = np.where((LEN[bs] >= LEN[a])[:, None], D[bs], D[a])
        d = d * np.sign((d @ D[a]) + 1e-12)[:, None]
        nrm = np.stack([-d[:, 1], d[:, 0]], axis=1)
        ref = P1[a]
        o1 = np.abs(((P1[bs] - ref) * nrm).sum(1))
        o2 = np.abs(((P2[bs] - ref) * nrm).sum(1))
        ok = np.maximum(o1, o2) <= off_tol
        if not ok.any():
            continue
        bs, d = bs[ok], d[ok]
        ta0 = np.zeros(len(bs))
        ta1 = ((P2[a] - ref)[None, :] * d).sum(1)
        tb0 = ((P1[bs] - ref) * d).sum(1)
        tb1 = ((P2[bs] - ref) * d).sum(1)
        gap = np.maximum(np.minimum(ta0, ta1), np.minimum(tb0, tb1)) - \
            np.minimum(np.maximum(ta0, ta1), np.maximum(tb0, tb1))
        for b in bs[gap <= gap_tol]:
            parent[find(a)] = find(int(b))
    groups: dict[int, list[int]] = {}
    for k in range(n):
        groups.setdefault(find(k), []).append(k)
    out = []
    for ks in groups.values():
        if len(ks) == 1:
            out.append(lines[ks[0]])
            continue
        pts = np.concatenate([[lines[k].p1, lines[k].p2] for k in ks])
        w = np.concatenate([[lines[k].length, lines[k].length] for k in ks])
        c = np.average(pts, axis=0, weights=w + 1e-6)
        _, _, vt = np.linalg.svd((pts - c) * np.sqrt(w + 1e-6)[:, None], full_matrices=False)
        d = vt[0]
        t = (pts - c) @ d
        p1, p2 = c + d * t.min(), c + d * t.max()
        # coverage: union of projected intervals
        iv = sorted(tuple(sorted(((lines[k].p1 - c) @ d, (lines[k].p2 - c) @ d))) for k in ks)
        cov, cur_a, cur_b = 0.0, iv[0][0], iv[0][1]
        for a, b in iv[1:]:
            if a > cur_b:
                cov += cur_b - cur_a
                cur_a, cur_b = a, b
            else:
                cur_b = max(cur_b, b)
        cov += cur_b - cur_a
        L = t.max() - t.min()
        out.append(Line(p1, p2, coverage=float(cov / L) if L > 0 else 1.0))
    return out


def merge_arcs(arcs: list[Arc], tol: float) -> list[Arc]:
    """Merge arcs sharing (nearly) the same circle and touching/overlapping."""
    arcs = list(arcs)
    changed = True
    while changed:
        changed = False
        for i in range(len(arcs)):
            for j in range(i + 1, len(arcs)):
                a, b = arcs[i], arcs[j]
                if np.hypot(*(a.center - b.center)) > 2 * tol + 0.02 * max(a.r, b.r):
                    continue
                if abs(a.r - b.r) > tol + 0.02 * max(a.r, b.r):
                    continue
                ends = [(a.p1, b.p1), (a.p1, b.p2), (a.p2, b.p1), (a.p2, b.p2)]
                if min(np.hypot(*(p - q)) for p, q in ends) > 4 * tol + 0.05 * a.r:
                    continue
                pts = np.concatenate([a.sample(), b.sample()])
                # order along the circle so the merged sweep is contiguous
                c = (a.center * a.length + b.center * b.length) / (a.length + b.length)
                ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
                ang_s = np.sort(ang)
                gaps = np.diff(np.concatenate([ang_s, [ang_s[0] + 2 * math.pi]]))
                k = int(np.argmax(gaps))
                start = ang_s[(k + 1) % len(ang_s)]
                sweep = 2 * math.pi - gaps[k]
                r = float(np.mean(np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1])))
                arcs[i] = Arc(center=c, r=r, a0=float(start), sweep=float(sweep), color=a.color)
                del arcs[j]
                changed = True
                break
            if changed:
                break
    return arcs


# ----------------------------------------------------------------- snapping
def _intersect(p, d, q, e):
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9:
        return None
    w = q - p
    t = (w[0] * e[1] - w[1] * e[0]) / den
    return p + d * t


def snap_endpoints(lines: list[Line], arcs: list[Arc], r: float) -> None:
    """In place: close L-corners to the exact line intersection, extend
    T-junction stems onto the through line, and pull arc ends onto
    neighbouring line ends (tangent points)."""
    if not lines:
        return
    cos15 = math.cos(math.radians(15))
    for i, a in enumerate(lines):
        # refresh arrays each outer step: earlier snaps move endpoints
        P1 = np.array([l.p1 for l in lines])
        P2 = np.array([l.p2 for l in lines])
        LEN = np.hypot(*(P2 - P1).T)
        D = (P2 - P1) / np.maximum(LEN, 1e-9)[:, None]
        da = _dir(a)
        for end in (0, 1):
            p = a.p1 if end == 0 else a.p2
            # prefilter: lines passing within r of p (segment distance)
            w = p - P1
            t = np.clip((w * D).sum(1), 0, LEN)
            near = np.hypot(*(P1 + D * t[:, None] - p).T) <= 2 * r
            near[i] = False
            near &= np.abs(D @ da) <= cos15
            best = None
            for j in np.flatnonzero(near):
                b = lines[j]
                db = D[j]
                x = _intersect(a.p1, da, b.p1, db)
                if x is None or np.hypot(*(x - p)) > r:
                    continue
                tb = (x - b.p1) @ db
                if tb < -r or tb > LEN[j] + r:
                    continue
                dist = float(np.hypot(*(x - p)))
                if best is None or dist < best[0]:
                    best = (dist, x, j, tb)
            if best is None:
                continue
            _, x, j, tb = best
            if end == 0:
                a.p1 = x.copy()
            else:
                a.p2 = x.copy()
            b = lines[j]
            if tb < r and np.hypot(*(b.p1 - x)) <= r:
                b.p1 = x.copy()
            elif tb > LEN[j] - r and np.hypot(*(b.p2 - x)) <= r:
                b.p2 = x.copy()
    # arc ends -> nearest line end
    for arc in arcs:
        for t in (0.0, 1.0):
            p = arc.point(t)
            best = None
            for l in lines:
                for end, q in ((0, l.p1), (1, l.p2)):
                    dd = float(np.hypot(*(q - p)))
                    if dd <= r and (best is None or dd < best[0]):
                        best = (dd, l, end)
            if best:
                _, l, end = best
                if end == 0:
                    l.p1 = p.copy()
                else:
                    l.p2 = p.copy()


def planarize(lines: list[Line], r: float) -> list[Line]:
    """Split each line at points where another line's endpoint touches it."""
    if not lines:
        return []
    E = np.concatenate([np.array([l.p1 for l in lines]), np.array([l.p2 for l in lines])])
    owner = np.concatenate([np.arange(len(lines)), np.arange(len(lines))])
    out = []
    for i, a in enumerate(lines):
        d = _dir(a)
        nrm = np.array([-d[1], d[0]])
        w = E - a.p1
        t = w @ d
        m = (np.abs(w @ nrm) <= r) & (t > r * 2) & (t < a.length - r * 2) & (owner != i)
        cuts = t[m]
        if not len(cuts):
            out.append(a)
            continue
        ts = [0.0] + sorted(cuts.tolist()) + [a.length]
        merged = [ts[0]]
        for tt in ts[1:]:
            if tt - merged[-1] > r * 2:
                merged.append(tt)
        merged[-1] = a.length
        for t0, t1 in zip(merged[:-1], merged[1:]):
            out.append(Line(a.p1 + d * t0, a.p1 + d * t1, coverage=a.coverage, color=a.color))
    return out


def sample_color(color_img: np.ndarray, pts: np.ndarray) -> tuple:
    h, w = color_img.shape[:2]
    xs = np.clip(pts[:, 0].round().astype(int), 0, w - 1)
    ys = np.clip(pts[:, 1].round().astype(int), 0, h - 1)
    c = np.median(color_img[ys, xs], axis=0)
    return tuple(int(v) for v in c)


@dataclass
class Linework:
    lines: list = field(default_factory=list)
    arcs: list = field(default_factory=list)
    monuments: list = field(default_factory=list)
    short: list = field(default_factory=list)     # rejected primitives (text-ish)


def extract(ink: np.ndarray, stroke_w: float, char_h: float, color_img=None) -> Linework:
    skel = skeletonize(ink > 0)
    paths = trace_paths(skel)
    tol = max(1.2, 0.5 * stroke_w)
    diag = float(np.hypot(*ink.shape))
    prims = []
    for p in paths:
        if len(p) < 2:
            continue
        prims.extend(fit_path(p, tol, min_arc_px=max(10, 1.5 * char_h), max_r=diag))
    lines = [p for p in prims if isinstance(p, Line)]
    arcs = [p for p in prims if isinstance(p, Arc)]
    # merge across junction gaps (skeleton spurs), text breaks and dashes
    lines = merge_collinear(lines, ang_tol=2.0, off_tol=max(1.5, 0.7 * stroke_w),
                            gap_tol=max(3.0, 1.5 * stroke_w))
    lmin = max(1.8 * char_h, 10 * stroke_w, 12)
    long_ = [l for l in lines if l.length >= lmin]
    shortl = [l for l in lines if l.length < lmin]
    # second, wider merge only among already-credible linework + dashes
    dash = [l for l in shortl if l.length >= 3 * stroke_w]
    cand = merge_collinear(long_ + dash, ang_tol=1.0, off_tol=max(1.5, 0.7 * stroke_w),
                           gap_tol=max(1.2 * char_h, 6 * stroke_w))
    keep = [l for l in cand if l.length >= lmin and (l.coverage >= 0.8 or l.length >= 3 * lmin)]
    arcs = [a for a in arcs if a.length >= max(1.2 * char_h, 8 * stroke_w) and a.r >= 0.6 * char_h]
    arcs = merge_arcs(arcs, tol)
    snap_endpoints(keep, arcs, r=max(3 * stroke_w, 0.6 * char_h))
    keep = [l for l in keep if l.length >= 2]
    keep = planarize(keep, r=max(1.5, stroke_w))
    if color_img is not None:
        for l in keep:
            l.color = sample_color(color_img, np.linspace(l.p1, l.p2, 16))
        for a in arcs:
            a.color = sample_color(color_img, a.sample(16))
    for k, l in enumerate(keep):
        l.id = k
    for k, a in enumerate(arcs):
        a.id = k
    return Linework(lines=keep, arcs=arcs, short=shortl)


def _in_box(p, c, ang_deg, w, h, margin):
    a = math.radians(ang_deg)
    u = np.array([math.cos(a), math.sin(a)])
    n = np.array([-u[1], u[0]])
    v = p - c
    return abs(v @ u) <= w / 2 + margin and abs(v @ n) <= h / 2 + margin


def bridge_label_gaps(linework: Linework, boxes, char_h: float, stroke_w: float) -> int:
    """Rejoin collinear line pieces whose gap is covered by a text label.

    Drafting (and our own mapcheck renders) often print a course's distance
    *on* the line over a knock-out box, cutting it in two.  Each half is then
    ~0.45 of the course, and the halves consistently vote a scale ~2.2x too
    large.  boxes: iterable of (center, angle_deg, width, height).
    Returns the number of joins made."""
    lines = linework.lines
    joins = 0
    ang_tol, off_tol = 2.0, max(1.5, 1.0 * stroke_w)
    for c, ang, w, h in boxes:
        reach = w / 2 + 1.5 * char_h
        changed = True
        while changed:
            changed = False
            ends = [(i, e, (l.p1 if e == 0 else l.p2)) for i, l in enumerate(lines)
                    for e in (0, 1)]
            near = [(i, e, p) for i, e, p in ends if np.hypot(*(p - c)) <= reach]
            for x in range(len(near)):
                for y in range(x + 1, len(near)):
                    i, ei, pi = near[x]
                    j, ej, pj = near[y]
                    if i == j:
                        continue
                    a, b = lines[i], lines[j]
                    if min(abs(a.angle - b.angle), 180 - abs(a.angle - b.angle)) > ang_tol:
                        continue
                    d = _dir(a)
                    nrm = np.array([-d[1], d[0]])
                    if abs((pj - pi) @ nrm) > off_tol:
                        continue
                    mid = (pi + pj) / 2
                    if not _in_box(mid, c, ang, w, h, 0.5 * char_h):
                        continue
                    # a real knock-out gap, not two courses meeting at a lot
                    # corner (planarized pieces touch: gap ~0) ...
                    if np.hypot(*(pj - pi)) < max(3 * stroke_w, 0.5 * char_h):
                        continue
                    # ... and no third line ends at either gap end (junction)
                    jr = max(2 * stroke_w, 0.3 * char_h)
                    if any(k not in (i, j) and np.hypot(*(q - p)) <= jr
                           for k, _, q in ends for p in (pi, pj)):
                        continue
                    # far ends of each piece
                    fa = a.p2 if ei == 0 else a.p1
                    fb = b.p2 if ej == 0 else b.p1
                    L = float(np.hypot(*(fb - fa)))
                    if L <= max(a.length, b.length):       # not facing each other
                        continue
                    # the knock-out under a label is drafting, not a dash:
                    # the joined line keeps its pieces' own coverage
                    col = tuple(int((ca + cb) / 2) for ca, cb in zip(a.color, b.color))
                    new = Line(fa.copy(), fb.copy(), coverage=min(a.coverage, b.coverage), color=col)
                    lines[i] = new
                    del lines[j]
                    joins += 1
                    changed = True
                    break
                if changed:
                    break
    for k, l in enumerate(lines):
        l.id = k
    return joins


def course_lengths(linework: Linework, r: float) -> dict:
    """Length of each line measured to the P.I. of any corner-return arc it
    runs into.  Plat distances go to the lot corner -- the intersection of
    the two tangents -- not to the P.C./P.T. where the drawn line stops.
    Returns {line.id: length_to_PI} for lines that end at an arc (only)."""
    out = {}
    for l in linework.lines:
        d = _dir(l)
        ext = {0: 0.0, 1: 0.0}
        for end, p in ((0, l.p1), (1, l.p2)):
            for a in linework.arcs:
                for t0, t1 in ((0.0, 1.0), (1.0, 0.0)):
                    if np.hypot(*(a.point(t0) - p)) > r:
                        continue
                    # the other tangent: prefer the straight line that leaves
                    # the arc's far end (robust to a mis-fitted sweep), else
                    # the arc's own tangent there
                    q = a.point(t1)
                    nxt = [m for m in linework.lines if m is not l and
                           min(np.hypot(*(m.p1 - q)), np.hypot(*(m.p2 - q))) <= r]
                    if nxt:
                        m = min(nxt, key=lambda m: min(np.hypot(*(m.p1 - q)), np.hypot(*(m.p2 - q))))
                        q, tan = m.p1, _dir(m)
                    else:
                        ang = a.a0 + a.sweep * t1
                        tan = np.array([-math.sin(ang), math.cos(ang)])
                    x = _intersect(l.p1, d, q, tan)
                    if x is None:
                        continue
                    t = float((x - l.p1) @ d)
                    grow = -t if end == 0 else t - l.length
                    # the P.I. lies beyond the drawn end, within ~one radius
                    if 0 < grow <= 1.5 * a.r:
                        ext[end] = max(ext[end], grow)
        if ext[0] or ext[1]:
            out[l.id] = l.length + ext[0] + ext[1]
    return out


@dataclass
class Monument:
    center: np.ndarray
    r: float


def _ring_frac(ink, c, r, n=48, ignore=None):
    """Fraction of n samples on the circle (c, r) that are ink; samples on
    `ignore` pixels (e.g. extracted lines crossing a symbol) are skipped."""
    h, w = ink.shape
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    xs = np.clip((c[0] + r * np.cos(a)).round().astype(int), 0, w - 1)
    ys = np.clip((c[1] + r * np.sin(a)).round().astype(int), 0, h - 1)
    v = ink[ys, xs] > 0
    if ignore is not None:
        keep = ignore[ys, xs] == 0
        if not keep.any():
            return 0.0
        v = v[keep]
    return float(v.mean())


MAX_RADIAL_SPREAD = 0.35
INNER_EMPTY, INNER_RING = 0.1, 0.7


def _radial_spread(ring_pts, c, r) -> float:
    if len(ring_pts) < 12 or r <= 0:
        return 0.0
    v = ring_pts - c
    ang = np.arctan2(v[:, 1], v[:, 0])
    rad = np.hypot(v[:, 0], v[:, 1])
    bins = np.digitize(ang, np.linspace(-math.pi, math.pi, 13))
    med = [float(np.median(rad[bins == b])) for b in range(1, 13) if (bins == b).sum() > 2]
    return (max(med) - min(med)) / r if len(med) >= 6 else 0.0


def _line_dirs_through(lines, c, r, sep=20.0) -> int:
    """Number of distinct (>= sep deg apart) line directions passing within r of c."""
    dirs = []
    for l in lines:
        d = l.p2 - l.p1
        L2 = float(d @ d)
        if L2 == 0:
            continue
        t = min(1.0, max(0.0, float((c - l.p1) @ d) / L2))
        if np.hypot(*(l.p1 + d * t - c)) <= r:
            a = l.angle
            if all(min(abs(a - b), 180 - abs(a - b)) > sep for b in dirs):
                dirs.append(a)
    return len(dirs)


def find_monuments(ink: np.ndarray, lines, char_h: float, stroke_w: float, text_boxes=()) -> list:
    """Survey monument symbols (bullseye / open circle) on the linework.

    Hough candidates with radius 0.3-0.8 char heights, accepted only if
    (a) the ring itself is >= 80% ink, (b) the band just inside the ring is
    mostly paper (hollow -- rejects filled blobs), and (c) a plat line
    passes within one radius of the centre (monuments sit on lot corners /
    lines -- rejects the 0s and Os in labels)."""
    rmin, rmax = max(3, int(0.3 * char_h)), max(5, int(0.8 * char_h))
    blur = cv2.GaussianBlur(ink, (5, 5), 1.5)
    cs = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1, minDist=2 * rmin,
                          param1=100, param2=18, minRadius=rmin, maxRadius=rmax)
    out = []
    if cs is None:
        return out
    line_px = np.zeros_like(ink)
    lt = max(2, int(round(stroke_w)) + 2)
    for l in lines:
        cv2.line(line_px, tuple(np.round(l.p1).astype(int)), tuple(np.round(l.p2).astype(int)), 255, lt)
    P1 = np.array([l.p1 for l in lines]) if lines else np.zeros((0, 2))
    P2 = np.array([l.p2 for l in lines]) if lines else np.zeros((0, 2))
    for x, y, r in cs[0]:
        # Hough centres are a few px off on thick hand-drawn rings: refine
        # centre (+-4 px) and ring radius to the best-inked circle
        best = max(((_ring_frac(ink, np.array([x + dx, y + dy]), rr), dx, dy, rr)
                    for dx in range(-4, 5, 2) for dy in range(-4, 5, 2)
                    for rr in range(rmin, rmax + 1)), key=lambda b: b[0])
        frac, dx, dy, rr = best
        c = np.array([x + dx, y + dy], float)
        # ink fraction is flat near the true centre; pin it (monuments are
        # control points) with a least-squares circle fit to the ring's ink
        h, w = ink.shape
        x0, x1 = int(max(0, c[0] - rr - 2 * stroke_w)), int(min(w, c[0] + rr + 2 * stroke_w + 1))
        y0, y1 = int(max(0, c[1] - rr - 2 * stroke_w)), int(min(h, c[1] + rr + 2 * stroke_w + 1))
        ys, xs = np.nonzero(ink[y0:y1, x0:x1])
        pts = np.stack([xs + x0, ys + y0], axis=1).astype(float)
        dd = np.hypot(*(pts - c).T)
        ring = pts[np.abs(dd - rr) <= max(1.5, stroke_w)]
        f = fit_circle(ring) if len(ring) >= 12 else None
        if f is not None and np.hypot(*(f[0] - c)) <= 4 and abs(f[1] - rr) <= stroke_w + 2:
            c, rr = f[0], f[1]
        # monuments are circles; a hollow "0"/"O" is an ellipse.  Radial
        # spread (max-min of per-30deg median radius, / r): 0.03-0.19 on
        # the 7 hand-verified P.R.M.s vs 0.57 on block13's "10'" zero.
        if _radial_spread(ring, c, rr) > MAX_RADIAL_SPREAD:
            continue
        # symbol structure at 0.4 r: a ring-in-ring P.R.M. (as on PB30 P82)
        # is solidly inked there (0.75-1.0), a plain hollow circle (render
        # markers) is empty (~0); letters/hatching crossing a ring are
        # half-inked (0.38, 0.56 on page1's false hits) -> reject between
        inner = _ring_frac(ink, c, max(2.0, 0.4 * rr), ignore=line_px)
        if INNER_EMPTY < inner < INNER_RING:
            continue
        r = rr + stroke_w / 2
        if frac < 0.8:
            continue
        if _ring_frac(ink, c, rr - max(stroke_w, 0.3 * rr)) > 0.5:
            continue
        if len(P1):
            d = P2 - P1
            L = np.maximum(np.hypot(*d.T), 1e-9)
            t = np.clip(((c - P1) * d).sum(1) / L ** 2, 0, 1)
            dist = np.hypot(*(P1 + d * t[:, None] - c).T)
            if dist.min() > r:
                continue
        else:
            continue
        if any(np.hypot(*(m.center - c)) < rmin for m in out):
            continue
        # Real monument symbols have a paper centre; looped digits / letters
        # (8, 9, 6, e, a) mostly don't -- measured on the probe: core ink 0.0
        # on all 5 real P.R.M.s vs > 0.2 on 13 of 17 false candidates.
        x, y = int(round(c[0])), int(round(c[1]))
        win = (slice(max(0, y - 2), y + 3), slice(max(0, x - 2), x + 3))
        free = line_px[win] == 0          # ignore lines drawn through the symbol
        core = float((ink[win][free] > 0).mean()) if free.any() else 0.0
        if core >= 0.2:
            continue
        # A monument on a lot corner has >= 2 line directions through it;
        # a lone-line candidate must also not sit inside a label's box.
        if _line_dirs_through(lines, c, r) < 2 and \
                any(_in_box(c, bc, ba, bw, bh, 0.0) for bc, ba, bw, bh in text_boxes):
            continue
        out.append(Monument(center=c, r=float(r)))
    return out


def split_at_points(lines, pts, r: float) -> list:
    """Split lines passing within r of any point (monuments) at the
    point's projection, so each lot course ends at its monument."""
    out = []
    for l in lines:
        d = _dir(l)
        nrm = np.array([-d[1], d[0]])
        cuts = sorted(float((p - l.p1) @ d) for p in pts
                      if abs(float((p - l.p1) @ nrm)) <= r and r < float((p - l.p1) @ d) < l.length - r)
        if not cuts:
            out.append(l)
            continue
        ts = [0.0] + cuts + [l.length]
        for t0, t1 in zip(ts[:-1], ts[1:]):
            out.append(Line(l.p1 + d * t0, l.p1 + d * t1, coverage=l.coverage, color=l.color))
    for k, l in enumerate(out):
        l.id = k
    return out
