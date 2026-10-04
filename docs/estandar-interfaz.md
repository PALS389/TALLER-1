# Estándar de la interfaz de usuario · RadVol 3D

**Capa 1 · Presentación** · Aplicación web · Responsable: Leyva Sandoval, Piero Alejandro

## 1. Estándares que sigue la interfaz

| Estándar | Qué regula | Cómo se aplica |
|---|---|---|
| **WCAG 2.2, nivel AA** (W3C, 2023), adoptado como **ISO/IEC 40500:2025** | Accesibilidad del contenido web. Define criterios verificables (contraste, teclado, foco, nombres accesibles, mensajes de estado…). | Es el estándar principal. Cada criterio de la sección 3 se comprueba y se registra. |
| **ISO 9241-110:2020** · Ergonomía de la interacción persona-sistema, parte 110 | Siete principios de interacción que debe cumplir un sistema interactivo. | Guía las decisiones de diseño del flujo (sección 4). |
| **Conventional Commits 1.0.0** | Formato de los mensajes de commit. | Ver `CONTRIBUTING.md`. |

> **Respuesta corta:** la interfaz sigue **WCAG 2.2 nivel AA (ISO/IEC 40500:2025)** y los principios de interacción de **ISO 9241-110:2020**.

## 2. Alcance

- Archivos: `web/index.html`, `web/estilos.css`, `web/js/*.js`.
- La interfaz **no decide reglas del dominio** (arquitectura en capas): la condición de "exactamente 4 vistas a 0°, 45°, 90° y 135°" la decide el servicio (capa 2). La interfaz la comprueba también, pero solo por comodidad del usuario.

## 3. Criterios WCAG 2.2 AA aplicados

| Criterio | Nombre | Cómo se cumple | Dónde |
|---|---|---|---|
| 1.1.1 | Contenido no textual | Cada corte del visor tiene `role="img"` y un `aria-label` que dice el plano y el número de corte. Los íconos decorativos usan `aria-hidden`. | `visor.js`, `index.html` |
| 1.3.1 | Información y relaciones | Regiones `header`, `main` y `footer`; un solo `h1`, secciones con `h2`; `label` asociado a cada campo; `fieldset` con `legend` para el órgano; métricas en `dl`. | `index.html` |
| 1.4.1 | Uso del color | Los estados (rechazado, completado…) siempre llevan texto, no solo color. | `main.js` |
| 1.4.3 | Contraste mínimo (texto ≥ 4.5:1) | Gris de texto `#56657A` (≥ 4.8:1 en todos los fondos); rojo de error `#BE123C` (5.2:1). | `estilos.css` |
| 1.4.10 | Reflujo | A 320 px de ancho no aparece desplazamiento horizontal. | `estilos.css` |
| 1.4.11 | Contraste no textual (≥ 3:1) | Bordes de campos, casillas y botones `#78879D` (3.2:1). | `estilos.css` |
| 2.1.1 | Teclado | Las casillas de carga y "Cargar las 4 a la vez" son `<button>`: se activan con Enter o Espacio. | `carga.js` |
| 2.4.1 | Evitar bloques | Enlace "Saltar al contenido principal", visible al recibir el foco. | `index.html` |
| 2.4.2 | Página titulada | `<title>Nuevo estudio · RadVol 3D</title>`. | `index.html` |
| 2.4.3 | Orden del foco | El orden de tabulación sigue el flujo de la página; al reconstruir, el foco pasa al resultado; al quitar una imagen, vuelve a su casilla. | `main.js`, `carga.js` |
| 2.4.7 | Foco visible | Contorno de 3 px en todos los controles (`:focus-visible`). | `estilos.css` |
| 2.5.7 | Movimientos de arrastre | Arrastrar archivos es opcional; siempre existe la alternativa de clic o teclado. | `carga.js` |
| 2.5.8 | Tamaño del objetivo (≥ 24×24 px) | Botones, casillas y deslizadores miden 24 px o más. | `estilos.css` |
| 3.1.1 | Idioma de la página | `<html lang="es">`. | `index.html` |
| 3.3.1 | Identificación de errores | El archivo rechazado se nombra y se describe el motivo, en la casilla y en el recuadro de errores. | `main.js`, `carga.js` |
| 3.3.2 | Etiquetas o instrucciones | Cada campo tiene etiqueta visible y la sección de carga explica formatos y formas de cargar. | `index.html` |
| 3.3.3 | Sugerencia ante errores | El mensaje dice cómo corregir ("usa .png o .npy", "se requieren exactamente 4"). | `carga.js` |
| 4.1.2 | Nombre, función, valor | Cada casilla anuncia ángulo, estado y acción; el selector de órgano usa `aria-pressed`; los deslizadores tienen `aria-label` y `aria-valuetext`. | `carga.js`, `visor.js` |
| 4.1.3 | Mensajes de estado | Estado del servicio y del estudio con `role="status"`; rechazos con `role="alert"`. | `index.html` |

