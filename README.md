# RadVol 3D · EN-2 · Servicio local de reconstrucción

**Épica 1 · Modelado tridimensional del órgano** · Sprint 1 · Responsable: Leyva Sandoval, Piero

> **EN-2 · Criterio de aceptación:** el servicio recibe 4 imágenes y devuelve el volumen
> reconstruido junto con el identificador del estudio.

## Qué hace

```
4 radiografías (0°, 45°, 90°, 135°)  ──►  POST /reconstruir  ──►  volumen 64×64×64 + id del estudio
      PNG 16 bits o NPY 64×64              ta2.retroproyectar()        guardado en almacenamiento/estudios/<id>/
                                           (+ U-Net EN-1 si hay pesos)
```

## Arquitectura en capas

El proyecto sigue la **arquitectura en capas cerradas** del documento de arquitectura de RadVol 3D:
cada capa solo usa la inmediatamente inferior.

```
web/                              Capa 1 · Presentación
 └─ js/api.js                       único módulo que llama al servicio
        │ HTTP · JSON
servicio/api/rutas.py             Entrada a la capa 2: traduce HTTP <-> casos de uso
        │
servicio/logica/                  Capa 2 · Lógica de negocio
 ├─ casos_uso.py                    registrar_estudio · procesar_estudio · consultar_resultado
 └─ tuberia/
     ├─ preproceso.py               etapa 1
     └─ reconstruccion.py           etapa 2
        │
servicio/persistencia/            Capa 3 · Persistencia
 └─ almacen_archivos.py             único que conoce las rutas en disco
        │
almacenamiento/estudios/<id>/     Capa 4 · Sistema de archivos (no se sube a git)
```

| Carpeta | Capa | Puede usar | No puede usar |
|---|---|---|---|
| `web/` | 1 · Presentación | el servicio, solo desde `api.js` | lógica ni almacenamiento |
| `servicio/api/` | Entrada a la capa 2 | `logica` | `persistencia` |
| `servicio/logica/` | 2 · Lógica de negocio | `persistencia` | HTTP (`fastapi`) ni rutas en disco |
| `servicio/persistencia/` | 3 · Persistencia | disco | `logica`, HTTP |
| `almacenamiento/` | 4 · Sistema de archivos | — | — |

`servicio/main.py` solo ensambla las capas y `servicio/config.py` reúne la configuración.
`CasosDeUso` recibe el almacén por inyección de dependencias, de modo que el futuro repositorio
con PostgreSQL (capas 3 y 4) se conecta sin modificar la lógica.

**Carpetas de apoyo** (no son capas): `docs/` documentación · `pruebas/` pruebas ·
`herramientas/` scripts de datos · `ejemplos/` estudios de prueba · `evidencias/` resultados ·
`datos/` entrega de TA-2 (no se sube a git) · `modelos/` pesos de EN-1 (opcional).

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

Prueba de aceptación de EN-2 (con el servicio corriendo):

```bash
python pruebas/prueba_aceptacion.py
```

Resultado: **14/14 pruebas aprobadas** sobre los 10 casos de test de pulmón. El volumen
coincide con la retroproyección de TA-2 (diferencia < 1e-5) y el PSNR medio (14.90 dB)
coincide con `proyecciones_report.csv`. Rechaza estudios con 3 imágenes o formatos no admitidos.

Cumplimiento de la arquitectura en capas (no requiere el servicio encendido):

```bash
python pruebas/prueba_capas.py
```

Analiza los `import` de cada archivo y comprueba que ninguna capa use una que no le corresponde.
Incluye un control que introduce una violación a propósito para verificar que se detecta.

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
- Capas 3 y 4 · Base de datos e integración: reemplazar los metadatos en JSON por un repositorio con PostgreSQL, conectándolo en `servicio/main.py` sin modificar `servicio/logica/`.

---
Prototipo de investigación en validación · No constituye diagnóstico médico.