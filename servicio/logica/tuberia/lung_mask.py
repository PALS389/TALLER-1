"""EN-42 lung-air extraction ported from Bray's delivered notebook.

This is a morphological research heuristic, not a trained or clinically
validated organ segmenter. Invalid candidates fail instead of becoming a body mesh.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import ndimage
from scipy.spatial import ConvexHull, QhullError


class InvalidLungMask(ValueError):
    """No plausible internal lung-air mask was found."""


@dataclass(frozen=True)
class LungMaskResult:
    mask: np.ndarray
    diagnostics: dict[str, Any]


def _internal_air(air: np.ndarray, axis: int) -> np.ndarray:
    result = np.zeros_like(air)
    structure = ndimage.generate_binary_structure(2, 1)
    for index in range(air.shape[axis]):
        section = np.take(air, index, axis=axis)
        labels, count = ndimage.label(section, structure=structure)
        if not count:
            continue
        boundary = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
        selector = [slice(None)] * 3
        selector[axis] = index
        result[tuple(selector)] = section & ~np.isin(labels, boundary[boundary > 0])
    return result


def _solidity(mask: np.ndarray, max_points: int = 4000) -> float:
    points = np.argwhere(mask & ~ndimage.binary_erosion(mask)).astype(float)
    if len(points) < 20:
        return 0.0
    if len(points) > max_points:
        points = points[np.random.default_rng(0).choice(len(points), max_points, replace=False)]
    try:
        hull_volume = ConvexHull(points).volume
    except QhullError:
        return 0.0
    return float(min(1.0, mask.sum() / max(hull_volume, 1.0)))


def _score(mask: np.ndarray) -> tuple[float, dict[str, Any] | None]:
    fraction = float(mask.sum() / mask.size)
    if not 0.012 <= fraction <= 0.30:
        return 0.0, None
    indices = np.argwhere(mask)
    extent = (indices.max(0) - indices.min(0) + 1).astype(float)
    if (extent / np.array(mask.shape) > 0.92).sum() >= 2:
        return 0.0, None
    filling = float(mask.sum() / np.prod(extent))
    if filling > 0.70:
        return 0.0, None
    labels, count = ndimage.label(mask)
    sizes = np.asarray(ndimage.sum(mask, labels, range(1, count + 1)))
    order = np.argsort(sizes)[::-1]
    large = [int(index) + 1 for index in order if sizes[index] >= 0.10 * sizes[order[0]]]
    if len(large) > 3:
        return 0.0, None
    solidity = float(np.mean([_solidity(labels == label) for label in large]))
    pair_ratio = float(sizes[order[1]] / sizes[order[0]]) if len(large) == 2 else 0.0
    if solidity < 0.55:
        return 0.0, None
    return solidity + 0.5 * pair_ratio, {
        "fraction": round(fraction, 3), "components": len(large),
        "solidity": round(solidity, 2), "bounding_box_filling": round(filling, 2),
        "pair_ratio": round(pair_ratio, 2),
    }


def _air_by_erosion(volume: np.ndarray, threshold: float, erosion: int,
                    structure: np.ndarray, minimum: int) -> np.ndarray | None:
    air = volume < threshold
    core = ndimage.binary_erosion(air, structure, iterations=erosion, border_value=1)
    labels, count = ndimage.label(core)
    if not count:
        return None
    sizes = np.asarray(ndimage.sum(core, labels, range(1, count + 1)))
    faces: dict[int, int] = {}
    for axis in range(3):
        for index in (0, -1):
            for label in np.unique(np.take(labels, index, axis=axis)):
                if label > 0:
                    faces[int(label)] = faces.get(int(label), 0) + 1
    exterior = {label for label, face_count in faces.items() if face_count >= 3}
    exterior.update(label for label in range(1, count + 1) if sizes[label - 1] > 0.40 * volume.size)
    candidates = [label for label in range(1, count + 1)
                  if label not in exterior and sizes[label - 1] >= minimum]
    if not candidates:
        return None
    candidates.sort(key=lambda label: -sizes[label - 1])
    largest = sizes[candidates[0] - 1]
    candidates = [label for index, label in enumerate(candidates)
                  if sizes[label - 1] >= (0.05 if index < 2 else 0.30) * largest][:3]
    return ndimage.binary_dilation(np.isin(labels, candidates), structure,
                                   iterations=erosion + 1, mask=air)


def _air_base(volume: np.ndarray, threshold: float, method: str, axis: int | None,
              structure: np.ndarray, closing: int, minimum: float) -> np.ndarray | None:
    air = volume < threshold
    if method == "sections":
        if axis is None:
            raise ValueError("Section extraction requires an axis.")
        result = _internal_air(air, axis)
        return result if result.any() else None
    closed = ndimage.binary_closing(air, structure, iterations=closing)
    labels, count = ndimage.label(closed)
    if not count:
        return None
    boundary: set[int] = set()
    for dimension in range(3):
        for index in (0, -1):
            boundary.update(np.unique(np.take(labels, index, axis=dimension)).tolist())
    sizes = np.asarray(ndimage.sum(closed, labels, range(1, count + 1)))
    keep = [label for label in range(1, count + 1)
            if label not in boundary and sizes[label - 1] >= minimum]
    return np.isin(labels, keep) if keep else None


def _remove_tissue_box(volume: np.ndarray, mask: np.ndarray) -> np.ndarray | None:
    from skimage.filters import threshold_otsu

    values = volume[mask]
    if values.size < 1000:
        return None
    threshold = threshold_otsu(values)
    lower = values < threshold
    if not 0.10 <= lower.mean() <= 0.90:
        return None
    separation = (values[~lower].mean() - values[lower].mean()) / np.sqrt(
        0.5 * (values[lower].var() + values[~lower].var()) + 1e-12)
    return mask & (volume < threshold) if separation >= 2.5 else None


def _separate_lungs(mask: np.ndarray, structure: np.ndarray, erosion: int,
                    minimum: float) -> np.ndarray | None:
    core = ndimage.binary_erosion(mask, structure, iterations=erosion, border_value=1)
    labels, count = ndimage.label(core)
    if not count:
        return None
    sizes = np.asarray(ndimage.sum(core, labels, range(1, count + 1)))
    candidates = [int(index) + 1 for index in np.argsort(sizes)[::-1][:2] if sizes[index] >= minimum]
    if not candidates:
        return None
    return ndimage.binary_dilation(np.isin(labels, candidates), structure,
                                   iterations=erosion + 1, mask=mask)


def _search(volume: np.ndarray, minimum: int) -> tuple[np.ndarray, dict[str, Any]] | None:
    smoothed = ndimage.gaussian_filter(volume, 1.0)
    structure = ndimage.generate_binary_structure(3, 1)
    reduced = smoothed[::2, ::2, ::2]
    low, high = np.percentile(smoothed, (1, 99))
    thresholds = [0.30, 0.25, 0.20, 0.15, 0.35, 0.40]
    thresholds += [float(low + (high - low) * fraction) for fraction in (0.06, 0.10, 0.14, 0.18, 0.22, 0.28, 0.34)]
    methods = [("boundary", None), ("sections", 2), ("sections", 0), ("sections", 1)]
    candidates = []
    for threshold in thresholds:
        for method, axis in methods:
            base = _air_base(reduced, threshold, method, axis, structure, 1, minimum / 8)
            if base is None:
                continue
            cleaned = _remove_tissue_box(reduced, base)
            mask = cleaned if cleaned is not None else base
            for erosion in (1, 2):
                separated = _separate_lungs(mask, structure, erosion, minimum / 8)
                if separated is None:
                    continue
                score, details = _score(separated)
                if details is not None:
                    candidates.append((float(separated.sum()), score, method, axis, threshold, cleaned is not None, erosion))
    candidates.sort(reverse=True)
    final = None
    largest = 0
    for _, _, method, axis, threshold, remove_box, small_erosion in candidates[:8]:
        erosion = small_erosion * 2
        base = _air_base(smoothed, threshold, method, axis, structure, 2, minimum)
        if base is None:
            continue
        if remove_box:
            base = _remove_tissue_box(smoothed, base)
            if base is None:
                continue
        mask = _separate_lungs(base, structure, erosion, minimum)
        if mask is None:
            continue
        opened = ndimage.binary_dilation(
            ndimage.binary_erosion(mask, structure, iterations=3, border_value=1),
            structure, iterations=3, mask=mask)
        if opened.sum() > 0.5 * mask.sum():
            mask = opened
        labels, count = ndimage.label(mask)
        if count > 1:
            sizes = np.asarray(ndimage.sum(mask, labels, range(1, count + 1)))
            order = np.argsort(sizes)[::-1][:2]
            mask = np.isin(labels, [int(index) + 1 for index in order if sizes[index] >= 0.10 * sizes[order[0]]])
        _, details = _score(mask)
        if details is not None and mask.sum() > largest:
            largest = int(mask.sum())
            details.update({"method": "search", "exterior_method": method, "axis": axis,
                            "threshold": round(float(threshold), 3), "tissue_box_removed": remove_box,
                            "erosion": erosion})
            final = mask, details
    if final is None:
        return None
    mask, details = final
    padded = np.pad(mask, 3, constant_values=False)
    padded = ndimage.binary_fill_holes(ndimage.binary_closing(padded, structure, iterations=2))
    return padded[3:-3, 3:-3, 3:-3], details


class EN42LungMaskExtractor:
    method = "en42_internal_lung_air_v1"

    def __init__(self, *, threshold: float = 0.30, minimum_voxels: int = 300) -> None:
        if not np.isfinite(threshold) or minimum_voxels < 8:
            raise ValueError("Invalid lung-mask configuration.")
        self.threshold = threshold
        self.minimum_voxels = minimum_voxels

    def extract(self, volume: np.ndarray, tumor_mask: np.ndarray | None = None) -> LungMaskResult:
        source = np.asarray(volume)
        if source.ndim != 3 or min(source.shape) < 16 or np.iscomplexobj(source) or not np.isfinite(source).all():
            raise InvalidLungMask("Expected a finite real 3D volume with at least 16 voxels per axis.")
        if float(np.ptp(source)) < 1e-6:
            raise InvalidLungMask("A uniform volume cannot identify lung air.")
        with np.errstate(over="ignore", invalid="ignore"):
            values = source.astype(np.float32)
        if not np.isfinite(values).all():
            raise InvalidLungMask("Volume values cannot be represented as finite float32 intensities.")
        tumor = None
        if tumor_mask is not None:
            tumor = np.asarray(tumor_mask)
            if tumor.shape != values.shape or np.iscomplexobj(tumor) or not np.isfinite(tumor).all():
                raise InvalidLungMask("Tumor mask must match the finite volume shape.")
            tumor = tumor > 0
        structure = ndimage.generate_binary_structure(3, 1)
        thresholds = [self.threshold] + [value for value in (0.25, 0.35, 0.20, 0.40) if value != self.threshold]
        result = None
        for threshold in thresholds:
            for erosion in (3, 4, 5, 6, 7):
                mask = _air_by_erosion(values, threshold, erosion, structure, self.minimum_voxels)
                if mask is None:
                    continue
                _, details = _score(mask)
                if details is not None:
                    details.update({"method": "erosion", "threshold": threshold, "erosion": erosion})
                    result = mask, details
                    break
            if result is not None:
                break
        if result is None:
            result = _search(values, self.minimum_voxels)
        if result is None:
            raise InvalidLungMask("No plausible lung-air mask was found; body-surface fallback is disabled.")
        mask, details = result
        if tumor is not None:
            mask = mask | tumor
        padded = np.pad(mask, 3, mode="edge")
        mask = ndimage.binary_closing(padded, structure, iterations=2)[3:-3, 3:-3, 3:-3]
        mask = ndimage.binary_fill_holes(mask)
        if _score(mask)[1] is None:
            raise InvalidLungMask("Final lung mask failed shape checks after tumor inclusion.")
        details.update({"valid": True, "mask_method": self.method, "mask_voxels": int(mask.sum()),
                        "clinical_validation": False})
        return LungMaskResult(mask.astype(np.uint8), details)
