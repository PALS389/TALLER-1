import re
import time
import uuid
from datetime import datetime

import numpy as np

from ..config import ANGULOS
from ..persistencia.almacen_archivos import EstudioNoEncontrado
from .tuberia.preproceso import ImagenInvalida, leer_proyeccion

PATRON_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PENDIENTE = "Pendiente"
COMPLETADO = "Reconstrucción completada"


class EstudioRechazado(ValueError):
    """El estudio no cumple una regla del dominio. Si hay un archivo culpable, se nombra."""

    def __init__(self, motivo: str, archivo: str | None = None):
        super().__init__(motivo)
        self.motivo = motivo
        self.archivo = archivo


class EstudioInexistente(LookupError):
    """Se pidió un estudio que no existe."""


class CasosDeUso:
    def __init__(self, almacen, reconstructor):
        self._almacen = almacen              # capa 3
        self._reconstructor = reconstructor  # etapa 2 de la tubería

    def describir(self) -> dict:
        """Método de reconstrucción activo, para informar el estado del servicio."""
        return {"metodo": self._reconstructor.metodo, "nota": self._reconstructor.nota,
                "angulos": list(ANGULOS)}

    # ---------- Registrar estudio ----------
    def registrar_estudio(self, imagenes: dict, id_estudio: str | None = None,
                          organo: str = "pulmon") -> str:
        """imagenes: {ángulo: (nombre_archivo, bytes) o None}. Devuelve el id del estudio."""
        # Regla del dominio: exactamente 4 vistas en los ángulos acordados
        faltan = [f"{a}°" for a in ANGULOS if not imagenes.get(a)]
        if faltan:
            raise EstudioRechazado(
                f"Se requieren exactamente 4 proyecciones. Falta: {', '.join(faltan)}.")

        if id_estudio:
            id_estudio = id_estudio.strip()
            if not PATRON_ID.match(id_estudio):
                raise EstudioRechazado("id_estudio solo admite letras, números, '-' y '_' (máx. 64).")
        else:
            id_estudio = "EST-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]

        # Etapa 1 · Preproceso: cada imagen se valida y se convierte a 64x64
        try:
            proyecciones = np.stack([leer_proyeccion(*imagenes[a]) for a in ANGULOS])
        except ImagenInvalida as e:
            raise EstudioRechazado(e.motivo, e.archivo)

        self._almacen.guardar_proyecciones(id_estudio, proyecciones)
        self._almacen.guardar_metadatos(id_estudio, {
            "id_estudio": id_estudio,
            "organo": organo,
            "estado": PENDIENTE,
            "angulos": list(ANGULOS),
            "archivos": {f"{a}°": imagenes[a][0] for a in ANGULOS},
            "fecha": datetime.now().isoformat(timespec="seconds"),
        })
        return id_estudio

    # ---------- Procesar estudio ----------
    def procesar_estudio(self, id_estudio: str) -> None:
        t0 = time.perf_counter()
        metadatos = self._leer(self._almacen.leer_metadatos, id_estudio)
        proyecciones = self._leer(self._almacen.leer_proyecciones, id_estudio)

        volumen = self._reconstructor.reconstruir(proyecciones)     # etapa 2
        self._almacen.guardar_volumen(id_estudio, volumen)

        metadatos.update({
            "estado": COMPLETADO,
            "metodo": self._reconstructor.metodo,
            "tiempo_s": round(time.perf_counter() - t0, 3),
            "estadisticas": {"min": round(float(volumen.min()), 4),
                             "max": round(float(volumen.max()), 4),
                             "media": round(float(volumen.mean()), 4)},
        })
        self._almacen.guardar_metadatos(id_estudio, metadatos)

    # ---------- Consultar resultado ----------
    def consultar_resultado(self, id_estudio: str) -> tuple[dict, np.ndarray]:
        metadatos = self._leer(self._almacen.leer_metadatos, id_estudio)
        volumen = self._leer(self._almacen.leer_volumen, id_estudio)
        return metadatos, volumen

    def obtener_volumen_npy(self, id_estudio: str) -> bytes:
        return self._leer(self._almacen.leer_volumen_bytes, id_estudio)

    # ---------- auxiliar ----------
    @staticmethod
    def _leer(operacion, id_estudio):
        if not PATRON_ID.match(id_estudio or ""):
            raise EstudioInexistente(id_estudio)
        try:
            return operacion(id_estudio)
        except EstudioNoEncontrado:
            raise EstudioInexistente(id_estudio)