import base64
import csv
import json
import sys
from pathlib import Path

import numpy as np
import requests

URL = "http://127.0.0.1:8000"
RAIZ = Path(__file__).resolve().parent.parent
EJEMPLOS = RAIZ / "ejemplos"
PULMON = RAIZ / "datos" / "TA2_entrega" / "processed" / "pulmon"
ANGULOS = (0, 45, 90, 135)
resultados = []


def registrar(nombre, ok, detalle=""):
    resultados.append((nombre, ok))
    print(f"  [{'OK ' if ok else 'FALLA'}] {nombre}  {detalle}")


def enviar(caso, ext=".png", omitir=None, id_estudio=None, reemplazo=None):
    archivos = {}
    for a in ANGULOS:
        if a == omitir:
            continue
        ruta = EJEMPLOS / caso / f"{caso}_{a:03d}{ext}"
        archivos[f"proyeccion_{a}"] = (ruta.name, ruta.read_bytes())
    if reemplazo:
        archivos[reemplazo[0]] = reemplazo[1]
    datos = {"id_estudio": id_estudio} if id_estudio else {}
    return requests.post(f"{URL}/reconstruir", files=archivos, data=datos, timeout=60)


def volumen_de(resp_json):
    v = resp_json["volumen"]
    return np.frombuffer(base64.b64decode(v["datos_base64"]), dtype=v["tipo"]).reshape(v["forma"])


print("PRUEBA DE ACEPTACIÓN · EN-2 · Servicio local de reconstrucción\n")

# 0. Servicio en línea
try:
    s = requests.get(f"{URL}/salud", timeout=5).json()
except requests.ConnectionError:
    sys.exit("El servicio no responde. Arráncalo con: uvicorn servicio.main:app")
print(f"Servicio: {s['estado']} · método: {s['metodo']} · versión {s['version']}\n")

# 1. Criterio principal, sobre TODOS los casos de test
casos = sorted(p.name for p in EJEMPLOS.iterdir() if p.is_dir())
print(f"1) 4 imágenes PNG -> volumen + identificador ({len(casos)} casos)")
tiempos, psnrs, filas = [], [], []
for caso in casos:
    r = enviar(caso, id_estudio=caso)
    ok = r.status_code == 200
    if ok:
        j = r.json()
        vol = volumen_de(j)
        ok = j["id_estudio"] == caso and vol.shape == (64, 64, 64)
        tiempos.append(j["tiempo_s"])
        detalle = f"id={j['id_estudio']}  forma={vol.shape}  {j['tiempo_s']:.2f} s"
        # Si el servicio usa retroproyección, debe coincidir con el _bp.npy de TA-2
        if j["metodo"] == "retroproyeccion_simple" and (PULMON / f"{caso}_bp.npy").exists():
            dif = float(np.abs(vol - np.load(PULMON / f"{caso}_bp.npy")).max())
            ok = ok and dif < 1e-3
            detalle += f"  |dif vs TA-2|={dif:.1e}"
        # PSNR contra la tomografía real (se compara con el reporte de TA-2)
        real = np.load(PULMON / f"{caso}_vol.npy")
        psnr = 10 * np.log10(1.0 / float(np.mean((vol - real) ** 2)))
        psnrs.append(psnr)
        detalle += f"  PSNR={psnr:.2f} dB"
        filas.append({"caso": caso, "id_devuelto": j["id_estudio"], "forma": list(vol.shape),
                      "tiempo_s": j["tiempo_s"], "psnr_db": round(psnr, 2)})
    else:
        detalle = f"HTTP {r.status_code}"
    registrar(caso, ok, detalle)

# 2. Sin id -> el servicio genera uno
print("\n2) Sin identificador -> el servicio lo genera")
j = enviar(casos[0], ext=".npy").json()
registrar("id generado automáticamente", j.get("id_estudio", "").startswith("EST-"), j.get("id_estudio"))

# 3. Descarga del volumen guardado
r = requests.get(f"{URL}{j['descarga']}", timeout=10)
registrar("descarga del volumen .npy", r.status_code == 200 and len(r.content) > 1_000_000,
          f"{len(r.content):,} bytes")

# 4. Casos de rechazo
print("\n3) Rechazos")
r = enviar(casos[0], omitir=90)
registrar("solo 3 imágenes -> rechazado", r.status_code == 422, r.json().get("detalle"))
r = enviar(casos[0], reemplazo=("proyeccion_45", ("nota.txt", b"hola")))
registrar("formato .txt -> rechazado", r.status_code == 422,
          f"{r.json().get('archivo_rechazado')}: {r.json().get('detalle')}")

# Resumen
aprobadas = sum(ok for _, ok in resultados)
print(f"\nRESULTADO: {aprobadas}/{len(resultados)} pruebas aprobadas")
if tiempos:
    print(f"  tiempo medio por estudio : {np.mean(tiempos):.2f} s")
    # Referencia: el PSNR que TA-2 calculó para esos mismos casos
    with open(RAIZ / "datos" / "TA2_entrega" / "proyecciones_report.csv", encoding="utf-8") as fh:
        ref = {r["caso"]: float(r["psnr_retroproyeccion_db"]) for r in csv.DictReader(fh)}
    ref_media = np.mean([ref[c] for c in casos if c in ref])
    print(f"  PSNR medio (test pulmón) : {np.mean(psnrs):.2f} dB  "
          f"(proyecciones_report.csv de TA-2: {ref_media:.2f} dB)")
(RAIZ / "evidencias").mkdir(exist_ok=True)
reporte = {
    "criterio": "El servicio recibe 4 imágenes y devuelve el volumen reconstruido "
                "junto con el identificador del estudio.",
    "metodo": s["metodo"],
    "aprobadas": aprobadas, "total": len(resultados),
    "cumple_criterio": aprobadas == len(resultados),
    "tiempo_medio_s": round(float(np.mean(tiempos)), 3) if tiempos else None,
    "psnr_medio_db": round(float(np.mean(psnrs)), 2) if psnrs else None,
    "casos": filas,
    "pruebas": [{"prueba": n, "aprobada": bool(o)} for n, o in resultados],
}
(RAIZ / "evidencias" / "prueba_aceptacion.json").write_text(
    json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
print("  reporte guardado en      : evidencias/prueba_aceptacion.json")
sys.exit(0 if aprobadas == len(resultados) else 1)