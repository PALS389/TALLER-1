"""Contract and error propagation tests without models or a database."""
import unittest
from types import SimpleNamespace

import numpy as np

from servicio.logica.tuberia.orchestrator import (
    PipelineOrchestrator, MeshResult, SegmentationResult,
)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.files = {}
        self.preprocessor = SimpleNamespace(execute=lambda _: np.zeros((4, 128, 128)))
        self.reconstructor = SimpleNamespace(reconstruct=lambda _: np.zeros((128, 128, 128)))
        self.segmenter = SimpleNamespace(segment=lambda v: SegmentationResult(v, 0.8))
        self.generator = SimpleNamespace(generate=lambda *_: MeshResult(b"organ", b"tumor"))
        self.store = SimpleNamespace(
            save_volume=lambda study, v: self.files.update({"volume": v}),
            save_mesh=self.save_mesh,
        )

    def save_mesh(self, study, name, content):
        self.files[name] = content
        return f"{study}/{name}"

    def execute(self):
        return PipelineOrchestrator(
            self.preprocessor, self.reconstructor, self.segmenter,
            self.generator, self.store,
        ).execute("EST-1", np.zeros((4, 128, 128)),
                   lambda study, stage, event, data: self.events.append((stage, event)))

    def test_four_stages_and_references(self):
        result = self.execute()
        self.assertEqual(self.events, [
            (1, "start"), (1, "success"), (2, "start"), (2, "success"),
            (3, "start"), (3, "success"), (4, "start"), (4, "success"),
        ])
        self.assertEqual(result.files.tumor_glb, "EST-1/tumor.glb")
        self.assertEqual(self.files["organ.glb"], b"organ")

    def test_invalid_shape_stops_without_success(self):
        self.preprocessor.execute = lambda _: np.zeros((4, 64, 64))
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(self.events, [(1, "start"), (1, "error")])
        self.assertFalse(self.files)

    def test_storage_failure_records_stage_error(self):
        def fail(*args):
            raise OSError("Storage unavailable")
        self.store.save_mesh = fail
        with self.assertRaises(OSError):
            self.execute()
        self.assertEqual(self.events[-2:], [(4, "start"), (4, "error")])

    def test_invalid_lung_mask_stops_before_mesh_storage(self):
        from servicio.logica.tuberia.lung_mask import InvalidLungMask

        def reject(*args):
            raise InvalidLungMask("No plausible lung mask")
        self.generator.generate = reject
        with self.assertRaises(InvalidLungMask):
            self.execute()
        self.assertEqual(self.events[-2:], [(4, "start"), (4, "error")])
        self.assertNotIn("organ.glb", self.files)
        self.assertNotIn("tumor.glb", self.files)

    def test_invalid_confidence_stops_before_meshes(self):
        self.segmenter.segment = lambda v: SegmentationResult(v, float("nan"))
        with self.assertRaises(ValueError):
            self.execute()
        self.assertEqual(self.events[-2:], [(3, "start"), (3, "error")])
        self.assertNotIn("tumor.glb", self.files)

    def test_regional_confidence_is_included_in_result_metrics(self):
        regions = {"upper_front_left": {"has_lesion": True, "mean_confidence": 0.8,
                                         "volume_mm3": 15.62}}
        self.segmenter.segment = lambda v: SegmentationResult(
            v, 0.8, probability_map=v, regional_confidence=regions,
        )
        result = self.execute()
        self.assertEqual(result.metrics["regional_confidence"], regions)
        self.assertEqual(result.metrics["confidence_threshold"], 0.5)


if __name__ == "__main__":
    unittest.main()
