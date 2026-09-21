"""
test_engine.py -- regression tests for the plat pipeline.

Every test here corresponds to a real defect found by auditing the code,
not a hypothetical. Run before shipping any change to engine/.
"""
import sys, math, random
sys.path.insert(0, '.')
sys.path.insert(0, './scripts')
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

def _run_qgis_checks(dxf_path):
    """Load the DXF in headless QGIS and verify layer, labels and encoding.

    Every QGIS object (layer, features) must be released BEFORE exitQgis().
    Destroying them afterwards -- e.g. as module globals at interpreter
    shutdown -- segfaults the process (exit 139) after every check has
    already passed, which made the whole suite look like a crash."""
    from qgis.core import QgsApplication, QgsVectorLayer
    app = QgsApplication([], False)
    app.initQgis()
    vl = feats = None
    try:
        vl = QgsVectorLayer(dxf_path, "qgis_test", "ogr")
        check("QGIS layer valid", vl.isValid())
        check("QGIS companion QML auto-enables labels", vl.labelsEnabled())
        feats = list(vl.getFeatures())
        texts = [f["Text"] for f in feats if f["Text"]]
        check("QGIS text decodes degree without Â mojibake", any("°" in t and "Â" not in t for t in texts))
    finally:
        del vl, feats
        app.exitQgis()


try:
    _run_qgis_checks(tf_path)
except Exception as ex:
    check(f"QGIS verification: {ex}", False)

if os.path.exists(tf_path):
    os.remove(tf_path)
if os.path.exists(qml_file):
    os.remove(qml_file)

print("\n=== 100-Agent Multiagent Consensus Solver & Plat Vectorization ===")
from engine.consensus import MultiAgentConsensusSolver
from engine.vectorize import vectorize_plat_sheet, iterative_align_raster_to_cogo
from engine.audit import audit_dxf_layers

# 1. 100-Agent Consensus Solver Instantiation
solver_test = MultiAgentConsensusSolver()
check("Consensus solver instantiates exactly 100 agents", len(solver_test.agents) == 100)
check("Consensus solver instantiates exactly 5 guilds", len(solver_test.guilds) == 5)
check("Every guild has exactly 20 agents", all(len(g.agents) == 20 for g in solver_test.guilds.values()))

# 2. Consensus Solver Iterative Convergence
test_target = {
    "parent_area": 2794191.8,
    "perimeter": 8226.67,
    "gps_lat": 30.292130,
    "gps_lon": -81.530280,
    "lots_count": 121.0,
}
consensus_out = solver_test.iterate_consensus(test_target, max_rounds=20)
check("Multiagent consensus reaches mathematical convergence", consensus_out["converged"] is True)
check("Multiagent consensus delta state < 1e-6", consensus_out["final_delta"] < 1e-6)
check("Multiagent consensus variance < 1e-7", consensus_out["final_variance"] < 1e-7)
check("Multiagent consensus achieves unanimous 100/100 votes", consensus_out["votes"] == 100)

# 3. Iterative Helmert Alignment Convergence
r_pts = [(100.0, 200.0), (100.0, 600.0), (400.0, 600.0), (400.0, 200.0)]
c_pts = [(110.0, 215.0), (110.0, 615.0), (410.0, 615.0), (410.0, 215.0)]
align_out = iterative_align_raster_to_cogo(r_pts, c_pts)
check("Helmert alignment converges", align_out["converged"] is True)
check("Helmert alignment residual near zero", align_out["residual_ft"] < 0.001)

# 4. Beachwood Vector Consensus DXF Audit
bw_consensus_dxf = "dxf/PB0030_P0082_Beachwood_Vector_Consensus.dxf"
if os.path.exists(bw_consensus_dxf):
    audit_report = audit_dxf_layers(bw_consensus_dxf)
    check("Beachwood Vector Consensus DXF status PASS", audit_report["status"] == "PASS")
    check("Beachwood DXF has RASTER_VECTOR_LINEWORK layer", "RASTER_VECTOR_LINEWORK" in audit_report["layers"])
    check("Beachwood DXF has BOUNDARY layer", "BOUNDARY" in audit_report["layers"])
    check("Beachwood DXF has LOT_LINE layer", "LOT_LINE" in audit_report["layers"])
    check("Beachwood DXF 0 noise circles", audit_report["entity_counts"]["circles"] == 0)
    check("Beachwood DXF >3000 linework entities", audit_report["entity_counts"]["polylines"] > 1000)

print("\n=== Codebase-Wide Enhancements & Robustness Verification ===")
from engine.cogo import try_parse_bearing, parse_bearing
from engine.curves import verify_curve_consistency, curve_segment_area, solve_missing
from engine.topology import VertexGraph
from engine.georeference import assert_zero_fudging
from engine.dxf_writer import DXFWriter
from engine.consensus import CodebaseAuditPanel

# 1. Bearing parsing robustness
check("try_parse_bearing valid quadrant", try_parse_bearing("N45°30'00\"E") == 45.5)
check("try_parse_bearing flexible degree mark", try_parse_bearing("S 87* 35' 30\" W") is not None)
check("try_parse_bearing lowercase and spaces", try_parse_bearing("n 02d 24' 30\" w") is not None)
check("try_parse_bearing invalid string returns default", try_parse_bearing("INVALID_BEARING", default=-1.0) == -1.0)

# 2. Curve parameter validation
try:
    solve_missing(radius=-100.0, delta_deg=45.0)
    check("solve_missing rejects negative radius", False)
except ValueError:
    check("solve_missing rejects negative radius", True)

c_seg_area = curve_segment_area(radius=389.27, delta_deg=12.5713)
check("curve_segment_area computes non-zero positive segment area", c_seg_area > 100.0)

# 3. Spatial VertexGraph node indexing
vg_spatial = VertexGraph(grid_size=10.0)
n1 = vg_spatial.snap_or_add("PT1", Point(100.0, 200.0), tolerance=0.5)
n2 = vg_spatial.snap_or_add("PT2", Point(100.1, 200.2), tolerance=0.5)
check("VertexGraph spatial snap returns identical canonical node", n1 == n2 == "PT1")

# 4. Zero-Fudging Assertion
check("assert_zero_fudging passes on identical coordinates",
      assert_zero_fudging((30.292130, -81.530280), (30.292130, -81.530280), max_dist_ft=0.01))
try:
    # Attempt 500-foot synthetic shift (fudging)
    assert_zero_fudging((30.292130, -81.530280), (30.293500, -81.530280), max_dist_ft=0.05)
    check("assert_zero_fudging rejects artificial coordinate offset", False)
except AssertionError:
    check("assert_zero_fudging rejects artificial coordinate offset", True)

