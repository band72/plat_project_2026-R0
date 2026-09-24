"""BEACHWOOD UNIT TWO -- full plat (PB 30, Pages 82 & 82A), both sheets in one frame.

Composition, no new geometry is invented here:
  * boundary, street centerlines, trimmed R/W lines and 25' fillets come from
    engine.centerline_geometry.solve_network() (derived from the caption + printed street data,
    90 internal checks);
  * every block comes from its own engine.cogo_block solver (lots traversed from the printed
    lot dimensions) and is placed by TRANSLATION ONLY: one printed block-corner P.I. is matched to
    the same fillet P.I. in the street network;
  * every other labelled block corner is then an independent check. A block whose check
    corners miss by more than 0.10' is drawn on the BLOCK-MISFIT layer (red) instead of hidden.
"""
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine.centerline_geometry import solve_network  # noqa: E402
from engine.cogo import Point  # noqa: E402
from engine.cogo_block import get_all_block_solvers  # noqa: E402
from engine.dxf_writer import DXFWriter  # noqa: E402
from scripts.plat_folder.common import out_dir, save_metrics  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PLAT_ID = "PB30_P82_Beachwood"
TOL = 0.10

# block -> (anchor solver point, anchor fillet id, [(check solver point, check fillet id), ...])
ANCHORS = {
    "BLOCK_18": ("B18_L19_PI_SE", "F_STARFISH_BEACHWOOD_NW", []),
    "BLOCK_17": ("B17_PI_NW", "F_STARFISH_MANGROVE_SE", [("B17_PI_SW", "F_SAIL_MANGROVE_NE"),
                                                        ("B17_L17_NE", "F_STARFISH_BEACHWOOD_SW"),
                                                        ("B17_L18_SE", "F_SAIL_BEACHWOOD_NW")]),
    "BLOCK_16": ("p1_nw_pi", "F_SAIL_MANGROVE_SE", [("p33_sw_pi", "F_MARINA_MANGROVE_NE"),
                                                    ("p29_ret_pi", "F_MARINA_SHELLFISH_N"),
                                                    ("p17_pi_ne", "F_SAIL_BEACHWOOD_SW"),
                                                    ("p18_pi_se", "F_SHELLFISH_BEACHWOOD_NW")]),
    "BLOCK_15": ("B15_L9_PI_NE", "F_SHELLFISH_BEACHWOOD_SW", [("B15_L10_PI_SE", "F_KEEL_BEACHWOOD_NW"),
                                                              ("B15_L1_PI_NW", "F_MARINA_SHELLFISH_S"),
                                                              ("B15_L17_PI_SW", "F_MARINA_KEEL_N")]),
    "BLOCK_14": ("B14_L1_PI_NE", "F_STARFISH_MANGROVE_SW", [("B14_TA_SE", "F_DRAIN40_MANGROVE_NW"),
                                                            ("B14_L11_NE", "F_DRAIN40_MANGROVE_SW"),
                                                            ("B14_L11_PI_SE", "F_CAPEHORN_MANGROVE_NW")]),
    "BLOCK_6": ("B6_L10_PI_NE", "F_KEEL_BEACHWOOD_SW", [("B6_L6_PI_W", "F_MARINA_KEEL_S")]),
    "BLOCK_7": ("B7_L24_PI_NW", "F_MARINA_MANGROVE_SE", [("B7_L23_PI_SW", "F_SANDS_MANGROVE_NE")]),
    "BLOCK_8": ("B8_L23_PI_NW", "F_SANDS_MANGROVE_SE", [("B8_L23_SW", "F_DRAIN40_MANGROVE_NE"),
                                                        ("B8_L22_NW", "F_DRAIN40_MANGROVE_SE"),
                                                        ("B8_L22_PI_SW", "F_CAPEHORN_MANGROVE_NE")]),
    "BLOCK_10": ("p13_nw", "BND:c4", []),
    "BLOCK_13": ("p11_pi_se", "F_SURFWOOD_MANGROVE_NW", [("p1_pi_ne", "F_CAPEHORN_MANGROVE_SW")]),
    "BLOCK_12": ("p5_sw", "F_BAYOU_MANGROVE_NE", [("p8_pi_nw", "F_SANSALVADORE_MANGROVE_SE")]),
    "BLOCK_11": ("p15_nw", "F_BAYOU_MANGROVE_SE", [("p14_sw", "F_SURFWOOD_MANGROVE_NE")]),
    "BLOCK_9": ("p27_pi", "F_CAPEHORN_MANGROVE_SE", [("p26_pi", "F_SANSALVADORE_MANGROVE_NE")]),
}
# Known-wrong or not-yet-anchorable blocks are listed, never silently dropped.
# block -> solver points that must fall on a vertex of the caption boundary (independent of the street network)
BOUNDARY_CHECKS = {
    "BLOCK_8": ["B8_L30_SE", "B8_L34_SE", "B8_L34_NE", "B8_L17_SE"],
    "BLOCK_7": ["B7_L11_SE"],
    "BLOCK_10": ["p13_sw", "p9_se", "p9_ne"],
    "BLOCK_12": ["p4_se", "p4_ne", "p_jog_c", "p_prm_san_salvadore"],
    "BLOCK_6": ["B6_BND_260_TOP", "B6_BND_PC", "B6_BND_PT", "B6_U", "B6_L12_SE"],
}
NOT_PLACED = {
}


