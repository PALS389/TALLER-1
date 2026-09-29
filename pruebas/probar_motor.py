import sys
import time
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))           # para poder hacer "from servicio ..."

from servicio.lectura import leer_proyeccion, ImagenInvalida
from servicio.reconstructor import Reconstructor

PULMON = RAIZ / "datos" / "TA2_entrega" / "processed" / "pulmon"
caso = sys.argv[1] if len(sys.argv) > 1 else "lung_003"
carpeta = RAIZ / "ejemplos" / caso

# 1. Motor
motor = Reconstructor()
print(f"Motor: {motor.metodo}  ·  {motor.nota}\n")

# 2. Leer las 4 imágenes como lo hará el servicio
proys = []
for ang in (0, 45, 90, 135):
    ruta = carpeta / f"{caso}_{ang:03d}.png"
    img = leer_proyeccion(ruta.name, ruta.read_bytes())
    proys.append(img)
    print(f"  leído {ruta.name:20s} forma={img.shape}  max={img.max():.3f}")
proys = np.stack(proys)

# 3. Reconstruir
t0 = time.perf_counter()
vol = motor.reconstruir(proys)
t = time.perf_counter() - t0
print(f"\nVolumen reconstruido: forma={vol.shape}  tipo={vol.dtype}  en {t:.3f} s")

# 4. Verificaciones
bp_ta2 = np.load(PULMON / f"{caso}_bp.npy")
real = np.load(PULMON / f"{caso}_vol.npy")
dif = float(np.abs(vol - bp_ta2).max())
psnr = 10 * np.log10(1.0 / float(np.mean((vol - real) ** 2)))
print(f"  a) diferencia máxima vs {caso}_bp.npy de TA-2 : {dif:.1e}  "
      f"{'OK' if dif < 1e-3 else 'REVISAR'}")
print(f"  b) PSNR vs tomografía real                  : {psnr:.2f} dB")

# 5. Rechazo de un archivo inválido
try:
    leer_proyeccion("nota.txt", b"hola")
except ImagenInvalida as e:
    print(f"\nRechazo correcto -> {e}")