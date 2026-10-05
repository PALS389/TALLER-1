from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.rutas import crear_rutas
from .config import DIR_ALMACENAMIENTO, DIR_WEB, VERSION
from .logica.casos_uso import CasosDeUso
from .logica.tuberia.reconstruccion import Reconstructor
from .persistencia.almacen_archivos import AlmacenArchivos

# Capa 3 -> Capa 2 -> entrada HTTP
almacen = AlmacenArchivos(DIR_ALMACENAMIENTO)
casos = CasosDeUso(almacen=almacen, reconstructor=Reconstructor())

app = FastAPI(
    title="RadVol 3D · Servicio de reconstrucción (EN-2)",
    description="Recibe 4 proyecciones radiográficas (0°, 45°, 90°, 135°) y devuelve "
                "el volumen 64×64×64 reconstruido con el identificador del estudio.",
    version=VERSION,
)
app.include_router(crear_rutas(casos))

# Capa 1: la interfaz web se sirve en la raíz (se monta al final para no tapar las rutas)
app.mount("/", StaticFiles(directory=DIR_WEB, html=True), name="web")