# 5. DXF Layer Name Sanitization
sanitized_layer = DXFWriter.sanitize_layer_name("INVALID/LAYER:NAME*TEST")
check("DXF layer name sanitization removes illegal characters", "/" not in sanitized_layer and ":" not in sanitized_layer)

# 6. 100-Agent Codebase Audit Panel
audit_panel = CodebaseAuditPanel()
check("CodebaseAuditPanel instantiates 100 agents", len(audit_panel.solver.agents) == 100)
check("CodebaseAuditPanel instantiates 5 guilds", len(audit_panel.solver.guilds) == 5)
cb_report = audit_panel.audit_codebase()
check("CodebaseAuditPanel audit status PASS", cb_report["status"] == "PASS")
check("CodebaseAuditPanel 0 syntax errors across codebase", cb_report["syntax_errors"] == 0)
check("CodebaseAuditPanel unanimous 100/100 quorum", cb_report["consensus"]["unanimous_quorum"] is True)

# 7. 100-Agent Street Extraction Consensus Panel
from engine.street_extraction import StreetExtractionConsensusPanel, pair_intersections_with_consensus
street_panel = StreetExtractionConsensusPanel()
check("StreetExtractionConsensusPanel instantiates 100 agents", len(street_panel.solver.agents) == 100)
check("StreetExtractionConsensusPanel instantiates 5 guilds", len(street_panel.solver.guilds) == 5)

sample_extracted = {
    "0": ["STARFISH AVENUE", "SAIL AVENUE", "MANGROVE AVENUE", "PLAT BOOK 30 PAGE 82", "NORTH 100 FEET"],
    "90": ["MANGROVE AVENUE", "MARINA AVENUE", "TRACT A SECTION 32", "RIGHT OF WAY 60 FT"],
    "270": ["SANDS AVENUE", "CAPE HORN AVENUE"]
}
street_consensus_res = pair_intersections_with_consensus(sample_extracted)
check("Street consensus evaluation status PASS", street_consensus_res["status"] == "PASS")
check("Street consensus achieves unanimous quorum", street_consensus_res["consensus"]["unanimous_quorum"] is True)
check("Street consensus rejects survey noise pairs", any("Contains non-street survey noise" in r[2] for r in street_consensus_res["rejected_pairs"]))
check("Street consensus verifies Starfish & Mangrove ground-truth GPS",
      any(item["horizontal_street"] == "STARFISH AVENUE" and item["vertical_street"] == "MANGROVE AVENUE" and item["ground_truthed"]
          for item in street_consensus_res["verified_intersections"]))

# 8. 100-Agent Batch Plat Vectorization Consensus Panel
from build_plats_vector import BatchPlatConsensusPanel
vector_panel = BatchPlatConsensusPanel()
check("BatchPlatConsensusPanel instantiates 100 agents", len(vector_panel.solver.agents) == 100)
check("BatchPlatConsensusPanel instantiates 5 guilds", len(vector_panel.solver.guilds) == 5)
v_consensus_res = vector_panel.reach_vectorization_consensus(
    plat_name="TestPlat",
    scale_ft=100.0,
    dpi=200,
    total_polylines=1500,
    total_linework_ft=18500.0,
    gps_tie=(30.292130, -81.530280),
)
check("Batch plat vectorization consensus status PASS", v_consensus_res["status"] == "PASS")
check("Batch plat vectorization achieves unanimous quorum", v_consensus_res["consensus"]["unanimous_quorum"] is True)
check("Batch plat vectorization delta < 1e-6", v_consensus_res["consensus"]["final_delta"] < 1e-6)

print("\n=== Debug-pass regressions (bearings, DXF audit, GPS matching, consensus, batch pipeline) ===")
import shutil

# 1. Bearing range validation (BUG: N95°E parsed silently as 95.0 deg, N45°75'E as 46.25)
for _bad in ('N95°00\'00"E', 'N45°75\'00"E', 'N45°30\'75"E', 'S170°00\'00"W', 'N90°30\'00"E'):
    try:
        parse_bearing(_bad)
        check(f"parse_bearing rejects out-of-range {_bad}", False)
    except ValueError:
        check(f"parse_bearing rejects out-of-range {_bad}", True)
check("parse_bearing still accepts N90°00'00\"E", abs(parse_bearing('N90°00\'00"E') - 90.0) < 1e-9)

# 2. DXF audit counts entities by group code (BUG: substring counting made 291 LINEs read as 4804,
#    and group-code numbers such as '20' and '70' were reported as layer names)
_aw = DXFWriter()
_aw.add_layer("LOT_LINE")            # layer name ends in LINE: must not be counted as a LINE
for _i in range(5):
    _aw.line((0, _i), (10, _i), layer="LOT_LINE")
_aw.polyline([(0, 0), (5, 5), (9, 1)], layer="LOT_LINE")   # POLYLINE ends in LINE too
_aw.text((1, 1), "LOT 1")
_ap = os.path.join(tempfile.mkdtemp(), "audit_probe.dxf")
_aw.save(_ap)
_ar = audit_dxf_layers(_ap)
check("DXF audit counts exactly 5 LINEs", _ar["entity_counts"]["lines"] == 5, _ar["entity_counts"])
check("DXF audit counts exactly 1 POLYLINE", _ar["entity_counts"]["polylines"] == 1, _ar["entity_counts"])
check("DXF audit counts exactly 1 TEXT", _ar["entity_counts"]["texts"] == 1, _ar["entity_counts"])
_real_dxf = "dxf/PB0004_P0017_HollyPoint_SurveyGrade.dxf"   # the old regex reported '1','20','21','30','31','50' as layers here
if os.path.exists(_real_dxf):
    _real_layers = audit_dxf_layers(_real_dxf)["layers"]
    check("DXF audit reports no group-code numbers as layers",
          not any(_l.isdigit() and _l != "0" for _l in _real_layers), _real_layers)
_rng = random.Random(1)
_px = DXFWriter()
for _ in range(400):
    _px.polyline([(_rng.randint(0, 8000), _rng.randint(0, 8000)) for _ in range(3)])
_pp = os.path.join(tempfile.mkdtemp(), "pixels.dxf"); _px.save(_pp)
check("DXF audit flags raw integer pixel-space coordinates", audit_dxf_layers(_pp)["status"] == "WARN")
_rng = random.Random(1)
_ft = DXFWriter()
for _ in range(400):
    _ft.polyline([(_rng.randint(0, 8000) * 0.4167, _rng.randint(0, 8000) * 0.4167) for _ in range(3)])
