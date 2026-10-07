"""
Layer 2 - Pipeline - Stage 2: Reconstruction.

Four projections (4, 128, 128) -> volume (128, 128, 128), using EN-1 when
weights are available. Otherwise, use simple backprojection.
"""
import numpy as np
from scipy import ndimage

from ... import config  # noqa: F401  (adds the TA-2 directory to the import path)

from ...config import ANGLES, WEIGHTS_PATH, GRID_SIZE


def simple_backprojection(projections: np.ndarray) -> np.ndarray:
    """Fallback reconstruction without deep learning dependencies."""
    volume = np.zeros((GRID_SIZE, GRID_SIZE, GRID_SIZE), dtype=np.float32)
    for projection, angle in zip(projections, ANGLES):
        expanded = np.repeat(projection[:, None, :], GRID_SIZE, axis=1) / float(GRID_SIZE)
        if angle != 0:
            expanded = ndimage.rotate(
                expanded, -float(angle), axes=(0, 1), reshape=False,
                order=1, mode="constant", cval=0.0, prefilter=False,
            )
        volume += expanded
    return volume / float(len(ANGLES))


class Reconstructor:
    def __init__(self, weights_path=WEIGHTS_PATH):
        self._en1 = None
        self.model = None
        self.method = "simple_backprojection_128"
        self.note = "No EN-1 weights: returning simple backprojection at 128^3."
        if weights_path.exists():
            self._load_en1(weights_path)

    def _load_en1(self, path):
        try:
            from .en1_reconstruction import EN1Reconstructor

            self._en1 = EN1Reconstructor(path)
        except Exception as exc:
            self.note = f"Could not load EN-1 ({exc.__class__.__name__}); using simple backprojection."
            return
        self.method = self._en1.method
        self.note = self._en1.note

    def reconstruct(self, projections: np.ndarray) -> np.ndarray:
        expected = (len(ANGLES), GRID_SIZE, GRID_SIZE)
        if projections.shape != expected:
            raise ValueError(f"expected {expected}, received {projections.shape}")
        if self._en1 is not None:
            return self._en1.reconstruct(projections)
        return simple_backprojection(np.asarray(projections, dtype=np.float32))
