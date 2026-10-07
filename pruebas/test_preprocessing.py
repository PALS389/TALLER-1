"""Verify preprocessing preserves the scale used to train EN-1."""
import unittest

import numpy as np

from servicio.logica.tuberia.preproceso import ProjectionPreprocessor


class PreprocessingTests(unittest.TestCase):
    def test_preserves_scale_and_produces_independent_contiguous_float32(self):
        source = np.full((4, 128, 128), 42.5, dtype=np.float64)[:, :, ::-1]
        result = ProjectionPreprocessor().execute(source)
        self.assertEqual(result.shape, (4, 128, 128))
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(result.flags.c_contiguous)
        self.assertTrue(np.all(result == 42.5))
        result[0, 0, 0] = 0
        self.assertEqual(source[0, 0, 0], 42.5)

    def test_rejects_wrong_shape_nonfinite_and_complex_values(self):
        for source in (np.zeros((4, 64, 64)), np.full((4, 128, 128), np.nan),
                       np.full((4, 128, 128), np.inf), np.zeros((4, 128, 128), dtype=complex)):
            with self.assertRaises(ValueError):
                ProjectionPreprocessor().execute(source)


if __name__ == "__main__":
    unittest.main()
