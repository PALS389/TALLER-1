from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypeVar

import numpy as np


StageObserver = Callable[[str, int, str, dict[str, Any] | None], None]
T = TypeVar("T")


@dataclass(frozen=True)
class ArtifactReferences:
    """Identifiers of the binary artifacts produced by the pipeline."""

    volume: str
    organ_glb: str | None = None
    tumor_glb: str | None = None

    def as_dict(self) -> dict[str, str]:
        return {key: value for key, value in {
            "volume": self.volume,
            "organ_glb": self.organ_glb,
            "tumor_glb": self.tumor_glb,
        }.items() if value is not None}


@dataclass(frozen=True)
class SegmentationResult:
    tumor_mask: np.ndarray
    confidence: float
    probability_map: np.ndarray | None = None
    regional_confidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    confidence_threshold: float = 0.5


@dataclass(frozen=True)
class MeshResult:
    organ_glb: bytes
    tumor_glb: bytes


@dataclass(frozen=True)
class PipelineResult:
    volume: np.ndarray
    tumor_mask: np.ndarray
    confidence: float
    files: ArtifactReferences
    metrics: dict[str, Any]
    method: str
    elapsed_seconds: float


class Preprocessor(Protocol):
    method: str

    def execute(self, projections: np.ndarray) -> np.ndarray:
        ...


class VolumeReconstructor(Protocol):
    method: str

    def reconstruct(self, projections: np.ndarray) -> np.ndarray:
        ...


class TumorSegmenter(Protocol):
    method: str

    def segment(self, volume: np.ndarray) -> SegmentationResult:
        ...


class MeshGenerator(Protocol):
    method: str

    def generate(self, volume: np.ndarray, tumor_mask: np.ndarray) -> MeshResult:
        ...


class ArtifactStore(Protocol):
    """Layer 3 contract for saving derived binary artifacts."""

    def save_volume(self, study_id: str, volume: np.ndarray) -> None:
        ...

    def save_mesh(self, study_id: str, name: str, content: bytes) -> str:
        ...


class PipelineOrchestrator:
    """Coordinate the four sequential stages of the RadVol3D pipeline."""

    method = "four_stage_pipeline"
    note = "Preprocessing, reconstruction, 3D U-Net segmentation and mesh generation."

    def __init__(
        self,
        preprocessor: Preprocessor,
        reconstructor: VolumeReconstructor,
        segmenter: TumorSegmenter,
        mesh_generator: MeshGenerator,
        artifact_store: ArtifactStore,
    ) -> None:
        self._preprocessor = preprocessor
        self._reconstructor = reconstructor
        self._segmenter = segmenter
        self._mesh_generator = mesh_generator
        self._artifact_store = artifact_store

    def execute(
        self,
        study_id: str,
        radiographs: np.ndarray,
        observer: StageObserver | None = None,
    ) -> PipelineResult:
        start = time.perf_counter()
        observe = observer or self._ignore_event

        projections = self._run_stage(
            study_id, 1, "preprocessing", observe,
            lambda: self._preprocessor.execute(radiographs),
            lambda array: self._validate_shape("preprocessing", array, (4, 128, 128)),
        )

        def validate_and_save_volume(array: np.ndarray) -> None:
            self._validate_shape("reconstruction", array, (128, 128, 128))
            self._artifact_store.save_volume(study_id, array)

        volume = self._run_stage(
            study_id, 2, "reconstruction", observe,
            lambda: self._reconstructor.reconstruct(projections),
            validate_and_save_volume,
        )

        def validate_segmentation(result: SegmentationResult) -> None:
            self._validate_shape("segmentation", result.tumor_mask, (128, 128, 128))
            if not np.isfinite(result.confidence) or not 0.0 <= result.confidence <= 1.0:
                raise ValueError("Segmentation confidence must be between 0 and 1.")
            if result.probability_map is not None:
                self._validate_shape("probability map", result.probability_map, (128, 128, 128))
                if np.any((result.probability_map < 0) | (result.probability_map > 1)):
                    raise ValueError("Segmentation probabilities must be between 0 and 1.")

        segmentation = self._run_stage(
            study_id, 3, "segmentation", observe,
            lambda: self._segmenter.segment(volume),
            validate_segmentation,
        )

        def generate_and_save_meshes() -> tuple[str, str]:
            meshes = self._mesh_generator.generate(volume, segmentation.tumor_mask)
            organ_ref = self._artifact_store.save_mesh(study_id, "organ.glb", meshes.organ_glb)
            tumor_ref = self._artifact_store.save_mesh(study_id, "tumor.glb", meshes.tumor_glb)
            return organ_ref, tumor_ref

        organ_ref, tumor_ref = self._run_stage(
            study_id, 4, "meshes", observe,
            generate_and_save_meshes,
        )
        mesh_metrics = getattr(self._mesh_generator, "last_metrics", {})

        return PipelineResult(
            volume=volume,
            tumor_mask=segmentation.tumor_mask,
            confidence=segmentation.confidence,
            files=ArtifactReferences(
                volume="volume.npy",
                organ_glb=organ_ref,
                tumor_glb=tumor_ref,
            ),
            metrics={"tumor_confidence": float(segmentation.confidence),
                      "confidence_threshold": float(segmentation.confidence_threshold),
                      "regional_confidence": segmentation.regional_confidence,
                      "meshes": mesh_metrics},
            method=self.method,
            elapsed_seconds=round(time.perf_counter() - start, 3),
        )

    def _run_stage(self, study_id: str, number: int, name: str,
                        observe: StageObserver, operation: Callable[[], T],
                        validate: Callable[[T], None] | None = None) -> T:
        observe(study_id, number, "start", {"name": name})
        try:
            result = operation()
            if validate is not None:
                validate(result)
        except Exception as exc:
            observe(study_id, number, "error", {"name": name, "reason": exc.__class__.__name__})
            raise
        observe(study_id, number, "success", {"name": name})
        return result

    @staticmethod
    def _validate_shape(name: str, array: np.ndarray, shape: tuple[int, ...]) -> None:
        if array.shape != shape:
            raise ValueError(f"Stage {name} produced {array.shape}; expected {shape}.")
        if not np.isfinite(array).all():
            raise ValueError(f"Stage {name} produced non-finite values.")

    @staticmethod
    def _ignore_event(_study_id: str, _stage: int, _event: str,
                        _data: dict[str, Any] | None = None) -> None:
        return None
