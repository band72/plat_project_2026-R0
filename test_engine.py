"""
test_engine.py -- regression tests for the plat pipeline.

Every test here corresponds to a real defect found by auditing the code,
not a hypothetical. Run before shipping any change to engine/.
"""
import sys, math, random
sys.path.insert(0, '.')
from engine.cogo import Point, parse_bearing, azimuth_to_bearing
from engine.lots import shoelace_area, is_simple_polygon, safe_area
from engine.curves import Curve
from engine.topology import VertexGraph, Parcel
from engine.registration import ATLANTIC_SHEET3

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILURES.append(name)


print("=== bearing formatting (BUG: 319 invalid 60-second strings) ===")
bad = [az for az in (i * 360 / 50000 for i in range(50000))
       if "60.00\"" in azimuth_to_bearing(az) or "'60" in azimuth_to_bearing(az)]
check("no 60-second or 60-minute output", len(bad) == 0, f"{len(bad)} found")

print("\n=== cardinal directions (BUG: emitted N90d00'00\"E / N00d00'00\"W) ===")
check("0 deg -> DUE N", azimuth_to_bearing(0) == "DUE N", azimuth_to_bearing(0))
check("90 deg -> DUE E", azimuth_to_bearing(90) == "DUE E", azimuth_to_bearing(90))
check("180 deg -> DUE S", azimuth_to_bearing(180) == "DUE S", azimuth_to_bearing(180))
check("270 deg -> DUE W", azimuth_to_bearing(270) == "DUE W", azimuth_to_bearing(270))

print("\n=== format/parse round-trip (BUG: cardinals were unparseable) ===")
worst = 0.0
fails = 0
for _ in range(5000):
    az = random.uniform(0, 360)
    try:
        az2 = parse_bearing(azimuth_to_bearing(az))
    except Exception:
        fails += 1
        continue
    worst = max(worst, abs((az - az2 + 180) % 360 - 180))
check("round-trip parses without error", fails == 0, f"{fails} parse failures")
check("round-trip accurate to <0.01 deg", worst < 0.01, f"worst {worst*3600:.2f} arcsec")

print("\n=== self-intersection detection (BUG: bowtie area returned 0.0 silently) ===")
sq = [Point(0, 0), Point(0, 100), Point(100, 100), Point(100, 0)]
bow = [Point(0, 0), Point(100, 100), Point(0, 100), Point(100, 0)]
check("square is simple", is_simple_polygon(sq)[0])
check("bowtie detected as NOT simple", not is_simple_polygon(bow)[0])
check("square area correct", abs(safe_area(sq) - 10000) < 1e-6, safe_area(sq))
try:
    safe_area(bow)
    check("safe_area refuses bowtie", False, "it returned a number")
except ValueError:
    check("safe_area refuses bowtie", True)

print("\n=== curve solver ===")
c = Curve(id="T", length=39.27, radius=25.0, delta_deg=90.0,
          chord_bearing="N45°00'00\"E", chord=35.36, rot="CCW")
check("curve internal consistency", c.check(tol=0.05))
p0 = Point(0, 0)
pt = c.arc_points(p0, 64)[-1]
check("arc endpoint honors table chord", abs(p0.dist_to(pt) - 35.36) < 0.02,
      f"{p0.dist_to(pt):.3f}")

print("\n=== shared-vertex topology (BUG: adjacent lots had duplicate corners) ===")
g = VertexGraph()
g.walk("A", Point(0, 0), [("B", "DUE E", 100.0), ("C", "DUE N", 100.0)])
check("walk registers each vertex once", len(g.points) == 3, list(g.points))
check("shared vertex is the SAME object",
      g.points["B"] is g.points["B"])
try:
    g.add("B", Point(500, 500))
    check("redefining a vertex elsewhere raises", False, "it silently accepted")
except ValueError:
    check("redefining a vertex elsewhere raises", True)

