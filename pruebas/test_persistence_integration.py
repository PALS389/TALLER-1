"""Persistence boundary tests; no database or network required."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from servicio.persistencia.almacen_archivos import AlmacenArchivos
from servicio.persistencia.storage import FileNotFoundInStorage
from servicio.persistencia.study_metadata import MetadataStore
from servicio.persistencia.repositories.processing_stage_repository import COMPLETED, RUNNING, WAITING


class PersistenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = AlmacenArchivos.__new__(AlmacenArchivos)
        self.store._metadatos = Mock()
        self.store._almacen = Mock()

    def test_extended_metadata_roundtrip(self):
        metadata = {"estado": "Reconstrucción completada", "metricas": {"confidence": 0.8},
                    "archivos_resultado": {"tumor_glb": "EST-1/tumor.glb"}}
        self.store.guardar_metadatos("EST-1", metadata)
        content = self.store._almacen.save_bytes.call_args.args[1]
        self.store._almacen.read_bytes.return_value = content
        self.store._metadatos.read.return_value = {"estado": metadata["estado"]}
        self.assertEqual(self.store.leer_metadatos("EST-1"), metadata)
        self.assertEqual(json.loads(content), metadata)

    def test_database_status_overrides_snapshot(self):
        self.store._metadatos.read.return_value = {"estado": "Error"}
        self.store._almacen.read_bytes.return_value = b'{"estado":"Procesando"}'
        self.assertEqual(self.store.leer_metadatos("EST-1")["estado"], "Error")

    def test_old_studies_without_snapshot(self):
        metadata = {"estado": "Pendiente"}
        self.store._metadatos.read.return_value = metadata
        self.store._almacen.read_bytes.side_effect = FileNotFoundInStorage()
        self.assertEqual(self.store.leer_metadatos("EST-1"), metadata)

    def test_mesh_reference_and_invalid_name(self):
        self.assertEqual(self.store.save_mesh("EST-1", "tumor.glb", b"glTF"), "EST-1/tumor.glb")
        with self.assertRaises(ValueError):
            self.store.save_mesh("EST-1", "../other.glb", b"glTF")

    def test_actual_stage_events_are_not_marked_skipped(self):
        from datetime import datetime
        metadata_store = MetadataStore.__new__(MetadataStore)
        metadata_store._stages = Mock()
        metadata_store._save_stages("EST-1", {"stage_statuses": {"1": "success", "2": "start"}}, datetime.now())
        statuses = [call.args[3] for call in metadata_store._stages.save.call_args_list]
        self.assertEqual(statuses, [COMPLETED, RUNNING, WAITING, WAITING])
