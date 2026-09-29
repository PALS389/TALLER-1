import sys
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
PULMON = RAIZ / "datos" / "TA2_entrega" / "processed" / "pulmon"
EJEMPLOS = RAIZ / "ejemplos"
ESCALA_PNG = 1000.0

caso = sys.argv[1] if len(sys.argv) > 1 else "lung_003"
original = np.load(PULMON / f"{caso}_proj.npy")

print(f"Verificación de {caso}: PNG exportado vs proyección original")
peor = 0.0
for i, ang in enumerate((0, 45, 90, 135)):
    img = Image.open(EJEMPLOS / caso / f"{caso}_{ang:03d}.png")
    recuperado = np.array(img).astype(np.float32) / ESCALA_PNG
    error = float(np.abs(recuperado - original[i]).max())
    peor = max(peor, error)
    print(f"  {ang:3d}°  tamaño={recuperado.shape}  modo={img.mode}  error máximo={error:.4f}")

print("RESULTADO:", "APROBADO" if peor <= 0.001 else "RECHAZADO",
      f"(error máximo {peor:.4f}, tolerancia 0.001)")