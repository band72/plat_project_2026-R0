"""
blocks.py -- bulk lot extraction, one BLOCK at a time.

Strategy (per the user): solve ~90% automatically, isolate the remainder
for manual work, and never let a hard block stop an easy one.

The division of labour that makes this work:
    HUMAN supplies, ONCE PER BLOCK (not per lot):
        - the block's front boundary (two endpoints on the scan)
        - the front bearing and the side bearing
        - the lot depth (or depths, if they vary)
        - the lot numbers in order
    MACHINE derives, for EVERY lot in the block:
        - each lot corner station, by junction-scanning the boundary
        - therefore every lot width
        - the closed ring, area, and full verification

So a 14-lot block costs a human 4 readings instead of 28. That is the
90/10 split.

ISOLATION: a block that fails its checks is quarantined with a reason and
the run continues. Failures are reported as a manual work queue, not as an
exception that halts the batch.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from engine.cogo import Point, parse_bearing
from engine.ticks import cluster_stations, scan_boundary_profile
from engine.topology import VertexGraph
from engine.verify import verify_ring


@dataclass
class BlockSpec:
    """What a human must supply for one block."""
    name: str
    sheet_image: str
    boundary_px: tuple           # (x1,y1,x2,y2) of the front boundary
    front_bearing: str
    side_bearing: str
    lot_numbers: list
    depth: float | list          # constant, or per-lot list
    ft_per_px: float = 50.0 / 300.0
    expected_total: float | None = None   # stated front run, if lettered
    exclude: list = field(default_factory=list)


@dataclass
class BlockResult:
    name: str
    status: str                  # "AUTO", "MANUAL", "PARTIAL"
    reason: str = ""
    parcels: dict = field(default_factory=dict)
    verifications: dict = field(default_factory=dict)
    derived_widths: list = field(default_factory=list)
    stations_ft: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def derive_lot_stations(mask, spec: BlockSpec, tol_ft=20.0,
                        start_tol_ft=20.0, end_tol_ft=2.0):
    """Junction-scan the block's front boundary to find lot corners."""
    prof = scan_boundary_profile(mask, spec.boundary_px)
    junc = cluster_stations(prof, "JUNCTION")
    st = [j["station_px"] * spec.ft_per_px for j in junc]
    x1, y1, x2, y2 = spec.boundary_px
    blen = math.hypot(x2 - x1, y2 - y1) * spec.ft_per_px
    blen_ft = blen
    # Drop spurious detections. Junction clusters bunch up where the
    # boundary meets other linework at its ends (observed: 0.3/3.7/10.5 ft
    # all detected at the start of one boundary). tol_ft is therefore set
    # to a MINIMUM PLAUSIBLE LOT WIDTH, not a pixel tolerance -- two real
    # lot corners are never 4 ft apart, so anything closer is noise.
    # The boundary's OWN endpoints register as junctions (other linework
    # meets it there), producing a phantom station a few feet in. Observed
    # a 3.67 ft station that shifted every derived width by one lot.
    # Exclude a minimum-lot-width zone at each end.
    # end_tol_ft is SEPARATE from tol_ft and much smaller: the phantom sits
    # only ~3.7 ft in, while a genuine final corner can legitimately be
    # ~10 ft from the boundary end (the 10.00' remainder on this block).
    # Using the min-lot-width value here deleted a real corner.
    # ASYMMETRIC, and that asymmetry is the whole fix. Phantom junctions
    # CLUSTER AT THE START of a boundary, where it meets other linework
    # (observed 0.33 / 3.67 / 10.50 ft on one boundary, which shifted every
    # derived width by one lot). A genuine FINAL corner, by contrast, can
    # sit only a few feet from the end (here 7.33 ft, the 10.00' monument
    # tie). Using one symmetric tolerance either keeps the phantoms or
    # deletes the last real corner -- three symmetric settings were tried
    # and none worked. Start wide, end tight.
    st = [s for s in st if start_tol_ft < s < (blen_ft - end_tol_ft)]
    # collapse near-duplicates
    clean = []
    for s in sorted(st):
        if not clean or s - clean[-1] > tol_ft:
            clean.append(s)
    return clean, blen


