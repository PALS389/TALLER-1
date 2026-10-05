import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SERVICIO = RAIZ / "servicio"

# Qué paquetes internos puede importar cada capa
PERMITIDO = {
    "api": {"logica", "config"},
    "logica": {"persistencia", "config"},
    "persistencia": {"config"},
}
# Bibliotecas que delatan que una capa hace un trabajo que no le toca
PROHIBIDO_EXTERNO = {
    "logica": {"fastapi", "starlette", "pathlib", "os", "shutil"},
    "persistencia": {"fastapi", "starlette"},
}
# Nombres que solo la capa 3 (y el ensamblador) pueden usar
PROHIBIDO_NOMBRE = {"api": {"DIR_ALMACENAMIENTO"}, "logica": {"DIR_ALMACENAMIENTO"}}


def modulo_de(ruta: Path) -> list:
    return list(ruta.relative_to(RAIZ).with_suffix("").parts)


def revisar(codigo: str, capa: str, modulo: list) -> list:
    """Devuelve la lista de violaciones encontradas en un archivo de la capa dada."""
    errores = []
    for nodo in ast.walk(ast.parse(codigo)):
        destinos = []
        if isinstance(nodo, ast.Import):
            destinos = [a.name.split(".") for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:                                   # import relativo: from ..x import y
                base = modulo[:-nodo.level]
                destinos = [base + (nodo.module.split(".") if nodo.module else [])]
            else:
                destinos = [nodo.module.split(".")]
        elif isinstance(nodo, ast.Name) and nodo.id in PROHIBIDO_NOMBRE.get(capa, ()):
            errores.append(f"usa {nodo.id} (solo la capa 3 conoce dónde se guarda)")

        for d in destinos:
            if d[0] == "servicio" and len(d) > 1:
                destino = d[1]
                if destino != capa and destino not in PERMITIDO[capa]:
                    errores.append(f"importa servicio.{'.'.join(d[1:])} (la capa '{capa}' no puede usar '{destino}')")
            elif d[0] in PROHIBIDO_EXTERNO.get(capa, ()):
                errores.append(f"importa {d[0]} (no corresponde a la capa '{capa}')")
    return errores


def revisar_servicio() -> list:
    resultados = []
    for capa in PERMITIDO:
        for archivo in sorted((SERVICIO / capa).rglob("*.py")):
            errores = revisar(archivo.read_text(encoding="utf-8"), capa, modulo_de(archivo))
            resultados.append((archivo.relative_to(RAIZ), capa, errores))
    return resultados


def revisar_web() -> list:
    """Capa 1: solo api.js puede llamar al servicio (fetch)."""
    return [(js.relative_to(RAIZ), "fetch() fuera de api.js")
            for js in sorted((RAIZ / "web" / "js").glob("*.js"))
            if js.name != "api.js" and "fetch(" in js.read_text(encoding="utf-8")]


if __name__ == "__main__":
    print("PRUEBA DE ARQUITECTURA · capas cerradas\n")
    fallos = 0

    for archivo, capa, errores in revisar_servicio():
        print(f"  [{'OK ' if not errores else 'FALLA'}] {str(archivo):48s} capa {capa}")
        for e in errores:
            print(f"          - {e}")
        fallos += bool(errores)

    web = revisar_web()
    print(f"  [{'OK ' if not web else 'FALLA'}] {'web/js/*.js':48s} capa 1 (solo api.js usa fetch)")
    for archivo, e in web:
        print(f"          - {archivo}: {e}")
    fallos += bool(web)

    # Control: una violación introducida a propósito DEBE detectarse
    trampa = "from ..persistencia.almacen_archivos import AlmacenArchivos\n"
    detectada = bool(revisar(trampa, "api", ["servicio", "api", "rutas"]))
    print(f"\n  Control: la ruta HTTP importando la capa 3 a propósito -> "
          f"{'DETECTADO' if detectada else 'NO DETECTADO'}")
    fallos += not detectada

    print(f"\nRESULTADO: {'se respetan las capas' if not fallos else f'{fallos} problema(s)'}")
    sys.exit(1 if fallos else 0)