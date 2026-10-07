import base64
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from ..config import GRID_SIZE, VERSION
from ..logica.casos_uso import StudyUseCases, StudyNotFound, StudyRejected
from ..logica.compatibility import to_legacy_metadata


def _error(estado: int, mensaje: str, archivo: Optional[str] = None):
    return JSONResponse(status_code=estado, content={
        "estado": "Rechazado", "detalle": mensaje, "archivo_rechazado": archivo})


def crear_rutas(casos: StudyUseCases) -> APIRouter:
    rutas = APIRouter()

    @rutas.get("/salud", tags=["servicio"])
    def salud():
        """Comprueba que el servicio está en línea y qué método de reconstrucción usa."""
        return {"estado": "en línea", "version": VERSION,
                **to_legacy_metadata(casos.describe()), "volumen": [GRID_SIZE] * 3}

    @rutas.post("/reconstruir", tags=["servicio"])
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
        imagenes = {}
        for ang, f in ((0, proyeccion_0), (45, proyeccion_45), (90, proyeccion_90), (135, proyeccion_135)):
            imagenes[ang] = (f.filename, await f.read()) if f is not None and f.filename else None

        try:
            id_estudio = casos.register_study(imagenes, id_estudio, organo)
        except StudyRejected as e:
            return _error(422, e.reason, e.filename)
        casos.process_study(id_estudio)
        metadata, volumen = casos.get_result(id_estudio)
        metadatos = to_legacy_metadata(metadata)

        respuesta = {**metadatos, "descarga": f"/estudios/{id_estudio}/volumen.npy"}
        if incluir_volumen:
            respuesta["volumen"] = {"forma": list(volumen.shape), "tipo": "float32", "orden": "C",
                                    "datos_base64": base64.b64encode(volumen.tobytes()).decode("ascii")}
        return respuesta

    @rutas.get("/estudios/{id_estudio}/volumen.npy", tags=["estudios"])
    def descargar_volumen(id_estudio: str):
        """Descarga el volumen reconstruido de un estudio como archivo .npy."""
        try:
            contenido = casos.get_volume_npy(id_estudio)
        except StudyNotFound:
            raise HTTPException(404, "Estudio no encontrado")
        return Response(contenido, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{id_estudio}_volumen.npy"'})

    return rutas
