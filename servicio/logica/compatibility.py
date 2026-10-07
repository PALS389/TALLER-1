"""Translate the existing persistence and API vocabulary at integration boundaries."""
from __future__ import annotations

from typing import Any

import numpy as np


LEGACY_METADATA_KEYS = {
    "study_id": "id_estudio", "patient": "paciente", "organ": "organo",
    "status": "estado", "angles": "angulos", "files": "archivos",
    "created_at": "fecha", "method": "metodo", "note": "nota",
    "elapsed_seconds": "tiempo_s", "statistics": "estadisticas",
    "metrics": "metricas", "result_files": "archivos_resultado",
}
LEGACY_STATUSES = {
    "pending": "Pendiente", "processing": "Procesando",
    "completed": "Reconstrucción completada", "error": "Error",
}
LEGACY_ORGANS = {"lung": "pulmon", "liver": "higado", "kidney": "rinon"}


def to_legacy_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    result = {LEGACY_METADATA_KEYS.get(key, key): value for key, value in metadata.items()}
    if "status" in metadata:
        result["estado"] = LEGACY_STATUSES.get(metadata["status"], metadata["status"])
    if "organ" in metadata:
        result["organo"] = LEGACY_ORGANS.get(metadata["organ"], metadata["organ"])
    if "statistics" in metadata:
        result["estadisticas"] = {
            "media" if key == "mean" else key: value
            for key, value in metadata["statistics"].items()
        }
    return result


def from_legacy_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = {value: key for key, value in LEGACY_METADATA_KEYS.items()}
    statuses = {value: key for key, value in LEGACY_STATUSES.items()}
    organs = {value: key for key, value in LEGACY_ORGANS.items()}
    result = {keys.get(key, key): value for key, value in metadata.items()}
    if "estado" in metadata:
        result["status"] = statuses.get(metadata["estado"], metadata["estado"])
    if "organo" in metadata:
        result["organ"] = organs.get(metadata["organo"], metadata["organo"])
    if "estadisticas" in metadata:
        result["statistics"] = {
            "mean" if key == "media" else key: value
            for key, value in metadata["estadisticas"].items()
        }
    return result


class LegacyFileStoreAdapter:
    """Expose the English file-store contract over the existing Layer 3 facade."""

    def __init__(self, legacy_store: Any) -> None:
        self._legacy_store = legacy_store

    def save_projections(self, study_id: str, projections: np.ndarray) -> None:
        self._legacy_store.guardar_proyecciones(study_id, projections)

    def read_projections(self, study_id: str) -> np.ndarray:
        return self._read(self._legacy_store.leer_proyecciones, study_id)

    def save_volume(self, study_id: str, volume: np.ndarray) -> None:
        self._legacy_store.guardar_volumen(study_id, volume)

    def save_mesh(self, study_id: str, name: str, content: bytes) -> str:
        return self._legacy_store.save_mesh(study_id, name, content)

    def read_mesh(self, study_id: str, name: str) -> bytes:
        return self._read(lambda identifier: self._legacy_store.read_mesh(identifier, name), study_id)

    def read_volume(self, study_id: str) -> np.ndarray:
        return self._read(self._legacy_store.leer_volumen, study_id)

    def read_volume_bytes(self, study_id: str) -> bytes:
        return self._read(self._legacy_store.leer_volumen_bytes, study_id)

    def save_metadata(self, study_id: str, metadata: dict[str, Any]) -> None:
        self._legacy_store.guardar_metadatos(study_id, to_legacy_metadata(metadata))

    def read_metadata(self, study_id: str) -> dict[str, Any]:
        return from_legacy_metadata(self._read(self._legacy_store.leer_metadatos, study_id))

    @staticmethod
    def _read(operation, study_id: str):
        try:
            return operation(study_id)
        except LookupError as exc:
            from ..persistencia.almacen_archivos import EstudioNoEncontrado as LegacyStudyNotFound

            if isinstance(exc, LegacyStudyNotFound):
                raise FileNotFoundError(study_id) from exc
            raise
