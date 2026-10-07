"""
Capa 3 · Persistencia · Almacén de archivos.

Guarda y recupera los archivos de un estudio (proyecciones, volumen y
metadatos) a partir de su identificador. Es el ÚNICO módulo que conoce cómo se
organizan: los metadatos en PostgreSQL y los binarios en el almacén de objetos
(capa 4). El resto del sistema pide "el volumen del estudio X" y recibe un
arreglo, sin saber de dónde salió.

Esta clase es un adaptador. Conserva los nombres en español que la capa 2 ya
importa, y delega el trabajo real en los módulos en inglés de esta misma capa:
`storage` para los binarios y `study_metadata` para las tablas. Así la capa de
lógica no necesita ni una línea de cambio.

---- English note for the rest of the layer ----

Public names are kept in Spanish on purpose: `servicio/main.py` builds this
class and `servicio/logica/casos_uso.py` imports `EstudioNoEncontrado` and
calls these eight methods. Renaming any of them would break the business
layer. Everything this adapter delegates to is written in English.

Run a self-check with:

    python -m servicio.persistencia.almacen_archivos
"""
from __future__ import annotations

import numpy as np

from ..config import ANGULOS
from . import layout
from .storage import FileNotFoundInStorage, ObjectStorage
from .study_metadata import MetadataStore, StudyMetadataNotFound


class EstudioNoEncontrado(LookupError):
    """No existe el archivo pedido para ese estudio."""


class AlmacenArchivos:
    def __init__(self, raiz=None):
        """`raiz` se acepta por compatibilidad con `servicio/main.py`.

        La ubicación real de los datos ya no es una carpeta del disco: viene de
        las variables de entorno que lee `settings.py`. El parámetro se
        conserva para que el ensamblado del servicio siga funcionando sin
        cambios; su valor se ignora.
        """
        self._raiz = raiz
        self._almacen = ObjectStorage()
        self._metadatos = MetadataStore()

    # ---------- proyecciones ----------
    def guardar_proyecciones(self, id_estudio: str, proyecciones: np.ndarray) -> None:
        """Guarda una imagen por ángulo, en el orden acordado en TA-2.

        La capa 2 entrega las cuatro vistas apiladas en un solo arreglo. El
        modelo de datos registra una fila por ángulo, así que aquí se separan.
        """
        if len(proyecciones) != len(ANGULOS):
            raise ValueError(
                f"Se esperaban {len(ANGULOS)} proyecciones y llegaron "
                f"{len(proyecciones)}."
            )
        with self._traducir_errores(id_estudio):
            for angulo, imagen in zip(ANGULOS, proyecciones):
                self._almacen.save_array(
                    layout.projection_path(id_estudio, angulo), imagen)

    def leer_proyecciones(self, id_estudio: str) -> np.ndarray:
        """Las cuatro proyecciones apiladas, en el mismo orden en que se guardaron."""
        with self._traducir_errores(id_estudio):
            imagenes = [self._almacen.read_array(
                layout.projection_path(id_estudio, angulo)) for angulo in ANGULOS]
        return np.stack(imagenes)

    # ---------- volumen ----------
    def guardar_volumen(self, id_estudio: str, volumen: np.ndarray) -> None:
        with self._traducir_errores(id_estudio):
            self._almacen.save_array(layout.volume_path(id_estudio), volumen)

    def leer_volumen(self, id_estudio: str) -> np.ndarray:
        with self._traducir_errores(id_estudio):
            return self._almacen.read_array(layout.volume_path(id_estudio))

    def leer_volumen_bytes(self, id_estudio: str) -> bytes:
        """El volumen como archivo .npy completo, listo para descargar."""
        with self._traducir_errores(id_estudio):
            return self._almacen.read_bytes(layout.volume_path(id_estudio))

    # ---------- metadatos ----------
    def guardar_metadatos(self, id_estudio: str, metadatos: dict) -> None:
        with self._traducir_errores(id_estudio):
            self._metadatos.save(id_estudio, metadatos)

    def leer_metadatos(self, id_estudio: str) -> dict:
        with self._traducir_errores(id_estudio):
            return self._metadatos.read(id_estudio)

    # ---------- traducción de errores ----------
    @staticmethod
    def _traducir_errores(id_estudio: str):
        """Convierte los errores de los módulos internos en `EstudioNoEncontrado`.

        La capa 2 solo conoce esa excepción, y la traduce a su vez en
        `EstudioInexistente`. Un identificador con una forma inválida se trata
        igual que uno inexistente, como hacía el almacén en disco.
        """
        from contextlib import contextmanager

        @contextmanager
        def traductor():
            try:
                yield
            except (FileNotFoundInStorage, StudyMetadataNotFound,
                    layout.InvalidStudyId) as error:
                raise EstudioNoEncontrado(id_estudio) from error

        return traductor()


