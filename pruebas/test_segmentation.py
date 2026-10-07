"""EN-4 probability aggregation and checkpoint compatibility tests."""
from pathlib import Path
import unittest

import numpy as np

from servicio.logica.tuberia.confidence import summarize_probabilities


class ConfidenceTests(unittest.TestCase):
    def test_strict_threshold_and_empty_regions(self):
        probabilities = np.full((128, 128, 128), 0.5, dtype=np.float32)
        result = summarize_probabilities(probabilities)
        self.assertFalse(result.tumor_mask.any())
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(len(result.regional_confidence), 8)
        for region in result.regional_confidence.values():
            self.assertEqual(region, {
                "has_lesion": False, "mean_confidence": 0.0, "volume_mm3": 0.0,
            })

    def test_octants_and_spacing_match_notebook_convention(self):
        probabilities = np.zeros((128, 128, 128), dtype=np.float32)
        probabilities[0, 0, 0] = 0.8
        probabilities[63, 63, 63] = 1.0
        probabilities[64, 64, 64] = 0.6
        result = summarize_probabilities(probabilities)
        upper = result.regional_confidence["upper_front_left"]
        lower = result.regional_confidence["lower_back_right"]
        self.assertEqual(upper["volume_mm3"], 31.25)
        self.assertAlmostEqual(upper["mean_confidence"], 0.9)
        self.assertEqual(lower["volume_mm3"], 15.62)
        self.assertEqual(lower["mean_confidence"], 0.6)
        self.assertEqual(result.tumor_mask.sum(), 3)
        self.assertAlmostEqual(result.confidence, 0.8)
        anisotropic = summarize_probabilities(probabilities, voxel_spacing_mm=(1, 2, 3))
        self.assertEqual(anisotropic.regional_confidence["upper_front_left"]["volume_mm3"], 12.0)

    def test_invalid_probabilities_and_configuration_are_rejected(self):
        for value in (float("nan"), float("inf"), -0.1, 1.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                summarize_probabilities(np.full((128, 128, 128), value))
        with self.assertRaises(ValueError):
            summarize_probabilities(np.zeros((64, 64, 64)))
        probabilities = np.zeros((128, 128, 128))
        with self.assertRaises(ValueError):
            summarize_probabilities(probabilities, threshold=1.0)
        with self.assertRaises(ValueError):
            summarize_probabilities(probabilities, voxel_spacing_mm=(2.5, -1.0, 2.5))


class CheckpointTests(unittest.TestCase):
    def test_supplied_weights_load_and_model_outputs_probabilities(self):
        try:
            import torch
            from servicio.logica.tuberia.en4_segmentation import EN4LungSegmenter
        except ImportError:
            self.skipTest("PyTorch is not installed")
        weights = Path(__file__).resolve().parents[1] / "modelos" / "en4_segmentador_pulmon.pth"
        if not weights.exists():
            self.skipTest("Local EN-4 weights are not available")
        segmenter = EN4LungSegmenter(str(weights), device="cpu")
        self.assertFalse(segmenter.model.training)
        self.assertTrue(all(not parameter.requires_grad for parameter in segmenter.model.parameters()))
        # A smaller grid verifies all encoder/decoder layers without a full inference allocation.
        with torch.inference_mode():
            probabilities = segmenter.model(torch.zeros((1, 1, 16, 16, 16)))
        self.assertEqual(tuple(probabilities.shape), (1, 1, 16, 16, 16))
        self.assertTrue(torch.isfinite(probabilities).all())
        self.assertTrue(((probabilities >= 0) & (probabilities <= 1)).all())


if __name__ == "__main__":
    unittest.main()
