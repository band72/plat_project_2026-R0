"""Tests for raster2dxf (raster plat -> DXF) and engine.labels alignment."""
import math

import cv2
import ezdxf
import numpy as np
import pytest
from ezdxf.enums import TextEntityAlignment

from engine.labels import course_label_positions
from raster2dxf import associate as A
from raster2dxf import linework as LW
from raster2dxf import text as T
from raster2dxf.export import Frame, aligned_placement, upright


# ------------------------------------------------------------ label alignment
@pytest.mark.parametrize("az", range(0, 360, 15))
def test_engine_labels_bearing_above_distance_below_never_upside_down(az):
    n2, e2 = 100 * math.cos(math.radians(az)), 100 * math.sin(math.radians(az))
    p = course_label_positions(0, 0, n2, e2, 2.0, 2.0)
    rot = p["angle"]
    assert not (95 < rot <= 275), "text would read upside down"
    r = math.radians(rot)
    up = np.array([math.cos(r), -math.sin(r)])          # (N, E)
    mid = np.array([n2 / 2, e2 / 2])
    assert (np.array(p["bearing_pos"]) - mid) @ up == pytest.approx(2.0)
    assert (np.array(p["distance_pos"]) - mid) @ up == pytest.approx(-2.0)
    assert p["bearing_align"] == (1, 1) and p["distance_align"] == (1, 3)


@pytest.mark.parametrize("ang", range(0, 360, 20))
@pytest.mark.parametrize("side", [1, -1])
def test_aligned_placement_uniform_gap_and_justification(ang, side):
    u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
    w1, w2 = np.zeros(2), 100 * u
    left = np.array([-u[1], u[0]])
    src = 50 * u + side * 7 * left
    p, rot, align = aligned_placement(w1, w2, 0.5, src, text_h=4.0)
    # insertion point is exactly GAP = 0.5*h off the line, on the source side
    off = (p - w1) @ left
    assert off == pytest.approx(side * 2.0)
    assert (p - w1) @ u == pytest.approx(50.0)
    assert not (95 < rot <= 275)
    r = math.radians(rot)
    up = np.array([-math.sin(r), math.cos(r)])
    above = (side * left) @ up > 0
    # text above the line hangs from its bottom, text below from its top,
    # so glyphs never overlap the line on either side
    assert align == (TextEntityAlignment.BOTTOM_CENTER if above else TextEntityAlignment.TOP_CENTER)
    # rotation parallel to the line
    assert abs(math.sin(math.radians(rot - ang))) < 1e-9


def test_aligned_placement_stacks_second_label():
    p0, _, _ = aligned_placement(np.zeros(2), np.array([100.0, 0]), 0.5, np.array([50.0, 5]), 4.0, 0)
    p1, _, _ = aligned_placement(np.zeros(2), np.array([100.0, 0]), 0.5, np.array([50.0, 5]), 4.0, 1)
    assert p1[1] - p0[1] == pytest.approx(1.4 * 4.0)


def test_upright():
    assert upright(270) == 90 and upright(180) == 0 and upright(90) == 90
    assert upright(272) == 92 and upright(93) == 93 and upright(100) == 280
    # all near-vertical lines, either direction, read bottom-to-top
    for a in (86, 90, 94, 266, 270, 274):
        assert 84 <= upright(a) <= 96


# ------------------------------------------------------------ OCR grammar
@pytest.mark.parametrize("raw,text", [
    ('N.87°35\'30"E.', 'N 87°35\'30" E'),
    ('S.89°58\'20"W', 'S 89°58\'20" W'),
    ("N2°24'30\"W", 'N 02°24\'30" W'),
])
def test_parse_bearing(raw, text):
    b = T.parse_bearing(raw)
    assert b and b["text"] == text


@pytest.mark.parametrize("raw,val", [("93.50'", 93.5), ("100.44°", 100.44), ("=76.78'", 76.78),
                                      ("75'", 75.0), ("-83.26—", 83.26)])
def test_classify_distance(raw, val):
    kind, v = T.classify(raw, 20, 20)
    assert kind == "distance" and v == pytest.approx(val)


def test_classify_other_kinds():
    assert T.classify("C12", 20, 20) == ("curve_id", "C12")
    assert T.classify("24", 30, 20)[0] == "lot"
    assert T.classify("R=25.00", 20, 20)[0] == "curve_data"


def test_bearing_azimuth_quadrants():
    az = lambda s: T.bearing_azimuth(T.parse_bearing(s))
    assert az('N10°00\'00"E') == pytest.approx(10)
    assert az('S10°00\'00"E') == pytest.approx(170)
    assert az('S10°00\'00"W') == pytest.approx(190)
    assert az('N10°00\'00"W') == pytest.approx(350)


def test_curve_columns_inferred_from_consistency():
    R, D = 25.0, math.radians(90)
    L, CH = R * D, 2 * R * math.sin(D / 2)
    rec = A._infer_columns([L, R, CH], 90.0)      # out-of-order columns
    assert rec["R"] == pytest.approx(R) and rec["L"] == pytest.approx(L)
    assert rec["CH"] == pytest.approx(CH) and rec["consistency"] < 1e-3