## 4. Principios ISO 9241-110:2020

| Principio | Aplicación en la interfaz |
|---|---|
| Idoneidad para las tareas | El flujo sigue la tarea del médico: datos → 4 proyecciones → volumen. |
| Autodescriptividad | Indicador de 3 pasos, estado del estudio siempre visible y ángulo en cada casilla. |
| Conformidad con las expectativas | Botones y diálogos estándar del navegador; mismo estilo en todas las secciones. |
| Aprendibilidad | Instrucciones junto a cada sección y ejemplo de identificador. |
| Controlabilidad | Quitar una imagen, limpiar todo o empezar un estudio nuevo en cualquier momento. |
| Robustez ante errores de uso | Se valida antes de enviar, se identifica el archivo y se conservan los archivos correctos. |
| Compromiso del usuario | Respuesta inmediata en cada acción y aspecto coherente con el prototipo del equipo. |

## 5. Criterios de aceptación cubiertos (HU-1.1)

| Criterio de HU-1.1 | Implementación |
|---|---|
| Admite exactamente 4 imágenes y muestra el ángulo asignado a cada una antes de procesar. | 4 casillas rotuladas 0°, 45°, 90° y 135°; el botón "Reconstruir" solo se habilita con 4 imágenes válidas. |
| Al finalizar, el estado cambia a «Reconstrucción completada» y queda habilitada la vista del volumen. | Estados *Pendiente → Listo para procesar → Procesando → Reconstrucción completada*; la sección 3 está bloqueada hasta ese estado. |
| Ante un número distinto de 4 o un formato no admitido, identifica el archivo rechazado y no inicia el procesamiento. | Selección de 3 o 5 archivos: se rechaza y se listan los archivos. Formato no admitido: la casilla se marca en rojo con el nombre y el motivo. Estado *Rechazado*, botón deshabilitado. |
| El tiempo entre la carga y la habilitación de la vista se muestra en segundos. | Indicador "Tiempo hasta la vista" (desde que se envía la carga hasta que la vista está dibujada). |

## 6. Verificación

Las capturas de cada prueba están en el registro semanal del equipo en Notion
(Semana del 04/10/2026 · Capa 1 · Interfaz de usuario).

### 6.1 Estado antes de los cambios (commit `5240bb6`)

Auditoría con los mismos criterios de la sección 3, sobre la versión anterior de la interfaz:

| Criterio | Hallazgo |
|---|---|
| 1.4.3 Contraste mínimo | 2 textos a 4.34:1 (se exige 4.5:1): descripción del encabezado y pie de página |
| 1.4.11 Contraste no textual | 7 controles a 1.48:1 (se exige 3:1): campo de identificador, 4 casillas, "Cargar las 4 a la vez" y "Limpiar" |
| 2.1.1 Teclado | Las 4 casillas de carga y "Cargar las 4 a la vez" no se alcanzaban con Tab |
| 2.4.7 Foco visible | Los botones no mostraban indicador de foco |
| 1.3.1 / 2.4.1 | Sin regiones `main` y `footer`, y sin enlace para saltar al contenido |
| HU-1.1 · criterio 3 | Al elegir más de 4 archivos se tomaban 4 en silencio, sin rechazar ni identificar el sobrante |

### 6.2 Resultado después de los cambios (commit `2e306a8`)

| Prueba | Herramienta | Resultado |
|---|---|---|
| Auditoría de accesibilidad | Lighthouse (Chrome DevTools), modo Navigation, Desktop | Puntaje de accesibilidad: **__ / 100** |
| Contraste de texto y de controles | Cálculo de la razón de contraste WCAG sobre cada texto y borde visible | 0 fallos en los estados inicial, rechazado y completado |
| Navegación solo con teclado | Manual: Tab, Enter y Espacio | Todos los controles alcanzables y con foco visible; Enter en una casilla abre el selector de archivos |
| Reflujo a 320 px | Ventana de 320 px de ancho | Sin desplazamiento horizontal |
| HU-1.1 · criterio 1 | Manual, `ejemplos/lung_003` | Cumple: 4 casillas con su ángulo; "Reconstruir" solo con 4 imágenes válidas |
| HU-1.1 · criterio 2 | Manual, `ejemplos/lung_003` | Cumple: el estado pasa a «Reconstrucción completada» y se desbloquea la vista |
| HU-1.1 · criterio 3 | Manual: 5 archivos, 3 archivos y `nota.txt` | Cumple: se rechaza, se nombra cada archivo y no se procesa |
| HU-1.1 · criterio 4 | Manual, `ejemplos/lung_003` | Cumple: se muestra "Tiempo hasta la vista" en segundos |

Verificado por: Leyva Sandoval, Piero · Fecha: 04/10/2026