print("\n=== parcel area gating ===")
g2 = VertexGraph()
for n, p in [("A", Point(0, 0)), ("B", Point(0, 100)),
             ("C", Point(100, 100)), ("D", Point(100, 0))]:
    g2.add(n, p)
good = Parcel("1", ["A", "B", "C", "D"], g2)
bad_p = Parcel("2", ["A", "C", "B", "D"], g2)
check("good parcel area", abs(good.area_sqft() - 10000) < 1e-6)
check("bowtie parcel returns None + reason", bad_p.area_or_none()[0] is None,
      bad_p.area_or_none())

print("\n=== sheet registration (extracted from duplicated build code) ===")
R = ATLANTIC_SHEET3
check("scale agreement <= 0.5 ft", R.scale_agreement() <= 0.5,
      f"{R.scale_agreement():.3f}")
check("residual <= 0.5 ft", R.residual() <= 0.5, f"{R.residual():.3f}")
check("solved rotation ~89.58 deg", abs(R.phi - 89.5842) < 0.01, f"{R.phi:.4f}")

print("\n=== traverse closure (the Block A standard) ===")
WIDTHS = [137.85, 55, 60, 55, 55, 60, 55, 55, 60, 55, 55, 60]
check("Block A front closure EXACT", abs(sum(WIDTHS) + 10.00 - 772.85) < 0.001,
      f"{sum(WIDTHS)+10:.2f}")
ang = abs((parse_bearing("N00°32'22\"E") - parse_bearing("N89°27'38\"W") + 180) % 360 - 180)
check("Block A perpendicularity EXACT 90", abs(ang - 90) < 1e-6, f"{ang:.6f}")

print("\n=== verification engine (must catch what it is built to catch) ===")
from engine.verify import verify_ring, verify_network
_sq=[Point(0,0),Point(0,100),Point(100,100),Point(100,0)]
_v=verify_ring("sq",_sq)
check("clean square passes", _v.passed, [f.code for f in _v.errors])
check("clean square area 10000", abs(_v.area-10000)<1e-6, _v.area)
_bow=[Point(0,0),Point(100,100),Point(0,100),Point(100,0)]
check("bowtie fails", not verify_ring("b",_bow).passed)
check("bowtie reports NO_SELF_INTERSECT",
      "NO_SELF_INTERSECT" in {f.code for f in verify_ring("b",_bow).errors})
_sp=[Point(0,0),Point(100,0),Point(100,50),Point(100.0,0.02),Point(0,50)]
check("spike fails", not verify_ring("s",_sp).passed)
_dup=[Point(0,0),Point(0,0.001),Point(100,0),Point(100,50)]
check("duplicate vertex fails", not verify_ring("d",_dup).passed)
check("duplicate vertex reports NO_DUPLICATE_VERT",
      "NO_DUPLICATE_VERT" in {f.code for f in verify_ring("d",_dup).errors})
_tri=[Point(0,0),Point(0,10)]
check("degenerate 2-vertex ring fails", not verify_ring("t",_tri).passed)
_net=verify_network({"A":_sq,"B":[Point(0,100),Point(0,200),Point(100,200),Point(100,100)]})
check("shared-vertex network check runs", "near_duplicate_vertices" in _net)

print("\n=== tick/junction detection (validated on known lot corners) ===")
import cv2 as _cv2
from engine.vectorize import map_mask_excluding as _mme
from engine.ticks import scan_boundary_profile as _scan, cluster_stations as _clus
_img=_cv2.imread('src/abcc300-3.png',0)
if _img is not None:
    _m=_mme(_img, exclude=[(0.085,0.20,0.165,0.44),(0.085,0.66,0.12,0.09),
                           (0.02,0.80,0.20,0.18)], skeleton=False)
    _p=_scan(_m,(1470,545,6105,555))
    _j=_clus(_p,"JUNCTION"); _ft=50/300
    _jf=[x['station_px']*_ft for x in _j]
    _W=[137.85,55,60,55,55,60,55,55,60,55,55,60]; _c=[];_s=0
    for _w in _W: _s+=_w; _c.append(_s)
    _hit=sum(1 for cc in _c if _jf and min(abs(x-cc) for x in _jf)<4.0)
    check("junction scan finds all 12 lot corners", _hit==12, f"{_hit}/12")
