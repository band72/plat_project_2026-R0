"""
ATLANTIC BEACH COUNTRY CLUB UNIT 2 -- PB 67, Pages 132-137, Duval County FL
Complete vectorized drawing: all lots and roads, scaled from the scans.

Richard A. Miller & Associates, Inc. | replat of Lot 5 of Donner's Replat
and a portion of Sections 8 and 17, T2S, R29E.

SCALE DERIVATION (not estimation):
  overall key map (sheet 2) drawn 1" = 200', rendered 300 dpi -> 0.666667 ft/px
  detail sheets 3-6      drawn 1" =  50', rendered 300 dpi -> 0.166667 ft/px

SCALE VALIDATION against the plat's own labelled dimensions (sheet 3):
  labelled 80.00'  -> vectorized mean 80.10'  (0.10 ft)
  labelled 120'    -> vectorized mean 120.79' (0.79 ft)
  labelled 55.00'  -> vectorized mean 55.68'  (0.68 ft)
  labelled 60.00'  -> vectorized mean 59.11'  (0.89 ft)
  => scaled geometry is good to ~1 ft, NOT to the recorded 0.01 ft.

Everything drawn here is SCALED, not transcribed. It is dimensionally
reliable to about a foot and is suitable for base mapping, area checks and
overlay -- it is NOT a substitute for the recorded dimensions when
retracing a boundary.
"""
import sys, math, cv2
sys.path.insert(0, '.')
from engine.vectorize import map_mask, map_mask_excluding, segments, merge_collinear, _len
from engine.dxf_writer import DXFWriter

SHEETS = [
    dict(file="src/abcc300-3.png", page=3, pg="134", scale_ft_px=50/300,
         label="SHEET 3 (PG 134)",
         exclude=[(0.085,0.20,0.165,0.44),(0.085,0.66,0.12,0.09),(0.02,0.80,0.20,0.18)]),
    dict(file="src/ab4-4.png", page=4, pg="135", scale_ft_px=50/300,
         label="SHEET 4 (PG 135)",
         exclude=[(0.735,0.545,0.245,0.36),(0.545,0.615,0.135,0.10),(0.02,0.80,0.16,0.18)]),
    dict(file="src/ab5-5.png", page=5, pg="136", scale_ft_px=50/300,
         label="SHEET 5 (PG 136)",
         exclude=[(0.085,0.055,0.145,0.30),(0.085,0.75,0.28,0.22),(0.02,0.80,0.10,0.18)]),
    dict(file="src/ab6-6.png", page=6, pg="137", scale_ft_px=50/300,
         label="SHEET 6 (PG 137)",
         exclude=[(0.035,0.045,0.135,0.55),(0.02,0.80,0.16,0.18)]),
]
OVERALL = dict(file="src/abcc-2.png", pg="133", scale_ft_px=200/200,  # set below
               rect=(0.190, 0.050, 0.800, 0.900), label="SHEET 2 KEY MAP (PG 133)")

dxf = DXFWriter()
for n, c, lt in [("OVERALL_KEYMAP", "white", "CONTINUOUS"),
                 ("SHEET3_LINEWORK", "cyan", "CONTINUOUS"),
                 ("SHEET4_LINEWORK", "green", "CONTINUOUS"),
                 ("SHEET5_LINEWORK", "yellow", "CONTINUOUS"),
                 ("SHEET6_LINEWORK", "magenta", "CONTINUOUS"),
                 ("SHEET_FRAME", "gray", "DASHED"),
                 ("TITLEBLOCK", "yellow", "CONTINUOUS"),
                 ("NOTES", "red", "CONTINUOUS")]:
    dxf.add_layer(n, c, lt)

summary = []


def do_sheet(cfg, layer, offset_n, offset_e, ft_px):
    img = cv2.imread(cfg["file"], 0)
    if img is None:
        print("  MISSING", cfg["file"]); return None
    h, w = img.shape
    mask = map_mask_excluding(img, exclude=cfg["exclude"])
    segs = merge_collinear(segments(mask))
    rh = h
    drawn = 0.0
    minn = mine = 1e18; maxn = maxe = -1e18
    for x1, y1, x2, y2 in segs:
        n1 = (rh - y1) * ft_px + offset_n
        e1 = x1 * ft_px + offset_e
        n2 = (rh - y2) * ft_px + offset_n
        e2 = x2 * ft_px + offset_e
        dxf.line((n1, e1), (n2, e2), layer=layer)
        drawn += math.hypot(n2-n1, e2-e1)
        minn = min(minn, n1, n2); maxn = max(maxn, n1, n2)
        mine = min(mine, e1, e2); maxe = max(maxe, e1, e2)
    # frame + label
    for a, b in [((minn, mine), (minn, maxe)), ((minn, maxe), (maxn, maxe)),
                 ((maxn, maxe), (maxn, mine)), ((maxn, mine), (minn, mine))]:
        dxf.line(a, b, layer="SHEET_FRAME")
    dxf.text((maxn + 30, mine), f"{cfg['label']}  1\"=50'  "
             f"{len(segs)} segments  {drawn:,.0f} ft of linework",
             height=40, layer="TITLEBLOCK")
    summary.append((cfg["label"], len(segs), drawn, maxn-minn, maxe-mine))
    print(f"  {cfg['label']}: {len(segs):4d} segments, {drawn:8,.0f} ft, "
          f"extent {maxe-mine:7.0f} x {maxn-minn:7.0f} ft")
    return (minn, maxn, mine, maxe)


