import base64
import re
import time
import uuid
from datetime import datetime
from typing import Optional

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import ANGULOS, DIR_ALMACENAMIENTO, DIR_WEB, VERSION
from .logica.tuberia.preproceso import ImagenInvalida, leer_proyeccion
from .logica.tuberia.reconstruccion import Reconstructor
from .persistencia.almacen_archivos import AlmacenArchivos, EstudioNoEncontrado

app = FastAPI(
    title="RadVol 3D · Servicio de reconstrucción (EN-2)",
    description="Recibe 4 proyecciones radiográficas (0°, 45°, 90°, 135°) y devuelve "
                "el volumen 64×64×64 reconstruido con el identificador del estudio.",
    version=VERSION,
)
motor = Reconstructor()              # se carga una sola vez al iniciar
almacen = AlmacenArchivos(DIR_ALMACENAMIENTO)   # capa 3: único que conoce las rutas
PATRON_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def nuevo_id() -> str:
    return "EST-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def error(estado: int, mensaje: str, archivo: Optional[str] = None):
    return JSONResponse(status_code=estado, content={
        "estado": "Rechazado", "detalle": mensaje, "archivo_rechazado": archivo})


@app.get("/salud", tags=["servicio"])
def salud():
    """Comprueba que el servicio está en línea y qué método de reconstrucción usa."""
    return {"estado": "en línea", "version": VERSION, "metodo": motor.metodo,
            "nota": motor.nota, "angulos": list(ANGULOS), "volumen": [64, 64, 64]}


@app.post("/reconstruir", tags=["servicio"])
async def reconstruir(
    proyeccion_0: Optional[UploadFile] = File(None, description="Proyección a 0° (AP)"),
    proyeccion_45: Optional[UploadFile] = File(None, description="Proyección a 45°"),
    proyeccion_90: Optional[UploadFile] = File(None, description="Proyección a 90° (lateral)"),
    proyeccion_135: Optional[UploadFile] = File(None, description="Proyección a 135°"),
    id_estudio: Optional[str] = Form(None, description="Opcional. Si se omite, se genera uno."),
    organo: str = Form("pulmon"),
    incluir_volumen: bool = Form(True, description="Si es false, solo devuelve los "
                                 "metadatos (útil para probar en /docs)."),
):
    """Criterio EN-2: recibe 4 imágenes y devuelve el volumen reconstruido + id del estudio."""
    t0 = time.perf_counter()
    archivos = {0: proyeccion_0, 45: proyeccion_45, 90: proyeccion_90, 135: proyeccion_135}

    # 1. Deben llegar exactamente las 4 proyecciones
    faltan = [f"{a}°" for a, f in archivos.items() if f is None or not f.filename]
    if faltan:
        return error(422, f"Se requieren exactamente 4 proyecciones. Falta: {', '.join(faltan)}.")

    # 2. Identificador del estudio
    if id_estudio:
        id_estudio = id_estudio.strip()
        if not PATRON_ID.match(id_estudio):
            return error(422, "id_estudio solo admite letras, números, '-' y '_' (máx. 64).")
    else:
        id_estudio = nuevo_id()

    # 3. Leer y validar cada imagen
    try:
        proys = np.stack([leer_proyeccion(f.filename, await f.read())
                          for f in archivos.values()])
    except ImagenInvalida as e:
        return error(422, e.motivo, e.archivo)

    # 4. Reconstruir
    volumen = motor.reconstruir(proys)
    segundos = time.perf_counter() - t0

    # 5. Guardar el estudio (capa 3)
    almacen.guardar_proyecciones(id_estudio, proys)
    almacen.guardar_volumen(id_estudio, volumen)
    meta = {
        "id_estudio": id_estudio,
        "organo": organo,
        "estado": "Reconstrucción completada",
        "metodo": motor.metodo,
        "angulos": list(ANGULOS),
        "archivos": {f"{a}°": f.filename for a, f in archivos.items()},
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "tiempo_s": round(segundos, 3),
        "estadisticas": {"min": round(float(volumen.min()), 4),
                         "max": round(float(volumen.max()), 4),
                         "media": round(float(volumen.mean()), 4)},
        "descarga": f"/estudios/{id_estudio}/volumen.npy",
    }
    almacen.guardar_metadatos(id_estudio, meta)

    # 6. Respuesta: metadatos + volumen en base64 (float32, orden C)
    if not incluir_volumen:
        return meta
    meta["volumen"] = {"forma": list(volumen.shape), "tipo": "float32", "orden": "C",
                       "datos_base64": base64.b64encode(volumen.tobytes()).decode("ascii")}
    return meta


@app.get("/estudios/{id_estudio}/volumen.npy", tags=["estudios"])
def descargar_volumen(id_estudio: str):
    """Descarga el volumen reconstruido de un estudio como archivo .npy."""
    if not PATRON_ID.match(id_estudio):
        raise HTTPException(404, "Estudio no encontrado")
    try:
        contenido = almacen.leer_volumen_bytes(id_estudio)
    except EstudioNoEncontrado:
        raise HTTPException(404, "Estudio no encontrado")
    return Response(contenido, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{id_estudio}_volumen.npy"'})


# La interfaz web se sirve en la raíz (se monta al final para no tapar las rutas)
app.mount("/", StaticFiles(directory=DIR_WEB, html=True), name="web")