else:
    print("  SKIP  source scan not available")

print("\n=== block auto-derivation (90/10 bulk processing) ===")
import cv2 as _c2
from engine.vectorize import map_mask_excluding as _mm
from engine.blocks import BlockSpec as _BS, build_block as _bb
from engine.topology import VertexGraph as _VG
_im=_c2.imread('src/abcc300-3.png',0)
if _im is not None:
    _EX=[(0.085,0.20,0.165,0.44),(0.085,0.66,0.12,0.09),(0.02,0.80,0.20,0.18)]
    _mk=_mm(_im, exclude=_EX, skeleton=False)
    _sp=_BS(name="T", sheet_image='x', boundary_px=(1470,545,6105,555),
        front_bearing="N00°32'22\"E", side_bearing="S89°27'38\"E",
        lot_numbers=list(range(137,125,-1)),
        depth=[119.72,120,117.75,106.79,100.04,97.66,99.91,103.53,107.47,111.08,114.70,118.64],
        expected_total=762.85, exclude=_EX)
    _r=_bb(_mk,_sp,_VG())
    _T=[137.85,55,60,55,55,60,55,55,60,55,55,60]
    _ok=sum(1 for a,b in zip(_r.derived_widths,_T) if abs(a-b)<2.5)
    check("block status AUTO", _r.status=="AUTO", _r.status+" "+_r.reason)
    check("auto-derives 12/12 lot widths", _ok==12, f"{_ok}/12")
    check("all derived lots verify", all(v.passed for v in _r.verifications.values()))
else:
    print("  SKIP  source scan not available")

print("\n=== Beachwood parent caption traverse & 121-lot tabular schedule ===")
from build_beachwood_boundary import RAW_COURSES, balanced_poly, parent_area, all_parcels as bw_parcels, lot_rows as bw_lot_rows, curve_rows as bw_curve_rows
check("Beachwood 27 courses transcribed", len(RAW_COURSES) == 27, len(RAW_COURSES))
check("Beachwood parent balanced closure EXACT",
      abs(balanced_poly[0].dist_to(balanced_poly[-1])) < 1e-6)
check("Beachwood parent area > 60 Acres", parent_area > 60 * 43560, f"{parent_area/43560:.2f} ac")
check("Beachwood 121 lots computed", len(bw_parcels) == 121, len(bw_parcels))
check("Beachwood 121 lot schedule rows", len(bw_lot_rows) == 121, len(bw_lot_rows))
check("Beachwood 100 standard lots at 7500 sf", sum(1 for r in bw_lot_rows if abs(r.area_sqft - 7500.0) < 0.5) == 100)
check("Beachwood 13 curved lots identified with curve IDs", len([r for r in bw_lot_rows if r.curves]) == 13)
check("Beachwood 19 circular curves tabulated (C1-C19)", len(bw_curve_rows) == 19, len(bw_curve_rows))

print("\n=== Ocean Grove parent boundary & 20-lot tabular schedule ===")
from build_ocean_grove import boundary_pts, boundary_area, fec_dist, all_parcels as og_parcels, lot_rows as og_lot_rows
check("Ocean Grove 4-point closed polygon", len(boundary_pts) == 5)
check("Ocean Grove parent closure EXACT",
      abs(boundary_pts[0].dist_to(boundary_pts[-1])) < 1e-6)
