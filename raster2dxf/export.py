"""DXF (ezdxf, R2010) + PNG output.

Label alignment (survey drafting convention):
  * text rotation is taken from the *geometry* (line direction / arc
    tangent), never from the noisy OCR box angle, then flipped 180 deg if
    it would read upside down (text reads left-to-right or bottom-to-top);
  * text is justified CENTER horizontally and BOTTOM (above the line) or
    TOP (below the line) vertically, with the insertion point a uniform
    GAP = 0.5 x text height off the line -- so the visible gap between the
    glyphs and the line is the same for every label regardless of font
    ascent/descent, instead of a baseline-left anchor at the midpoint that
    makes below-line text sit on/over the line;
  * the label keeps the side of the line and the along-line station the
    draftsman used on the source (clamped to 10-90%), and when a bearing
    and a distance share a side they are stacked, not overprinted.
"""
from __future__ import annotations

import math

import cv2
import ezdxf
import numpy as np
from ezdxf.enums import TextEntityAlignment

LAYERS = {
    # name: (ACI color, linetype)
    "PLAT-LINE": (7, "CONTINUOUS"),
    "PLAT-LINE-DASH": (8, "DASHED"),
    "PLAT-CURVE": (4, "CONTINUOUS"),
    "PLAT-TEXT-BRG": (3, "CONTINUOUS"),
    "PLAT-TEXT-DIST": (2, "CONTINUOUS"),
    "PLAT-TEXT-CURVE": (6, "CONTINUOUS"),
    "PLAT-TEXT-LOTNO": (5, "CONTINUOUS"),
    "PLAT-TEXT-AREA": (5, "CONTINUOUS"),
    "PLAT-TEXT-MISC": (9, "CONTINUOUS"),
    "PLAT-TEXT-UNASSOC": (30, "CONTINUOUS"),
    "PLAT-TABLE-CURVE": (6, "CONTINUOUS"),
    "PLAT-TABLE": (6, "CONTINUOUS"),
    "PLAT-NOTES": (7, "CONTINUOUS"),
    "PLAT-QA": (1, "CONTINUOUS"),
    "PLAT-MON": (1, "CONTINUOUS"),
    "PLAT-TEXT-LOWCONF": (8, "CONTINUOUS"),     # frozen: unvalidated OCR, kept for review
}
FROZEN = {"PLAT-TEXT-LOWCONF"}
KIND_LAYER = {"bearing": "PLAT-TEXT-BRG", "distance": "PLAT-TEXT-DIST",
              "curve_id": "PLAT-TEXT-CURVE", "curve_data": "PLAT-TEXT-CURVE",
              "lot": "PLAT-TEXT-LOTNO", "area": "PLAT-TEXT-AREA", "table": "PLAT-TABLE",
              "text": "PLAT-TEXT-MISC"}
APPID = "RASTER2DXF"


class Frame:
    """pixel (x right, y down) -> world (X east, Y north, feet or px)."""

    def __init__(self, shape, ft_per_px, rotation_deg):
        self.h, self.w = shape[:2]
        self.s = ft_per_px or 1.0
        self.rot = math.radians(-rotation_deg)         # clockwise by rotation_deg
        self.c = np.array([self.w / 2 * self.s, self.h / 2 * self.s])

    def pt(self, p):
        q = np.array([p[0] * self.s, (self.h - p[1]) * self.s]) - self.c
        c, s = math.cos(self.rot), math.sin(self.rot)
        return np.array([c * q[0] - s * q[1], s * q[0] + c * q[1]]) + self.c

    def ang(self, img_deg):
        """image-direction angle (deg, y down) -> world CCW-from-east angle."""
        return (-img_deg + math.degrees(self.rot)) % 360


UPRIGHT_BAND = 5.0   # deg: near-vertical text always reads bottom-to-top


def upright(a):
    """Flip text that would read upside down.  The flip window is shifted by
    UPRIGHT_BAND so labels on near-vertical lines (85-95 / 265-275 deg) all
    end up reading bottom-to-top instead of flip-flopping around 90/270."""
    a %= 360
    return (a + 180) % 360 if 90 + UPRIGHT_BAND < a <= 270 + UPRIGHT_BAND else a