def build_block(mask, spec: BlockSpec, graph: VertexGraph | None = None,
                width_tol=1.5) -> BlockResult:
    """Attempt a block automatically; isolate it if the evidence is weak."""
    g = graph or VertexGraph()
    res = BlockResult(name=spec.name, status="AUTO")

    stations, blen = derive_lot_stations(mask, spec)
    res.stations_ft = stations
    n_expected = len(spec.lot_numbers)

    # station count must produce exactly the expected number of lots
    if len(stations) < n_expected:
        res.status = "MANUAL"
        res.reason = (f"junction scan found {len(stations)} corner stations, "
                      f"need >= {n_expected} for {n_expected} lots")
        return res

    # take the first n_expected+1 boundaries (0 .. last corner)
    edges = [0.0] + stations[:n_expected]
    widths = [edges[i + 1] - edges[i] for i in range(n_expected)]
    res.derived_widths = widths

    if any(w <= 0.5 for w in widths):
        res.status = "MANUAL"
        res.reason = f"derived a non-physical lot width: {min(widths):.2f} ft"
        return res

    if spec.expected_total is not None:
        diff = abs(sum(widths) - spec.expected_total)
        res.notes.append(f"derived front run {sum(widths):.2f} ft vs stated "
                         f"{spec.expected_total:.2f} ft (diff {diff:.2f})")
        if diff > 5.0:
            res.status = "PARTIAL"
            res.reason = (f"derived run differs from the stated total by "
                          f"{diff:.2f} ft -- widths need manual confirmation")

    # bearings must be complementary; this is cheap and catches a bad read
    ang = abs((parse_bearing(spec.front_bearing)
               - parse_bearing(spec.side_bearing) + 180) % 360 - 180)
    res.notes.append(f"front/side included angle {ang:.6f} deg")
    if abs(ang - 90.0) > 0.01:
        res.status = "MANUAL"
        res.reason = (f"front and side bearings are not perpendicular "
                      f"({ang:.4f} deg) -- at least one is misread")
        return res

    depths = spec.depth if isinstance(spec.depth, list) else [spec.depth] * n_expected
    if len(depths) != n_expected:
        res.status = "MANUAL"
        res.reason = f"{len(depths)} depths supplied for {n_expected} lots"
        return res

    # build the ring network with shared vertices
    tag = spec.name.replace(" ", "")
    sz = parse_bearing(spec.side_bearing)
    g.walk(f"{tag}_F0", Point(0.0, 0.0),
           [(f"{tag}_F{i+1}", spec.front_bearing, w) for i, w in enumerate(widths)])
    for i in range(n_expected + 1):
        d = depths[min(i, n_expected - 1)]
        g.add(f"{tag}_S{i}", g.points[f"{tag}_F{i}"].offset(sz, d))

    for i, num in enumerate(spec.lot_numbers):
        ring = [g.points[f"{tag}_F{i}"], g.points[f"{tag}_F{i+1}"],
                g.points[f"{tag}_S{i+1}"], g.points[f"{tag}_S{i}"]]
        res.parcels[str(num)] = ring
        res.verifications[str(num)] = verify_ring(str(num), ring)

    failed = [k for k, v in res.verifications.items() if not v.passed]
    if failed:
        res.status = "PARTIAL"
        res.reason = f"lots failing geometric checks: {failed}"
    return res


def run_batch(mask_provider, specs: list) -> dict:
    """Process many blocks, isolating failures instead of halting."""
    out = {"AUTO": [], "PARTIAL": [], "MANUAL": []}
    graph = VertexGraph()
    for spec in specs:
        mask = mask_provider(spec)
        try:
            r = build_block(mask, spec, graph)
        except Exception as e:
            r = BlockResult(name=spec.name, status="MANUAL",
                            reason=f"{type(e).__name__}: {e}")
        out[r.status].append(r)
    return out


def summarize(batch: dict) -> str:
    lines = []
    total_lots = sum(len(r.parcels) for g in batch.values() for r in g)
    auto_lots = sum(len(r.parcels) for r in batch["AUTO"])
    lines.append(f"blocks: AUTO {len(batch['AUTO'])}  "
                 f"PARTIAL {len(batch['PARTIAL'])}  MANUAL {len(batch['MANUAL'])}")
    lines.append(f"lots built: {total_lots}  (fully automatic: {auto_lots})")
    if total_lots:
        lines.append(f"automatic share: {100*auto_lots/total_lots:.0f}%")
    for status in ("PARTIAL", "MANUAL"):
        for r in batch[status]:
            lines.append(f"  [{status}] {r.name}: {r.reason}")
    return "\n".join(lines)
