"""Compose the trained four-stage pipeline with injected Layer 3 storage."""
from __future__ import annotations

from ...config import SEGMENTATION_WEIGHTS_PATH, WEIGHTS_PATH
from .meshes import EN42MeshGenerator
from .orchestrator import ArtifactStore, PipelineOrchestrator, Preprocessor
from .preproceso import ProjectionPreprocessor


def create_pipeline(
    preprocessor: Preprocessor | None,
    artifact_store: ArtifactStore,
    *,
    reconstruction_weights: str = str(WEIGHTS_PATH),
    segmentation_weights: str = str(SEGMENTATION_WEIGHTS_PATH),
    device: str | None = None,
) -> PipelineOrchestrator:
    """Require trained models; model loading failures propagate to the caller."""
    from .en1_reconstruction import EN1Reconstructor
    from .en4_segmentation import EN4LungSegmenter

    return PipelineOrchestrator(
        preprocessor=preprocessor if preprocessor is not None else ProjectionPreprocessor(),
        reconstructor=EN1Reconstructor(reconstruction_weights, device=device),
        segmenter=EN4LungSegmenter(segmentation_weights, device=device),
        mesh_generator=EN42MeshGenerator(),
        artifact_store=artifact_store,
    )
