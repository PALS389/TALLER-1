from __future__ import annotations

from typing import Any

import numpy as np
from scipy import ndimage

import torch
import torch.nn as nn
import torch.nn.functional as F

G = 128
FOV_MM = 320.0
HU_MIN = -1000.0
HU_MAX = 1000.0

EN1_ANGLES = (0.0, 45.0, 90.0, 135.0)
ROTATION_AXES = (0, 1)
INTEGRATION_AXIS = 1
DETECTOR_AXIS = 1

FILTER_EXPONENT = 0.500
FBP_CALIBRATION = (17.7935, -0.0110)
BP_CALIBRATION = (1.4131, -0.0591)


def project(volume: np.ndarray, angles=EN1_ANGLES, order: int = 1) -> np.ndarray:
    """Volume (128,128,128) -> projections (4,128,128)."""
    volume = np.asarray(volume, dtype=np.float32)
    projections = []
    for angle in angles:
        rotated = volume if angle == 0.0 else ndimage.rotate(
            volume,
            angle,
            axes=ROTATION_AXES,
            reshape=False,
            order=order,
            mode="constant",
            cval=0.0,
            prefilter=False,
        )
        projections.append(rotated.sum(axis=INTEGRATION_AXIS))
    return np.stack(projections).astype(np.float32)


def backproject(projections: np.ndarray, angles=EN1_ANGLES,
                   order: int = 1) -> np.ndarray:
    """Projections (4,128,128) -> dirty volume (128,128,128)."""
    projections = np.asarray(projections, dtype=np.float32)
    n_projections, size, _ = projections.shape
    if n_projections != len(angles):
        raise ValueError(
            f"Expected {len(angles)} projections, received {n_projections}."
        )

    accumulated = np.zeros((size, size, size), dtype=np.float32)
    for projection, angle in zip(projections, angles):
        expanded = np.repeat(
            np.expand_dims(projection, INTEGRATION_AXIS),
            size,
            axis=INTEGRATION_AXIS,
        ) / float(size)
        if angle != 0.0:
            expanded = ndimage.rotate(
                expanded,
                -angle,
                axes=ROTATION_AXES,
                reshape=False,
                order=order,
                mode="constant",
                cval=0.0,
                prefilter=False,
            )
        accumulated += expanded
    return (accumulated / n_projections).astype(np.float32)


def ramp_filter(projections: np.ndarray, axis: int = DETECTOR_AXIS,
                 exponent: float = FILTER_EXPONENT,
                 window: str = "hann", padding: int = 4,
                 mode: str = "reflect") -> np.ndarray:
    """Filtered-backprojection ramp filter used by the trained EN-1 model."""
    projections = np.asarray(projections, dtype=np.float32)
    n = projections.shape[axis]
    padded_size = int(2 ** np.ceil(np.log2(max(2, int(padding) * n))))
    width = [(0, 0)] * projections.ndim
    width[axis] = (0, padded_size - n)
    try:
        padded = np.pad(projections, width, mode=mode)
    except Exception:
        padded = np.pad(projections, width, mode="edge")

    frequencies = np.fft.rfftfreq(padded_size).astype(np.float32)
    ramp = (2.0 * frequencies) ** float(exponent)
    if window == "hann":
        ramp = ramp * (0.5 + 0.5 * np.cos(np.pi * frequencies / frequencies[-1]))
    ramp[0] = ramp[1] if exponent > 0 else 1.0

    shape = [1] * projections.ndim
    shape[axis] = ramp.size
    filtered = np.fft.irfft(
        np.fft.rfft(padded, axis=axis) * ramp.reshape(shape),
        n=padded_size,
        axis=axis,
    )
    crop = [slice(None)] * projections.ndim
    crop[axis] = slice(0, n)
    return filtered[tuple(crop)].astype(np.float32)


def apply_affine(volume: np.ndarray, calibration: tuple[float, float]) -> np.ndarray:
    """Apply y = a*x + b and clip to the model range."""
    a, b = calibration
    return np.clip(np.asarray(volume, dtype=np.float32) * a + b, 0.0, 1.0).astype(np.float32)


def block(input_channels: int, output: int, groups: int = 8) -> nn.Sequential:
    group_count = min(groups, output)
    while output % group_count:
        group_count -= 1
    return nn.Sequential(
        nn.Conv3d(input_channels, output, 3, padding=1, bias=False),
        nn.GroupNorm(group_count, output),
        nn.SiLU(inplace=True),
        nn.Conv3d(output, output, 3, padding=1, bias=False),
        nn.GroupNorm(group_count, output),
        nn.SiLU(inplace=True),
    )


class UNet3DResidual(nn.Module):
    """3D U-Net whose output is the filtered channel plus a learned residual."""

    def __init__(self, input_channels: int = 2, base: int = 16) -> None:
        super().__init__()
        c1, c2, c3, c4, c5 = base, base * 2, base * 4, base * 8, base * 16
        self.e1 = block(input_channels, c1)
        self.e2 = block(c1, c2)
        self.e3 = block(c2, c3)
        self.e4 = block(c3, c4)
        self.bottleneck = block(c4, c5)
        self.d4 = block(c5 + c4, c4)
        self.d3 = block(c4 + c3, c3)
        self.d2 = block(c3 + c2, c2)
        self.d1 = block(c2 + c1, c1)
        self.output = nn.Conv3d(c1, 1, 1)
        self.pool = nn.MaxPool3d(2)
        nn.init.zeros_(self.output.weight)
        nn.init.zeros_(self.output.bias)

    @staticmethod
    def _upsample(x, target):
        return F.interpolate(x, size=target.shape[2:], mode="trilinear", align_corners=False)

    def forward(self, x):
        s1 = self.e1(x)
        s2 = self.e2(self.pool(s1))
        s3 = self.e3(self.pool(s2))
        s4 = self.e4(self.pool(s3))
        y = self.bottleneck(self.pool(s4))
        y = self.d4(torch.cat([self._upsample(y, s4), s4], 1))
        y = self.d3(torch.cat([self._upsample(y, s3), s3], 1))
        y = self.d2(torch.cat([self._upsample(y, s2), s2], 1))
        y = self.d1(torch.cat([self._upsample(y, s1), s1], 1))
        return x[:, :1] + self.output(y)


