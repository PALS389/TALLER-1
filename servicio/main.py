from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.rutas import crear_rutas
from .config import DIR_ALMACENAMIENTO, DIR_WEB, GRID_SIZE, VERSION
from .logica.casos_uso import StudyUseCases
from .logica.compatibility import LegacyFileStoreAdapter
from .logica.tuberia.factory import create_pipeline
from .persistencia.almacen_archivos import AlmacenArchivos

# Capa 3 -> Capa 2 -> entrada HTTP
almacen = AlmacenArchivos(DIR_ALMACENAMIENTO)
file_store = LegacyFileStoreAdapter(almacen)
casos = StudyUseCases(file_store=file_store, pipeline=create_pipeline(None, file_store))

app = FastAPI(
    title="RadVol 3D · Servicio de reconstrucción (EN-2)",
    description="Recibe 4 proyecciones radiográficas (0°, 45°, 90°, 135°) y devuelve "
                f"el volumen {GRID_SIZE}×{GRID_SIZE}×{GRID_SIZE} reconstruido con el identificador del estudio.",
    version=VERSION,
)
app.include_router(crear_rutas(casos))

# Capa 1: la interfaz web se sirve en la raíz (se monta al final para no tapar las rutas)
app.mount("/", StaticFiles(directory=DIR_WEB, html=True), name="web")
