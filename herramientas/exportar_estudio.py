import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos" / "TA2_entrega"
PULMON = DATOS / "processed" / "pulmon"
SALIDA = RAIZ / "ejemplos"

ANGULOS = (0, 45, 90, 135)
ESCALA_PNG = 1000.0   # debe coincidir con servicio/config.py


def exportar(caso: str) -> Path:
    proy = np.load(PULMON / f"{caso}_proj.npy").astype(np.float32)
    if proy.shape != (4, 64, 64):
        raise SystemExit(f"{caso}: forma inesperada {proy.shape}")
    destino = SALIDA / caso
    destino.mkdir(parents=True, exist_ok=True)
    for img, ang in zip(proy, ANGULOS):
        np.save(destino / f"{caso}_{ang:03d}.npy", img)
        entero = np.clip(np.round(img * ESCALA_PNG), 0, 65535).astype(np.uint16)
        Image.fromarray(entero).save(destino / f"{caso}_{ang:03d}.png")
    print(f"{caso}: 4 PNG + 4 NPY en {destino}")
    return destino


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "--test":
        splits = json.loads((DATOS / "splits.json").read_text(encoding="utf-8"))
        casos = splits["particiones"]["pulmon"]["test"]
    else:
        casos = sys.argv[1:]
    for c in casos:
        exportar(c)