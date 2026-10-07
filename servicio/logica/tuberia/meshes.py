from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import ndimage

from .orchestrator import MeshResult

VOXEL_MM = 2.5
MAX_TRIANGLES = 25_000
ORGAN_COLOR = (200, 200, 210, 160)
TUMOR_COLOR = (220, 64, 80, 255)


class MissingMeshDependency(RuntimeError):
    """A mesh dependency is not installed in the runtime."""


class InvalidMesh(ValueError):
    """A mask could not produce a valid surface."""


@dataclass(frozen=True)
class GeneratedMesh:
    vertices: np.ndarray
    faces: np.ndarray
    metrics: dict[str, Any]


def _marching_cubes(smoothed: np.ndarray, level: float, voxel_mm: float, step: int):
    try:
        from skimage import measure
    except ImportError as exc:
        raise MissingMeshDependency(
            "Install scikit-image to generate surfaces with marching cubes."
        ) from exc

    try:
        vertices, faces, _, _ = measure.marching_cubes(
            smoothed,
            level=level,
            spacing=(voxel_mm, voxel_mm, voxel_mm),
            step_size=step,
        )
    except (ValueError, RuntimeError):
        return None, None
    return vertices, faces


def mesh_volume_mm3(vertices: np.ndarray, faces: np.ndarray) -> float:
    """Volume enclosed by a triangular mesh, in cubic millimetres."""
    vertices64 = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    a = vertices64[faces[:, 0]]
    b = vertices64[faces[:, 1]]
    c = vertices64[faces[:, 2]]
    return float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)


def taubin_smoothing(vertices: np.ndarray, faces: np.ndarray, iterations: int = 10,
                     lam: float = 0.50, mu: float = -0.53) -> np.ndarray:
    """Smooth without the systematic shrinkage of ordinary Laplacian smoothing."""
    vertices64 = np.asarray(vertices, dtype=np.float64).copy()
    faces = np.asarray(faces, dtype=np.int64)
    n_vertices = vertices64.shape[0]

    edges = np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = np.vstack([edges, edges[:, ::-1]])
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges = edges[order]
    unique = np.ones(len(edges), dtype=bool)
    unique[1:] = (edges[1:] != edges[:-1]).any(axis=1)
    edges = edges[unique]

    start = edges[:, 0]
    end = edges[:, 1]
    degree = np.bincount(start, minlength=n_vertices).astype(np.float64)
    degree[degree == 0] = 1.0

    for step in range(iterations):
        factor = lam if step % 2 == 0 else mu
        neighbour_sum = np.zeros_like(vertices64)
        np.add.at(neighbour_sum, start, vertices64[end])
        vertices64 = vertices64 + factor * (neighbour_sum / degree[:, None] - vertices64)
    return vertices64


def adaptive_sigma(voxel_count: int) -> float:
    """Scale Gaussian smoothing to object size so small tumors keep their volume."""
    radius = (3.0 * max(float(voxel_count), 1.0) / (4.0 * np.pi)) ** (1.0 / 3.0)
    return float(np.clip(radius / 20.0, 0.20, 1.20))


def _decimate_by_clustering(vertices: np.ndarray, faces: np.ndarray,
                             target: int) -> tuple[np.ndarray, np.ndarray]:
    vertices64 = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    ratio = max(1.0, len(faces) / float(target))
    step = (vertices64.max(0) - vertices64.min(0)).max()
    step /= max(8.0, (len(vertices64) / ratio) ** (1 / 3) * 2.0)
    key = np.floor((vertices64 - vertices64.min(0)) / step).astype(np.int64)
    _, inverse = np.unique(key, axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)

    new_vertices = np.zeros((inverse.max() + 1, 3))
    counts = np.bincount(inverse, minlength=new_vertices.shape[0]).astype(np.float64)
    np.add.at(new_vertices, inverse, vertices64)
    new_vertices /= counts[:, None]

    new_faces = inverse[faces]
    valid = ((new_faces[:, 0] != new_faces[:, 1])
             & (new_faces[:, 1] != new_faces[:, 2])
             & (new_faces[:, 0] != new_faces[:, 2]))
    return new_vertices, new_faces[valid]


