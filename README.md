# RadVol 3D · EN-2 · Servicio local de reconstrucción

**Épica 1 · Modelado tridimensional del órgano** · Sprint 1 · Responsable: Leyva Sandoval, Piero

> **EN-2 · Criterio de aceptación:** el servicio recibe 4 imágenes y devuelve el volumen
> reconstruido junto con el identificador del estudio.

## Qué hace

```
4 radiografías (0°, 45°, 90°, 135°)  ──►  POST /reconstruir  ──►  volumen 64×64×64 + id del estudio
      PNG 16 bits o NPY 64×64              ta2.retroproyectar()        guardado en estudios/<id>/
                                           (+ U-Net EN-1 si hay pesos)
```

## Estructura

| Carpeta | Contenido |
|---|---|
| `servicio/` | `config.py` (rutas), `lectura.py` (valida imágenes), `reconstructor.py` (motor), `main.py` (API FastAPI) |
| `web/` | Interfaz: `index.html`, `estilos.css`, `app.js` |
| `herramientas/` | `explorar_datos.py`, `exportar_estudio.py`, `verificar_png.py` |
| `pruebas/` | `probar_motor.py`, `prueba_aceptacion.py` |
| `evidencias/` | Figuras y reporte de la prueba de aceptación |
| `datos/` | `TA2_entrega/` descomprimido (no se sube a git) |
| `modelos/` | `unet_pulmon.pth` de EN-1 (opcional) |

## Instalación (Linux / WSL)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
unzip -q TA2_entrega.zip -d datos/TA2_entrega
python herramientas/exportar_estudio.py --test
```

## Uso

```bash
uvicorn servicio.main:app --reload
```

- Interfaz: <http://127.0.0.1:8000/>
- Documentación interactiva: <http://127.0.0.1:8000/docs>

| Endpoint | Descripción |
|---|---|
| `GET /salud` | Estado del servicio y método activo |
| `POST /reconstruir` | Campos `proyeccion_0`, `proyeccion_45`, `proyeccion_90`, `proyeccion_135` (+ `id_estudio` opcional) |
| `GET /estudios/{id}/volumen.npy` | Descarga el volumen guardado |

## Verificación

```bash
python pruebas/prueba_aceptacion.py      # con el servicio corriendo
```

Resultado: **14/14 pruebas aprobadas** sobre los 10 casos de test de pulmón. El volumen
coincide con la retroproyección de TA-2 (diferencia < 1e-5) y el PSNR medio (14.90 dB)
coincide con `proyecciones_report.csv`. Rechaza estudios con 3 imágenes o formatos no admitidos.

## Interfaz de usuario

La interfaz (`web/`) sigue **WCAG 2.2 nivel AA (ISO/IEC 40500:2025)** y los principios de
**ISO 9241-110:2020**, y cumple los criterios de aceptación de **HU-1.1**.
Criterios aplicados y verificación: [`docs/estandar-interfaz.md`](docs/estandar-interfaz.md).
Convención de commits: [`CONTRIBUTING.md`](CONTRIBUTING.md) (Conventional Commits 1.0.0).

| Módulo | Responsabilidad |
|---|---|
| `web/js/api.js` | Único punto de contacto con el servicio (capa 2) |
| `web/js/carga.js` | Casillas de las 4 proyecciones, validación de formulario y rechazos |
| `web/js/visor.js` | Cortes axial, coronal y sagital |
| `web/js/imagen.js` | Lectura de PNG/NPY para la vista previa |
| `web/js/main.js` | Estados del estudio (HU-1.1) y unión de los módulos |

## Pendiente (siguientes sprints)

- Conectar la U-Net de EN-1: copiar los pesos a `modelos/unet_pulmon.pth` e instalar `torch` y `monai`.
- HU-1.1: flujo completo del médico sobre este servicio.

---
Prototipo de investigación en validación · No constituye diagnóstico médico.