def aligned_placement(w1, w2, t, side_pt, text_h, stack=0):
    """Insertion point, rotation and alignment for a label parallel to the
    world segment w1->w2 at station t, on the side of side_pt.
    Returns (point, rotation_deg, TextEntityAlignment)."""
    d = w2 - w1
    L = float(np.hypot(*d))
    u = d / L
    left = np.array([-u[1], u[0]])
    side = 1.0 if float((side_pt - w1) @ left) >= 0 else -1.0
    rot = upright(math.degrees(math.atan2(u[1], u[0])))
    r = math.radians(rot)
    up = np.array([-math.sin(r), math.cos(r)])        # text "up" direction
    above = float(left @ up) * side > 0
    gap = 0.5 * text_h + stack * 1.4 * text_h
    base = w1 + u * (L * min(0.9, max(0.1, t)))
    p = base + left * side * gap
    return p, rot, (TextEntityAlignment.BOTTOM_CENTER if above else TextEntityAlignment.TOP_CENTER)


def trusted(lab, char_h) -> bool:
    """Unassociated OCR is only drawn when it is grammar-valid survey text or
    a confident, reasonably sized read; everything else goes to the frozen
    PLAT-TEXT-LOWCONF layer (still in the DXF for review, not plotted)."""
    t = lab.text.strip()
    if lab.kind in ("bearing", "curve_id", "curve_data", "area", "table"):
        return True
    if lab.kind == "distance":
        return lab.conf >= 50 and ("." in t or "'" in t)
    if lab.kind == "lot":
        return lab.conf >= 70 and lab.height >= 1.1 * char_h and t.isalnum()
    alnum = sum(c.isalnum() for c in t)
    return lab.conf >= 75 and alnum >= 3 and alnum >= 0.7 * len(t.replace(" ", ""))


def _new_doc(feet: bool):
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 2 if feet else 0
    doc.header["$MEASUREMENT"] = 0
    doc.appids.add(APPID)
    for name, (color, lt) in LAYERS.items():
        layer = doc.layers.add(name, color=color, linetype=lt)
        if name in FROZEN:
            layer.freeze()
    if "PLAT" not in doc.styles:
        doc.styles.add("PLAT", font="arial.ttf")
    return doc


def _rgb(bgr):
    b, g, r = bgr
    return (int(r), int(g), int(b))


