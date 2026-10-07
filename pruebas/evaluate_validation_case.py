"""Compare EN-4 segmentation on original and EN-1 reconstructed volumes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from servicio.logica.tuberia.en1_reconstruction import EN1Reconstructor
from servicio.logica.tuberia.en4_segmentation import EN4LungSegmenter
from servicio.logica.tuberia.preproceso import ProjectionPreprocessor, read_projection
from servicio.config import WEIGHTS_PATH


def dice_score(predicted: np.ndarray, reference: np.ndarray) -> float:
    predicted_mask = predicted > 0
    reference_mask = reference > 0
    total = int(predicted_mask.sum()) + int(reference_mask.sum())
    return 2.0 * int(np.logical_and(predicted_mask, reference_mask).sum()) / total if total else 1.0


def evaluate(directory: Path, case_id: str) -> dict:
    projections = np.stack([
        read_projection((path := directory / f"{case_id}_{angle:03d}.npy").name, path.read_bytes())
        for angle in (0, 45, 90, 135)
    ])
    projections = ProjectionPreprocessor().execute(projections)
    original = np.load(directory / f"{case_id}_vol.npy", allow_pickle=False)
    reference = np.load(directory / f"{case_id}_tumor.npy", allow_pickle=False)
    if original.shape != (128, 128, 128) or reference.shape != original.shape:
        raise ValueError("Reference arrays must have shape (128, 128, 128).")
    torch.set_num_threads(4)
    start = time.perf_counter()
    reconstructor = EN1Reconstructor(WEIGHTS_PATH, device="cpu")
    segmenter = EN4LungSegmenter(device="cpu")
    reconstructed = reconstructor.reconstruct(projections)
    original_result = segmenter.segment(original)
    reconstructed_result = segmenter.segment(reconstructed)
    np.save(directory / f"{case_id}_reconstructed.npy", reconstructed, allow_pickle=False)
    np.save(directory / f"{case_id}_predicted_tumor.npy", reconstructed_result.tumor_mask, allow_pickle=False)
    np.save(directory / f"{case_id}_probabilities.npy", reconstructed_result.probability_map, allow_pickle=False)
    report = {
        "case_id": case_id,
        "projection_shape": list(projections.shape),
        "reference_tumor_voxels": int((reference > 0).sum()),
        "dice_original_volume": dice_score(original_result.tumor_mask, reference),
        "dice_reconstructed_volume": dice_score(reconstructed_result.tumor_mask, reference),
        "predicted_tumor_voxels_original": int(original_result.tumor_mask.sum()),
        "predicted_tumor_voxels_reconstructed": int(reconstructed_result.tumor_mask.sum()),
        "reconstructed_regional_confidence": reconstructed_result.regional_confidence,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "limitation": "Single-case technical evaluation; no interface or Supabase verification.",
    }
    (directory / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("datos/validation/lung_003"))
    parser.add_argument("--case", default="lung_003")
    arguments = parser.parse_args()
    print(json.dumps(evaluate(arguments.directory, arguments.case), indent=2))