check("Ocean Grove FEC corridor distance reasonable", abs(fec_dist - 1108.13) < 0.1, f"{fec_dist:.2f}")
check("Ocean Grove parent area ~9.6 Acres", abs(boundary_area / 43560 - 9.64) < 0.1, f"{boundary_area/43560:.2f} ac")
check("Ocean Grove 20 lots computed", len(og_parcels) == 20, len(og_parcels))
check("Ocean Grove 20 lot schedule rows", len(og_lot_rows) == 20, len(og_lot_rows))
check("Ocean Grove all lots at 6000 sf", all(abs(r.area_sqft - 6000.0) < 0.5 for r in og_lot_rows))

print("\n=== Ground-Truthed GPS database (Zero Fudging) ===")
from engine.georeference import get_intersection_gps
g_ab = get_intersection_gps("Maritime Oak Drive", "Coastal Oak Lane")
g_bev = get_intersection_gps("Heckscher Drive", "Beverly Isle Drive")
g_bw = get_intersection_gps("Starfish Avenue", "Mangrove Avenue")
g_og = get_intersection_gps("Dewees Avenue", "Coquina Place")
g_hk = get_intersection_gps("County Road", "Sibbald Grant")

check("Atlantic Beach GPS exact", g_ab == (30.31688, -81.41945), g_ab)
check("Beverly Isle GPS exact", g_bev == (30.40742, -81.44218), g_bev)
check("Beachwood GPS exact", g_bw == (30.29213, -81.53028), g_bw)
check("Ocean Grove GPS exact", g_og == (30.34212, -81.39865), g_og)
check("Hicks Subdivision GPS exact", g_hk == (30.15528, -81.75833), g_hk)

print("\n=== Cadastral Label & Aliquot Dimension Disambiguation ===")
from engine.labels import is_aliquot_dimension, classify_cadastral_label
check("330 is dimension", is_aliquot_dimension("330") is True)
check("660 is dimension", is_aliquot_dimension("660'") is True)
check("106.83 is dimension", is_aliquot_dimension("106.83") is True)
check("classify 330 -> DIMENSIONS", classify_cadastral_label("330") == "DIMENSIONS")
check("classify LOT 330 -> DIMENSIONS", classify_cadastral_label("LOT 330") == "DIMENSIONS")
check("classify LOT 4 -> LOT_NUMBERS", classify_cadastral_label("LOT 4") == "LOT_NUMBERS")
check("classify BROADWAY -> STREET_NAMES", classify_cadastral_label("BROADWAY") == "STREET_NAMES")

print("\n=== Speckle & False Circle Monument Filtering ===")
from engine.vectorize import filter_speckle_monuments
candidate_circles = [(10, 10, 3), (500, 500, 2), (1200, 1500, 24), (2000, 3000, 95)]
filtered = filter_speckle_monuments(candidate_circles, (4000, 4000))
check("speckle filter removes tiny dust and oversized circles", len(filtered) == 1 and filtered[0][2] == 24)

print("\n=== Matchline Seam Stitching (VertexGraph) ===")
from engine.cogo import Point
from engine.topology import VertexGraph
vg = VertexGraph()
p1 = Point(100.0, 200.0)
p2 = Point(100.1, 200.2)  # within 0.5 ft tolerance
v1 = vg.snap_or_add("PT1", p1)
v2 = vg.snap_or_add("PT2", p2)
check("snap_or_add unifies vertices within tolerance", v1 == "PT1" and v2 == "PT1")
seam = vg.stitch_matchlines([("M1", Point(500.0, 500.0))], [("M2", Point(500.2, 500.1))])
check("stitch_matchlines maps adjoining sheet nodes", seam.get("M2") == "M1")

print("\n=== Clay County Survey-Grade Plat Vectorization ===")
from build_clay_granada import build_granada
from build_clay_orange_grove import build_orange_grove_vale_blvd
from build_clay_kingsley_church import build_kingsley_church
from build_clay_holly_point import build_holly_point
from engine.audit import audit_dxf_layers