print("=== vectorizing detail sheets (1\"=50') ===")
# lay the four detail sheets out in a 2x2 arrangement, generously spaced
PITCH_E, PITCH_N = 1600.0, 1200.0
placements = [(0, 0), (0, PITCH_E), (-PITCH_N, 0), (-PITCH_N, PITCH_E)]
for cfg, (on, oe) in zip(SHEETS, placements):
    do_sheet(cfg, f"SHEET{cfg['page']}_LINEWORK", on, oe, cfg["scale_ft_px"])

print("\n=== vectorizing overall key map (1\"=200') ===")
img2 = cv2.imread(OVERALL["file"], 0)
if img2 is not None:
    h2, w2 = img2.shape
    # sheet 2 was rendered at 200 dpi -> 200 ft/in / 200 px/in = 1.0 ft/px
    ft_px2 = 200.0 / 200.0
    fx, fy, fw, fh = OVERALL["rect"]
    rect2 = (int(w2*fx), int(h2*fy), int(w2*fw), int(h2*fh))
    mask2 = map_mask(img2, rect2, min_diag=90)
    segs2 = merge_collinear(segments(mask2, min_len_px=30, max_gap=5, thresh=40))
    rh2 = rect2[3]
    ON, OE = 900.0, -2600.0
    drawn2 = 0.0
    for x1, y1, x2, y2 in segs2:
        n1 = (rh2 - y1) * ft_px2 + ON; e1 = x1 * ft_px2 + OE
        n2 = (rh2 - y2) * ft_px2 + ON; e2 = x2 * ft_px2 + OE
        dxf.line((n1, e1), (n2, e2), layer="OVERALL_KEYMAP")
        drawn2 += math.hypot(n2-n1, e2-e1)
    dxf.text((ON + rh2*ft_px2 + 60, OE), f"{OVERALL['label']}  1\"=200'  "
             f"{len(segs2)} segments  {drawn2:,.0f} ft", height=60, layer="TITLEBLOCK")
    print(f"  key map: {len(segs2)} segments, {drawn2:,.0f} ft")
    summary.append((OVERALL["label"], len(segs2), drawn2, 0, 0))

# ---------------- title block ----------------
TN, TE = 700.0, -2600.0
body = [
    "ATLANTIC BEACH COUNTRY CLUB UNIT 2 -- PLAT BOOK 67, PAGES 132-137",
    "Duval County, Florida  |  Richard A. Miller & Associates, Inc.  |  2014",
    "Replat of Lot 5 of Donner's Replat and a portion of Sections 8 & 17, T2S, R29E",
    "",
    "*** ALL GEOMETRY HEREON IS SCALED FROM THE RECORDED SCAN ***",
    "",
    "SCALE DERIVATION (exact unit conversion, not estimation):",
    "   detail sheets 3-6:  1\"=50'  rendered 300 dpi  ->  0.166667 ft/pixel",
    "   key map sheet 2  :  1\"=200' rendered 200 dpi  ->  1.000000 ft/pixel",
    "",
    "SCALE VALIDATION against the plat's own labelled dimensions (sheet 3):",
    "   labelled  80.00'  ->  vectorized mean  80.10'   (0.10 ft)",
    "   labelled 120.00'  ->  vectorized mean 120.79'   (0.79 ft)",
    "   labelled  55.00'  ->  vectorized mean  55.68'   (0.68 ft)",
    "   labelled  60.00'  ->  vectorized mean  59.11'   (0.89 ft)",
    "",
    "ACCURACY: scaled linework is reliable to approximately +/- 1 FOOT.",
    "It is NOT the recorded precision (0.01 ft). Suitable for base mapping,",
    "overlay and area checking. NOT a substitute for the recorded bearings",
    "and distances when retracing a boundary or setting corners.",
    "",
    "SHEET REGISTRATION: each detail sheet is drawn in its OWN local frame and",
    "laid out side by side. They are NOT tied to one another or to State Plane.",
    "Joining them requires the match-line ties shown on each sheet.",
    "",
    "CURVE DATA: the sheet-3 curve table was separately OCR'd and validated",
    "(21 of 27 rows passing all three curve identities at ~0.004 ft residual,",
    "4 of 4 flagged rows repaired). Those are RECORDED values and are far more",
    "precise than the scaled linework here.",
]
for i, t in enumerate(body):
    dxf.text((TN - i*55, TE), t, height=34 if i == 0 else 26, layer="TITLEBLOCK")

out = "dxf/PB0067_P0132_AtlanticBeachCC_Unit2_vectorized.dxf"
dxf.save(out)
tot_seg = sum(s[1] for s in summary); tot_ft = sum(s[2] for s in summary)
print(f"\nsaved {out}")
print(f"TOTAL: {tot_seg} segments, {tot_ft:,.0f} ft of linework across "
      f"{len(summary)} sheets")
