"""Verify GLB outputs for predicted tumors and tumor-free studies."""
import io
import unittest

import numpy as np

from servicio.logica.tuberia.meshes import EN42MeshGenerator


class MeshTests(unittest.TestCase):
    def setUp(self):
        try:
            import trimesh
            import skimage
        except ImportError:
            self.skipTest("Mesh dependencies are not installed")
        self.trimesh = trimesh
        self.volume = np.zeros((32, 32, 32), dtype=np.float32)
        self.volume[4:28, 4:28, 4:28] = 0.8

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

    def test_nonempty_tumor_exports_surface(self):
        mask = np.zeros_like(self.volume)
        mask[12:20, 12:20, 12:20] = 1
        result = EN42MeshGenerator().generate(self.volume, mask)
        tumor = self.trimesh.load(io.BytesIO(result.tumor_glb), file_type="glb")
        self.assertTrue(tumor.geometry)
        self.assertTrue(all(mesh.is_watertight for mesh in tumor.geometry.values()))


if __name__ == "__main__":
    unittest.main()
