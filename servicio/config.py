"""Configuración central del servicio. Todas las rutas y constantes en un solo lugar."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Datos entregados por TA-2 (contienen ta2.py con los operadores verificados)
DIR_TA2 = RAIZ / "datos" / "TA2_entrega"
# Pesos del modelo de EN-1 (opcional). Si no existe, se usa la retroproyección.
RUTA_PESOS = RAIZ / "modelos" / "unet_pulmon.pth"
# Carpeta donde se guarda cada estudio procesado
DIR_ESTUDIOS = RAIZ / "estudios"
# Interfaz web
DIR_WEB = RAIZ / "web"

# Geometría acordada en TA-2 (no cambiar)
ANGULOS = (0, 45, 90, 135)
TAM = 64                      # cada proyección es 64 x 64 y el volumen 64^3
ESCALA_PNG = 1000.0           # PNG de 16 bits guarda valor * 1000
FORMATOS = (".png", ".npy")

VERSION = "0.1.0"

# Permite hacer "import ta2" sin copiar ni reescribir el archivo de TA-2
if str(DIR_TA2) not in sys.path:
    sys.path.insert(0, str(DIR_TA2))