def mesh_from_mask(mask: np.ndarray, *, voxel_mm: float = VOXEL_MM,
                        max_triangles: int = MAX_TRIANGLES,
                        sigma: float | None = None,
                        smoothing_iterations: int = 10,
                        tolerance_pct: float = 1.0,
                        error_max_pct: float = 3.0) -> GeneratedMesh:
    """Build a volume-preserving mesh from a binary volumetric mask."""
    mask = np.asarray(mask) > 0
    n_voxels = int(mask.sum())
    current_sigma = sigma if sigma is not None else (
        adaptive_sigma(n_voxels) if n_voxels >= 8 else 0.2
    )

    best: GeneratedMesh | None = None
    for _ in range(4):
        mesh = _build_mesh_once(
            mask,
            voxel_mm=voxel_mm,
            max_triangles=max_triangles,
            sigma=current_sigma,
            smoothing_iterations=smoothing_iterations,
            tolerance_pct=tolerance_pct,
        )
        if best is None or mesh.metrics["volume_error_pct"] < best.metrics["volume_error_pct"]:
            best = mesh
        if (mesh.metrics["volume_error_pct"] <= error_max_pct
                or mesh.metrics["triangles"] > max_triangles):
            break
        current_sigma = max(0.2, current_sigma * 0.6)

    if best is None:
        raise InvalidMesh("Could not generate the mesh.")
    return best


def _build_mesh_once(mask: np.ndarray, *, voxel_mm: float, max_triangles: int,
                   sigma: float, smoothing_iterations: int,
                   tolerance_pct: float) -> GeneratedMesh:
    n_voxels = int(mask.sum())
    if n_voxels < 8:
        raise InvalidMesh("The mask is empty or too small.")

    indices = np.argwhere(mask)
    lo = np.maximum(indices.min(0) - 3, 0)
    hi = np.minimum(indices.max(0) + 4, mask.shape)
    cropped = mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]].astype(np.float32)
    cropped = np.pad(cropped, 1, mode="constant", constant_values=0)
    smooth = ndimage.gaussian_filter(cropped, sigma=sigma)
    offset = (lo - 1).astype(np.float64) * voxel_mm
    mask_volume = n_voxels * voxel_mm ** 3

    step_used = 1
    for step in (1, 2, 3, 4):
        vertices, faces = _marching_cubes(smooth, 0.5, voxel_mm, step)
        if vertices is None:
            continue
        step_used = step
        if len(faces) <= max_triangles:
            break
    else:
        raise InvalidMesh("Marching cubes found no surface.")

    def build(level: float):
        vertices2, faces2 = _marching_cubes(smooth, level, voxel_mm, step_used)
        if vertices2 is None:
            return None, None, 0.0
        if smoothing_iterations:
            vertices2 = taubin_smoothing(vertices2, faces2, smoothing_iterations)
        return vertices2, faces2, mesh_volume_mm3(vertices2, faces2)

    def error(mesh_volume: float) -> float:
        return 100.0 * (mesh_volume - mask_volume) / mask_volume

    vertices, faces, mesh_volume = build(0.5)
    best = (abs(error(mesh_volume)) if vertices is not None else 1e9,
            0.5, vertices, faces, mesh_volume)

    if vertices is None or abs(error(mesh_volume)) > tolerance_pct:
        low = 0.10
        high = 0.90
        for _ in range(16):
            level = 0.5 * (low + high)
            vertices2, faces2, volume2 = build(level)
            if vertices2 is None:
                high = level
                continue
            err = error(volume2)
            if abs(err) < best[0]:
                best = (abs(err), level, vertices2, faces2, volume2)
            if abs(err) <= tolerance_pct / 2.0:
                break
            if err > 0:
                low = level
            else:
                high = level

    _, level, vertices, faces, mesh_volume = best
    if vertices is None or faces is None:
        raise InvalidMesh("Marching cubes found no surface.")

    raw_triangles = int(len(faces))
    decimated = False
    if len(faces) > max_triangles:
        vertices, faces = _decimate_by_clustering(vertices, faces, max_triangles)
        decimated = True
        mesh_volume = mesh_volume_mm3(vertices, faces)

    a = vertices[faces[:, 0]]
    b = vertices[faces[:, 1]]
    c = vertices[faces[:, 2]]
    if np.einsum("ij,ij->i", a, np.cross(b, c)).sum() < 0:
        faces = faces[:, ::-1].copy()

    vertices = vertices + offset
    metrics = {
        "mask_voxels": n_voxels,
        "sigma": round(float(sigma), 3),
        "iso_level": round(float(level), 3),
        "marching_cubes_step": step_used,
        "raw_triangles": raw_triangles,
        "triangles": int(len(faces)),
        "vertices": int(len(vertices)),
        "cluster_decimated": decimated,
        "mask_volume_cm3": round(mask_volume / 1000.0, 3),
        "mesh_volume_cm3": round(mesh_volume / 1000.0, 3),
        "volume_error_pct": round(
            100.0 * abs(mesh_volume - mask_volume) / max(mask_volume, 1e-9), 2
        ),
    }
    return GeneratedMesh(vertices=vertices, faces=faces, metrics=metrics)


