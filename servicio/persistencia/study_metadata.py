"""
Capa 3 · Persistencia · Metadata store.

Translates between the dictionary the business layer works with and the tables
of the data model. It is the only module that knows both vocabularies.

The dictionary is handed back to the interface and shown on screen as it comes,
so what `read` returns must match what `save` received: the same keys, in the
same order, with the same types. Every mapping below exists to keep that true.

    id_estudio    -> study.study_code
    organo        -> organ, matched by a normalised name
    estado        -> study.status, in the canonical vocabulary
    angulos       -> the angles of the projection rows
    archivos      -> projection.original_name, one per angle
    fecha         -> study.date_time
    metodo        -> model, through the reconstruction stage
    tiempo_s      -> study.total_time_sec
    estadisticas  -> study.volume_min, volume_max, volume_mean

The business layer reports one duration for the whole pipeline rather than one
per stage, so the end of the reconstruction stage is derived from the
registration time plus that measured duration.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import layout
from .repositories.model_repository import RECONSTRUCTION, ModelRepository
from .repositories.organ_repository import OrganRepository, normalise
from .repositories.processing_stage_repository import (COMPLETED, SKIPPED,
                                                       WAITING,
                                                       ProcessingStageRepository)
from .repositories.projection_repository import (ProjectionFile,
                                                 ProjectionRepository)
from .repositories.study_repository import (StudyRepository,
                                            to_business_status,
                                            to_database_status)

# The reconstruction method the business layer names carries no version of its
# own, so it is registered as the first one.
DEFAULT_MODEL_VERSION = "v1"

PREPROCESSING_STAGE = 1
RECONSTRUCTION_STAGE = 2
SEGMENTATION_STAGE = 3
MESH_STAGE = 4


class StudyMetadataNotFound(LookupError):
    """No study with that identifier is stored."""


class MetadataStore:
    """Reads and writes the metadata of a study across the data model."""

    def __init__(self) -> None:
        self._organs = OrganRepository()
        self._studies = StudyRepository()
        self._projections = ProjectionRepository()
        self._models = ModelRepository()
        self._stages = ProcessingStageRepository()

    # ---------- write ----------
    def save(self, study_id: str, metadata: dict) -> None:
        """Store the metadata of a study, replacing what was stored before.

        The business layer calls this twice: once on registration, and again
        once processing has finished, with the same dictionary plus the results.
        """
        layout.check_study_id(study_id)
        registered_at = datetime.fromisoformat(metadata["fecha"])
        statistics = metadata.get("estadisticas") or {}

        self._studies.save(
            study_id,
            self._organs.find_id_by_name(metadata["organo"]),
            registered_at,
            to_database_status(metadata["estado"]),
            total_time_sec=metadata.get("tiempo_s"),
            volume_min=statistics.get("min"),
            volume_max=statistics.get("max"),
            volume_mean=statistics.get("media"),
        )
        self._save_projections(study_id, metadata)
        self._save_stages(study_id, metadata, registered_at)

    def _save_projections(self, study_id: str, metadata: dict) -> None:
        names = metadata.get("archivos") or {}
        angles = metadata.get("angulos") or []
        files = [ProjectionFile(angle,
                                layout.projection_path(study_id, angle),
                                names[f"{angle}°"])
                 for angle in angles if f"{angle}°" in names]
        self._projections.save_all(study_id, files)

    def _save_stages(self, study_id: str, metadata: dict,
                     registered_at: datetime) -> None:
        """Record the pipeline as far as it has got.

        Preprocessing has already happened by the time a study is registered:
        its four images were read and validated. The reconstruction stage is
        only complete once the business layer reports the method it used.
        Segmentation and meshes are recorded as omitted, not left out, so the
        interface can show the whole pipeline and say what was skipped.
        """
        self._stages.save(study_id, PREPROCESSING_STAGE, registered_at, COMPLETED)

        method = metadata.get("metodo")
        if method is None:
            self._stages.save(study_id, RECONSTRUCTION_STAGE, registered_at, WAITING)
            self._stages.save(study_id, SEGMENTATION_STAGE, registered_at, WAITING)
            self._stages.save(study_id, MESH_STAGE, registered_at, WAITING)
            return

        model_id = self._models.find_or_create(method, RECONSTRUCTION,
                                               DEFAULT_MODEL_VERSION)
        duration = metadata.get("tiempo_s")
        finished_at = (registered_at + timedelta(seconds=float(duration))
                       if duration is not None else None)
        self._stages.save(study_id, RECONSTRUCTION_STAGE, registered_at, COMPLETED,
                          model_id=model_id, finished_at=finished_at)
        self._stages.save(study_id, SEGMENTATION_STAGE, registered_at, SKIPPED)
        self._stages.save(study_id, MESH_STAGE, registered_at, SKIPPED)

    # ---------- read ----------
    def read(self, study_id: str) -> dict:
        """The metadata of a study, as the business layer wrote it.

        Keys are rebuilt in the order the business layer creates them, because
        the interface prints the dictionary as it arrives. Optional keys appear
        only once the value behind them exists.
        """
        layout.check_study_id(study_id)
        study = self._studies.find(study_id)
        if study is None:
            raise StudyMetadataNotFound(study_id)

        projections = self._projections.find_by_study(study_id)
        metadata = {
            "id_estudio": study["study_code"],
            "organo": normalise(self._organs.find_name_by_id(study["organ_id"])),
            "estado": to_business_status(study["status"]),
            "angulos": [projection.angle_degrees for projection in projections],
            "archivos": {f"{projection.angle_degrees}°": projection.original_name
                         for projection in projections},
            "fecha": study["date_time"].isoformat(timespec="seconds"),
        }

        method = self._read_method(study_id)
        if method is not None:
            metadata["metodo"] = method
        if study["total_time_sec"] is not None:
            metadata["tiempo_s"] = study["total_time_sec"]
        if study["volume_min"] is not None:
            metadata["estadisticas"] = {"min": study["volume_min"],
                                        "max": study["volume_max"],
                                        "media": study["volume_mean"]}
        return metadata

    def _read_method(self, study_id: str) -> str | None:
        """Name of the model the reconstruction stage used, when there is one."""
        for stage in self._stages.find_by_study(study_id):
            if stage["stage_number"] != RECONSTRUCTION_STAGE:
                continue
            if stage["model_id"] is None:
                return None
            model = self._models.find_by_id(stage["model_id"])
            return None if model is None else model["model_name"]
        return None