"""Beachwood Unit Two -- combined DXF: the road right-of-way map + the full-plat blocks and lots, in one file.

  * right-of-way content comes from engine.cogo_road_centerlines (C-BOUNDARY, C-ROAD-ROW-EDGE, C-ROAD-FILLET, C-ROAD-CNTR,
    C-ROAD-CURV, C-ROAD-ALIGNMENT, C-ROAD-PI-TANGENT, C-ROAD-TEXT street names / curve data, C-ROAD-INTX / TIE points, CONTROL);
  * blocks and lots come from scripts/plat_folder/build_beachwood_full.py (LOT, LOT-CURVE, BLOCK-MISFIT, LOT-TEXT, BLOCK-TEXT);
    its own simpler BOUNDARY / ROW / CENTERLINE / FILLET copies are dropped so nothing is drawn twice.
Both are built in the same local grid (Starfish Ave CL x Mangrove Ave CL = N 10000, E 10000), so no transformation is applied.
The road map's Mangrove Ave pieces north of Starfish Ave are left out: on the plat Mangrove begins at Starfish (Block 18 Lots 1-2
run through there -- see REFINEMENT_LOG tick 8).
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine import dxf_writer
from engine.dxf_writer import writer_suffix  # noqa: E402
from engine.cogo_road_centerlines import BeachwoodRoadCenterlineEngine  # noqa: E402
from scripts.plat_folder.common import out_dir  # noqa: E402

PLAT_ID = "PB30_P82_Beachwood"
ROAD_LINEWORK = {"C-ROAD-ROW-EDGE", "C-ROAD-CNTR", "C-ROAD-ALIGNMENT", "C-ROAD-PI-TANGENT"}
FULLPLAT_KEEP = {"LOT", "LOT-CURVE", "BLOCK-MISFIT", "LOT-TEXT", "BLOCK-TEXT", "TITLEBLOCK"}


def capture(build):
    """Run a builder that ends in DXFWriter.save() and return the writer instead of writing the file."""
    got = {}
    orig = dxf_writer.DXFWriter.save
    dxf_writer.DXFWriter.save = lambda self, path: got.setdefault("w", self)
    try:
        build()
    finally:
        dxf_writer.DXFWriter.save = orig
    return got["w"]


def layer_of(ent):
    return ent.split("\n")[3]


def vertices(ent):
    """(E, N) pairs of an entity (DXF group codes 10/20 and 11/21)."""
    lines = ent.split("\n")
    pts, x = [], None
    for code, val in zip(lines[0::2], lines[1::2]):
        if code in ("10", "11"):
            x = float(val)
        elif code in ("20", "21") and x is not None:
            pts.append((x, float(val)))
            x = None
    return pts


def mangrove_north_of_starfish(ent):
    """Road-map linework in the Mangrove corridor north of the Starfish centreline (not on the plat)."""
    if layer_of(ent) not in ROAD_LINEWORK:
        return False
    pts = vertices(ent)
    return (bool(pts) and all(9950.0 <= e <= 10050.0 and n >= 9999.0 for e, n in pts)
            and any(n > 10005.0 for _, n in pts))


def main():
    road = capture(lambda: BeachwoodRoadCenterlineEngine(base_n=10000.0, base_e=10000.0).export_dxf("unused.dxf"))
    import scripts.plat_folder.build_beachwood_full as full
    plat = capture(full.main)

    out = dxf_writer.DXFWriter()
    for name, lay in {**road.layers, **{k: v for k, v in plat.layers.items() if k in FULLPLAT_KEEP}}.items():
        out.layers[name] = lay
    out.custom_linetypes = set(road.custom_linetypes) | set(plat.custom_linetypes)
    out.styles.update(road.styles)
    out.styles.update(plat.styles)
    dropped = [e for e in road.entities if mangrove_north_of_starfish(e)]
    out.entities = []
    clipped = 0
    for e in road.entities:
        if e in dropped or layer_of(e) == "TITLEBLOCK":
            continue
        if e.split("\n")[1] in ("TEXT", "POINT") and ("Mangrove" in e or "STA " in e) or (e.split("\n")[1] == "POINT" and layer_of(e).startswith("C-ROAD")):
            pts = vertices(e)
            if pts and 9900.0 <= pts[0][0] <= 10100.0 and pts[0][1] > 10030.0:   # labels / points for Mangrove north of Starfish
                clipped += 1
                continue
        if layer_of(e) in ROAD_LINEWORK and e.split("\n")[1] == "POLYLINE":
            pts = vertices(e)
            keep = [pt for pt in pts if not (9950.0 <= pt[0] <= 10050.0 and pt[1] > 10005.0)]
            if len(keep) != len(pts):                        # a long baseline running on north of Starfish: clip it
                clipped += 1
                if len(keep) >= 2:
                    tmp = dxf_writer.DXFWriter()
                    tmp.polyline([(n_, e_) for e_, n_ in keep], layer_of(e))
                    out.entities.append(tmp.entities[-1])
                continue
        out.entities.append(e)
    out.entities += [e for e in plat.entities if layer_of(e) in FULLPLAT_KEEP]
    out.text((10300.0, 10560.0), f"BEACHWOOD UNIT TWO - COMBINED RIGHT-OF-WAY MAP + BLOCKS ({writer_suffix().strip('_')})", 20.0, "TITLEBLOCK", halign=1, valign=2)
    # L#/C# course tags keyed to Sheet 2 (Line & Curve Tables)
    from scripts.plat_folder.beachwood_tables_mapcheck import course_tags
    out.add_layer("COURSE-TAG", "green")
    for n_, e_, tag in course_tags():
        out.text((n_, e_), tag, 2.6, "COURSE-TAG", halign=1, valign=2)

    path = os.path.join(out_dir(PLAT_ID), f"PB0030_P0082_Beachwood_Combined_ROW_Blocks{writer_suffix()}.dxf")
    out.save(path)
    counts = {}
    for e in out.entities:
        counts[layer_of(e)] = counts.get(layer_of(e), 0) + 1
    print(f"road entities {len(road.entities)} (dropped {len(dropped)}, clipped {clipped} Mangrove-north-of-Starfish), "
          f"plat entities kept {sum(1 for e in plat.entities if layer_of(e) in FULLPLAT_KEEP)}")
    for k in sorted(counts):
        print(f"  {k:<20} {counts[k]}")
    print(f"-> {path}")

    # PNG preview straight from the merged entities
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    style = {"C-BOUNDARY": ("#000", 1.6), "C-ROAD-ROW-EDGE": ("#b58900", 0.7), "C-ROAD-FILLET": ("#c0c", 0.9),
             "C-ROAD-CNTR": ("#999", 0.5), "C-ROAD-CURV": ("#999", 0.5), "C-ROAD-ALIGNMENT": ("#bbb", 0.4),
             "C-ROAD-PI-TANGENT": ("#ccc", 0.3), "LOT": ("#0a7", 0.6), "LOT-CURVE": ("#c0c", 0.8), "BLOCK-MISFIT": ("#e00", 0.9)}
    fig, ax = plt.subplots(figsize=(18, 20))
    for e in out.entities:
        lay = layer_of(e)
        kind = e.split("\n")[1]
        pts = vertices(e)
        if kind in ("LINE", "POLYLINE") and lay in style and len(pts) >= 2:
            col, lw = style[lay]
            ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, lw=lw)
        elif kind == "TEXT" and lay in ("C-ROAD-TEXT", "BLOCK-TEXT") and pts:
            txt = e.split("\n")[e.split("\n").index("1") + 1] if "1" in e.split("\n") else ""
            ax.text(pts[0][0], pts[0][1], txt.replace("%%d", "°"), fontsize=3.2 if lay == "C-ROAD-TEXT" else 9,
                    color="#555" if lay == "C-ROAD-TEXT" else "#000", ha="center", va="center")
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"Beachwood Unit Two (PB 30 Pg 82/82A) - combined right-of-way map + blocks ({writer_suffix().strip('_')})")
    fig.tight_layout()
    png = path.replace(f"{writer_suffix()}.dxf", ".png")
    fig.savefig(png, dpi=150)
    plt.close(fig)
    print(f"-> {png}")
    return path


if __name__ == "__main__":
    main()
