"""Verify English business contracts and compatibility with existing metadata."""
import io
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import numpy as np

from servicio.logica.casos_uso import (
    StudyAlreadyCompleted, StudyAlreadyExists, StudyInProgress,
    StudyNotFound, StudyRejected, StudyUseCases,
)
from servicio.logica.compatibility import (
    LegacyFileStoreAdapter, from_legacy_metadata, to_legacy_metadata,
)
from servicio.logica.tuberia.preproceso import InvalidImage, ProjectionPreprocessor, read_projection
from servicio.logica.tuberia.orchestrator import MeshResult, PipelineOrchestrator, SegmentationResult


class BusinessContractTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {}
        self.projections = {}
        self.volumes = {}
        self.store = SimpleNamespace(
            save_projections=lambda key, value: self.projections.update({key: value}),
            read_projections=lambda key: self.projections[key],
            save_metadata=lambda key, value: self.metadata.update({key: dict(value)}),
            read_metadata=self.read_metadata,
            save_volume=lambda key, value: self.volumes.update({key: value}),
            read_volume=lambda key: self.volumes[key],
        )
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.cases = StudyUseCases(
            self.store,
            reconstructor=SimpleNamespace(
                method="test_reconstruction", note="Test engine",
                reconstruct=lambda _: np.ones((128, 128, 128), dtype=np.float32),
            ),
            executor=self.executor,
        )
        content = io.BytesIO()
        np.save(content, np.ones((128, 128), dtype=np.float32))
        self.images = {angle: (f"view_{angle}.npy", content.getvalue())
                       for angle in (0, 45, 90, 135)}

    def tearDown(self):
        self.executor.shutdown(wait=True)

    def read_metadata(self, key):
        if key not in self.metadata:
            raise FileNotFoundError(key)
        return dict(self.metadata[key])

    def test_register_process_and_query_using_english_contract(self):
        study_id = self.cases.register_study(self.images, "TEST-1", patient={"name": "Test"})
        self.assertEqual(self.metadata[study_id]["status"], "pending")
        job = self.cases.process_study(study_id)
        job.result(timeout=5)
        result = self.cases.get_results(study_id)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["statistics"]["mean"], 1.0)
        self.assertEqual(result["files"]["volume"], "volume.npy")
        self.assertEqual(self.cases.describe()["method"], "test_reconstruction")

    def test_missing_or_extra_angles_are_rejected_before_storage(self):
        for angles in ((0, 45, 90), (0, 45, 90, 135, 180)):
            images = {angle: self.images[0] for angle in angles}
            with self.assertRaises(StudyRejected):
                self.cases.register_study(images)
        self.assertFalse(self.metadata)
        self.assertFalse(self.projections)

    def test_missing_study_uses_domain_exception(self):
        def missing(_):
            raise FileNotFoundError("Missing study")
        self.store.read_metadata = missing
        with self.assertRaises(StudyNotFound):
            self.cases.get_results("MISSING")

    def test_only_completed_registered_meshes_can_be_read(self):
        self.metadata["TEST-1"] = {"status": "completed", "result_files": {"tumor_glb": "TEST-1/tumor.glb"}}
        self.store.read_mesh = lambda study_id, name: b"glTF"
        self.assertEqual(self.cases.get_mesh_glb("TEST-1", "tumor.glb"), b"glTF")
        for name in ("organ.glb", "metadata.json", "../tumor.glb"):
            with self.assertRaises(StudyNotFound):
                self.cases.get_mesh_glb("TEST-1", name)
        self.metadata["TEST-1"]["status"] = "processing"
        with self.assertRaises(StudyNotFound):
            self.cases.get_mesh_glb("TEST-1", "tumor.glb")

    def test_invalid_image_identifies_filename_in_english_contract(self):
        with self.assertRaises(InvalidImage) as error:
            read_projection("invalid.txt", b"invalid")
        self.assertEqual(error.exception.filename, "invalid.txt")
        self.assertIn("unsupported format", error.exception.reason)

    def test_existing_metadata_round_trip(self):
        metadata = {
            "study_id": "TEST-1", "organ": "lung", "status": "completed",
            "angles": [0, 45, 90, 135], "created_at": "2026-10-07T10:00:00",
            "statistics": {"min": 0.0, "max": 1.0, "mean": 0.5},
        }
        legacy = to_legacy_metadata(metadata)
        self.assertEqual(legacy["estado"], "Reconstrucción completada")
        self.assertEqual(legacy["estadisticas"]["media"], 0.5)
        self.assertEqual(from_legacy_metadata(legacy), metadata)

    def test_adapter_translates_existing_file_store(self):
        saved = {}
        legacy_store = SimpleNamespace(**{
            "guardar_metadatos": lambda key, value: saved.update({key: value}),
            "leer_metadatos": lambda key: saved[key],
        })
        adapter = LegacyFileStoreAdapter(legacy_store)
        metadata = {"study_id": "TEST-1", "status": "pending", "organ": "lung"}
        adapter.save_metadata("TEST-1", metadata)
        self.assertEqual(saved["TEST-1"]["estado"], "Pendiente")
        self.assertEqual(adapter.read_metadata("TEST-1"), metadata)

    def test_duplicate_registration_does_not_overwrite_study(self):
        self.cases.register_study(self.images, "TEST-1", patient={"name": "Original"})
        with self.assertRaises(StudyAlreadyExists):
            self.cases.register_study(self.images, "TEST-1", patient={"name": "Replacement"})
        self.assertEqual(self.metadata["TEST-1"]["patient"]["name"], "Original")

    def test_completed_study_cannot_run_twice(self):
        self.cases.register_study(self.images, "TEST-1")
        self.cases.process_study("TEST-1", in_background=False)
        with self.assertRaises(StudyAlreadyCompleted):
            self.cases.process_study("TEST-1")

    def test_background_progress_and_duplicate_execution(self):
        started = Event()
        release = Event()

        def reconstruct(_):
            started.set()
            if not release.wait(timeout=5):
                raise TimeoutError("Test worker was not released")
            return np.ones((128, 128, 128), dtype=np.float32)

        self.cases._reconstructor.reconstruct = reconstruct
        self.cases.register_study(self.images, "TEST-1")
        job = self.cases.process_study("TEST-1")
        try:
            self.assertTrue(started.wait(timeout=3))
            result = self.cases.get_results("TEST-1")
            self.assertEqual(result["status"], "processing")
            self.assertEqual(result["progress"]["stage"], 2)
            self.assertEqual(result["progress"]["event"], "start")
            with self.assertRaises(StudyInProgress):
                self.cases.process_study("TEST-1")
        finally:
            release.set()
            job.result(timeout=5)

    def test_missing_projections_are_reported_as_processing_error(self):
        self.cases.register_study(self.images, "TEST-1")

        def missing(_):
            raise FileNotFoundError("Projection not found")

        self.store.read_projections = missing
        with self.assertRaises(StudyNotFound):
            self.cases.process_study("TEST-1", in_background=False)
        result = self.cases.get_results("TEST-1")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "StudyNotFound")

    def test_failed_volume_save_records_error_and_can_be_retried(self):
        self.cases.register_study(self.images, "TEST-1")
        original_save = self.store.save_volume

        def fail(*_):
            raise OSError("Test storage failure")

        self.store.save_volume = fail
        with self.assertRaises(OSError):
            self.cases.process_study("TEST-1", in_background=False)
        result = self.cases.get_results("TEST-1")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["stage_statuses"]["2"], "error")
        self.store.save_volume = original_save
        self.cases.process_study("TEST-1", in_background=False)
        result = self.cases.get_results("TEST-1")
        self.assertEqual(result["status"], "completed")
        self.assertIsNone(result["error"])

    def test_close_does_not_shutdown_injected_executor(self):
        self.cases.close()
        with self.assertRaises(RuntimeError):
            self.cases.register_study(self.images, "TEST-1")
        self.assertEqual(self.executor.submit(lambda: 42).result(timeout=3), 42)

    def test_full_pipeline_records_four_stages_without_external_services(self):
        stored_meshes = {}
        self.store.save_mesh = lambda key, name, value: (
            stored_meshes.update({name: value}) or f"{key}/{name}"
        )
        pipeline = PipelineOrchestrator(
            ProjectionPreprocessor(), self.cases._reconstructor,
            SimpleNamespace(segment=lambda volume: SegmentationResult(
                np.zeros_like(volume, dtype=np.uint8), 0.0,
            )),
            SimpleNamespace(generate=lambda *_: MeshResult(b"organ", b"tumor")),
            self.store,
        )
        events = []
        stages = SimpleNamespace(
            record_waiting=lambda key, stage: events.append((stage, "waiting")),
            record_start=lambda key, stage: events.append((stage, "start")),
            record_success=lambda key, stage, data: events.append((stage, "success")),
            record_error=lambda key, stage, reason: events.append((stage, "error")),
        )
        cases = StudyUseCases(self.store, pipeline=pipeline, stages=stages, executor=self.executor)
        cases.register_study(self.images, "TEST-1")
        cases.process_study("TEST-1", in_background=False)
        result = cases.get_results("TEST-1")
        self.assertEqual(result["progress"]["completed_stages"], 4)
        self.assertEqual(result["stage_statuses"], {str(stage): "success" for stage in range(1, 5)})
        self.assertEqual(events[:4], [(stage, "waiting") for stage in range(1, 5)])
        self.assertEqual(result["files"]["tumor_glb"], "TEST-1/tumor.glb")
        self.assertEqual(set(stored_meshes), {"organ.glb", "tumor.glb"})

    def test_extra_empty_view_is_still_rejected(self):
        images = dict(self.images)
        images[180] = None
        with self.assertRaises(StudyRejected):
            self.cases.register_study(images)

    def test_pending_study_has_no_finished_result(self):
        self.cases.register_study(self.images, "TEST-1")
        with self.assertRaises(StudyInProgress):
            self.cases.get_result("TEST-1")

    def test_failure_to_save_final_metadata_is_reported(self):
        self.cases.register_study(self.images, "TEST-1")
        original_save = self.store.save_metadata

        def fail_completion(key, metadata):
            if metadata["status"] == "completed":
                raise OSError("Cannot save completion")
            original_save(key, metadata)

        self.store.save_metadata = fail_completion
        with self.assertRaises(OSError):
            self.cases.process_study("TEST-1", in_background=False)
        self.assertEqual(self.cases.get_results("TEST-1")["status"], "error")

    def test_storage_error_does_not_hide_original_processing_failure(self):
        self.cases.register_study(self.images, "TEST-1")
        original_save = self.store.save_metadata

        def fail_reconstruction(_):
            raise ValueError("Original processing failure")

        def fail_error_state(key, metadata):
            if metadata["status"] == "error":
                raise OSError("Cannot save error state")
            original_save(key, metadata)

        self.cases._reconstructor.reconstruct = fail_reconstruction
        self.store.save_metadata = fail_error_state
        with self.assertRaisesRegex(ValueError, "Original processing failure") as error:
            self.cases.process_study("TEST-1", in_background=False)
        self.assertIn("Could not persist the failure state: OSError.", error.exception.__notes__)


if __name__ == "__main__":
    unittest.main()