def write_dxf(path, prep, linework, labels, cal, curve_table, char_h, notes=None, curve_blocks=()):
    fr = Frame(prep.ink.shape, cal["ft_per_px"], cal["rotation_deg"])
    doc = _new_doc(cal["ft_per_px"] is not None)
    msp = doc.modelspace()
    use_color = prep.kind == "render"
    text_h = float(np.median([l.height for l in labels if l.kind in ("bearing", "distance")]
                             or [char_h])) * fr.s * 0.9
    lab_by_geom: dict = {}
    for lab in labels:
        if lab.assoc:
            lab_by_geom.setdefault(lab.assoc["geom"], []).append(lab)

    geom_world = {}
    for l in linework.lines:
        w1, w2 = fr.pt(l.p1), fr.pt(l.p2)
        geom_world[("L", l.id)] = (w1, w2)
        e = msp.add_line(w1, w2, dxfattribs={"layer": "PLAT-LINE-DASH" if l.dashed else "PLAT-LINE"})
        if use_color:
            e.rgb = _rgb(l.color)
        xd = [(1000, f"line {l.id}"), (1040, round(l.length * fr.s, 3)), (1040, round(l.coverage, 3))]
        for lab in lab_by_geom.get(("L", l.id), []):
            xd.append((1000, f"{lab.kind}={lab.text}"))
        e.set_xdata(APPID, xd)
    for a in linework.arcs:
        c = fr.pt(a.center)
        p1, p2 = fr.pt(a.p1), fr.pt(a.p2)
        a1 = math.degrees(math.atan2(*(p1 - c)[::-1]))
        a2 = math.degrees(math.atan2(*(p2 - c)[::-1]))
        # image sweep sign flips with the y-axis: positive image sweep = clockwise in world
        if a.sweep > 0:
            a1, a2 = a2, a1
        e = msp.add_arc(c, a.r * fr.s, a1, a2, dxfattribs={"layer": "PLAT-CURVE"})
        if use_color:
            e.rgb = _rgb(a.color)
        xd = [(1000, f"arc {a.id}"), (1040, round(a.r * fr.s, 3)), (1040, round(a.length * fr.s, 3))]
        for lab in lab_by_geom.get(("A", a.id), []):
            xd.append((1000, f"{lab.kind}={lab.text}"))
            if lab.kind == "curve_id" and lab.value in curve_table:
                rec = curve_table[lab.value]
                for k in ("R", "L", "CH", "T", "delta"):
                    if rec.get(k) is not None:
                        xd.append((1000, f"{k}={rec[k]}"))
        e.set_xdata(APPID, xd)
        geom_world[("A", a.id)] = (c, a)

    for m in getattr(linework, "monuments", []):
        c = fr.pt(m.center)
        msp.add_circle(c, m.r * fr.s, dxfattribs={"layer": "PLAT-MON"})
        msp.add_point(c, dxfattribs={"layer": "PLAT-MON"})
    for geom, labs in lab_by_geom.items():
        sides: dict = {}
        labs.sort(key=lambda l: abs(l.assoc["offset"]))
        for lab in labs:
            src = fr.pt(lab.center)
            if geom[0] == "L":
                w1, w2 = geom_world[geom]
            else:
                c, a = geom_world[geom]
                t = min(0.9, max(0.1, lab.assoc["t"]))
                pa = fr.pt(a.point(t))
                pb = fr.pt(a.point(min(1.0, t + 0.01)))
                tan = pb - pa
                if np.hypot(*tan) == 0:
                    continue
                tan /= np.hypot(*tan)
                w1, w2 = pa - tan, pa + tan
                lab.assoc = dict(lab.assoc, t=0.5)
            d = w2 - w1
            left = np.array([-d[1], d[0]])
            side = 1 if float((src - w1) @ left) >= 0 else -1
            stack = sides.get(side, 0)
            sides[side] = stack + 1
            p, rot, align = aligned_placement(w1, w2, lab.assoc["t"], src, text_h, stack)
            txt = lab.value["text"] if lab.kind == "bearing" else lab.text
            if lab.kind == "bearing" and lab.value.get("dist"):
                txt += f" - {lab.value['dist']:.2f}'"
            if lab.kind == "distance":
                txt = f"{lab.value:.2f}'" if "." in lab.text else f"{int(lab.value)}'"
            e = msp.add_text(txt.replace("°", "%%d"), height=text_h,
                             dxfattribs={"layer": KIND_LAYER[lab.kind], "rotation": rot, "style": "PLAT"})
            e.set_placement(p, align=align)
    med_h = float(np.median([l.height for l in labels] or [char_h]))
    for lab in labels:
        if lab.assoc or lab.kind == "empty" or not lab.text:
            continue
        layer = "PLAT-TEXT-UNASSOC" if lab.kind in ("bearing", "distance") else KIND_LAYER[lab.kind]
        if not trusted(lab, char_h) or (notes and notes[0] and lab.kind == "text"):
            layer = "PLAT-TEXT-LOWCONF"      # (notes image: the MTEXT is the readable copy)
        h = min(lab.height, 1.6 * med_h) * fr.s * (1.0 if lab.kind in ("lot",) else 0.9)
        rot = upright(fr.ang(lab.angle))
        e = msp.add_text(lab.text.replace("°", "%%d"), height=h,
                         dxfattribs={"layer": layer, "rotation": rot, "style": "PLAT"})
        e.set_placement(fr.pt(lab.center), align=TextEntityAlignment.MIDDLE_CENTER)
    # curve-data blocks: one clean, solved label per block + XDATA on its arc
    arcs_by_id = {e.get_xdata(APPID)[0][1]: e for e in msp.query("ARC") if e.has_xdata(APPID)}
    for b in curve_blocks:
        if not b.get("R") or not b.get("delta"):
            continue
        dv = b["derived"]
        parts = [f"%%c={_fmt_dms(b['delta'])}{'*' if 'delta' in dv else ''}",
                 f"R={b['R']:.2f}'{'*' if 'R' in dv else ''}"]
        for k in ("T", "L"):
            v = b["fields"].get(k, dv.get(k))
            if v:
                parts.append(f"{k}={v:.2f}'{'*' if k in dv else ''}")
        txt = "  ".join(parts) + ("" if b["consistent"] else "  (UNCHECKED)")
        e = msp.add_text(txt, height=text_h, dxfattribs={"layer": "PLAT-TEXT-CURVE", "style": "PLAT"})
        e.set_placement(fr.pt(b["center"]) - np.array([0, 1.5 * text_h]), align=TextEntityAlignment.TOP_CENTER)
        arc = arcs_by_id.get(f"arc {b['arc']}") if b.get("arc") is not None else None
        if arc is not None:
            xd = list(arc.get_xdata(APPID)) + [(1000, f"CURVE_DATA R={b['R']:.2f} D={b['delta']:.4f} "
                                                      f"consistent={b['consistent']}")]
            arc.set_xdata(APPID, xd)
    # text-only image: the notes as one paragraph (fragment labels are then
    # left on their layers for review but the MTEXT is the readable copy)
    if notes and notes[0]:
        mt = msp.add_mtext(notes[0].replace("°", "%%d"), dxfattribs={"layer": "PLAT-NOTES", "style": "PLAT",
                                                                     "char_height": char_h * fr.s * 0.8})
        mt.set_location(fr.pt((0.02 * fr.w, 0.02 * fr.h)), attachment_point=1)
        mt.dxf.width = 0.96 * fr.w * fr.s
    # QA markers
    by_id = {l.id: l for l in labels}
    for q in cal["qa"]:
        lab = by_id[q["label"]]
        p = fr.pt(lab.center)
        msp.add_circle(p, 1.2 * text_h + lab.width * fr.s / 2, dxfattribs={"layer": "PLAT-QA"})
        note = (f"MEAS {q['measured']:.2f}" if q["kind"] == "distance"
                else f"MEAS AZ {q['measured_az']:.1f}")
        msp.add_text(note, height=text_h * 0.7, dxfattribs={"layer": "PLAT-QA"}).set_placement(
            p + np.array([0, -1.6 * text_h - lab.height * fr.s]), align=TextEntityAlignment.TOP_CENTER)
    # rebuilt curve table, right of the drawing
    if curve_table:
        x0 = fr.w * fr.s * 1.05
        y0 = fr.h * fr.s
        th = text_h
        cols = ["CURVE", "RADIUS", "LENGTH", "CHORD", "TANGENT", "DELTA"]
        for j, c in enumerate(cols):
            msp.add_text(c, height=th, dxfattribs={"layer": "PLAT-TABLE-CURVE"}).set_placement(
                (x0 + j * 9 * th, y0), align=TextEntityAlignment.BOTTOM_LEFT)
        for i, (cid, rec) in enumerate(sorted(curve_table.items(), key=lambda kv: int(kv[0][1:]))):
            vals = [cid] + [f"{rec[k]:.2f}" if rec.get(k) else "" for k in ("R", "L", "CH", "T")] \
                + [_fmt_dms(rec["delta"]) if rec.get("delta") else ""]
            for j, v in enumerate(vals):
                msp.add_text(v, height=th, dxfattribs={"layer": "PLAT-TABLE-CURVE"}).set_placement(
                    (x0 + j * 9 * th, y0 - (i + 1) * 1.6 * th), align=TextEntityAlignment.BOTTOM_LEFT)
    doc.saveas(path)
    return doc


