"""
Layer 2 - Pipeline - Stage 1: Preprocessing.

Convert an uploaded PNG or NPY radiograph into a float32 projection and
identify invalid files in validation errors.
"""
import io

import numpy as np
from PIL import Image

from ...config import ESCALA_PNG as PNG_SCALE, FORMATOS as SUPPORTED_FORMATS, GRID_SIZE


class InvalidImage(ValueError):
    """Validation error identifying the rejected file."""

    def __init__(self, filename: str, reason: str):
        super().__init__(f"{filename}: {reason}")
        self.filename = filename
        self.reason = reason


def read_projection(filename: str, content: bytes) -> np.ndarray:
    """Convert PNG or NPY bytes into a float32 projection of the configured size."""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in SUPPORTED_FORMATS:
        raise InvalidImage(filename, f"unsupported format '{ext or 'no extension'}' "
                                    f"(accepted: {', '.join(SUPPORTED_FORMATS)})")
    try:
        if ext == ".npy":
            arr = np.load(io.BytesIO(content), allow_pickle=False)
        else:
            img = Image.open(io.BytesIO(content))
            if img.mode not in ("I;16", "I;16B", "I", "L"):
                img = img.convert("L")
            arr = np.array(img)
            # Recover original values from scaled 16-bit PNGs.
            arr = arr.astype(np.float32) / (PNG_SCALE if arr.dtype != np.uint8 else 1.0)
    except Exception as exc:
        raise InvalidImage(filename, f"could not read image ({exc.__class__.__name__})")

    arr = np.asarray(arr, dtype=np.float32)
    if arr.shape != (GRID_SIZE, GRID_SIZE):
        raise InvalidImage(filename, f"shape {arr.shape}; expected ({GRID_SIZE}, {GRID_SIZE})")
    if not np.isfinite(arr).all():
        raise InvalidImage(filename, "contains non-finite values")
    return arr


class ProjectionPreprocessor:
    """Prepare decoded projections without changing EN-1's calibrated scale."""

    method = "validated_float32_projections"

    def execute(self, projections: np.ndarray) -> np.ndarray:
        expected_shape = (4, GRID_SIZE, GRID_SIZE)
        if np.iscomplexobj(projections):
            raise ValueError("Projections must contain real values.")
        array = np.array(projections, dtype=np.float32, order="C", copy=True)
        if array.shape != expected_shape:
            raise ValueError(f"Expected projections {expected_shape}, received {array.shape}.")
        if not np.isfinite(array).all():
            raise ValueError("Projections must contain finite values.")
        return array
