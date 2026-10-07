"""Regression tests against the former body-box lung surface."""
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from scipy import ndimage

from pruebas.lung_phantom import lung_phantom
from servicio.logica.tuberia.lung_mask import EN42LungMaskExtractor, InvalidLungMask


class LungMaskTests(unittest.TestCase):
    def setUp(self):
        self.extractor = EN42LungMaskExtractor()
        self.volume = lung_phantom()

    def test_internal_lungs_exclude_exterior_air_and_body(self):
        result = self.extractor.extract(self.volume)
        self.assertEqual(result.mask.dtype, np.uint8)
        self.assertEqual(result.mask.shape, self.volume.shape)
        self.assertEqual(int(result.mask[0].sum()), 0)
        self.assertEqual(result.mask[32, 32, 32], 0)
        self.assertEqual(result.mask[20, 32, 32], 1)
        self.assertEqual(result.mask[44, 32, 32], 1)
        self.assertEqual(ndimage.label(result.mask)[1], 2)
        self.assertLess(result.mask.sum(), (self.volume > 0.05).sum() / 2)
        self.assertFalse(result.diagnostics["clinical_validation"])

    def test_trachea_connection_does_not_merge_lungs_with_exterior(self):
        self.volume[19:22, 31:34, :33] = 0.12
        result = self.extractor.extract(self.volume)
        self.assertFalse(result.mask[0].any())
        self.assertFalse(result.mask[:, :, 0].any())
        self.assertTrue(result.mask[20, 32, 32])

    def test_tumor_inside_lung_is_included(self):
        tumor = np.zeros_like(self.volume, dtype=np.uint8)
        tumor[19:22, 31:34, 31:34] = 1
        self.volume[tumor > 0] = 0.9
        result = self.extractor.extract(self.volume, tumor)
        self.assertTrue(np.all(result.mask[tumor > 0] == 1))

    def test_invalid_volumes_fail_instead_of_generating_a_box(self):
        for volume in (np.zeros((32, 32, 32)), np.ones((32, 32, 32)),
                       np.zeros((8, 8, 8)), np.zeros((32, 32)),
                       np.full((32, 32, 32), np.nan), np.ones((32, 32, 32), dtype=complex)):
            with self.subTest(shape=volume.shape), self.assertRaises(InvalidLungMask):
                self.extractor.extract(volume)

    def test_solid_chest_without_lungs_is_rejected(self):
        self.volume[self.volume == 0.12] = 0.75
        with self.assertRaises(InvalidLungMask):
            self.extractor.extract(self.volume)

    def test_tumor_shape_is_checked(self):
        with self.assertRaises(InvalidLungMask):
            self.extractor.extract(self.volume, np.zeros((32, 32, 32)))

    def test_search_fallback_still_excludes_body_and_background(self):
        with patch("servicio.logica.tuberia.lung_mask._air_by_erosion", return_value=None):
            result = self.extractor.extract(self.volume)
        self.assertEqual(result.diagnostics["method"], "search")
        self.assertFalse(result.mask[0].any())
        self.assertFalse(result.mask[32, 32, 32])
        self.assertTrue(result.mask[20, 32, 32])
        self.assertTrue(result.mask[44, 32, 32])

    def test_float32_overflow_is_rejected(self):
        volume = self.volume.astype(np.float64) * 1e100
        with self.assertRaises(InvalidLungMask):
            self.extractor.extract(volume)

    def test_local_en1_case_matches_bray_reference(self):
        directory = Path(__file__).resolve().parents[1] / "datos/validation/lung_003"
        reference = directory / "lung_003_bray_reference.npy"
        if not reference.exists():
            self.skipTest("Local EN-1 validation data are not present.")
        result = self.extractor.extract(
            np.load(directory / "lung_003_reconstructed.npy", allow_pickle=False),
            np.load(directory / "lung_003_predicted_tumor.npy", allow_pickle=False))
        np.testing.assert_array_equal(result.mask, np.load(reference, allow_pickle=False))