def main():
    net = solve_network()
    fil = {f.id: f for f in net.fillets}
    solvers = get_all_block_solvers()

    bstart = {c["id"]: c["start"] for c in net.boundary}
    placed, checks = {}, []
    for bname, (a_pt, a_fid, chk) in ANCHORS.items():
        s = solvers[bname]
        src = s.points[a_pt]
        dst = fil[a_fid].corner if a_fid in fil else bstart[a_fid.split(":")[1]]  # "BND:cN" = caption course N's start
        dn, de = dst[0] - src.n, dst[1] - src.e
        worst = 0.0
        for c_pt, c_fid in chk:
            p = s.points[c_pt]
            r = math.hypot(p.n + dn - fil[c_fid].corner[0], p.e + de - fil[c_fid].corner[1])
            worst = max(worst, r)
            checks.append({"block": bname, "solver_point": c_pt, "fillet": c_fid,
                           "location": fil[c_fid].location, "residual_ft": round(r, 3)})
        bverts = [c["start"] for c in net.boundary]
        for c_pt in BOUNDARY_CHECKS.get(bname, []):
            p = s.points[c_pt]
            r = min(math.hypot(p.n + dn - v[0], p.e + de - v[1]) for v in bverts)
            worst = max(worst, r)
            checks.append({"block": bname, "solver_point": c_pt, "fillet": "nearest caption-boundary vertex",
                           "location": "plat boundary", "residual_ft": round(r, 3)})
        placed[bname] = {"shift": (dn, de), "worst_check_ft": round(worst, 3),
                         "n_checks": len(chk) + len(BOUNDARY_CHECKS.get(bname, [])), "ok": worst <= TOL}

    # ---------------- DXF ----------------
    dxf = DXFWriter()
    for name, col, lt in [("BOUNDARY", "white", "CONTINUOUS"), ("ROW", "yellow", "CONTINUOUS"),
                          ("CENTERLINE", "gray", "DASHED"), ("FILLET", "magenta", "CONTINUOUS"),
                          ("LOT", "cyan", "CONTINUOUS"), ("LOT-CURVE", "magenta", "CONTINUOUS"),
                          ("BLOCK-MISFIT", "red", "CONTINUOUS"), ("LOT-TEXT", "white", "CONTINUOUS"),
                          ("BLOCK-TEXT", "yellow", "CONTINUOUS"), ("TITLEBLOCK", "yellow", "CONTINUOUS")]:
        dxf.add_layer(name, col, lt)

    segs = []  # (layer, [(n, e), ...]) for the PNG
    for c in net.boundary:
        dxf.line(c["start"], c["end"], "BOUNDARY")
        segs.append(("BOUNDARY", [c["start"], c["end"]]))
    # The street network models Mangrove Ave up to the north boundary (c27) as a reference baseline. On the plat,
    # Mangrove begins at Starfish Ave (Block 18 Lots 1-3 are continuous north of it), so any Mangrove piece north of
    # the Starfish centerline is left out of the drawing.
    starfish_cl = net.streets["STARFISH"].centerline

    def north_of_starfish(street, pts):
        if "Mangrove" not in street:
            return False
        mid = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        side = starfish_cl.signed_offset(mid)
        ref = starfish_cl.signed_offset(fil["F_SAIL_MANGROVE_NE"].corner)   # a point known to be south of Starfish
        return side * ref < 0

    dropped = 0
    for street, pts in net.row_linework:
        if north_of_starfish(street, pts):
            dropped += 1
            continue
        dxf.polyline(pts, "ROW")
        segs.append(("ROW", pts))
    for r in net.runs:
        if north_of_starfish(r.street, [r.p0, r.p1]):
            dropped += 1
            continue
        dxf.line(r.p0, r.p1, "CENTERLINE")
        segs.append(("CENTERLINE", [r.p0, r.p1]))
    print(f"network pieces north of Starfish on Mangrove left out (not on the plat): {dropped}")
    for pc in net.placed_curves.values():
        pts = pc.arc_points(n_segments=48)
        dxf.polyline(pts, "CENTERLINE")
        segs.append(("CENTERLINE", pts))
    for f in net.fillets:
        dxf.polyline(f.arc_pts, "FILLET")
        segs.append(("FILLET", f.arc_pts))

    texts = []
    lot_count = 0
    for bname, info in placed.items():
        dn, de = info["shift"]
        s = solvers[bname]
        lot_layer = "LOT" if info["ok"] else "BLOCK-MISFIT"
        allp = []
        for num, res in s.solve_all().items():
            lot_count += 1
            for c in res.courses:
                if c.is_curve:
                    pts = [(p.n + dn, p.e + de) for p in c.arc_points]
                    layer = "LOT-CURVE" if info["ok"] else "BLOCK-MISFIT"
                else:
                    pts = [(c.start_pt.n + dn, c.start_pt.e + de), (c.end_pt.n + dn, c.end_pt.e + de)]
                    layer = lot_layer
                dxf.polyline(pts, layer)
                segs.append((layer, pts))
            v = s.lots[num].vertices
            cn = sum(p.n for p in v) / len(v) + dn
            ce = sum(p.e for p in v) / len(v) + de
            allp.append((cn, ce))
            dxf.text((cn, ce), num, height=6.0, layer="LOT-TEXT", halign=1, valign=2)
            texts.append((cn, ce, num, 4))
        bn = sum(p[0] for p in allp) / len(allp)
        be = sum(p[1] for p in allp) / len(allp)
        label = bname.replace("_", " ")
        dxf.text((bn, be), f"({label.split()[1]})", height=14.0, layer="BLOCK-TEXT", halign=1, valign=2)
        texts.append((bn, be, f"({label.split()[1]})", 9))

    xs = [p[1] for _, pts in segs for p in pts]
    ys = [p[0] for _, pts in segs for p in pts]
    tb = (max(ys) + 60, (min(xs) + max(xs)) / 2)
    dxf.text(tb, "BEACHWOOD UNIT TWO  --  PLAT BOOK 30, PAGES 82 & 82A, DUVAL COUNTY, FL (1960)", 20.0, "TITLEBLOCK", halign=1, valign=2)
    dxf.text((tb[0] - 30, tb[1]), f"Full plat composed from street network + {len(placed)} block solvers "
             f"({lot_count} lots). Not placed: {', '.join(NOT_PLACED) or 'none'}", 9.0, "TITLEBLOCK", halign=1, valign=2)

    d = out_dir(PLAT_ID)
    dxf_path = os.path.join(d, "PB0030_P0082_Beachwood_FullPlat_claude.dxf")
    dxf.save(dxf_path)

    # ---------------- PNG ----------------
    style = {"BOUNDARY": ("#000", 1.6, "-"), "ROW": ("#b58900", 0.7, "-"), "CENTERLINE": ("#999", 0.5, "--"),
             "FILLET": ("#c0c", 0.9, "-"), "LOT": ("#0a7", 0.6, "-"), "LOT-CURVE": ("#c0c", 0.8, "-"),
             "BLOCK-MISFIT": ("#e00", 0.9, "-")}
    fig, ax = plt.subplots(figsize=(18, 20))
    for layer, pts in segs:
        col, lw, ls = style[layer]
        ax.plot([p[1] for p in pts], [p[0] for p in pts], color=col, lw=lw, ls=ls)
    for n, e, s_, fs in texts:
        ax.text(e, n, s_, ha="center", va="center", fontsize=fs)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Beachwood Unit Two (PB 30 Pg 82/82A) - full plat, claude composition\n"
                 f"{len(placed)} blocks placed / {lot_count} lots; not yet placed: {', '.join(NOT_PLACED) or 'none'}", fontsize=11)
    fig.tight_layout()
    png_path = os.path.join(d, "PB0030_P0082_Beachwood_FullPlat.png")
    fig.savefig(png_path, dpi=150)
    plt.close(fig)

    save_metrics(PLAT_ID, {
        "plat_id": PLAT_ID,
        "source": "Plat/Duval_Plat_Book_30_Page_82-2.pdf (2 sheets)",
        "boundary_courses": len(net.boundary),
        "boundary_closure_ft": round(net.boundary_closure_ft, 4),
        "network_checks_failing": sum(not c.ok for c in net.checks),
        "blocks_placed": {k: {kk: vv for kk, vv in v.items() if kk != "shift"} for k, v in placed.items()},
        "block_corner_checks": checks,
        "lots_placed": lot_count,
        "not_placed": NOT_PLACED,
        "outputs": [os.path.relpath(dxf_path), os.path.relpath(png_path)],
    })

    print(f"boundary closure {net.boundary_closure_ft:.3f}'  network checks failing: {sum(not c.ok for c in net.checks)}")
    for b, v in placed.items():
        print(f"  {b:<9} checks {v['n_checks']}  worst {v['worst_check_ft']:8.3f}'  {'OK' if v['ok'] else 'MISFIT'}")
    for c in checks:
        print(f"     {c['block']:<9} {c['solver_point']:<14} vs {c['fillet']:<28} {c['residual_ft']:8.3f}'")
    print(f"lots placed: {lot_count}   not placed: {list(NOT_PLACED)}")
    print(f"-> {dxf_path}\n-> {png_path}")


if __name__ == "__main__":
    main()
