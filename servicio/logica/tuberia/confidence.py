"""EN-4 probability summaries using the notebook's eight array octants."""
from __future__ import annotations

from typing import Any

import numpy as np

from .orchestrator import SegmentationResult


def summarize_probabilities(
    probability_map: np.ndarray,
    *,
    threshold: float = 0.5,
    voxel_spacing_mm: tuple[float, float, float] = (2.5, 2.5, 2.5),
) -> SegmentationResult:
    """Average probabilities over predicted tumor voxels, not background.

    Region names follow EN-4's array-axis convention, not verified patient
    orientation. Volumes use the supplied spacing, in millimetres per voxel.
    Model probabilities are not calibrated diagnostic confidence scores.
    """
    probabilities = np.asarray(probability_map, dtype=np.float32)
    if probabilities.shape != (128, 128, 128):
        raise ValueError(f"Expected probability map (128, 128, 128), received {probabilities.shape}.")
    if not np.isfinite(probabilities).all() or np.any((probabilities < 0) | (probabilities > 1)):
        raise ValueError("Probabilities must be finite values between 0 and 1.")
    if not np.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("Confidence threshold must be between 0 and 1, exclusively.")
    spacing = np.asarray(voxel_spacing_mm, dtype=np.float64)
    if spacing.shape != (3,) or not np.isfinite(spacing).all() or np.any(spacing <= 0):
        raise ValueError("Voxel spacing must contain three positive finite values.")

    voxel_volume = float(np.prod(spacing))
    tumor_mask = probabilities > threshold
    regions: dict[str, dict[str, Any]] = {}
    for z_index, z_name in enumerate(("upper", "lower")):
        for y_index, y_name in enumerate(("front", "back")):
            for x_index, x_name in enumerate(("left", "right")):
                slices = tuple(slice(index * 64, (index + 1) * 64)
                               for index in (z_index, y_index, x_index))
                selected = probabilities[slices][tumor_mask[slices]]
                regions[f"{z_name}_{y_name}_{x_name}"] = {
                    "has_lesion": bool(selected.size),
                    "mean_confidence": round(float(selected.mean()), 4) if selected.size else 0.0,
                    "volume_mm3": round(int(selected.size) * voxel_volume, 2),
                }

    selected = probabilities[tumor_mask]
    return SegmentationResult(
        tumor_mask=tumor_mask.astype(np.uint8),
        confidence=float(selected.mean()) if selected.size else 0.0,
        probability_map=probabilities,
        regional_confidence=regions,
        confidence_threshold=threshold,
    )
