# Guía de contribución · RadVol 3D

## Mensajes de commit

El proyecto sigue **[Conventional Commits 1.0.0](https://www.conventionalcommits.org/es/v1.0.0/)**.

```
<tipo>(<alcance>): <descripción>

[cuerpo opcional: qué cambia y por qué]

[pie opcional: referencias, BREAKING CHANGE]
```

### Tipos

| Tipo | Cuándo usarlo |
|---|---|
| `feat` | Nueva funcionalidad visible para el usuario |
| `fix` | Corrección de un error o de un incumplimiento de un estándar |
| `refactor` | Cambio interno del código que no altera el comportamiento |
| `docs` | Solo documentación |
| `style` | Formato del código (espacios, comas), sin cambiar la lógica |
| `test` | Agregar o corregir pruebas |
| `chore` | Mantenimiento (dependencias, configuración) |

### Alcances usados

`web` (interfaz) · `api` (servicio FastAPI) · `motor` (reconstrucción) · `datos` (herramientas de datos)

### Reglas

- Descripción en minúsculas, en modo imperativo y sin punto final: `agregar…`, `corregir…`, `separar…`.
- Un commit = un cambio lógico.
- En el cuerpo, citar el elemento del backlog (`HU-1.1`, `EN-2`) o el criterio del estándar (`WCAG 2.4.7`) cuando aplique.

### Ejemplos

```
feat(web): cumplir criterios de aceptación de HU-1.1 en la interfaz
fix(web): cumplir WCAG 2.2 AA en teclado, foco, contraste y nombres accesibles
refactor(web): separar app.js en módulos
docs: definir el estándar de la interfaz y la convención de commits
```

## Estándar de la interfaz

Ver [`docs/estandar-interfaz.md`](docs/estandar-interfaz.md): WCAG 2.2 nivel AA (ISO/IEC 40500:2025) e ISO 9241-110:2020.