def export_glb_bytes(mesh: GeneratedMesh, color_rgba: tuple[int, int, int, int]) -> bytes:
    """Export a mesh to GLB bytes without using filesystem paths."""
    try:
        import trimesh
    except ImportError as exc:
        raise MissingMeshDependency(
            "Install trimesh to export meshes in GLB format."
        ) from exc

    mesh = trimesh.Trimesh(
        vertices=np.asarray(mesh.vertices, dtype=np.float32),
        faces=np.asarray(mesh.faces, dtype=np.int64),
        process=False,
    )
    _ = mesh.vertex_normals
    mesh.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=[channel / 255.0 for channel in color_rgba],
            metallicFactor=0.0,
            roughnessFactor=0.85,
            alphaMode="BLEND" if color_rgba[3] < 255 else "OPAQUE",
        )
    )
    exported = mesh.export(file_type="glb")
    return bytes(exported)


def export_empty_glb_bytes() -> bytes:
    """Represent a study with no predicted tumor using an empty GLB scene."""
    try:
        import trimesh
    except ImportError as exc:
        raise MissingMeshDependency("Install trimesh to export meshes in GLB format.") from exc
    return bytes(trimesh.exchange.gltf.export_glb(trimesh.Scene()))


class EN42MeshGenerator:
    """Generate organ and tumor GLB meshes from the reconstructed volume."""

    method = "marching_cubes_glb_en42"

    def __init__(self, *, voxel_mm: float = VOXEL_MM,
                 max_triangles: int = MAX_TRIANGLES,
                 organ_threshold: float = 0.05) -> None:
        self._voxel_mm = voxel_mm
        self._max_triangles = max_triangles
        self._organ_threshold = organ_threshold
        self.last_metrics: dict[str, dict[str, Any]] = {}

    def generate(self, volume: np.ndarray, tumor_mask: np.ndarray) -> MeshResult:
        tumor = np.asarray(tumor_mask) > 0
        organ = self._organ_mask(volume, tumor)

        organ_mesh = mesh_from_mask(
            organ,
            voxel_mm=self._voxel_mm,
            max_triangles=self._max_triangles,
            error_max_pct=5.0,
        )
        if tumor.any():
            tumor_mesh = mesh_from_mask(
                tumor,
                voxel_mm=self._voxel_mm,
                max_triangles=self._max_triangles,
                error_max_pct=5.0,
            )
            tumor_metrics = tumor_mesh.metrics
            tumor_glb = export_glb_bytes(tumor_mesh, TUMOR_COLOR)
        else:
            tumor_metrics = {"has_lesion": False, "mask_voxels": 0, "triangles": 0}
            tumor_glb = export_empty_glb_bytes()
        self.last_metrics = {
            "organ": organ_mesh.metrics,
            "tumor": tumor_metrics,
        }
        return MeshResult(
            organ_glb=export_glb_bytes(organ_mesh, ORGAN_COLOR),
            tumor_glb=tumor_glb,
        )

    def _organ_mask(self, volume: np.ndarray, tumor: np.ndarray) -> np.ndarray:
        volume = np.asarray(volume, dtype=np.float32)
        organ = volume > self._organ_threshold
        organ = ndimage.binary_closing(organ, iterations=2)
        organ = ndimage.binary_fill_holes(organ)
        return np.logical_or(organ, tumor).astype(np.uint8)
