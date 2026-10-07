"""Verify GLB outputs for predicted tumors and tumor-free studies."""
import io
import unittest

import numpy as np

from servicio.logica.tuberia.meshes import EN42MeshGenerator
from pruebas.lung_phantom import lung_phantom


class MeshTests(unittest.TestCase):
    def setUp(self):
        try:
            import trimesh
            import skimage
        except ImportError:
            self.skipTest("Mesh dependencies are not installed")
        self.trimesh = trimesh
        self.volume = lung_phantom()

    def test_empty_tumor_exports_empty_scene(self):
        generator = EN42MeshGenerator()
        result = generator.generate(self.volume, np.zeros_like(self.volume))
        self.assertEqual(result.organ_glb[:4], b"glTF")
        self.assertEqual(result.tumor_glb[:4], b"glTF")
        tumor = self.trimesh.load(io.BytesIO(result.tumor_glb), file_type="glb")
        self.assertFalse(tumor.geometry)
        organ = self.trimesh.load(io.BytesIO(result.organ_glb), file_type="glb")
        self.assertTrue(organ.geometry)
        self.assertFalse(generator.last_metrics["tumor"]["has_lesion"])
        self.assertEqual(generator.last_metrics["organ"]["segmentation"]["mask_method"],
                         "en42_internal_lung_air_v1")
        self.assertLess(generator.last_metrics["organ"]["mask_voxels"],
                        (self.volume > 0.05).sum() / 2)

    def test_nonempty_tumor_exports_surface(self):
        mask = np.zeros_like(self.volume)
        mask[19:22, 31:34, 31:34] = 1
        result = EN42MeshGenerator().generate(self.volume, mask)
        tumor = self.trimesh.load(io.BytesIO(result.tumor_glb), file_type="glb")
        self.assertTrue(tumor.geometry)
        self.assertTrue(all(mesh.is_watertight for mesh in tumor.geometry.values()))


if __name__ == "__main__":
    unittest.main()
