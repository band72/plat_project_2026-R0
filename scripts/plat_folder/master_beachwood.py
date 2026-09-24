"""Beachwood Unit Two -- MASTER PLAT: one DXF with
    top:    combined linework (road R/W map + blocks + lots), lot lines/curves labelled only with their L# / C# tag;
    middle: LINE TABLE and CURVE TABLE (Sheet 2);
    bottom: MAP CHECK SUMMARY (Sheet 3), below the curve table.
Built from the same writers that produce the three separate sheets, so all four files always agree.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from engine import dxf_writer
from engine.dxf_writer import writer_suffix  # noqa: E402
from scripts.plat_folder.common import out_dir  # noqa: E402

PLAT_ID = "PB30_P82_Beachwood"
GAP = 150.0


def capture_all(build):
    """Run a builder, returning every DXFWriter it would have saved (in order) instead of writing files."""
    got = []
    orig = dxf_writer.DXFWriter.save
    dxf_writer.DXFWriter.save = lambda self, path: got.append(self)
    try:
        build()
    finally:
        dxf_writer.DXFWriter.save = orig
    return got


def shift(ent, dn, de):
    """Translate a DXF entity string: group codes 10/11 are Easting, 20/21 Northing."""
    lines = ent.split("\n")
    for i in range(0, len(lines) - 1, 2):
        c = lines[i].strip()
        if c in ("10", "11"):
            lines[i + 1] = f"{float(lines[i + 1]) + de:.4f}"
        elif c in ("20", "21"):
            lines[i + 1] = f"{float(lines[i + 1]) + dn:.4f}"
    return "\n".join(lines)


def bbox(writer):
    es, ns = [], []
    for ent in writer.entities:
        lines = ent.split("\n")
        for i in range(0, len(lines) - 1, 2):
            if lines[i].strip() in ("10", "11"):
                es.append(float(lines[i + 1]))
            elif lines[i].strip() in ("20", "21"):
                ns.append(float(lines[i + 1]))
    return min(ns), max(ns), min(es), max(es)          # n_min, n_max, e_min, e_max


def main():
    import contextlib
    import io
    import scripts.plat_folder.beachwood_tables_mapcheck as tm
    import scripts.plat_folder.combine_beachwood as cb
    with contextlib.redirect_stdout(io.StringIO()):
        plan = [w for w in capture_all(cb.main) if any("COURSE-TAG" in e for e in w.entities)][-1]
        sheet2, sheet3 = [w for w in capture_all(tm.write_sheets)][-2:]

    master = dxf_writer.DXFWriter()
    for w in (plan, sheet2, sheet3):
        master.layers.update(w.layers)
        master.custom_linetypes |= set(w.custom_linetypes)
        master.styles.update(w.styles)
    master.entities = [e for e in plan.entities if e.split("\n")[3] != "TITLEBLOCK"]   # master carries its own title

    pn0, pn1, pe0, pe1 = bbox(plan)
    t_n0, t_n1, t_e0, _ = bbox(sheet2)
    dn2, de2 = (pn0 - GAP) - t_n1, pe0 - t_e0          # tables: top just below the plan, left-aligned with it
    master.entities += [shift(e, dn2, de2) for e in sheet2.entities]
    m_n0, m_n1, m_e0, _ = bbox(sheet3)
    dn3, de3 = (t_n0 + dn2 - GAP) - m_n1, pe0 - m_e0     # map checks: below the curve / line tables
    master.entities += [shift(e, dn3, de3) for e in sheet3.entities]

    master.text((pn1 + 120.0, pe0), f"BEACHWOOD UNIT TWO  --  PLAT BOOK 30, PAGES 82 & 82A, DUVAL COUNTY, FLORIDA  --  MASTER PLAT ({writer_suffix().strip('_')})",
                28.0, "TITLEBLOCK")
    master.text((pn1 + 80.0, pe0), "Plan (top) -- lot lines and curves are tagged L# / C#; see LINE and CURVE TABLES (middle) and "
                "LOT MAP CHECKS (bottom).", 12.0, "TITLEBLOCK")

    path = os.path.join(out_dir(PLAT_ID), f"PB0030_P0082_Beachwood_MasterPlat{writer_suffix()}.dxf")
    master.save(path)
    n0, n1, e0, e1 = bbox(master)
    print(f"entities {len(master.entities)}  extents N {n0:.0f}..{n1:.0f}  E {e0:.0f}..{e1:.0f}")
    print(f"-> {path}")
    return path


if __name__ == "__main__":
    main()