# ------------------------------------------------------------ linework
def _canvas():
    img = np.zeros((400, 600), np.uint8)
    cv2.line(img, (50, 50), (550, 50), 255, 4)
    cv2.line(img, (50, 50), (50, 350), 255, 4)
    cv2.ellipse(img, (300, 250), (100, 100), 0, 0, 90, 255, 4)
    return img


def test_extract_lines_and_arc():
    lw = LW.extract(_canvas(), 4.0, 14.0)
    long_ = [l for l in lw.lines if l.length > 200]
    assert len(long_) >= 2
    angs = sorted(round(l.angle) % 180 for l in long_)
    assert 0 in angs and 90 in angs
    assert lw.arcs, "quarter circle should be fitted as an arc"
    a = max(lw.arcs, key=lambda a: a.length)
    assert a.r == pytest.approx(100, rel=0.05)
    assert abs(math.degrees(a.sweep)) == pytest.approx(90, abs=10)


def test_corner_snapped_to_intersection():
    lw = LW.extract(_canvas(), 4.0, 14.0)
    ends = [p for l in lw.lines for p in (l.p1, l.p2)]
    assert min(np.hypot(*(p - np.array([50, 50]))) for p in ends) < 2.0


def test_collinear_merge_marks_dashed():
    segs = [LW.Line(np.array([x, 10.0]), np.array([x + 10, 10.0])) for x in range(0, 200, 20)]
    out = LW.merge_collinear(segs, gap_tol=12)
    assert len(out) == 1 and out[0].dashed and out[0].length == pytest.approx(190)


def test_frame_arc_direction_survives_y_flip(tmp_path):
    """A quarter arc drawn clockwise on screen must come out as the same
    screen-space quarter in the DXF (start/end swapped for the y flip)."""
    arc = LW.Arc(center=np.array([100.0, 100.0]), r=50, a0=0.0, sweep=math.pi / 2)  # screen: E -> S
    fr = Frame((200, 200), None, 0.0)
    c = fr.pt(arc.center)
    mid = fr.pt(arc.point(0.5))
    ang_mid = math.degrees(math.atan2(*(mid - c)[::-1])) % 360
    assert ang_mid == pytest.approx(315)   # screen SE == world SE (y up)


# ------------------------------------------------ geometry-constrained decoding
def _lab(i, center, angle, alts):
    lab = T.Label(id=i, center=np.array(center, float), angle=angle, width=60, height=14)
    lab.alts = alts
    T.apply_alt(lab, alts[0])
    lab.angle0 = angle - alts[0][1]
    return lab


def _alt(txt, conf, rot=0):
    kind, val = T.classify(txt, 14, 14)
    return (conf, rot, txt, conf, kind, val)


def test_reconcile_picks_geometry_consistent_reading():
    """Scale 0.25 ft/px.  Lines of 400/200/399.2 px carry 100.00', 50.00',
    99.80'.  The 99.80' label's top OCR read is the upside-down '866'' --
    reconcile must find the scale from the other two and pick 99.80'."""
    lines = [LW.Line(np.array([0.0, 0]), np.array([400.0, 0])),
             LW.Line(np.array([0.0, 100]), np.array([200.0, 100])),
             LW.Line(np.array([0.0, 300]), np.array([399.2, 300]))]
    for k, l in enumerate(lines):
        l.id = k
    lw = LW.Linework(lines=lines, arcs=[])
    labels = [_lab(0, (200, -10), 0, [_alt("100.00'", 80)]),
              _lab(1, (100, 90), 0, [_alt("50.00'", 80)]),
              _lab(2, (200, 290), 0, [_alt("866'", 85, 0), _alt("99.80'", 60, 180)])]
    cal = A.reconcile(labels, lw, 14.0)
    assert cal["ft_per_px"] == pytest.approx(0.25, rel=1e-3)
    assert labels[2].value == pytest.approx(99.80) and labels[2].verified
    assert labels[2].assoc["geom"] == ("L", 2)
    assert labels[2].angle % 360 == pytest.approx(180)


def test_reconcile_bearing_digit_split():
    """Three bearings fix rotation 0; 'N2024'30"W' on a line at azimuth
    ~2.4 deg west of north must decode as N 02°24'30" W, not 20°24'."""
    def seg(az_deg, y0):
        a = math.radians(az_deg)
        d = np.array([math.sin(a), -math.cos(a)])       # image: x right, y down
        p1 = np.array([500.0 + y0, 500.0])
        return LW.Line(p1, p1 + 300 * d)
    lines = [seg(10, 0), seg(45, 300), seg(80, 600), seg(-2.4083, 900)]
    for k, l in enumerate(lines):
        l.id = k
    lw = LW.Linework(lines=lines, arcs=[])
    labs = []
    for k, (l, txt) in enumerate(zip(lines, ['N10°00\'00"E', 'N45°00\'00"E', 'N80°00\'00"E', 'N2024\'30"W'])):
        mid = (l.p1 + l.p2) / 2
        d = l.p2 - l.p1
        ang = math.degrees(math.atan2(d[1], d[0]))
        n = np.array([-d[1], d[0]]) / np.hypot(*d)
        labs.append(_lab(k, mid + 10 * n, ang, [_alt(txt, 70)]))
    cal = A.reconcile(labs, lw, 14.0)
    assert cal["rotation_deg"] == pytest.approx(0, abs=0.5)
    assert labs[3].value["text"] == 'N 02°24\'30" W' and labs[3].verified