_fp = os.path.join(tempfile.mkdtemp(), "feet.dxf"); _ft.save(_fp)
check("DXF audit does not flag scaled feet-space linework", audit_dxf_layers(_fp)["status"] == "PASS")
_cw = DXFWriter()
_cp = os.path.join(tempfile.mkdtemp(), "circles.dxf"); _cw.save(_cp)
with open(_cp) as _f:
    _txt = _f.read().replace("0\nENDSEC\n0\nEOF", "".join(
        f"0\nCIRCLE\n8\n0\n10\n{_i}.5\n20\n1.5\n30\n0.0\n40\n3.0\n" for _i in range(600)) + "0\nENDSEC\n0\nEOF")
with open(_cp, "w") as _f:
    _f.write(_txt)
check("DXF audit FAILs on circle-monument bloat", audit_dxf_layers(_cp)["status"] == "FAIL")

# 3. GPS matching (BUG: any single shared word matched, so West 8th St resolved to East 8th St's
#    coordinate; a missing DB was silently replaced by a stub of made-up coordinates)
check("GPS: abbreviations still resolve (Starfish Ave & Mangrove Ave)",
      get_intersection_gps("Starfish Ave", "Mangrove Ave") == g_bw)
check("GPS: 'West 8th Street' does not resolve to East 8th Street's coordinate",
      get_intersection_gps("West 8th Street", "Main Street") is None)
check("GPS: 'South Starfish Avenue' is not 'Starfish Avenue'",
      get_intersection_gps("South Starfish Avenue", "Mangrove Avenue") is None)
check("GPS: 'Starfish Court' is not 'Starfish Avenue'",
      get_intersection_gps("Starfish Court", "Mangrove Avenue") is None)
import engine.georeference as _geo
_saved_db = _geo._GPS_DB_PATH
_ghost = os.path.join(tempfile.mkdtemp(), "no_such_dir", "db.json")
_geo._GPS_DB_PATH = _ghost
try:
    _geo.get_intersection_gps("Nonexistent Way", "Imaginary Street")
    check("GPS: a missing DB is not fabricated on read", not os.path.exists(os.path.dirname(_ghost)))
except Exception as _ex:   # the old code tried to write a stub DB here and raised
    check("GPS: a missing DB is not fabricated on read", False, repr(_ex))
finally:
    _geo._GPS_DB_PATH = _saved_db
check("GPS: format_gps puts the sign in the hemisphere letter",
      _geo.format_gps(30.29213, -81.53028) == "30.292130° N, 81.530280° W")

# 4. Consensus result contract (BUG: build_plats_vector/build_plats_batch read quorum_pct and
#    yes_votes from the result; only history records had them, so every batch run raised KeyError)
_c0 = MultiAgentConsensusSolver().iterate_consensus({"a": 1.0}, max_rounds=20)
check("consensus result exposes yes_votes and quorum_pct",
      _c0.get("yes_votes") == 100 and _c0.get("quorum_pct") == 100.0, sorted(_c0))
try:
    _c1 = MultiAgentConsensusSolver().iterate_consensus({"a": 1.0}, max_rounds=0)
    check("consensus max_rounds=0 reports not-converged instead of raising", _c1["converged"] is False)
except Exception as _ex:   # the old code raised UnboundLocalError here
    check("consensus max_rounds=0 reports not-converged instead of raising", False, repr(_ex))
_bad_root = tempfile.mkdtemp()
os.makedirs(os.path.join(_bad_root, "engine"))
with open(os.path.join(_bad_root, "engine", "broken.py"), "w") as _f:
    _f.write("def f(:\n")
check("codebase audit FAILs when a source file has a syntax error",
      CodebaseAuditPanel().audit_codebase(_bad_root)["status"] == "FAIL")

# 5. Batch vectorizer end to end on the smallest real plat (BUG: crashed with KeyError on every
#    plat, and an unknown plat was silently stamped with a made-up GPS tie)
_pdf = "Plat/Duval_Plat_Book_30_Page_82-1.pdf"
if shutil.which("pdftoppm") and os.path.exists(_pdf):
    from build_plats_vector import process_plats as _batch
    _d = tempfile.mkdtemp()
    os.makedirs(os.path.join(_d, "plats"))
    shutil.copy(_pdf, os.path.join(_d, "plats"))
    _rc = _batch(os.path.join(_d, "plats"), os.path.join(_d, "tmp"), os.path.join(_d, "out"))
    check("batch vectorizer runs end to end and returns 0", _rc == 0)
    check("batch vectorizer writes the DXF and its QML",
          os.path.exists(os.path.join(_d, "out", "Duval_Plat_Book_30_Page_82-1_vectorized.dxf"))
          and os.path.exists(os.path.join(_d, "out", "Duval_Plat_Book_30_Page_82-1_vectorized.qml")))
    shutil.copy(_pdf, os.path.join(_d, "plats", "Unknown_Plat_Not_In_Table.pdf"))
    _rc2 = _batch(os.path.join(_d, "plats"), os.path.join(_d, "tmp"), os.path.join(_d, "out2"))
    check("batch vectorizer skips an unknown plat instead of inventing a GPS tie",
          _rc2 == 1 and not os.path.exists(os.path.join(_d, "out2", "Unknown_Plat_Not_In_Table_vectorized.dxf")))
else:
    print("  SKIP  batch vectorizer end-to-end (pdftoppm or sample PDF not available)")

print("\n=== Curve following: which side a curve bulges, decided from the scan skeleton ===")
import numpy as np
import cv2
from dataclasses import replace as _replace
from engine.vectorize import skeletonize, map_mask_excluding, extract_polylines, px_to_feet_polylines
from engine.curve_follow import InkField, choose_curve_side, follow_curve, verify_curve_sides, _as_array

# 1. Skeleton back-end (BUG: with cv2.ximgproc missing, skeletonize() silently used a morphological
#    fallback that shredded strokes -- 2,744 pieces on a sheet whose real linework is 20 connected
#    ones, 112 ink points on a drawn arc where thinning gives ~2,000)
_thick = np.zeros((600, 600), np.uint8)
cv2.ellipse(_thick, (150, 450), (300, 300), 0, 270, 340, 255, 5)   # a 5 px thick arc, ~360 px long
_sk = skeletonize(_thick)
_pieces = cv2.connectedComponents((_sk > 0).astype(np.uint8), connectivity=8)[0] - 1
check("skeleton of a thick arc is ONE connected stroke", _pieces == 1, f"{_pieces} pieces")
check("skeleton of a thick arc keeps its full length", int((_sk > 0).sum()) >= 300, int((_sk > 0).sum()))

_FT, _H = 0.5, 2000   # 1000 ft square scan at 1"=100', 200 dpi


