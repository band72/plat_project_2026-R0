"""
test_beverly_isle_cogo.py -- Unit tests for Beverly Isle Plat Cadastral Engine.
Verifies COGO solver, curve table parameters, traverse closures, parcel areas, and DXF compliance.
"""

import math
import os
import unittest

import numpy as np

from engine.audit import dxf_audit
from engine.cogo_beverly_isle import BeverlyIsleCogoSolver
from engine.handdrawn_extractor import PlatCalloutExtractor, PlatImageNormalizer
from engine.lots import is_simple_polygon


class TestBeverlyIsleCogo(unittest.TestCase):
    """Test suite for Beverly Isle cadastral reconstruction."""

    @classmethod
    def setUpClass(cls):
        cls.solver = BeverlyIsleCogoSolver(base_n=10000.0, base_e=10000.0)
        cls.parcels = cls.solver.solve_geometry()

    def test_parcel_count(self):
        """All 20 parcels must be successfully solved."""
        self.assertEqual(len(self.parcels), 20)
        for i in range(1, 20):
            self.assertIn(f"Lot {i}", self.parcels)
        self.assertIn("Parcel 20", self.parcels)

    def test_parcels_simple_polygons(self):
        """Every parcel boundary must be a valid, simple non-self-intersecting polygon."""
        for lot_id, p in self.parcels.items():
            simple, msg = is_simple_polygon(p.boundary_points)
            self.assertTrue(simple, f"{lot_id} is not a simple polygon: {msg}")

    def test_zero_misclosure(self):
        """All parcels must achieve EXACT 0.0000 ft misclosure."""
        for lot_id, p in self.parcels.items():
            self.assertLessEqual(p.misclose_dist, 0.0001,
                                 f"{lot_id} misclosure {p.misclose_dist} exceeds 0.0001 ft")
            self.assertEqual(p.precision_ratio, "EXACT (0.0000 ft)")

    def test_curve_table_parameters(self):
        """Centerline curves a, b, c must mathematically match the plat's Curve Data Table."""
        # Curve a: Rad = 97.37, Tan = 30.0, Delta = 34°15'
        ca = self.solver.curves['a']
        self.assertAlmostEqual(ca['radius'], 97.37, places=2)
        calc_tan_a = ca['radius'] * math.tan(math.radians(ca['delta_deg'] / 2))
        self.assertAlmostEqual(calc_tan_a, 30.00, places=1)

        # Curve b: Rad = 35.10, Tan = 59.0, Delta = 118°30'
        cb = self.solver.curves['b']
        self.assertAlmostEqual(cb['radius'], 35.10, places=2)
        calc_tan_b = cb['radius'] * math.tan(math.radians(cb['delta_deg'] / 2))
        self.assertAlmostEqual(calc_tan_b, 59.00, places=1)

        # Curve c: Rad = 50.11, Tan = 197.32, Delta = 151°30'
        cc = self.solver.curves['c']
        self.assertAlmostEqual(cc['radius'], 50.11, places=2)
        calc_tan_c = cc['radius'] * math.tan(math.radians(cc['delta_deg'] / 2))
        self.assertAlmostEqual(calc_tan_c, 197.32, places=1)

    def test_total_acreage_reasonable(self):
        """Total radial parcel acreage of Island No. 5 should be ~2.3 acres."""
        total_sqft = sum(p.area_sqft for p in self.parcels.values() if p.lot_id != "Parcel 20")
        total_acres = total_sqft / 43560.0
        self.assertGreater(total_acres, 2.0)
        self.assertLess(total_acres, 3.0)

    def test_dxf_compliance(self):
        """Generated DXF must pass automated audit with 0 noise circles and valid extents."""
        dxf_path = 'dxf/Duval_BeverlyIsle_1968.dxf'
        if os.path.exists(dxf_path):
            res = dxf_audit(dxf_path)
            self.assertEqual(res['status'], 'PASS')
            self.assertEqual(res['entity_counts']['circles'], 0)
            self.assertGreater(res['entity_counts']['polylines'], 15)

    def test_image_normalizer_dual_support(self):
        """Normalizer must handle both 3-channel RGB color and 1-channel monochrome."""
        norm = PlatImageNormalizer()

        # Simulated RGB photo with amber tint
        rgb_img = np.full((100, 100, 3), 200, dtype=np.uint8)
        rgb_img[:, :, 0] = 120  # low blue
        rgb_img[:, :, 2] = 230  # high red -> amber tint
        gray_out, bin_out = norm.normalize(rgb_img)
        self.assertEqual(gray_out.shape, (100, 100))
        self.assertEqual(bin_out.shape, (100, 100))

        # Simulated clean monochrome scan
        mono_img = np.full((100, 100), 255, dtype=np.uint8)
        mono_img[40:60, :] = 0  # black stroke
        gray_mono, bin_mono = norm.normalize(mono_img)
        self.assertEqual(gray_mono.shape, (100, 100))
        self.assertEqual(bin_mono.shape, (100, 100))
        self.assertGreater(np.count_nonzero(bin_mono), 0)

    def test_callout_parser_regex(self):
        """Verify regex extraction of quadrant bearings, distances, and curve rows."""
        self.assertEqual(PlatCalloutExtractor.parse_bearing("N 37°52'54\" W"), "N 37°52'54\" W")
        self.assertEqual(PlatCalloutExtractor.parse_bearing("S 02°11'20\" W"), "S 02°11'20\" W")
        self.assertEqual(PlatCalloutExtractor.parse_distance("544.44'"), 544.44)
        self.assertEqual(PlatCalloutExtractor.parse_distance("180.75"), 180.75)

        crow = PlatCalloutExtractor.parse_curve_row("a 97.37' 30.0' 34° 15'")
        self.assertIsNotNone(crow)
        self.assertEqual(crow['name'], 'a')
        self.assertEqual(crow['radius'], 97.37)
        self.assertEqual(crow['tangent'], 30.0)


if __name__ == '__main__':
    unittest.main()
