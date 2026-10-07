from __future__ import annotations

import re
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait as wait_for_jobs
from datetime import datetime
from threading import Lock
from typing import Any, Callable, ParamSpec, Protocol, TypeVar

import numpy as np

from ..config import ANGLES, GRID_SIZE
from .tuberia.preproceso import InvalidImage, read_projection
from .tuberia.orchestrator import ArtifactReferences, PipelineResult, StageObserver, VolumeReconstructor

STUDY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PENDING = "pending"
PROCESSING = "processing"
COMPLETED = "completed"
ERROR = "error"
TaskParameters = ParamSpec("TaskParameters")
TaskResult = TypeVar("TaskResult")


class FileStore(Protocol):
    """Layer 3 contract for binary artifacts and study metadata."""

    def save_projections(self, study_id: str, projections: np.ndarray) -> None:
        ...

    def read_projections(self, study_id: str) -> np.ndarray:
        ...

    def save_volume(self, study_id: str, volume: np.ndarray) -> None:
        ...

    def read_volume(self, study_id: str) -> np.ndarray:
        ...

    def read_volume_bytes(self, study_id: str) -> bytes:
        ...

    def read_mesh(self, study_id: str, name: str) -> bytes:
        ...

    def save_metadata(self, study_id: str, metadata: dict[str, Any]) -> None:
        ...

    def read_metadata(self, study_id: str) -> dict[str, Any]:
        ...


class StageRepository(Protocol):
    """Optional repository for tracking individual processing stages."""

    def record_waiting(self, study_id: str, stage: int) -> None:
        ...

    def record_start(self, study_id: str, stage: int) -> None:
        ...

    def record_success(self, study_id: str, stage: int, metrics: dict[str, Any] | None = None) -> None:
        ...

    def record_error(self, study_id: str, stage: int, reason: str) -> None:
        ...


class BackgroundExecutor(Protocol):
    """Minimal executor contract for background processing."""

    def submit(self, function: Callable[TaskParameters, TaskResult], /,
               *args: TaskParameters.args, **kwargs: TaskParameters.kwargs) -> Future[TaskResult]:
        ...


class StudyPipeline(Protocol):
    method: str
    note: str

    def execute(self, study_id: str, radiographs: np.ndarray,
                observer: StageObserver | None = None) -> PipelineResult:
        ...