def test_render_low_contrast_stroke_is_ink(tmp_path):
    """Dark-theme render: a blue stroke on a navy fill (diff ~66, below an
    Otsu threshold set by bright white text) must still be ink; a faint
    gridline (diff ~27) must not."""
    from raster2dxf.preprocess import prepare
    img = np.full((400, 600, 3), (34, 27, 22), np.uint8)             # bg #161b22
    cv2.rectangle(img, (50, 50), (550, 350), (78, 45, 23), -1)        # lot fill
    cv2.line(img, (300, 60), (300, 340), (130, 90, 60), 3)            # lot line, low contrast
    cv2.line(img, (0, 20), (599, 20), (61, 54, 48), 1)                # faint gridline
    for x in range(80, 520, 40):
        cv2.putText(img, "LOT", (x, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    path = str(tmp_path / "r.png")
    cv2.imwrite(path, img)
    p = prepare(path)
    assert p.kind == "render"
    assert (p.ink[150:300, 298:303] > 0).mean() > 0.8
    assert (p.ink[20, 100:500] > 0).mean() < 0.05



def test_render_text_mask_uses_strict_threshold(tmp_path):
    """Renders: the low linework threshold must not leak into the text mask
    (faint strokes stay linework-only; bright text is in both)."""
    from raster2dxf.preprocess import prepare
    img = np.full((300, 400, 3), (34, 27, 22), np.uint8)
    cv2.line(img, (200, 10), (200, 290), (80, 70, 60), 2)           # faint stroke (diff ~50)
    for y in range(40, 290, 30):                                     # text-heavy, like real renders
        cv2.putText(img, "75.0 LOT", (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    path = str(tmp_path / "r.png")
    cv2.imwrite(path, img)
    p = prepare(path)
    assert (p.ink[50:250, 199:202] > 0).mean() > 0.8
    assert (p.text_ink[50:250, 199:202] > 0).mean() < 0.1
    assert p.text_ink[120:155, 20:150].any()


def test_bridge_label_gap_restores_full_course():
    """A 400 px course cut by a 60 px knock-out label box must come back as
    one 400 px line (else the halves vote a ~2.2x scale)."""
    a = LW.Line(np.array([0.0, 100]), np.array([170.0, 100]))
    b = LW.Line(np.array([230.0, 100]), np.array([400.0, 100]))
    other = LW.Line(np.array([0.0, 300]), np.array([400.0, 300]))
    lw = LW.Linework(lines=[a, b, other], arcs=[])
    n = LW.bridge_label_gaps(lw, [(np.array([200.0, 100]), 0.0, 60.0, 14.0)], 14.0, 3.0)
    assert n == 1 and len(lw.lines) == 2
    full = max(lw.lines[:2], key=lambda l: l.length)
    assert full.length == pytest.approx(400)
    # a gap with no label over it is left alone
    lw2 = LW.Linework(lines=[LW.Line(np.array([0.0, 0]), np.array([170.0, 0])),
                             LW.Line(np.array([230.0, 0]), np.array([400.0, 0]))], arcs=[])
    assert LW.bridge_label_gaps(lw2, [(np.array([200.0, 100]), 0.0, 60.0, 14.0)], 14.0, 3.0) == 0


def test_bridge_skips_lot_corner_and_junction():
    # two frontage courses meeting at a lot corner (gap 0), label nearby
    a = LW.Line(np.array([0.0, 100]), np.array([200.0, 100]))
    b = LW.Line(np.array([200.0, 100]), np.array([400.0, 100]))
    lw = LW.Linework(lines=[a, b], arcs=[])
    assert LW.bridge_label_gaps(lw, [(np.array([200.0, 100]), 0.0, 60.0, 14.0)], 14.0, 3.0) == 0
    # real gap, but a lot line ends there (T-junction) -> not a knock-out
    a = LW.Line(np.array([0.0, 100]), np.array([170.0, 100]))
    b = LW.Line(np.array([230.0, 100]), np.array([400.0, 100]))
    side = LW.Line(np.array([170.0, 100]), np.array([170.0, 300]))
    lw = LW.Linework(lines=[a, b, side], arcs=[])
    assert LW.bridge_label_gaps(lw, [(np.array([200.0, 100]), 0.0, 60.0, 14.0)], 14.0, 3.0) == 0


@pytest.mark.parametrize("raw,brg,dist", [
    ('N87°35\'30"E - 1453.5\'', 'N 87°35\'30" E', 1453.5),
    ('S. 1° 01\' 40" E. - 1509.24\'', 'S 01°01\'40" E', 1509.24),
])
def test_combined_course_call(raw, brg, dist):
    kind, v = T.classify(raw, 14, 14)
    assert kind == "bearing" and v["text"] == brg and v["dist"] == pytest.approx(dist)
    rs = T.bearing_readings(raw)
    assert rs and rs[0][1]["dist"] == pytest.approx(dist)


def test_combined_course_votes_scale():
    lines = [LW.Line(np.array([0.0, y]), np.array([L, y])) for y, L in ((0, 400.0), (100, 200.0), (200, 300.0))]
    for k, l in enumerate(lines):
        l.id = k
    lw = LW.Linework(lines=lines, arcs=[])
    labs = [_lab(k, ((l.p1 + l.p2) / 2) + np.array([0, -10.0]), 0,
                 [_alt(f'N90°00\'00"E - {l.length * 0.5:.2f}\'', 80)]) for k, l in enumerate(lines)]
    cal = A.reconcile(labs, lw, 14.0)
    assert cal["ft_per_px"] == pytest.approx(0.5, rel=1e-3)


def test_bearing_repairs_are_costed_candidates():
    rs = {b["text"]: c for c, b in T.bearing_readings('187°35\'30"E')}
    assert rs['N 87°35\'30" E'] == 2 and rs['S 87°35\'30" E'] == 2
    rs = {b["text"]: c for c, b in T.bearing_readings("($01°01'40!")}
    assert rs.get('S 01°01\'40" E') == 2 and rs.get('S 01°01\'40" W') == 2
    assert all(c <= 3 for c in rs.values())
    # strict reads never get repair candidates mixed in
    assert [c for c, _ in T.bearing_readings('N87°35\'30"E')][0] == 0
    # classify stays strict
    assert T.classify('187°35\'30"E', 14, 14)[0] != "bearing"


def test_rotation_needs_three_agreeing_labels():
    """Two bearings agreeing on a 40 deg rotation is chance, not calibration:
    the output drawing must not be rotated."""
    def seg(az_deg, x0):
        a = math.radians(az_deg)
        d = np.array([math.sin(a), -math.cos(a)])
        p1 = np.array([x0, 500.0])
        return LW.Line(p1, p1 + 300 * d)
    lines = [seg(50, 100), seg(100, 600)]      # written 10° / 60° -> both say rot 40
    for k, l in enumerate(lines):
        l.id = k
    lw = LW.Linework(lines=lines, arcs=[])
    labs = []
    for k, (l, txt) in enumerate(zip(lines, ['N10°00\'00"E', 'N60°00\'00"E'])):
        d = l.p2 - l.p1
        n = np.array([-d[1], d[0]]) / np.hypot(*d)
        labs.append(_lab(k, (l.p1 + l.p2) / 2 + 10 * n, math.degrees(math.atan2(d[1], d[0])), [_alt(txt, 90)]))
    cal = A.reconcile(labs, lw, 14.0)
    assert cal["rotation_deg"] == 0.0 and cal["rot_inliers"] == 0


def test_letter_digit_misreads_inside_bearing():
    rs = [b["text"] for c, b in T.bearing_readings("N1°S8'48\"E") if c == 0]
    assert rs == ['N 01°58\'48" E']


def test_small_rotation_accepted_from_two_labels():
    def seg(az_deg, x0):
        a = math.radians(az_deg)
        d = np.array([math.sin(a), -math.cos(a)])
        p1 = np.array([x0, 500.0])
        return LW.Line(p1, p1 + 300 * d)
    lines = [seg(12.9, 100), seg(62.9, 600)]   # written 10° / 60° -> rotation -2.9 (scan skew)
    for k, l in enumerate(lines):
        l.id = k
    lw = LW.Linework(lines=lines, arcs=[])
    labs = []
    for k, (l, txt) in enumerate(zip(lines, ['N10°00\'00"E', 'N60°00\'00"E'])):
        d = l.p2 - l.p1
        n = np.array([-d[1], d[0]]) / np.hypot(*d)
        labs.append(_lab(k, (l.p1 + l.p2) / 2 + 10 * n, math.degrees(math.atan2(d[1], d[0])), [_alt(txt, 90)]))
    cal = A.reconcile(labs, lw, 14.0)
    assert cal["rotation_deg"] == pytest.approx(-2.9, abs=0.05)


@pytest.mark.parametrize("word", ["NORTHLINE", "SOUTH LINE", "NOBLE", "SILLIE"])
def test_words_are_not_bearings(word):
    assert T.bearing_readings(word) == []


def test_truth_scale_metric_term():
    """Scale term: right = 1, wrong = 0, abstain = 0.5; for an image whose
    truth is 'no dimensions', any reported scale is wrong."""
    from raster2dxf import pipeline as PL
    from types import SimpleNamespace
    ink = np.zeros((50, 50), np.uint8)
    prep = SimpleNamespace(stroke_w=2.0, ink=ink, name="block13_mapcheck_drawing.png")
    lw = LW.Linework(lines=[], arcs=[])
    cal = lambda f: dict(ft_per_px=f, scale_inliers=3, scale_votes=5)
    term = lambda name, f: PL.metrics(SimpleNamespace(**{**prep.__dict__, "name": name}), lw, [],
                                       ink, cal(f), 10.0)["scale_consistency"]
    assert term("block13_mapcheck_drawing.png", 0.2749) == 1.0
    assert term("block13_mapcheck_drawing.png", 0.457) == 0.0
    assert term("block13_mapcheck_drawing.png", None) == 0.5
    assert term("mapcheck_individual_parcels_grid.png", 0.034) == 0.0
    assert term("mapcheck_individual_parcels_grid.png", None) == 1.0
    assert term("unknown.png", 0.3) == pytest.approx(0.6)


def test_identical_weak_reads_rejected_but_strong_identical_kept():
    lines = [LW.Line(np.array([0.0, y]), np.array([580.0, y])) for y in (0, 100, 200)]
    for k, l in enumerate(lines):
        l.id = k
    lw = LW.Linework(lines=lines, arcs=[])
    weak = [_lab(k, (290, l.p1[1] - 10), 0, [_alt("20", 40)]) for k, l in enumerate(lines)]
    assert A.reconcile(weak, lw, 14.0)["ft_per_px"] is None
    strong = [_lab(k, (290, l.p1[1] - 10), 0, [_alt("75'", 60)]) for k, l in enumerate(lines)]
    assert A.reconcile(strong, lw, 14.0)["ft_per_px"] == pytest.approx(75 / 580, rel=1e-3)


def test_scan_scale_tolerance_absorbs_drafting_error():
    """Hand-drafted plat: three courses drawn 3-4% off scale (as measured on
    crop_lot23_24_detail) agree at scan tolerance, not at digital."""
    lines = [LW.Line(np.array([0.0, y]), np.array([L, y])) for y, L in ((0, 300.0), (100, 250.0), (200, 400.0))]
    for k, l in enumerate(lines):
        l.id = k
    lw = LW.Linework(lines=lines, arcs=[])
    vals = [300 * 0.34, 250 * 0.34 * 1.03, 400 * 0.34 * 0.97]
    mk = lambda: [_lab(k, ((l.p1 + l.p2) / 2) + np.array([0, -10.0]), 0, [_alt(f"{v:.2f}'", 80)])
                  for k, (l, v) in enumerate(zip(lines, vals))]
    assert A.reconcile(mk(), lw, 14.0, A.DIGITAL_SCALE_TOL)["ft_per_px"] is None
    assert A.reconcile(mk(), lw, 14.0, A.SCAN_SCALE_TOL)["ft_per_px"] == pytest.approx(0.34, rel=0.035)


@pytest.mark.parametrize("raw,val", [("-—/02, 38!", 102.38), ("——/02.38'_", 102.38), ("/03.17'", 103.17)])
def test_italic_one_read_as_slash(raw, val):
    kind, v = T.classify(raw, 20, 20)
    assert kind == "distance" and v == pytest.approx(val)


def test_fraction_slash_kept():
    assert "1/2" in T.normalize("1/2")


def test_course_length_runs_to_arc_PI():
    """Line from (0,0) to (75,0) then a R=25 corner return curving down to
    (100,25): the plat distance runs to the P.I. at (100,0) -> 100 px."""
    line = LW.Line(np.array([0.0, 0.0]), np.array([75.0, 0.0]))
    line.id = 0
    arc = LW.Arc(center=np.array([75.0, 25.0]), r=25.0, a0=-math.pi / 2, sweep=math.pi / 2)
    lw = LW.Linework(lines=[line], arcs=[arc])
    assert arc.point(1.0) == pytest.approx([100.0, 25.0])
    assert LW.course_lengths(lw, 3.0)[0] == pytest.approx(100.0, abs=1e-6)
    # a line not touching any arc is not listed
    other = LW.Line(np.array([0.0, 100.0]), np.array([50.0, 100.0]))
    other.id = 1
    assert 1 not in LW.course_lengths(LW.Linework(lines=[line, other], arcs=[arc]), 3.0)


def test_course_length_uses_adjoining_line_when_arc_sweep_is_off():
    """Arc fitted with a 117 deg sweep (scan artefact) instead of 90: the
    P.I. still comes from intersecting with the adjoining straight line."""
    line = LW.Line(np.array([100.0, 0.0]), np.array([300.0, 0.0]))
    side = LW.Line(np.array([0.0, 100.0]), np.array([0.0, 300.0]))
    line.id, side.id = 0, 1
    c = np.array([100.0, 100.0])
    a0 = -math.pi / 2
    arc = LW.Arc(center=c, r=100.0, a0=a0, sweep=-math.radians(117))   # overshoots
    arc_end = arc.point(1.0)
    side.p1 = arc_end.copy()                    # side line leaves the arc's far end
    side.p2 = arc_end + np.array([0.0, 200.0])
    lw = LW.Linework(lines=[line, side], arcs=[arc])
    L = LW.course_lengths(lw, 5.0)[0]
    x_pi = arc_end[0]                           # intersection of y=0 with x=arc_end.x
    assert L == pytest.approx(300.0 - x_pi, abs=1e-6)


def test_qa_flags_only_meaningful_disagreements():
    mk = lambda txt, conf: T.Label(id=0, center=np.zeros(2), angle=0, width=10, height=10,
                                   text=txt, conf=conf, kind="distance", value=T.classify(txt, 10, 10)[1])
    tol = A.SCAN_SCALE_TOL
    assert A._qa_worthy(mk("93.50'", 87), 139.26, tol)          # real: line runs through a monument
    assert A._qa_worthy(mk("80°", 82), 96.5, tol)               # ° is a foot-mark misread
    assert not A._qa_worthy(mk("83.26'", 80), 78.2, tol)        # 6%: ordinary drafting error
    assert not A._qa_worthy(mk("46", 44), 26.2, tol)            # weak read
    assert not A._qa_worthy(mk("9.52'", 82), 73.9, tol)         # 7x off: misread, not a finding


def _bullseye_canvas():
    img = np.zeros((300, 400), np.uint8)
    cv2.line(img, (20, 150), (380, 150), 255, 4)             # frontage through the monument
    cv2.circle(img, (200, 150), 14, 255, 4)                  # monument ring
    cv2.circle(img, (200, 150), 5, 255, 2)                   # inner ring, paper centre (as on PB30 P82)
    return img


def test_monument_found_and_line_split_at_it():
    img = _bullseye_canvas()
    lines = [LW.Line(np.array([20.0, 150]), np.array([380.0, 150]))]
    ms = LW.find_monuments(img, lines, 30.0, 4.0)
    assert len(ms) == 1 and np.hypot(*(ms[0].center - [200, 150])) <= 3
    parts = LW.split_at_points(lines, [ms[0].center], 3.0)
    assert len(parts) == 2 and sorted(round(p.length) for p in parts) == [180, 180]


def test_monument_rejected_inside_text_box_or_off_line():
    img = _bullseye_canvas()
    lines = [LW.Line(np.array([20.0, 150]), np.array([380.0, 150]))]
    assert LW.find_monuments(img, lines, 30.0, 4.0, [(np.array([200.0, 150]), 0.0, 60, 40)]) == []
    far = [LW.Line(np.array([20.0, 280]), np.array([380.0, 280]))]
    assert LW.find_monuments(img, far, 30.0, 4.0) == []


def test_monument_at_lot_corner_survives_label_box_but_filled_loop_does_not():
    img = np.zeros((300, 400), np.uint8)
    cv2.line(img, (20, 150), (380, 150), 255, 4)
    cv2.line(img, (200, 150), (200, 290), 255, 4)           # second course: lot corner
    cv2.circle(img, (200, 150), 14, 255, 4)
    lines = [LW.Line(np.array([20.0, 150]), np.array([380.0, 150])),
             LW.Line(np.array([200.0, 150]), np.array([200.0, 290]))]
    box = [(np.array([200.0, 150]), 0.0, 60, 40)]            # "P.R.M." label over the ring
    assert len(LW.find_monuments(img, lines, 30.0, 4.0, box)) == 1
    # a digit-like loop beside the line, with ink at its centre, is rejected
    # even outside any label box
    img2 = np.zeros((300, 400), np.uint8)
    cv2.line(img2, (20, 150), (380, 150), 255, 4)
    cv2.circle(img2, (200, 138), 14, 255, 4)
    cv2.circle(img2, (200, 138), 4, 255, -1)
    one = [LW.Line(np.array([20.0, 150]), np.array([380.0, 150]))]
    assert LW.find_monuments(img2, one, 30.0, 4.0) == []


def test_monument_f1():
    from raster2dxf.pipeline import monument_f1
    shape = (500, 500)
    assert monument_f1([(100, 100), (300, 300)], [(102, 99), (300, 305)], shape) == 1.0
    assert monument_f1([(100, 100)], [(100, 100), (300, 300)], shape) == pytest.approx(2 / 3)
    assert monument_f1([(100, 100), (200, 200)], [(100, 100)], shape) == pytest.approx(2 / 3)
    # edge-cut symbols ignored both ways
    assert monument_f1([(100, 100), (495, 250)], [(100, 100)], shape) == 1.0
    assert monument_f1([], [], shape) == 1.0


def test_elliptical_zero_is_not_a_monument():
    img = np.zeros((300, 400), np.uint8)
    cv2.line(img, (200, 20), (200, 280), 255, 3)
    cv2.ellipse(img, (212, 150), (7, 13), 0, 0, 360, 255, 3)     # hollow "0" beside the line
    lines = [LW.Line(np.array([200.0, 20]), np.array([200.0, 280]))]
    assert LW.find_monuments(img, lines, 30.0, 3.0) == []
    assert LW._radial_spread(np.array([[10 * math.cos(a), 10 * math.sin(a)] for a in np.linspace(0, 6.2, 60)]),
                             np.zeros(2), 10.0) == pytest.approx(0, abs=1e-6)


def test_ring_with_half_inked_interior_is_rejected():
    """A ring crossed by letter strokes (half-inked interior) is not a
    monument; a ring-in-ring P.R.M. and a plain hollow circle both are."""
    base = np.zeros((300, 400), np.uint8)
    cv2.line(base, (20, 150), (380, 150), 255, 4)
    lines = [LW.Line(np.array([20.0, 150]), np.array([380.0, 150]))]
    prm = base.copy(); cv2.circle(prm, (200, 150), 14, 255, 4); cv2.circle(prm, (200, 150), 5, 255, 2)
    plain = base.copy(); cv2.circle(plain, (200, 150), 14, 255, 4)
    lettered = base.copy(); cv2.circle(lettered, (200, 150), 14, 255, 4)
    cv2.line(lettered, (190, 138), (196, 162), 255, 3)       # letter strokes through the interior
    cv2.line(lettered, (206, 138), (210, 162), 255, 3)
    assert len(LW.find_monuments(prm, lines, 30.0, 4.0)) == 1
    assert len(LW.find_monuments(plain, lines, 30.0, 4.0)) == 1
    assert LW.find_monuments(lettered, lines, 30.0, 4.0) == []


def test_truth_file_is_well_formed():
    """Every truth entry names a real training image and its monument
    coordinates lie inside that image."""
    import json, os
    t = json.load(open(os.path.join("raster2dxf", "truth.json")))
    d = os.path.join("Plat", "training", "drawings")
    for name, rec in t["scales"].items():
        assert os.path.exists(os.path.join(d, name)), name
        assert rec.get("no_scale") or rec["ft_per_px"] > 0
    for name, pts in t["monuments"].items():
        im = cv2.imread(os.path.join(d, name))
        assert im is not None, name
        h, w = im.shape[:2]
        assert all(0 <= x < w and 0 <= y < h for x, y in pts), name


def test_table_cells_are_not_dimensions():
    """A row of numbers far from all linework (a line/curve table) is
    re-kinded "table"; a distance beside its course is left alone, and a
    lone far-away distance (no row neighbours) is left alone too."""
    lw = LW.Linework(lines=[LW.Line(np.array([0.0, 0.0]), np.array([400.0, 0.0]))], arcs=[])
    lw.lines[0].id = 0
    mk = lambda i, x, y, txt: _lab(i, (x, y), 0, [_alt(txt, 80)])
    on_line = mk(0, 200, -10, "100.00'")
    row = [mk(1, 100, 500, "75.00"), mk(2, 200, 500, "N88°58'20\"E"), mk(3, 300, 500, "77.25")]
    lone = mk(4, 200, 900, "12.50'")
    labs = [on_line] + row + [lone]
    assert A.mark_table_cells(labs, lw, 14.0) == 3          # 75.00, the bearing, 77.25
    assert on_line.kind == "distance" and lone.kind == "distance"
    assert all(l.kind == "table" for l in row)
    A.reconcile(labs, lw, 14.0)
    assert row[0].kind == "table" and not row[0].assoc


def test_lot_number_rows_are_not_tables():
    """Bare integers in a row far from lines (lot numbers "24 25 26" on a
    sheet) must not become table cells."""
    lw = LW.Linework(lines=[LW.Line(np.array([0.0, 0.0]), np.array([400.0, 0.0]))], arcs=[])
    labs = [_lab(i, (100 * (i + 1), 500), 0, [_alt(t, 90)]) for i, t in enumerate(["24", "25", "26"])]
    for l in labs:
        l.kind = "distance"                      # as a misread would classify them
    assert A.mark_table_cells(labs, lw, 14.0) == 0


def test_text_only_image_gets_notes_mtext(tmp_path):
    """A notes panel (no linework) becomes a PLAT-NOTES MTEXT paragraph and
    isn't scored as a linework failure."""
    from raster2dxf.pipeline import process
    img = np.full((220, 900), 255, np.uint8)
    for i, t in enumerate(["NOTES", "BEARINGS AND DISTANCES SHOWN", "ON CURVES ARE CHORD VALUES"]):
        cv2.putText(img, t, (20, 50 + 60 * i), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 3)
    path = str(tmp_path / "notes.png")
    cv2.imwrite(path, img)
    rep = process(path, str(tmp_path / "out"))
    assert rep["n_lines"] == 0 and rep["notes"] and "CHORD" in rep["notes"][0].upper()
    assert rep["metrics"]["line_f1"] == 1.0
    doc = ezdxf.readfile(str(tmp_path / "out" / "dxf" / "notes.dxf"))
    mt = doc.modelspace().query('MTEXT[layer=="PLAT-NOTES"]')
    assert len(mt) == 1 and "DISTANCES" in mt[0].text.upper()


# ------------------------------------------------ curve-data blocks
from raster2dxf import curvedata as CD


@pytest.mark.parametrize("raw,key,val", [
    ("A> 36° 20°,", "delta", 36 + 20 / 60),
    ("4=36°20'", "delta", 36 + 20 / 60),
    ("Δ=36°20'00\"", "delta", 36 + 20 / 60),
    ("R.=327.01'", "R", 327.01),
    ("T.= 107.31'", "T", 107.31),
    ("L=260.19'", "L", 260.19),
])
def test_curve_field_parsing_tolerates_misread_keys(raw, key, val):
    assert CD.parse_fields(raw)[key] == pytest.approx(val)


def test_curve_solve_derives_and_checks():
    # Cape Horn centreline curve: R=327.01, T=107.31 -> Δ derived; with Δ given it must check
    d = CD.solve({"R": 327.01, "T": 107.31})
    assert d["delta"] == pytest.approx(36.33, abs=0.02)
    ok = CD.solve({"R": 327.01, "T": 107.31, "delta": 36 + 20 / 60})
    assert ok["consistent"] and ok["check"] < 0.002
    bad = CD.solve({"R": 934.5, "T": 107.31, "delta": 36 + 20 / 60})     # misread R
    assert not bad["consistent"]
    fix = CD.solve({"T": 107.31, "delta": 36 + 20 / 60})                 # R from T and Δ
    assert fix["R"] == pytest.approx(327.0, abs=0.3) and "R" in fix["derived"]


def test_unwrap_straightens_arc_text():
    """Text drawn along a circle becomes a straight horizontal strip."""
    img = np.full((600, 600), 255, np.uint8)
    c = np.array([300.0, 300.0])
    for i, ch in enumerate("ABCDEFGH"):                      # letters along r=200, top arc
        t = math.radians(-120 + 8 * i)
        p = (int(c[0] + 200 * math.cos(t)) - 8, int(c[1] + 200 * math.sin(t)) + 8)
        cv2.putText(img, ch, p, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2)
    strip = CD.unwrap(img, c, 180, 225, math.radians(-125), math.radians(-60), 200, True, True)
    ink_rows = np.flatnonzero((strip < 128).sum(1))
    assert strip.shape[1] > strip.shape[0] and ink_rows.size and np.ptp(ink_rows) < 30


def test_curve_field_vote_and_R_key_misread():
    assert CD.parse_fields("3° 20'00\"- &.=459_36'")["R"] == pytest.approx(459.36)
    assert CD._vote([{"R": 459.36}, {"R": 459.36, "delta": 36.3333}, {"R": 1374.0}]) == \
        {"R": 459.36, "delta": 36.33}
    assert "R" not in CD.parse_fields("N 58°21'40\" W")


def test_solve_after_dropping_misread_T():
    f = {"delta": 36.33, "R": 459.36, "T": 2.0}
    assert not CD.solve(f)["consistent"]
    D = math.radians(36.33)
    kept = {k: v for k, v in f.items() if k not in ("T",) or abs(v / (459.36 * math.tan(D / 2)) - 1) <= 0.05}
    assert "T" not in kept and CD.solve(kept)["derived"]["T"] == pytest.approx(150.7, abs=0.3)


def test_curve_score_against_catalog():
    from raster2dxf.pipeline import curve_score
    good = [dict(source="dewarp", R=459.36, fields={"R": 459.36, "delta": 36.33})]
    bad = [dict(source="dewarp", R=1374.0, fields={"T": 450.73, "delta": 36.33})]
    frag = [dict(source="identity", R=25.0, fields={"R": 25.0})]    # non-dewarp: not scored
    assert curve_score(good, "page1_300dpi.png") == (1, 0)
    assert curve_score(bad + frag, "page1_300dpi.png") == (0, 1)
    assert curve_score(good, "block13_mapcheck_drawing.png") is None


def test_curve_id_links_to_arc_and_table():
    arc = LW.Arc(center=np.array([500.0, 1500.0]), r=1000.0, a0=-math.pi / 2 - 0.2, sweep=0.4)
    arc.id = 0
    lw = LW.Linework(lines=[], arcs=[arc])
    # "C3" drawn ~4 char heights inside the curve (as on block16)
    lab = _lab(0, (500, 500 + 4 * 14), 0, [_alt("C3", 90)])
    A.associate([lab], lw, 14.0)
    assert lab.assoc and lab.assoc["geom"] == ("A", 0)
    table = {"C3": {"id": "C3", "R": 389.27}}
    links = A.link_curve_ids([lab], lw, table, 389.27 / 1000.0)
    assert links[0]["verified"] is True
    assert A.link_curve_ids([lab], lw, table, 0.2)[0]["verified"] is False


def test_curve_id_column_of_table_is_table():
    lw = LW.Linework(lines=[LW.Line(np.array([0.0, 0.0]), np.array([400.0, 0.0]))], arcs=[])
    row = [_lab(0, (100, 600), 0, [_alt("C3", 90)]), _lab(1, (200, 600), 0, [_alt("389.27", 90)]),
           _lab(2, (300, 600), 0, [_alt("85.41", 90)])]
    A.mark_table_cells(row, lw, 14.0)
    assert row[0].kind == "table"


def test_two_curve_ids_share_one_arc():
    arc = LW.Arc(center=np.array([500.0, 1500.0]), r=1000.0, a0=-math.pi / 2 - 0.2, sweep=0.4)
    arc.id = 0
    lw = LW.Linework(lines=[], arcs=[arc])
    a = _lab(0, (400, 560), 0, [_alt("C3", 90)])
    b = _lab(1, (600, 560), 0, [_alt("C4", 90)])
    A.associate([a, b], lw, 14.0)
    assert a.assoc and b.assoc