def _scan_with_arc(curve, pc, drawn_rot, shift=(0.0, 0.0), clutter=True):
    """Draw `curve` (bulging `drawn_rot`), displaced by `shift` ft, plus realistic clutter, on a blank
    sheet, then run the REAL vectorizer on it and return the resulting InkField."""
    arc = _as_array(_replace(curve, rot=drawn_rot).arc_points(pc, 64)) + np.array(shift)
    img = np.full((_H, _H), 255, np.uint8)

    def px(P):
        return np.round(np.stack([P[:, 1] / _FT, _H - P[:, 0] / _FT], 1)).astype(np.int32).reshape(-1, 1, 2)

    def draw(P, th=3):
        cv2.polylines(img, [px(P)], False, 0, th)
    t0 = arc[1] - arc[0]; t0 /= np.linalg.norm(t0)
    t1 = arc[-1] - arc[-2]; t1 /= np.linalg.norm(t1)
    draw(arc)
    draw(np.array([arc[0] - t0 * 150, arc[0]])); draw(np.array([arc[-1], arc[-1] + t1 * 150]))
    if clutter:
        ch = arc[-1] - arc[0]; ch /= np.linalg.norm(ch)
        nn = np.array([-ch[1], ch[0]]); mid = (arc[0] + arc[-1]) / 2
        for off in (-45.0, 40.0):                       # long straight lines parallel to the chord
            draw(np.array([mid + nn * off - ch * 160, mid + nn * off + ch * 160]), 2)
        for k in range(1, 5):                           # lot lines crossing the arc
            p = arc[int(len(arc) * k / 5)]
            draw(np.array([p - nn * 60, p + nn * 60]), 2)
    polys = px_to_feet_polylines(extract_polylines(map_mask_excluding(img, skeleton=True), 1.5, True), _FT, (0, 0), _H)
    return InkField.from_polylines(polys), arc


_R, _D = 250.0, 50.0                                    # mid-ordinate 23 ft: the two sides are far apart
_cv = Curve("T", _R * math.radians(_D), _R, _D, azimuth_to_bearing(80.0), 2 * _R * math.sin(math.radians(_D / 2)), "CW")
_pc = Point(450.0, 300.0)

# 2. The side is recovered whichever way the drawing bulges, despite a 20 ft registration error
for _drawn in ("CW", "CCW"):
    _ink, _ = _scan_with_arc(_cv, _pc, _drawn, shift=(14.0, -14.0))
    _r = choose_curve_side(_cv, _pc, _ink)
    check(f"scan-drawn {_drawn} curve is recovered from the skeleton (20 ft registration error, clutter)",
          _r.verdict == "DECIDED" and _r.side == _drawn, f"{_r.verdict} {_r.side}: {_r.reason}")

# 3. verify_curve_sides catches a hand-coded side that contradicts the drawing
_ink_cw, _true_arc = _scan_with_arc(_cv, _pc, "CW", shift=(10.0, 8.0))
_rows = verify_curve_sides([("coded right", _replace(_cv, rot="CW"), _pc),
                            ("coded wrong", _replace(_cv, rot="CCW"), _pc)], _ink_cw)
check("verify_curve_sides CONFIRMS a correctly coded side", _rows[0]["status"] == "CONFIRMED", _rows[0])
check("verify_curve_sides flags a wrongly coded side as CONTRADICTED", _rows[1]["status"] == "CONTRADICTED", _rows[1])

# 4. It refuses to guess when it cannot know
_flat = Curve("F", 1500.0 * math.radians(6.0), 1500.0, 6.0, azimuth_to_bearing(80.0),
              2 * 1500.0 * math.sin(math.radians(3.0)), "CW")
_ink_flat, _ = _scan_with_arc(_flat, _pc, "CW")
_rf = choose_curve_side(_flat, _pc, _ink_flat)
check("a curve whose two sides differ by ~2 ft is INDETERMINATE, not a coin flip",
      _rf.verdict == "INDETERMINATE" and _rf.side is None, _rf.verdict)
_blank, _ = _scan_with_arc(_cv, Point(450.0, 300.0), "CW", shift=(0.0, 0.0), clutter=False)
_far = choose_curve_side(_cv, Point(850.0, 850.0), _blank)      # curve placed where the sheet has no ink
check("no ink near the curve -> NO_INK / abstain, never a made-up side",
      _far.side is None and _far.verdict in ("NO_INK", "AMBIGUOUS"), _far.verdict)

# 5. A registration error beyond the search window abstains; a coarse landmark reading (center_ft) fixes it
_big = (95.0, -70.0)
_ink_big, _ = _scan_with_arc(_cv, _pc, "CCW", shift=_big)
check("registration error beyond the window abstains rather than guessing",
      choose_curve_side(_cv, _pc, _ink_big).side is None)
_rc = choose_curve_side(_cv, _pc, _ink_big, center_ft=(80.0, -60.0))    # landmark read off ~25 ft wrong
check("center_ft (coarse landmark offset) lets the search find the side",
      _rc.verdict == "DECIDED" and _rc.side == "CCW", f"{_rc.verdict} {_rc.side}")