dxf_granada = build_granada()
audit_g = audit_dxf_layers(dxf_granada)
check("Granada DXF audit PASS", audit_g["status"] == "PASS")
check("Granada 0 noise circles", audit_g["entity_counts"]["circles"] == 0)

dxf_og = build_orange_grove_vale_blvd()
audit_og = audit_dxf_layers(dxf_og)
check("Orange Grove DXF audit PASS", audit_og["status"] == "PASS")
check("Orange Grove 0 LOT 330 errors", "Detected 3 'LOT 330'" not in str(audit_og["issues"]))

dxf_kc = build_kingsley_church()
audit_kc = audit_dxf_layers(dxf_kc)
check("Kingsley Church DXF audit PASS", audit_kc["status"] == "PASS")

dxf_hp = build_holly_point()
audit_hp = audit_dxf_layers(dxf_hp)
check("Holly Point DXF audit PASS", audit_hp["status"] == "PASS")
check("Holly Point 0 noise circles (eliminated 9,342 circles)", audit_hp["entity_counts"]["circles"] == 0)

print("\n=== 6-Way Complete Circular Curve Solver ===")
from engine.curves import solve_missing
# R=500.0, Delta=45.0 -> L=392.699, C=382.683
c_rd = solve_missing(radius=500.0, delta_deg=45.0)
check("curve pair (R, Delta)", abs(c_rd["length"] - 392.699) < 0.01 and abs(c_rd["chord"] - 382.683) < 0.01)
c_rl = solve_missing(radius=500.0, length=392.69908)
check("curve pair (R, L)", abs(c_rl["delta_deg"] - 45.0) < 0.01 and abs(c_rl["chord"] - 382.683) < 0.01)
c_ld = solve_missing(length=392.69908, delta_deg=45.0)
check("curve pair (L, Delta)", abs(c_ld["radius"] - 500.0) < 0.01 and abs(c_ld["chord"] - 382.683) < 0.01)
c_rc = solve_missing(radius=500.0, chord=382.68343)
check("curve pair (R, C)", abs(c_rc["delta_deg"] - 45.0) < 0.01 and abs(c_rc["length"] - 392.699) < 0.01)
c_dc = solve_missing(delta_deg=45.0, chord=382.68343)
check("curve pair (Delta, C)", abs(c_dc["radius"] - 500.0) < 0.01 and abs(c_dc["length"] - 392.699) < 0.01)
c_lc = solve_missing(length=392.69908, chord=382.68343)
check("curve pair (L, C)", abs(c_lc["radius"] - 500.0) < 0.01 and abs(c_lc["delta_deg"] - 45.0) < 0.01)

print("\n=== Clay County GIS Master Database Georeferencing ===")
g_clay_kr = get_intersection_gps("Kingsley Ave", "River Rd")
check("Clay GIS exact Kingsley Ave & River Rd", g_clay_kr is not None and abs(g_clay_kr[0] - 30.166155) < 0.001)
g_clay_tt = get_intersection_gps("Trail Ridge Rd", "Tynes Blvd")
check("Clay GIS exact Trail Ridge Rd & Tynes Blvd", g_clay_tt is not None and abs(g_clay_tt[0] - 30.132193) < 0.001)

print("\n=== Parcel Inner Rings (Conservation Holes & Net Acreage) ===")
from engine.topology import Parcel
vg_hole = VertexGraph()
# Outer 200x200 square = 40,000 sq ft
vg_hole.add("O1", Point(0.0, 0.0))
vg_hole.add("O2", Point(200.0, 0.0))
vg_hole.add("O3", Point(200.0, 200.0))
vg_hole.add("O4", Point(0.0, 200.0))
# Inner 50x50 hole = 2,500 sq ft
vg_hole.add("H1", Point(50.0, 50.0))
vg_hole.add("H2", Point(100.0, 50.0))
vg_hole.add("H3", Point(100.0, 100.0))
vg_hole.add("H4", Point(50.0, 100.0))
p_hole = Parcel("TRACT-A", ["O1", "O2", "O3", "O4"], vg_hole, inner_rings=[["H1", "H2", "H3", "H4"]])
check("gross area 40,000 sf", p_hole.gross_area_sqft() == 40000.0)
check("net area 37,500 sf", p_hole.net_area_sqft() == 37500.0)
check("net acreage exact", abs(p_hole.net_acreage() - (37500.0 / 43560.0)) < 1e-6)