class StudyRejected(ValueError):
    """A study violates a domain rule, optionally identifying the invalid file."""

    def __init__(self, reason: str, filename: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.filename = filename


class StudyNotFound(LookupError):
    """The requested study does not exist."""


class StudyInProgress(RuntimeError):
    """The study has not produced all its artifacts yet."""


class StudyAlreadyCompleted(RuntimeError):
    """A completed study cannot be processed again."""


class StudyAlreadyExists(StudyRejected):
    """Registration cannot overwrite an existing study."""

    def __init__(self, study_id: str) -> None:
        super().__init__(f"Study '{study_id}' already exists.")


class StudyUseCases:
    def __init__(
        self,
        file_store: FileStore,
        reconstructor: VolumeReconstructor | None = None,
        *,
        pipeline: StudyPipeline | None = None,
        stages: StageRepository | None = None,
        executor: BackgroundExecutor | None = None,
    ) -> None:
        if pipeline is None and reconstructor is None:
            raise ValueError("Provide a pipeline or a reconstructor.")
        self._file_store = file_store              # Layer 3
        self._pipeline = pipeline
        self._reconstructor = reconstructor  # Compatibility with the original reconstruction-only flow
        self._stages = stages
        self._owned_executor: ThreadPoolExecutor | None = None
        if executor is None:
            self._owned_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="radvol3d")
            self._executor: BackgroundExecutor = self._owned_executor
        else:
            self._executor = executor
        self._jobs: dict[str, Future[None]] = {}
        self._jobs_lock = Lock()
        self._closed = False

    def describe(self) -> dict:
        """Describe the active processing engine."""
        engine = self._pipeline or self._reconstructor
        return {"method": getattr(engine, "method", "radvol3d_pipeline"),
                "note": getattr(engine, "note", "Business pipeline ready to execute."),
                "angles": list(ANGLES)}

    # ---------- Register study ----------
    def register_study(
        self,
        images: dict[int, tuple[str, bytes] | None],
        study_id: str | None = None,
        organ: str = "lung",
        patient: dict[str, Any] | None = None,
    ) -> str:
        """Validate the four required views and register a pending study."""
        # Domain rule: exactly four views at the required angles
        received = {angle for angle, image in images.items() if image}
        expected = set(ANGLES)
        missing = [f"{a}°" for a in ANGLES if a not in received]
        extra = [f"{a}°" for a in sorted(set(images) - expected)]
        if missing or extra:
            details = []
            if missing:
                details.append(f"Missing: {', '.join(missing)}")
            if extra:
                details.append(f"Unexpected: {', '.join(extra)}")
            raise StudyRejected(
                f"Exactly four projections at 0, 45, 90 and 135 degrees are required. {'; '.join(details)}.")

        if study_id:
            study_id = study_id.strip()
            if not STUDY_ID_PATTERN.match(study_id):
                raise StudyRejected("study_id accepts only letters, digits, '-' and '_' (maximum 64 characters).")
        else:
            study_id = "EST-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]

        # Validate images and convert them to the configured grid size.
        try:
            projections = np.stack([read_projection(*images[a]) for a in ANGLES])
        except InvalidImage as e:
            raise StudyRejected(e.reason, e.filename)

        metadata = {
            "study_id": study_id,
            "patient": patient or {},
            "organ": organ,
            "status": PENDING,
            "angles": list(ANGLES),
            "files": {f"{a}°": images[a][0] for a in ANGLES},
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        with self._jobs_lock:
            self._ensure_open()
            try:
                self._file_store.read_metadata(study_id)
            except FileNotFoundError:
                pass
            else:
                raise StudyAlreadyExists(study_id)
            self._file_store.save_projections(study_id, projections)
            self._file_store.save_metadata(study_id, metadata)
        return study_id

    # ---------- Process study ----------
    def process_study(self, study_id: str, *, in_background: bool = True) -> Future[None] | None:
        """Execute the study pipeline.

        Schedule background work by default. Tests and legacy callers can use
        ``in_background=False`` to wait for completion before returning.
        """
        if not STUDY_ID_PATTERN.match(study_id or ""):
            raise StudyNotFound(study_id)
        with self._jobs_lock:
            self._ensure_open()
            existing = self._jobs.get(study_id)
            if existing is not None and not existing.done():
                raise StudyInProgress(study_id)
            metadata = self._read(self._file_store.read_metadata, study_id)
            if metadata["status"] == COMPLETED:
                raise StudyAlreadyCompleted(study_id)
            if metadata["status"] == PROCESSING:
                raise StudyInProgress(study_id)
            if in_background:
                job = self._executor.submit(self._process_study, study_id)
                self._jobs[study_id] = job
                return job
            job = Future()
            job.set_running_or_notify_cancel()
            self._jobs[study_id] = job
        try:
            self._process_study(study_id)
        except Exception as exc:
            job.set_exception(exc)
            raise
        job.set_result(None)
        return None

    def _process_study(self, study_id: str) -> None:
        metadata = self._read(self._file_store.read_metadata, study_id)
        try:
            self._save_metadata(study_id, metadata, status=PROCESSING, error=None,
                                progress=None, stage_statuses={}, stage_details={}, metrics={},
                                statistics={}, result_files={})
            for stage in ((1, 2, 3, 4) if self._pipeline is not None else (2,)):
                self._record_stage(study_id, stage, "waiting")
            projections = self._read(self._file_store.read_projections, study_id)
            result = self._run_pipeline(study_id, projections)
            metadata = self._read(self._file_store.read_metadata, study_id)
            metadata.update({
                "status": COMPLETED,
                "method": result.method,
                "elapsed_seconds": result.elapsed_seconds,
                "statistics": {"min": round(float(result.volume.min()), 4),
                               "max": round(float(result.volume.max()), 4),
                               "mean": round(float(result.volume.mean()), 4)},
                "metrics": result.metrics,
                "result_files": result.files.as_dict(),
                "error": None,
            })
            self._file_store.save_metadata(study_id, metadata)
        except Exception as exc:
            try:
                metadata = self._read(self._file_store.read_metadata, study_id)
                self._save_metadata(study_id, metadata, status=ERROR, error=exc.__class__.__name__)
            except Exception as storage_error:
                exc.add_note(f"Could not persist the failure state: {storage_error.__class__.__name__}.")
            raise

    def _run_pipeline(self, study_id: str, projections: np.ndarray) -> PipelineResult:
        if self._pipeline is not None:
            return self._pipeline.execute(study_id, projections, observer=self._record_stage)

        reconstructor = self._reconstructor
        if reconstructor is None:
            raise RuntimeError("No processing engine is configured.")

        start = time.perf_counter()
        self._record_stage(study_id, 2, "start", {"name": "reconstruction"})
        try:
            volume = reconstructor.reconstruct(projections)
            if volume.shape != (GRID_SIZE, GRID_SIZE, GRID_SIZE) or not np.isfinite(volume).all():
                raise ValueError("Reconstruction must produce a finite volume of the configured size.")
            self._file_store.save_volume(study_id, volume)
        except Exception as exc:
            self._record_stage(study_id, 2, "error", {"name": "reconstruction",
                                                     "reason": exc.__class__.__name__})
            raise
        self._record_stage(study_id, 2, "success", {"name": "reconstruction"})
        return PipelineResult(
            volume=volume,
            tumor_mask=np.zeros_like(volume, dtype=np.uint8),
            confidence=0.0,
            files=ArtifactReferences(volume="volume.npy"),
            metrics={},
            method=reconstructor.method,
            elapsed_seconds=round(time.perf_counter() - start, 3),
        )

    def _record_stage(self, study_id: str, stage: int, event: str,
                         data: dict[str, Any] | None = None) -> None:
        metadata = self._read(self._file_store.read_metadata, study_id)
        stage_statuses = dict(metadata.get("stage_statuses", {}))
        stage_statuses[str(stage)] = event
        stage_details = dict(metadata.get("stage_details", {}))
        details = dict(stage_details.get(str(stage), {}))
        if event == "start":
            details["started_at"] = datetime.now().isoformat()
        elif event in ("success", "error"):
            details["finished_at"] = datetime.now().isoformat()
        stage_details[str(stage)] = details
        progress = metadata.get("progress")
        if event != "waiting":
            progress = {"stage": stage, "event": event,
                        "name": (data or {}).get("name"),
                        "completed_stages": sum(value == "success" for value in stage_statuses.values())}
        self._save_metadata(study_id, metadata, stage_statuses=stage_statuses,
                            stage_details=stage_details, progress=progress)
        if self._stages is None:
            return
        if event == "waiting":
            self._stages.record_waiting(study_id, stage)
        elif event == "start":
            self._stages.record_start(study_id, stage)
        elif event == "success":
            self._stages.record_success(study_id, stage, data)
        elif event == "error":
            self._stages.record_error(study_id, stage, str((data or {}).get("reason", "")))

    # ---------- Query results ----------
    def get_result(self, study_id: str) -> tuple[dict, np.ndarray]:
        job = self._jobs.get(study_id)
        if job is not None:
            job.result()
        metadata = self._read(self._file_store.read_metadata, study_id)
        if metadata["status"] in (PENDING, PROCESSING):
            raise StudyInProgress(study_id)
        volume = self._read(self._file_store.read_volume, study_id)
        return metadata, volume

    def get_volume_npy(self, study_id: str) -> bytes:
        return self._read(self._file_store.read_volume_bytes, study_id)

    def get_mesh_glb(self, study_id: str, name: str) -> bytes:
        keys = {"organ.glb": "organ_glb", "tumor.glb": "tumor_glb"}
        if name not in keys:
            raise StudyNotFound(study_id)
        metadata = self._read(self._file_store.read_metadata, study_id)
        if metadata["status"] != COMPLETED or not metadata.get("result_files", {}).get(keys[name]):
            raise StudyNotFound(study_id)
        return self._read(lambda identifier: self._file_store.read_mesh(identifier, name), study_id)

    def get_results(self, study_id: str) -> dict[str, Any]:
        """Return the study status, metrics and artifact references."""
        metadata = self._read(self._file_store.read_metadata, study_id)
        return {
            "study_id": metadata["study_id"],
            "status": metadata["status"],
            "metrics": metadata.get("metrics", {}),
            "statistics": metadata.get("statistics", {}),
            "files": metadata.get("result_files", {}),
            "error": metadata.get("error"),
            "progress": metadata.get("progress"),
            "stage_statuses": metadata.get("stage_statuses", {}),
        }

    def close(self, *, wait: bool = True) -> None:
        """Stop accepting work; injected executors remain owned by the caller."""
        with self._jobs_lock:
            self._closed = True
            jobs = list(self._jobs.values())
        if self._owned_executor is not None:
            self._owned_executor.shutdown(wait=wait)
        elif wait:
            wait_for_jobs(jobs)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Study use cases are closed.")

    def _save_metadata(self, study_id: str, metadata: dict[str, Any], **changes: Any) -> None:
        updated = dict(metadata)
        updated.update(changes)
        self._file_store.save_metadata(study_id, updated)

    # ---------- Helpers ----------
    @staticmethod
    def _read(operation, study_id):
        if not STUDY_ID_PATTERN.match(study_id or ""):
            raise StudyNotFound(study_id)
        try:
            return operation(study_id)
        except FileNotFoundError:
            raise StudyNotFound(study_id)
