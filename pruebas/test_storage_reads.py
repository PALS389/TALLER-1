"""Bounded retry behavior for idempotent storage reads."""
import unittest
from unittest.mock import Mock, patch

import httpx

from servicio.persistencia.storage import ObjectStorage, StorageError, FileNotFoundInStorage


class StorageReadTests(unittest.TestCase):
    def setUp(self):
        self.store = ObjectStorage.__new__(ObjectStorage)
        self.store._bucket_name = "test"
        self.store._bucket = Mock()

    @patch("servicio.persistencia.storage.time.sleep")
    def test_transient_transport_error_is_retried(self, sleep):
        self.store._bucket.download.side_effect = [httpx.ReadError("Temporary"), b"glTF"]
        self.assertEqual(self.store.read_bytes("EST-1/organ.glb"), b"glTF")
        self.assertEqual(self.store._bucket.download.call_count, 2)
        sleep.assert_called_once()

    @patch("servicio.persistencia.storage.time.sleep")
    def test_retry_limit(self, sleep):
        self.store._bucket.download.side_effect = httpx.ReadError("Temporary")
        with self.assertRaises(StorageError):
            self.store.read_bytes("EST-1/organ.glb")
        self.assertEqual(self.store._bucket.download.call_count, 3)

    def test_missing_object_is_not_retried(self):
        self.store._bucket.download.side_effect = RuntimeError("Object not found")
        with self.assertRaises(FileNotFoundInStorage):
            self.store.read_bytes("EST-1/tumor.glb")
        self.assertEqual(self.store._bucket.download.call_count, 1)
