import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")                 # genera la imagen sin abrir ventanas
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos" / "TA2_entrega"
PULMON = DATOS / "processed" / "pulmon"
SALIDA = RAIZ / "evidencias"

caso = sys.argv[1] if len(sys.argv) > 1 else "lung_003"

# 1. Particiones
splits = json.loads((DATOS / "splits.json").read_text(encoding="utf-8"))
p = splits["particiones"]["pulmon"]
print("Particiones de pulmón -> train=%d | val=%d | test=%d"
      % (len(p["train"]), len(p["val"]), len(p["test"])))
print("Casos de test:", ", ".join(p["test"]))

# 2. Archivos del caso
proy = np.load(PULMON / f"{caso}_proj.npy")
bp = np.load(PULMON / f"{caso}_bp.npy")
vol = np.load(PULMON / f"{caso}_vol.npy")
for nombre, arr in (("proyecciones", proy), ("retroproyeccion", bp), ("tomografia", vol)):
    print(f"{nombre:16s} forma={arr.shape}  tipo={arr.dtype}  "
          f"min={arr.min():.3f}  max={arr.max():.3f}")

# 3. Figura de evidencia
SALIDA.mkdir(exist_ok=True)
fig, ax = plt.subplots(2, 4, figsize=(13, 6.6))
fig.suptitle(f"Caso {caso} · entrada y salida esperada del servicio", fontsize=13)
for i, ang in enumerate((0, 45, 90, 135)):
    ax[0, i].imshow(proy[i].T[::-1], cmap="gray")
    ax[0, i].set_title(f"Proyección {ang}°")
k = vol.shape[2] // 2
ax[1, 0].imshow(bp[:, :, k], cmap="gray");            ax[1, 0].set_title("Retroproyección · axial")
ax[1, 1].imshow(vol[:, :, k], cmap="gray");           ax[1, 1].set_title("Tomografía real · axial")
ax[1, 2].imshow(bp[:, k, :].T[::-1], cmap="gray");    ax[1, 2].set_title("Retroproyección · coronal")
ax[1, 3].imshow(vol[:, k, :].T[::-1], cmap="gray");   ax[1, 3].set_title("Tomografía real · coronal")
for a in ax.ravel():
    a.axis("off")
fig.tight_layout()
ruta = SALIDA / f"paso2_{caso}.png"
fig.savefig(ruta, dpi=110)
print("Figura guardada en:", ruta)