"""Configuración central del servicio. Todas las rutas y constantes en un solo lugar."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Datos entregados por TA-2 (contienen ta2.py con los operadores verificados)
DIR_TA2 = RAIZ / "datos" / "TA2_entrega"
# Optional EN-1 weights. Missing weights trigger simple backprojection.
WEIGHTS_PATH = RAIZ / "modelos" / "en1_pesos_liviano.pth"
SEGMENTATION_WEIGHTS_PATH = RAIZ / "modelos" / "en4_segmentador_pulmon.pth"
RUTA_PESOS = WEIGHTS_PATH
# Capa 4 · sistema de archivos: aquí guarda la capa 3 cada estudio procesado
DIR_ALMACENAMIENTO = RAIZ / "almacenamiento" / "estudios"
# Interfaz web
DIR_WEB = RAIZ / "web"

# Geometría acordada en TA-2 (no cambiar)
ANGLES = (0, 45, 90, 135)
GRID_SIZE = 128                # Each projection is 128 x 128; volumes are 128^3.
# Preserve the configuration names used by the existing persistence layer.
ANGULOS = ANGLES
TAM = GRID_SIZE
ESCALA_PNG = 1000.0           # PNG de 16 bits guarda valor * 1000
FORMATOS = (".png", ".npy")

VERSION = "0.1.0"

# Permite hacer "import ta2" sin copiar ni reescribir el archivo de TA-2
if str(DIR_TA2) not in sys.path:
    sys.path.insert(0, str(DIR_TA2))