def _fmt_dms(x):
    d = int(x)
    m = int((x - d) * 60)
    s = round(((x - d) * 60 - m) * 60)
    if s == 60:
        m, s = m + 1, 0
    return f"{d}%%d{m:02d}'{s:02d}\""


def render_png(doc, path, max_px=3000):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf import bbox
    ext = bbox.extents(doc.modelspace())
    if not ext.has_data:
        return
    w, h = ext.size.x, ext.size.y
    asp = w / h if h else 1
    fw = 12 if asp >= 1 else max(4, 12 * asp)
    fh = fw / asp if asp else 12
    dpi = max(80, min(300, int(max_px / max(fw, fh))))
    fig = plt.figure(figsize=(fw, fh))
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(doc)
    # WHITE background: ACI 7 ("white/black") is drawn black, as in paper space
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE,
                        color_policy=ColorPolicy.COLOR)
    Frontend(ctx, MatplotlibBackend(ax), config=cfg).draw_layout(doc.modelspace(), finalize=True)
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)


def render_overlay(path, prep, linework, labels, max_px=2400):
    base = prep.color.copy()
    base = cv2.addWeighted(base, 0.35, np.full_like(base, 255 if not prep.dark_bg else 0), 0.65, 0)
    th = max(1, int(round(prep.stroke_w * 0.6)))
    for l in linework.lines:
        cv2.line(base, tuple(np.round(l.p1).astype(int)), tuple(np.round(l.p2).astype(int)),
                 (0, 0, 230) if not l.dashed else (0, 140, 255), th, cv2.LINE_AA)
    for a in linework.arcs:
        cv2.polylines(base, [np.round(a.sample()).astype(np.int32)], False, (230, 80, 0), th + 1, cv2.LINE_AA)
    colors = {"bearing": (0, 160, 0), "distance": (0, 170, 200), "curve_id": (200, 0, 200),
              "curve_data": (200, 0, 200), "lot": (200, 60, 60), "area": (200, 60, 60)}
    for lab in labels:
        if lab.box is None or not lab.text:
            continue
        c = colors.get(lab.kind, (150, 150, 150))
        cv2.polylines(base, [lab.box.astype(np.int32)], True, c, 1 if lab.assoc or lab.kind not in
                      ("bearing", "distance") else 3, cv2.LINE_AA)
    h, w = base.shape[:2]
    s = min(1.0, max_px / max(h, w))
    if s < 1:
        base = cv2.resize(base, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(path, base)
