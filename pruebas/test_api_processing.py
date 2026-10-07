"""HTTP integration contracts with injected business services."""
import unittest
from unittest.mock import Mock

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from servicio.api.rutas import crear_rutas
from servicio.logica.casos_uso import StudyNotFound


class ApiProcessingTests(unittest.TestCase):
    def setUp(self):
        self.cases = Mock()
        self.cases.register_study.return_value = "EST-1"
        app = FastAPI()
        app.include_router(crear_rutas(self.cases))
        self.client = TestClient(app)

    def test_background_submission_returns_without_waiting(self):
        response = self.client.post("/reconstruir", data={"wait_for_result": "false"})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["result_url"], "/estudios/EST-1")
        self.cases.process_study.assert_called_once_with("EST-1")
        self.cases.get_result.assert_not_called()

    def test_polling_processing_does_not_wait_for_job(self):
        self.cases.get_results.return_value = {"study_id": "EST-1", "status": "processing"}
        response = self.client.get("/estudios/EST-1")
        self.assertEqual(response.json()["estado"], "Procesando")
        self.cases.get_result.assert_not_called()

    def test_completed_poll_includes_volume_and_metrics(self):
        self.cases.get_results.return_value = {"status": "completed"}
        self.cases.get_result.return_value = (
            {"study_id": "EST-1", "status": "completed", "metrics": {"tumor_confidence": 0.8}},
            np.zeros((128, 128, 128), dtype=np.float32))
        response = self.client.get("/estudios/EST-1")
        self.assertEqual(response.json()["volumen"]["forma"], [128, 128, 128])
        self.assertEqual(response.json()["metricas"]["tumor_confidence"], 0.8)

    def test_missing_study_returns_404(self):
        self.cases.get_results.side_effect = StudyNotFound()
        self.assertEqual(self.client.get("/estudios/missing").status_code, 404)

    def test_mesh_response_and_content_type(self):
        self.cases.get_mesh_glb.return_value = b"glTF-test"
        response = self.client.get("/estudios/EST-1/meshes/tumor.glb")
        self.assertEqual(response.content, b"glTF-test")
        self.assertEqual(response.headers["content-type"], "model/gltf-binary")
        self.cases.get_mesh_glb.assert_called_once_with("EST-1", "tumor.glb")

    def test_unknown_mesh_is_rejected_before_business_access(self):
        response = self.client.get("/estudios/EST-1/meshes/metadata.json")
        self.assertEqual(response.status_code, 404)
        self.cases.get_mesh_glb.assert_not_called()

    def test_missing_mesh_returns_404(self):
        self.cases.get_mesh_glb.side_effect = StudyNotFound()
        self.assertEqual(self.client.get("/estudios/EST-1/meshes/organ.glb").status_code, 404)

    def test_metadata_only_does_not_load_volume(self):
        self.cases.get_results.return_value = {"study_id": "EST-1", "status": "completed",
                                              "files": {"organ_glb": "EST-1/organ.glb"}}
        response = self.client.get("/estudios/EST-1?include_volume=false")
        self.assertEqual(response.json()["archivos"]["organ_glb"], "EST-1/organ.glb")
        self.cases.get_result.assert_not_called()