class EN1Reconstructor:
    """EN-1 128^3 reconstructor, loaded once and reused by the use cases."""

    method = "en1_unet3d_residual_128"

    def __init__(self, weights_path, device: str | None = None) -> None:
        self.device = torch.device(
            device if device is not None else (
                "cuda" if torch.cuda.is_available() else "cpu"
            )
        )
        data = torch.load(weights_path, map_location="cpu", weights_only=False)

        if isinstance(data, dict) and data.get("mejores_pesos"):
            state, self.weights_source = data["mejores_pesos"], "mejores_pesos"
        elif isinstance(data, dict) and "pesos" in data:
            state, self.weights_source = data["pesos"], "pesos"
        elif isinstance(data, dict) and "modelo" in data:
            state, self.weights_source = data["modelo"], "modelo"
        elif isinstance(data, dict) and "state_dict" in data:
            state, self.weights_source = data["state_dict"], "state_dict"
        else:
            state, data, self.weights_source = data, {}, "plain_state_dict"

        metadata: dict[str, Any] = data if isinstance(data, dict) else {}
        self.channels = int(metadata.get("canales", 2))
        self.base = int(metadata.get("base", metadata.get("cfg", {}).get("base_canales", 16)))
        self.grid_size = int(metadata.get("rejilla", G))
        self.exponent = float(metadata.get("exponente_filtro", FILTER_EXPONENT))
        self.cal_fbp = tuple(metadata.get("calibracion_fbp", FBP_CALIBRATION))
        self.cal_bp = tuple(metadata.get("calibracion_bp", BP_CALIBRATION))
        self.epoch = metadata.get("mejor_epoca", metadata.get("epoca"))
        self.validation_psnr = metadata.get(
            "psnr_validacion",
            metadata.get("mejor_psnr", metadata.get("psnr")),
        )

        self.model = UNet3DResidual(self.channels, self.base).to(self.device)
        # The supplied checkpoint uses the original Spanish layer names.
        legacy_layers = {"cuello": "bottleneck", "salida": "output", "reducir": "pool"}
        state = {
            ".".join(legacy_layers.get(part, part) for part in key.split(".")): value
            for key, value in state.items()
        }
        self.model.load_state_dict(state, strict=True)
        self.model.eval()
        for parameter in self.model.parameters():
            parameter.requires_grad_(False)
        self.note = f"EN-1 loaded on {self.device} from {self.weights_source}."

    def describe(self) -> dict[str, Any]:
        return {
            "device": str(self.device),
            "grid_size": self.grid_size,
            "input_channels": self.channels,
            "base_channels": self.base,
            "parameters": sum(p.numel() for p in self.model.parameters()),
            "filter_exponent": self.exponent,
            "fbp_calibration": list(self.cal_fbp),
            "bp_calibration": list(self.cal_bp),
            "best_epoch": self.epoch,
            "validation_psnr": self.validation_psnr,
            "weights_source": self.weights_source,
        }

    def prepare_input(self, projections: np.ndarray):
        projections = np.asarray(projections, dtype=np.float32)
        expected_shape = (len(EN1_ANGLES), self.grid_size, self.grid_size)
        if projections.shape != expected_shape:
            raise ValueError(f"Expected {expected_shape}, received {projections.shape}.")
        if not np.isfinite(projections).all():
            raise ValueError("Projections contain NaN or infinite values.")

        fbp = apply_affine(
            backproject(ramp_filter(projections, exponent=self.exponent)),
            self.cal_fbp,
        )
        bp = apply_affine(backproject(projections), self.cal_bp)
        model_input = np.stack([fbp, bp])[None].astype(np.float32)
        return torch.from_numpy(model_input).to(self.device)

    @torch.no_grad()
    def reconstruct(self, projections: np.ndarray) -> np.ndarray:
        """Projections (4,128,128) -> volume (128,128,128) float32 in [0,1]."""
        model_input = self.prepare_input(projections)
        prediction = self.model(model_input).clamp(0.0, 1.0)
        return prediction[0, 0].float().cpu().numpy()

    def baseline(self, projections: np.ndarray) -> np.ndarray:
        projections = np.asarray(projections, dtype=np.float32)
        return apply_affine(
            backproject(ramp_filter(projections, exponent=self.exponent)),
            self.cal_fbp,
        )

    @staticmethod
    def to_hu(volume: np.ndarray) -> np.ndarray:
        volume = np.asarray(volume, dtype=np.float32)
        return volume * (HU_MAX - HU_MIN) + HU_MIN

    @staticmethod
    def from_hu(volume_hu: np.ndarray) -> np.ndarray:
        volume = np.asarray(volume_hu, dtype=np.float32)
        return np.clip((volume - HU_MIN) / (HU_MAX - HU_MIN), 0.0, 1.0)

    @staticmethod
    def spacing_mm() -> tuple[float, float, float]:
        spacing = FOV_MM / G
        return spacing, spacing, spacing
