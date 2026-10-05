"""
Capa 2 · Tubería · Etapa 2: Reconstrucción.

4 proyecciones (4, 64, 64) -> volumen (64, 64, 64).
"""
import numpy as np

from ... import config  # noqa: F401  (agrega la carpeta de TA-2 al path)
import ta2

from ...config import ANGULOS, RUTA_PESOS


class Reconstructor:
    def __init__(self, ruta_pesos=RUTA_PESOS):
        self.modelo = None
        self.torch = None
        self.metodo = "retroproyeccion_simple"
        self.nota = "Sin pesos de EN-1: se devuelve la retroproyección de TA-2."
        if ruta_pesos.exists():
            self._cargar_unet(ruta_pesos)

    def _cargar_unet(self, ruta):
        try:
            import torch
            from monai.networks.nets import UNet
        except ImportError:
            self.nota = "Hay pesos, pero falta instalar torch y monai."
            return
        # Misma arquitectura que EN-1 (notebook EN1_BASE)
        modelo = UNet(spatial_dims=3, in_channels=1, out_channels=1,
                      channels=(16, 32, 64, 128), strides=(2, 2, 2), num_res_units=2)
        try:
            modelo.load_state_dict(torch.load(ruta, map_location="cpu"))
        except Exception as exc:
            self.nota = f"No se pudieron cargar los pesos ({exc.__class__.__name__})."
            return
        modelo.eval()
        self.modelo, self.torch = modelo, torch
        self.metodo = "unet_refinamiento"
        self.nota = f"U-Net de EN-1 cargada desde {ruta.name}."

    def reconstruir(self, proyecciones: np.ndarray) -> np.ndarray:
        if proyecciones.shape != (len(ANGULOS), 64, 64):
            raise ValueError(f"se esperaban (4, 64, 64) y llegó {proyecciones.shape}")
        bp = ta2.retroproyectar(proyecciones, angulos=tuple(float(a) for a in ANGULOS))
        if self.modelo is None:
            return bp
        with self.torch.no_grad():
            x = self.torch.from_numpy(bp)[None, None]          # (1, 1, 64, 64, 64)
            y = self.modelo(x)[0, 0].numpy()
        return np.clip(y, 0.0, 1.0).astype(np.float32)