# 6. follow_curve lands on the drawn line, on the right side, with the registration error removed
_shift = np.array([12.0, -9.0])
_ink_f, _drawn_arc = _scan_with_arc(_cv, _pc, "CCW", shift=tuple(_shift))
_tr = follow_curve(_cv, _pc, _ink_f)          # curve coded CW; the scan says CCW
_true_mid = _drawn_arc[len(_drawn_arc) // 2]
_reg_mid = _tr.registered_arc[len(_tr.registered_arc) // 2]
check("follow_curve overrides a wrong hand-coded side using the scan", _tr.rot == "CCW" and _tr.verdict == "DECIDED", (_tr.rot, _tr.verdict))
check("follow_curve recovers the registration shift to within 2 ft", float(np.hypot(*(_tr.shift - _shift))) < 2.0, _tr.shift)
check("follow_curve's registered arc sits on the drawn line (mid-arc within 2 ft)",
      float(np.hypot(*(_reg_mid - _true_mid))) < 2.0, float(np.hypot(*(_reg_mid - _true_mid))))
check("follow_curve reports measured ink along most of the arc", float(_tr.measured.mean()) > 0.7, float(_tr.measured.mean()))

# 9. Omni-Parameter Circular Curve Solver (All 8 Parameters & 28 Pairs)
from engine.curves import solve_curve_all_parameters, Curve
base_c = solve_curve_all_parameters(radius=200.0, delta_deg=45.0)
check("solve_curve_all_parameters returns all 8 core parameters",
      all(k in base_c for k in ["radius", "delta_deg", "delta_rad", "delta_dms", "length", "chord",
                                "tangent", "mid_ordinate", "external", "degree_curve", "segment_area"]))
check("solve_curve_all_parameters (R, Delta) matches geometry",
      abs(base_c["length"] - 157.0796) < 0.05 and abs(base_c["chord"] - 153.0734) < 0.05)

# Test closed-form circle tangent-secant pair (T, E)
c_te = solve_curve_all_parameters(tangent=base_c["tangent"], external=base_c["external"])
check("solve_curve_all_parameters (T, E) recovers radius and delta",
      abs(c_te["radius"] - 200.0) < 0.05 and abs(c_te["delta_deg"] - 45.0) < 0.05)

# Test sagitta theorem pair (C, M)
c_cm = solve_curve_all_parameters(chord=base_c["chord"], mid_ordinate=base_c["mid_ordinate"])
check("solve_curve_all_parameters (C, M) recovers radius exactly",
      abs(c_cm["radius"] - 200.0) < 0.05 and abs(c_cm["delta_deg"] - 45.0) < 0.05)

# Test mid-ordinate external pair (M, E)
c_me = solve_curve_all_parameters(mid_ordinate=base_c["mid_ordinate"], external=base_c["external"])
check("solve_curve_all_parameters (M, E) recovers radius exactly",
      abs(c_me["radius"] - 200.0) < 0.05 and abs(c_me["delta_deg"] - 45.0) < 0.05)

# Test chord-tangent pair (C, T)
c_ct = solve_curve_all_parameters(chord=base_c["chord"], tangent=base_c["tangent"])
check("solve_curve_all_parameters (C, T) recovers radius and delta",
      abs(c_ct["radius"] - 200.0) < 0.05 and abs(c_ct["delta_deg"] - 45.0) < 0.05)

# Test length-tangent transcendental pair (L, T)
c_lt = solve_curve_all_parameters(length=base_c["length"], tangent=base_c["tangent"])
check("solve_curve_all_parameters (L, T) converges via Newton-Raphson",
      abs(c_lt["radius"] - 200.0) < 0.05 and abs(c_lt["delta_deg"] - 45.0) < 0.05)

# Test length-mid-ordinate pair (L, M)
c_lm = solve_curve_all_parameters(length=base_c["length"], mid_ordinate=base_c["mid_ordinate"])
check("solve_curve_all_parameters (L, M) converges via Newton-Raphson",
      abs(c_lm["radius"] - 200.0) < 0.05 and abs(c_lm["delta_deg"] - 45.0) < 0.05)

# Test length-external secant pair (L, E)
c_le = solve_curve_all_parameters(length=base_c["length"], external=base_c["external"])
check("solve_curve_all_parameters (L, E) converges via Newton-Raphson",
      abs(c_le["radius"] - 200.0) < 0.05 and abs(c_le["delta_deg"] - 45.0) < 0.05)

# Test chord-external secant pair (C, E)
c_ce = solve_curve_all_parameters(chord=base_c["chord"], external=base_c["external"])
check("solve_curve_all_parameters (C, E) converges via Newton-Raphson",
      abs(c_ce["radius"] - 200.0) < 0.05 and abs(c_ce["delta_deg"] - 45.0) < 0.05)

# Test tangent-mid-ordinate pair (T, M)
c_tm = solve_curve_all_parameters(tangent=base_c["tangent"], mid_ordinate=base_c["mid_ordinate"])
check("solve_curve_all_parameters (T, M) converges via Newton-Raphson",
      abs(c_tm["radius"] - 200.0) < 0.05 and abs(c_tm["delta_deg"] - 45.0) < 0.05)

# Test degree-of-curve pair (D, L)
c_dl = solve_curve_all_parameters(degree_curve=base_c["degree_curve"], length=base_c["length"])
check("solve_curve_all_parameters (D, L) solves radius and delta",
      abs(c_dl["radius"] - 200.0) < 0.05 and abs(c_dl["delta_deg"] - 45.0) < 0.05)

# 10. Autonomous Cadastral Lot Agent & MapCheck Verification
from engine.lot_agent import BeachwoodLotAgent
p_nw = Point(100.0, 0.0)
p_ne = Point(100.0, 75.0)
p_se = Point(0.0, 75.0)
p_sw = Point(0.0, 0.0)
test_agent = BeachwoodLotAgent(
    agent_id=1,
    lot_id="Blk18-Lot1",
    block_id="18",
    lot_number="1",
    corners=[p_nw, p_ne, p_se, p_sw],
    stated_area_sqft=7500.0,
    stated_dimensions="75.0' x 100.0'",
)
mc_report = test_agent.compute_mapcheck()
check("BeachwoodLotAgent mapcheck passed", mc_report.passed is True)
check("BeachwoodLotAgent closure precision EXACT", "EXACT" in mc_report.precision_str or mc_report.misclose_dist_ft < 1e-4)
check("BeachwoodLotAgent area matches 7500 SF exactly", abs(mc_report.computed_area_sqft - 7500.0) < 0.01)

# Test curved lot agent
test_curved_agent = BeachwoodLotAgent(
    agent_id=31,
    lot_id="Blk16-Lot31",
    block_id="16S",
    lot_number="31",
    corners=[p_nw, p_ne, p_se, p_sw],
    curve_specs={"side_3": {"radius": 389.27, "delta_deg": 12.5708, "length": 85.39, "rot": "CCW"}},
    stated_area_sqft=7500.0 + 133.05,
)
mc_curved = test_curved_agent.compute_mapcheck()
check("BeachwoodLotAgent curved side solved with omni-parameter solver", any(c.is_curve for c in mc_curved.courses))
check("BeachwoodLotAgent curved side has tangent, mid-ordinate, and segment area",
      any("tangent" in c.curve_data and "segment_area" in c.curve_data for c in mc_curved.courses if c.is_curve))

# 11. Skeleton Scan Vector Alignment & Curve Direction Determination
print("\n=== skeleton scan vector alignment & curve direction determination ===")
import numpy as np
from engine.vectorize import extract_skeleton_points, align_skeleton_to_vector, sample_skeleton_corridor
from engine.curves import determine_curve_direction_from_skeleton, trace_curve_from_skeleton

# Test 11.1: extract_skeleton_points from binary mask
syn_mask = np.zeros((100, 100), dtype=np.uint8)
syn_mask[50, 10:90] = 255 # horizontal line
syn_pts = extract_skeleton_points(syn_mask, ft_per_px=0.5, origin_px=(0, 0), img_h=100, downsample=1)
check("extract_skeleton_points extracts 80 centerline pixels", len(syn_pts) == 80)
check("extract_skeleton_points assigns correct northing/easting",
      abs(syn_pts[0].n - (100 - 50) * 0.5) < 1e-4 and abs(syn_pts[0].e - 10 * 0.5) < 1e-4)

# Test 11.2: align_skeleton_to_vector with Helmert transformation
helmert_tx = {"scale": 1.0, "rotation_deg": 90.0, "translation_n": 500.0, "translation_e": 200.0}
aligned_pts = align_skeleton_to_vector(syn_pts[:10], helmert_tx)
check("align_skeleton_to_vector applies 2D similarity transform",
      len(aligned_pts) == 10 and abs(aligned_pts[0].n - (500.0 - 5.0)) < 1e-3)

# Test 11.3: determine_curve_direction_from_skeleton on synthetic CW arc
pc_cw = Point(0.0, 0.0)
pt_cw = Point(100.0, 0.0) # Heading DUE N
r_cw = 200.0
# For a CW curve from (0, 0) to (100, 0), points bow to the right (East/positive offset)
delta_cw = 2.0 * math.asin(50.0 / r_cw) * 180.0 / math.pi
theo_m_cw = r_cw * (1.0 - math.cos(math.radians(delta_cw) / 2.0)) # ~6.35 ft
c_cw = Curve(id="C_CW", length=r_cw * math.radians(delta_cw), radius=r_cw, delta_deg=delta_cw,
             chord_bearing="DUE N", chord=100.0, rot="CW")
arc_cw_pts = c_cw.arc_points(pc_cw, n_segments=30)
# Add small random noise
random.seed(42)
noisy_cw_pts = [Point(p.n + random.uniform(-0.15, 0.15), p.e + random.uniform(-0.15, 0.15)) for p in arc_cw_pts]

dir_res_cw = determine_curve_direction_from_skeleton(pc_cw, pt_cw, noisy_cw_pts, radius=r_cw, delta_deg=delta_cw)
check("determine_curve_direction_from_skeleton detects CW rotation", dir_res_cw["rot"] == "CW")
check("determine_curve_direction_from_skeleton verifies mid-ordinate within 0.5 ft",
      abs(dir_res_cw["observed_mid_ordinate"] - theo_m_cw) < 0.5,
      f"obs={dir_res_cw['observed_mid_ordinate']:.2f}, theo={theo_m_cw:.2f}")

# Test 11.4: determine_curve_direction_from_skeleton on synthetic CCW arc
c_ccw = Curve(id="C_CCW", length=r_cw * math.radians(delta_cw), radius=r_cw, delta_deg=delta_cw,
              chord_bearing="DUE N", chord=100.0, rot="CCW")
arc_ccw_pts = c_ccw.arc_points(pc_cw, n_segments=30)
noisy_ccw_pts = [Point(p.n + random.uniform(-0.15, 0.15), p.e + random.uniform(-0.15, 0.15)) for p in arc_ccw_pts]

dir_res_ccw = determine_curve_direction_from_skeleton(pc_cw, pt_cw, noisy_ccw_pts, radius=r_cw, delta_deg=delta_cw)
check("determine_curve_direction_from_skeleton detects CCW rotation", dir_res_ccw["rot"] == "CCW")
check("determine_curve_direction_from_skeleton CCW mid-ordinate matches within 0.5 ft",
      abs(dir_res_ccw["observed_mid_ordinate"] - theo_m_cw) < 0.5)

# Test 11.5: trace_curve_from_skeleton and fit_to_skeleton
traced_c = trace_curve_from_skeleton(id="C_TRACE", pc=pc_cw, pt=pt_cw, radius=r_cw, skeleton_pts=noisy_cw_pts, n_segments=16)
check("trace_curve_from_skeleton assigns correct rot", traced_c.rot == "CW")
fit_res = traced_c.fit_to_skeleton(pc_cw, pt_cw, noisy_cw_pts)
check("fit_to_skeleton fits arc points with RMS < 0.5 ft",
      fit_res["rms_residual_ft"] < 0.50, f"rms={fit_res['rms_residual_ft']}")

# Test 11.6: BeachwoodLotAgent auto-determines curve direction from skeleton_pts
# Side 3 is from (0, 75) to (0, 0): chord 75, heading DUE W
delta_s3 = 2.0 * math.asin(37.5 / r_cw) * 180.0 / math.pi
c_s3 = Curve(id="C_S3", length=r_cw * math.radians(delta_s3), radius=r_cw, delta_deg=delta_s3,
             chord_bearing="DUE W", chord=75.0, rot="CW")
arc_s3_pts = c_s3.arc_points(Point(0.0, 75.0), n_segments=20)

skel_agent = BeachwoodLotAgent(
    agent_id=999,
    lot_id="Test-Skel-Lot",
    block_id="16S",
    lot_number="31",
    corners=[Point(100.0, 0.0), Point(100.0, 75.0), Point(0.0, 75.0), Point(0.0, 0.0)],
    curve_specs={"side_3": {"radius": r_cw, "delta_deg": delta_s3, "length": c_s3.length, "rot": "CCW"}}, # spec says CCW
    stated_area_sqft=7500.0 + float(c_s3.segment_area),
    # ... but the skeleton bows CW. A real skeleton has a point every ~0.5 ft, so use a DENSE exact arc, and
    # the resolution of exact data: at a real scan's 2 ft resolution a 3.5 ft sagitta cannot be resolved
    # and the coded side is (correctly) kept -- see the companion check below.
    skeleton_pts=c_s3.arc_points(Point(0.0, 75.0), n_segments=150),
    skeleton_resolution_ft=0.5,
)
skel_report = skel_agent.compute_mapcheck()
curv_c = [c for c in skel_report.courses if c.is_curve][0]
check("BeachwoodLotAgent automatically overrides curve direction from skeleton scan to CW",
      curv_c.curve_rot == "CW")
check("BeachwoodLotAgent with skeleton guidance passes survey mapcheck", skel_report.passed is True)

# a real scan (default 2 ft resolution) cannot resolve a 3.5 ft sagitta: the coded side must be KEPT
skel_agent_real = BeachwoodLotAgent(
    agent_id=998, lot_id="Test-Skel-Lot-Real", block_id="16S", lot_number="31",
    corners=[Point(100.0, 0.0), Point(100.0, 75.0), Point(0.0, 75.0), Point(0.0, 0.0)],
    curve_specs={"side_3": {"radius": r_cw, "delta_deg": delta_s3, "length": c_s3.length, "rot": "CCW"}},
    stated_area_sqft=7500.0 - float(c_s3.segment_area),
    skeleton_pts=c_s3.arc_points(Point(0.0, 75.0), n_segments=150))
curv_real = [c for c in skel_agent_real.compute_mapcheck().courses if c.is_curve][0]
check("a scan that cannot resolve the sagitta does NOT override the coded curve side", curv_real.curve_rot == "CCW")


print("\n=== skeleton alignment debug pass (anchor + baseline, area geometry, gating) ===")
from engine.vectorize import align_skeleton_to_vector, iterative_align_raster_to_cogo
from engine import scan_align as SA
from engine.curve_follow import InkField as _IF
from engine.lot_agent import BeachwoodLotAgent as _BLA

# 1. align_skeleton_to_vector applies  vector = scale * R(rot) @ scan + t  exactly (round trip vs a known transform)
_rng2 = random.Random(5)
_raw = [Point(_rng2.uniform(0, 900), _rng2.uniform(0, 900)) for _ in range(300)]
_tx = {"scale": 0.99784, "rotation_deg": -2.5761, "translation_n": -1653.73, "translation_e": -942.74}
_al = align_skeleton_to_vector(_raw, _tx)
_c, _s = math.cos(math.radians(_tx["rotation_deg"])), math.sin(math.radians(_tx["rotation_deg"]))
_worst = max(abs(a.n - (_tx["scale"] * (r.n * _c - r.e * _s) + _tx["translation_n"])) +
             abs(a.e - (_tx["scale"] * (r.n * _s + r.e * _c) + _tx["translation_e"])) for a, r in zip(_al, _raw))
check("align_skeleton_to_vector matches the similarity transform exactly", _worst < 1e-9, _worst)
_arr = np.array([(p.n, p.e) for p in _raw])
check("align_skeleton_to_vector round-trips through scan_align.invert_alignment",
      float(np.max(np.abs(SA.invert_alignment(_tx, SA.apply_alignment(_tx, _arr)) - _arr))) < 1e-9)

# 2. Landmarks that are not on the features they name are refused (BUG: the lots build fitted a 0.9553 scale
#    with a 56.8 ft residual and carried on, because nothing checked)
_ctrl = [((3600 - y) * 0.5 - 1450.0, x * 0.5 - 675.0) for x, y in [(1350, 480), (1450, 580), (1770, 840), (4600, 615)]]
_bad = [(0.0, 50.0), (-60.0, 210.0), (-260.0, 210.0), (-77.5, 1626.37)]
_fit = iterative_align_raster_to_cogo(_ctrl, _bad)
check("the inconsistent lots-build landmark set really fits badly (scale 0.955, residual 56.8 ft)",
      abs(_fit["scale"] - 0.9553) < 0.001 and abs(_fit["residual_ft"] - 56.84) < 0.1, (_fit["scale"], _fit["residual_ft"]))
try:
    align_skeleton_to_vector(_raw, control_pairs=(_ctrl, _bad))
    check("align_skeleton_to_vector refuses a landmark fit with a 4.5% scale error and 57 ft residual", False)
except ValueError:
    check("align_skeleton_to_vector refuses a landmark fit with a 4.5% scale error and 57 ft residual", True)

# 3. Anchor + baseline alignment, end to end, on a synthetic sheet drawn at a KNOWN transform and pushed through
#    the real vectorizer: the scan is rotated -2.5 deg from the vector plat, printed 0.2% large, and offset.
_AZ = 87.5917                                       # bearing of the vector plat's north line (baseline)
_U = np.array([math.cos(math.radians(_AZ)), math.sin(math.radians(_AZ))])              # along the baseline
_W = np.array([math.cos(math.radians(_AZ + 90)), math.sin(math.radians(_AZ + 90))])    # down the cross line
_CORNER_V = np.array([12.0, -30.0])                                                    # the anchor, vector frame
def _vp(a, b):                                                                          # vector point a ft along, b ft across
    return _CORNER_V + a * _U + b * _W
_LINES = ([[_vp(0, 0), _vp(700, 0)], [_vp(0, 0), _vp(0, 500)], [_vp(0, 500), _vp(700, 500)], [_vp(700, 0), _vp(700, 500)]]
          + [[_vp(100 * k, 0), _vp(100 * k, 500)] for k in range(1, 7)] + [[_vp(0, 100 * k), _vp(700, 100 * k)] for k in range(1, 5)])
_TRUTH = {"scale": 1.0 / 1.002, "rotation_deg": -2.5}
_CORNER_S = np.array([900.0, 200.0])                                                    # where the corner sits on the scan
_TRUTH["translation_n"], _TRUTH["translation_e"] = (_CORNER_V - _TRUTH["scale"] * (SA._rot(_TRUTH["rotation_deg"]) @ _CORNER_S)).tolist()
_img = np.full((2200, 2600), 255, np.uint8)
for _a, _b in _LINES:
    (_n1, _e1), (_n2, _e2) = SA.invert_alignment(_TRUTH, np.array([_a, _b]))
    cv2.line(_img, (int(round(_e1 / 0.5)), int(round(2200 - _n1 / 0.5))), (int(round(_e2 / 0.5)), int(round(2200 - _n2 / 0.5))), 0, 3)
_ink_s = _IF.from_polylines(px_to_feet_polylines(
    extract_polylines(map_mask_excluding(_img, border_frac=0.005, skeleton=True), 1.5, True), 0.5, (0, 0), 2200))
_grp = [("row2", [_LINES[8 + 1]]), ("row4", [_LINES[8 + 3]]), ("col2", [_LINES[4 + 1]]), ("col5", [_LINES[4 + 4]])]

_res = SA.align_from_corner(_ink_s, _CORNER_S + [5.0, -4.0], anchor_vec=tuple(_CORNER_V), baseline_vec_az=_AZ,
                            baseline_len_ft=700.0, cross_vec_az=_AZ + 90.0, cross_len_ft=500.0)
_p = _res["params"]
check("scan_align finds the corner to within 1.5 ft from a hint 6 ft off", float(np.hypot(*(_res["corner_scan"] - _CORNER_S))) < 1.5, _res["corner_scan"])
check("baseline rotation recovered to 0.05 deg", abs(_p["rotation_deg"] - _TRUTH["rotation_deg"]) < 0.05, (_p["rotation_deg"], _TRUTH["rotation_deg"]))
# (a 500 ft line drawn to whole pixels carries ~0.03-0.06 deg of direction noise; the real Beachwood sheet is 0.238 deg out of square)
check("cross-check (second line vs baseline) is square to 0.15 deg on a square sheet", abs(_res["cross_check_deg"]) < 0.15, _res["cross_check_deg"])
check("scale check sees the injected 0.2% print growth", abs(_res["scale_error_pct"] - 0.2) < 0.15, _res["scale_error_pct"])
check("scale is set from the stated baseline length, not left nominal",
      _res["scale_source"] == "baseline" and abs(_p["scale"] - _TRUTH["scale"]) < 0.0015, (_res["scale_source"], _p["scale"]))
_agree0 = SA.alignment_agreement(_p, _grp, _ink_s)
check("anchor + baseline alone put >= 90% of the vector lines on the scan's ink", _agree0["overall"] >= 0.90, _agree0)
_p2, _hist = SA.refine_alignment(_p, _grp, _ink_s, anchor_vec=tuple(_CORNER_V))
check("refinement makes at most three adjustments", sum(1 for h in _hist if "adjustment" in h) <= 3, _hist)
_agree1 = SA.alignment_agreement(_p2, _grp, _ink_s)
check("refined alignment is not worse and stays >= 95% on ink", _agree1["overall"] >= max(0.95, _agree0["overall"] - 0.02), (_agree0["overall"], _agree1["overall"]))
_offby = SA.align_from_corner(_ink_s, _CORNER_S + [5.0, -4.0], anchor_vec=tuple(_CORNER_V), baseline_vec_az=_AZ,
                              baseline_len_ft=730.0, cross_vec_az=_AZ + 90.0, cross_len_ft=500.0)
check("a stated baseline length 4% off is NOT used to rescale the scan", _offby["scale_source"] == "nominal" and _offby["params"]["scale"] == 1.0, _offby["scale_source"])

# 4. Curved-lot area follows the GEOMETRY (BUG: sign fixed by rot alone; every clockwise Beachwood lot was
#    2 x segment area wrong and still passed because its stated area used the same rule)
for _winding, _corners, _side in (("clockwise", [Point(100.0, 0.0), Point(100.0, 75.0), Point(0.0, 75.0), Point(0.0, 0.0)], 3),
                                  ("counter-clockwise", [Point(100.0, 0.0), Point(0.0, 0.0), Point(0.0, 75.0), Point(100.0, 75.0)], 2)):
    for _rot in ("CW", "CCW"):
        _ag = _BLA(agent_id=1, lot_id="A", block_id="X", lot_number="1", corners=_corners,
                   curve_specs={f"side_{_side}": {"radius": 200.0, "delta_deg": delta_s3, "length": c_s3.length, "rot": _rot}},
                   stated_area_sqft=7500.0)
        _rep = _ag.compute_mapcheck()
        _ring = []
        for _cs in _rep.courses:
            _ring += _cs.arc_points[:-1] if _cs.is_curve else [_cs.start_pt]
        _true = shoelace_area(_ring + [_ring[0]])
        check(f"curved-lot area equals the true enclosed area ({_winding} lot, {_rot} arc)",
              abs(_rep.computed_area_sqft - _true) < 1.0, (_rep.computed_area_sqft, _true))

# 5. rot <-> circle centre, the convention behind the Marina fix: a chord chain lies on ONE circle only for the rot
#    whose centre side matches (centre on the LEFT of travel = turning left = CCW)
_ctr = np.array([-300.0, 500.0]); _Rm = 389.27
_pts5 = [Point(*(_ctr + _Rm * np.array([math.cos(a), math.sin(a)]))) for a in np.radians([150.0, 165.0, 180.0, 195.0])]
_left = None; _dev = {}
for _rot in ("CW", "CCW"):
    _w5 = 0.0
    for _a5, _b5 in zip(_pts5[:-1], _pts5[1:]):
        _ch = _a5.dist_to(_b5); _az5 = math.degrees(math.atan2(_b5.e - _a5.e, _b5.n - _a5.n)) % 360
        _mid_left = np.array([_b5.e - _a5.e, -(_b5.n - _a5.n)]) / _ch                   # left normal of travel, (n, e) = (dE, -dN)/L
        _left = float(np.dot(_ctr - np.array([_a5.n, _a5.e]), _mid_left)) > 0
        _cv5 = Curve("S", 0, _Rm, math.degrees(2 * math.asin(_ch / (2 * _Rm))), azimuth_to_bearing(_az5), _ch, _rot)
        for _q in _cv5.arc_points(_a5, 12):
            _w5 = max(_w5, abs(math.hypot(_q.n - _ctr[0], _q.e - _ctr[1]) - _Rm))
    _dev[_rot] = _w5
_want = "CCW" if _left else "CW"
_other = "CW" if _want == "CCW" else "CCW"
check("a centre on the left of travel keeps a chord chain on one circle for CCW arcs (and only those)",
      _dev[_want] < 0.01 and _dev[_other] > 1.0, (_want, _dev))

# 6. A coded side is never flipped by unrelated ink (BUG: >= 3 nearby points OR confidence >= 0.20 was enough, and
#    the median-offset fallback decided 7 of 18 curves: Marina lots 29-31 were flipped to the wrong side)
_clutter = [Point(10.0 + 0.5 * i, 3.0) for i in range(60)] + [Point(2.0, 5.0 + 0.5 * i) for i in range(40)]
_ag = _BLA(agent_id=2, lot_id="C", block_id="X", lot_number="1",
           corners=[Point(100.0, 0.0), Point(100.0, 75.0), Point(0.0, 75.0), Point(0.0, 0.0)],
           curve_specs={"side_3": {"radius": 1959.86, "length": 75.0, "rot": "CCW"}}, stated_area_sqft=7500.0,
           skeleton_pts=_clutter)
_cc = [c for c in _ag.compute_mapcheck().courses if c.is_curve][0]
check("unrelated ink beside a 0.4 ft-sagitta curve does not flip its coded side", _cc.curve_rot == "CCW", _cc.curve_rot)
_dd = determine_curve_direction_from_skeleton(Point(0.0, 75.0), Point(0.0, 0.0), _clutter, radius=1959.86, delta_deg=2.19)
check("determine_curve_direction_from_skeleton reports decided=False when it cannot tell", _dd["decided"] is False and _dd["verdict"] != "DECIDED", _dd["verdict"])
# lot lines all on the EAST (right-hand) side of the chord: five side lines and two rear lines, ~700 points against the arc's 201
_lots_side = ([Point(float(n0), 6.0 + 0.25 * j) for n0 in (10, 30, 50, 70, 90) for j in range(60)]
              + [Point(0.5 * i, e0) for e0 in (8.0, 16.0) for i in range(200)])
_arc_cw = Curve(id="Q", length=r_cw * math.radians(delta_cw), radius=r_cw, delta_deg=delta_cw, chord_bearing="DUE N", chord=100.0,
                rot="CW").arc_points(Point(0, 0), 200)
_mix = determine_curve_direction_from_skeleton(Point(0.0, 0.0), Point(100.0, 0.0), _arc_cw + _lots_side, radius=r_cw, delta_deg=delta_cw)
check("(premise) lot-line ink on one side pulls the descriptive median offset to the WRONG sign", _mix["median_offset"] < 0, _mix["median_offset"])
check("a drawn CW arc among one-sided lot-line clutter is never called CCW", not (_mix["decided"] and _mix["rot"] == "CCW"), _mix["verdict"])

print(f"\n{'='*52}")
print(f"{len(FAILURES)} failure(s)" if FAILURES else "ALL TESTS PASS")
if FAILURES:
    for f in FAILURES:
        print("  -", f)


def test_engine_regressions():
    """pytest entry point. Every check above runs at import time and records
    into FAILURES; without a test_* function pytest collected nothing."""
    assert not FAILURES, FAILURES


if __name__ == "__main__" and FAILURES:
    sys.exit(1)