def _autoprueba() -> int:
    """Repite lo que hace la capa 2 y comprueba que los metadatos vuelven iguales."""
    from .repositories.study_repository import StudyRepository

    print("=" * 62)
    print("AUTOPRUEBA DEL ALMACÉN DE ARCHIVOS")
    print("=" * 62)

    almacen = AlmacenArchivos("carpeta-que-ya-no-se-usa")
    fallos: list[str] = []
    id_estudio = "AUTOPRUEBA-ALMACEN"

    # Limpieza previa, por si quedó algo de una ejecución anterior.
    StudyRepository().delete(id_estudio)

    # --- 1. Lo que hace casos_uso.registrar_estudio ---
    proyecciones = np.stack([np.full((64, 64), float(a), dtype=np.float32)
                             for a in ANGULOS])
    almacen.guardar_proyecciones(id_estudio, proyecciones)

    al_registrar = {
        "id_estudio": id_estudio,
        "organo": "pulmon",
        "estado": "Pendiente",
        "angulos": list(ANGULOS),
        "archivos": {f"{a}°": f"vista_{a}.png" for a in ANGULOS},
        "fecha": "2026-10-06T18:45:30",
    }
    almacen.guardar_metadatos(id_estudio, dict(al_registrar))
    print("  1. registrar estudio : 4 proyecciones y metadatos guardados")

    leido = almacen.leer_metadatos(id_estudio)
    if leido != al_registrar:
        fallos.append(f"tras registrar, los metadatos cambiaron: {leido}")
    elif list(leido) != list(al_registrar):
        fallos.append(f"el orden de las claves cambió: {list(leido)}")
    else:
        print("  2. leer metadatos    : idénticos, mismas claves y mismo orden")

    recuperadas = almacen.leer_proyecciones(id_estudio)
    if recuperadas.shape != proyecciones.shape:
        fallos.append(f"las proyecciones volvieron con forma {recuperadas.shape}")
    elif not np.array_equal(recuperadas, proyecciones):
        fallos.append("las proyecciones volvieron con otros valores o en otro orden")
    else:
        print(f"  3. leer proyecciones : {recuperadas.shape}, idénticas y en orden")

    # --- 2. Lo que hace casos_uso.procesar_estudio ---
    volumen = np.random.default_rng(0).random((64, 64, 64)).astype(np.float32)
    almacen.guardar_volumen(id_estudio, volumen)

    tras_procesar = dict(al_registrar)
    tras_procesar.update({
        "estado": "Reconstrucción completada",
        "metodo": "retroproyeccion_simple",
        "tiempo_s": 0.023,
        "estadisticas": {"min": round(float(volumen.min()), 4),
                         "max": round(float(volumen.max()), 4),
                         "media": round(float(volumen.mean()), 4)},
    })
    almacen.guardar_metadatos(id_estudio, dict(tras_procesar))
    print("  4. procesar estudio  : volumen y metadatos actualizados")

    leido = almacen.leer_metadatos(id_estudio)
    if leido != tras_procesar:
        diferencias = {c for c in set(leido) | set(tras_procesar)
                       if leido.get(c) != tras_procesar.get(c)}
        fallos.append(f"tras procesar, cambiaron estas claves: {sorted(diferencias)}")
    elif list(leido) != list(tras_procesar):
        fallos.append(f"el orden de las claves cambió: {list(leido)}")
    else:
        print("  5. leer metadatos    : idénticos, con método, tiempo y estadísticas")
        print(f"       metodo={leido['metodo']!r}  tiempo_s={leido['tiempo_s']!r}")
        print(f"       estadisticas={leido['estadisticas']}")

    # La interfaz hace j.tiempo_s.toFixed(2): tiene que ser un número.
    if not isinstance(leido.get("tiempo_s"), float):
        fallos.append("tiempo_s no volvió como número")

    # --- 3. Lo que hace casos_uso.consultar_resultado ---
    if not np.array_equal(almacen.leer_volumen(id_estudio), volumen):
        fallos.append("el volumen volvió con otros valores")
    else:
        print("  6. leer volumen      : idéntico")

    crudo = almacen.leer_volumen_bytes(id_estudio)
    if not crudo.startswith(b"\x93NUMPY"):
        fallos.append("los bytes del volumen no son un archivo .npy")
    else:
        print(f"  7. volumen para descargar : {len(crudo):,} bytes, .npy válido")

    # --- 4. Errores ---
    for descripcion, operacion in (
        ("un estudio inexistente", lambda: almacen.leer_metadatos("NO-EXISTE-NADA")),
        ("un volumen inexistente", lambda: almacen.leer_volumen("NO-EXISTE-NADA")),
        ("un identificador inválido", lambda: almacen.leer_metadatos("../otro")),
    ):
        try:
            operacion()
            fallos.append(f"{descripcion} no lanzó EstudioNoEncontrado")
        except EstudioNoEncontrado:
            print(f"  8. {descripcion:<26}: lanza EstudioNoEncontrado")

    # --- 5. Limpieza ---
    StudyRepository().delete(id_estudio)
    almacen._almacen.remove([layout.volume_path(id_estudio)]
                            + [layout.projection_path(id_estudio, a) for a in ANGULOS])
    print("  9. limpieza          : estudio y archivos eliminados")

    print()
    if fallos:
        for fallo in fallos:
            print(f"  FALLÓ: {fallo}")
        return 1
    print("  AUTOPRUEBA SUPERADA")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(_autoprueba())