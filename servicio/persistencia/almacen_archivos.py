"""
Capa 3 · Persistencia · Almacén de archivos.

Guarda y recupera los archivos de un estudio (proyecciones, volumen y metadatos)
a partir de su identificador. Es el ÚNICO módulo que conoce cómo se organizan en
disco (capa 4 · sistema de archivos). El resto del sistema pide "el volumen del
estudio X" y recibe un arreglo, sin saber de dónde salió.

Si mañana los metadatos pasan a PostgreSQL o los archivos a otro lugar, solo
cambia esta capa.
"""
import json
from pathlib import Path

import numpy as np


class EstudioNoEncontrado(LookupError):
    """No existe el archivo pedido para ese estudio."""


class AlmacenArchivos:
    def __init__(self, raiz):
        self._raiz = Path(raiz).resolve()
        self._raiz.mkdir(parents=True, exist_ok=True)

    # ---------- organización interna (nadie más la conoce) ----------
    def _carpeta(self, id_estudio: str) -> Path:
        carpeta = (self._raiz / id_estudio).resolve()
        if carpeta.parent != self._raiz:            # evita salir de la raíz (p. ej. "../")
            raise EstudioNoEncontrado(id_estudio)
        return carpeta

    def _archivo(self, id_estudio: str, nombre: str, crear=False) -> Path:
        carpeta = self._carpeta(id_estudio)
        if crear:
            carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta / nombre

    def _leer(self, id_estudio: str, nombre: str) -> Path:
        ruta = self._archivo(id_estudio, nombre)
        if not ruta.exists():
            raise EstudioNoEncontrado(f"{id_estudio}/{nombre}")
        return ruta

    # ---------- proyecciones ----------
    def guardar_proyecciones(self, id_estudio: str, proyecciones: np.ndarray) -> None:
        np.save(self._archivo(id_estudio, "proyecciones.npy", crear=True), proyecciones)

    def leer_proyecciones(self, id_estudio: str) -> np.ndarray:
        return np.load(self._leer(id_estudio, "proyecciones.npy"))

    # ---------- volumen ----------
    def guardar_volumen(self, id_estudio: str, volumen: np.ndarray) -> None:
        np.save(self._archivo(id_estudio, "volumen.npy", crear=True), volumen)

    def leer_volumen(self, id_estudio: str) -> np.ndarray:
        return np.load(self._leer(id_estudio, "volumen.npy"))

    def leer_volumen_bytes(self, id_estudio: str) -> bytes:
        """El volumen como archivo .npy completo, listo para descargar."""
        return self._leer(id_estudio, "volumen.npy").read_bytes()

    # ---------- metadatos ----------
    def guardar_metadatos(self, id_estudio: str, metadatos: dict) -> None:
        self._archivo(id_estudio, "metadatos.json", crear=True).write_text(
            json.dumps(metadatos, indent=2, ensure_ascii=False), encoding="utf-8")

    def leer_metadatos(self, id_estudio: str) -> dict:
        return json.loads(self._leer(id_estudio, "metadatos.json").read_text(encoding="utf-8"))