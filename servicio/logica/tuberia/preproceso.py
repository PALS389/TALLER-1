"""
Capa 2 · Tubería · Etapa 1: Preproceso.

Convierte cada radiografía tal como se subió (bytes de un .png o .npy) en una
matriz 64x64 float32 y rechaza la que no sea válida, identificando el archivo.
"""
import io

import numpy as np
from PIL import Image

from ...config import ESCALA_PNG, FORMATOS, TAM


class ImagenInvalida(ValueError):
    """Error con el nombre del archivo rechazado, para mostrarlo al médico."""

    def __init__(self, archivo: str, motivo: str):
        super().__init__(f"{archivo}: {motivo}")
        self.archivo = archivo
        self.motivo = motivo


def leer_proyeccion(nombre: str, contenido: bytes) -> np.ndarray:
    """Convierte los bytes de un archivo .png o .npy en una matriz 64x64 float32."""
    ext = ("." + nombre.rsplit(".", 1)[-1].lower()) if "." in nombre else ""
    if ext not in FORMATOS:
        raise ImagenInvalida(nombre, f"formato '{ext or 'sin extensión'}' no admitido "
                                     f"(se aceptan {', '.join(FORMATOS)})")
    try:
        if ext == ".npy":
            arr = np.load(io.BytesIO(contenido), allow_pickle=False)
        else:
            img = Image.open(io.BytesIO(contenido))
            if img.mode not in ("I;16", "I;16B", "I", "L"):
                img = img.convert("L")
            arr = np.array(img)
            # PNG de 16 bits: se recupera el valor original dividiendo entre la escala
            arr = arr.astype(np.float32) / (ESCALA_PNG if arr.dtype != np.uint8 else 1.0)
    except Exception as exc:  # archivo dañado o que no es imagen
        raise ImagenInvalida(nombre, f"no se pudo leer ({exc.__class__.__name__})")

    arr = np.asarray(arr, dtype=np.float32)
    if arr.shape != (TAM, TAM):
        raise ImagenInvalida(nombre, f"tamaño {arr.shape}, se esperaba ({TAM}, {TAM})")
    if not np.isfinite(arr).all():
        raise ImagenInvalida(nombre, "contiene valores no numéricos")
    return arr