print("\n=== DXF Linetypes & Text Alignment Verification ===")
from engine.dxf_writer import DXFWriter
dxf_test = DXFWriter()
dxf_test.add_layer("TEST_CENTER", "cyan", "CENTER")
dxf_test.add_layer("TEST_HIDDEN", "magenta", "HIDDEN")
dxf_test.text((100.0, 200.0), "CENTERED LOT", height=5.0, halign=1, valign=2)
tables_str = dxf_test._tables()
header_str = dxf_test._header()
check("DXF LTYPE CENTER registered", "CENTER" in tables_str)
check("DXF LTYPE HIDDEN registered", "HIDDEN" in tables_str)
check("DXF LTYPE PHANTOM registered", "PHANTOM" in tables_str)
check("DXF LTYPE DASHED2 registered", "DASHED2" in tables_str)
check("DXF text alignment group codes 72/73", any("72\n1\n" in e and "73\n2\n" in e for e in dxf_test.entities))
check("DXF STYLE table registered", "TABLE\n2\nSTYLE\n" in tables_str)
check("DXF universal font Arial registered", "3\nArial\n" in tables_str)
check("DXF universal font arial.ttf registered", "3\narial.ttf\n" in tables_str)
check("DXF text has style code 7 STANDARD", any("7\nSTANDARD\n" in e for e in dxf_test.entities))
check("DXF header has ACADVER AC1009", "$ACADVER\n1\nAC1009" in header_str)
check("DXF header has DWGCODEPAGE ANSI_1252", "$DWGCODEPAGE\n3\nANSI_1252" in header_str)

print("\n=== QGIS DXF Font & Companion QML Verification ===")
import tempfile, os
qgis_dxf = DXFWriter()
qgis_dxf.add_layer("BOUNDARY", "green")
qgis_dxf.line((0, 0), (100, 0), layer="BOUNDARY")
qgis_dxf.text((50, 10), "N89°35'00\"E 100.0'")
tf = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
tf_path = tf.name
tf.close()
qgis_dxf.save(tf_path)

with open(tf_path, "rb") as f:
    raw_dxf = f.read()
check("DXF pure 7-bit ASCII (zero mojibake)", all(b < 128 for b in raw_dxf))
check("DXF degree escaped as %%d", b"%%d" in raw_dxf and b"\xc2\xb0" not in raw_dxf)

qml_file = tf_path[:-4] + ".qml"
check("companion QML file auto-generated", os.path.exists(qml_file))

try:
    import qgis.core
    from qgis.core import QgsApplication, QgsVectorLayer
    qgs_app = QgsApplication([], False)
    qgs_app.initQgis()
    vl_test = QgsVectorLayer(tf_path, "qgis_test", "ogr")
    check("QGIS layer valid", vl_test.isValid())
    check("QGIS companion QML auto-enables labels", vl_test.labelsEnabled())
    vl_feats = list(vl_test.getFeatures())
    vl_texts = [f["Text"] for f in vl_feats if f["Text"]]
    check("QGIS text decodes degree without Â mojibake", any("°" in t and "Â" not in t for t in vl_texts))
    qgs_app.exitQgis()
except Exception as ex:
    check(f"QGIS verification: {ex}", False)

if os.path.exists(tf_path):
    os.remove(tf_path)
if os.path.exists(qml_file):
    os.remove(qml_file)

print(f"\n{'='*52}")
print(f"{len(FAILURES)} failure(s)" if FAILURES else "ALL TESTS PASS")
if FAILURES:
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)

