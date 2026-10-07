"""Inference for the EN-4 lung tumor segmenter supplied with EN_04.ipynb."""
from __future__ import annotations

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from ...config import SEGMENTATION_WEIGHTS_PATH
from .confidence import summarize_probabilities
from .en1_reconstruction import block
from .orchestrator import SegmentationResult


class UNet3DTumorSegmenter(nn.Module):
    """EN-4 architecture: one input channel and a sigmoid probability output."""

    def __init__(self, base_channels: int = 16) -> None:
        super().__init__()
        c1, c2, c3, c4, c5 = (base_channels * factor for factor in (1, 2, 4, 8, 16))
        self.e1 = block(1, c1)
        self.e2 = block(c1, c2)
        self.e3 = block(c2, c3)
        self.e4 = block(c3, c4)
        self.bottleneck = block(c4, c5)
        self.d4 = block(c5 + c4, c4)
        self.d3 = block(c4 + c3, c3)
        self.d2 = block(c3 + c2, c2)
        self.d1 = block(c2 + c1, c1)
        self.output = nn.Sequential(nn.Conv3d(c1, 1, 1), nn.Sigmoid())
        self.pool = nn.MaxPool3d(2)

    @staticmethod
    def _upsample(value: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return F.interpolate(value, size=target.shape[2:], mode="trilinear", align_corners=False)

    def forward(self, volume: torch.Tensor) -> torch.Tensor:
        s1 = self.e1(volume)
        s2 = self.e2(self.pool(s1))
        s3 = self.e3(self.pool(s2))
        s4 = self.e4(self.pool(s3))
        value = self.bottleneck(self.pool(s4))
        value = self.d4(torch.cat([self._upsample(value, s4), s4], dim=1))
        value = self.d3(torch.cat([self._upsample(value, s3), s3], dim=1))
        value = self.d2(torch.cat([self._upsample(value, s2), s2], dim=1))
        value = self.d1(torch.cat([self._upsample(value, s1), s1], dim=1))
        return self.output(value)


class EN4LungSegmenter:
    """Load EN-4 once, then infer tumor masks and regional probability summaries."""

    method = "en4_lung_unet3d"

    def __init__(
        self,
        weights_path: str = str(SEGMENTATION_WEIGHTS_PATH),
        *,
        device: str | None = None,
        threshold: float = 0.5,
        voxel_spacing_mm: tuple[float, float, float] = (2.5, 2.5, 2.5),
    ) -> None:
        if not np.isfinite(threshold) or not 0 < threshold < 1:
            raise ValueError("Confidence threshold must be between 0 and 1, exclusively.")
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.threshold = threshold
        self.voxel_spacing_mm = voxel_spacing_mm
        state = torch.load(weights_path, map_location="cpu", weights_only=True)
        if not isinstance(state, dict) or not state:
            raise ValueError("EN-4 weights must be a non-empty state dictionary.")
        # Keep compatibility with the supplied notebook's checkpoint vocabulary.
        legacy_layers = {"cuello": "bottleneck", "salida": "output", "reducir": "pool"}
        state = {
            ".".join(legacy_layers.get(part, part) for part in key.split(".")): value
            for key, value in state.items()
        }
        self.model = UNet3DTumorSegmenter()
        self.model.load_state_dict(state, strict=True)
        self.model.to(self.device).eval()
        self.model.requires_grad_(False)

    def segment(self, volume: np.ndarray) -> SegmentationResult:
        """Preserve the notebook's input values without per-study rescaling."""
        array = np.asarray(volume, dtype=np.float32)
        if array.shape != (128, 128, 128) or not np.isfinite(array).all():
            raise ValueError("EN-4 requires a finite volume of shape (128, 128, 128).")
        tensor = torch.from_numpy(np.ascontiguousarray(array))[None, None].to(self.device)
        with torch.inference_mode():
            probabilities = self.model(tensor)[0, 0].cpu().numpy()
        return summarize_probabilities(
            probabilities, threshold=self.threshold, voxel_spacing_mm=self.voxel_spacing_mm,
        )
