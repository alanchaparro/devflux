# DevFlux

DevFlux es una aplicación de terminal (TUI) para **crear, continuar, revisar y mejorar proyectos de software conversando en lenguaje natural**. La persona usuaria describe qué necesita; DevFlux prepara una confirmación clara, ejecuta un flujo interno de agentes y entrega archivos funcionales en una carpeta de proyecto.

El objetivo del producto es que el flujo principal se sienta así:

```text
Inicio → Preparar → Crear → Listo
```

Sin pedir que la persona entienda roles internos, tokens, prompts, rutas técnicas o detalles del proveedor.

## Qué puede hacer

- Crear un proyecto nuevo a partir de una idea escrita en chat.
- Continuar un proyecto reciente sin buscar carpetas manualmente.
- Pedir mejoras sobre el proyecto activo sin perder contexto.
- Responder preguntas sobre el proyecto sin iniciar una generación de archivos.
- Mostrar un inspector de archivos con árbol, estado por archivo y vista de diff/final.
- Abrir la carpeta activa, copiar archivos generados o abrir un archivo puntual desde la TUI.
- Mantener diagnósticos y entregas internas fuera del proyecto generado.

## Para quién es

DevFlux está pensado para personas que quieren avanzar desde una idea hasta un proyecto funcional con una experiencia guiada. También puede servir a equipos técnicos que quieran prototipar o revisar cambios, pero la interfaz está diseñada para no exponer decisiones internas salvo que se abra Diagnóstico.

## Requisitos

- Python 3.11 o superior.
- Una terminal compatible con aplicaciones TUI.
- Uno de estos proveedores configurables desde el asistente inicial:
  - **Ollama Cloud**: requiere API key.
  - **Ollama Local**: requiere tener tu instancia/modelo local disponible.

## Instalación

### Instalación recomendada con pipx

```bash
pipx install devflux
```

### Instalación para desarrollo local

```bash
git clone <repo-url>
cd devflux
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .[test]
```

> En Windows, activá el entorno con `.venv\\Scripts\\activate`.

## Primer inicio

Ejecutá:

```bash
devflux
```

En el primer inicio, DevFlux muestra un asistente navegable:

1. Elegí **Ollama Cloud** u **Ollama Local** con `↑/↓`.
2. Confirmá con `Enter`.
3. Si elegiste Cloud, pegá la API key cuando se solicite.
4. Elegí el modelo con el selector.
5. DevFlux entra directamente a la pantalla principal.

La API key se guarda de forma privada y nunca se muestra en la interfaz, diagnósticos o logs del chat.

## Uso básico

### Crear un proyecto

1. Abrí DevFlux con `devflux`.
2. Escribí tu idea, por ejemplo:

   ```text
   Quiero una web simple para registrar recetas familiares
   ```

3. DevFlux propone una confirmación en lenguaje claro y muestra la carpeta donde creará el proyecto.
4. Presioná `Enter` para aplicar o `Esc` para cambiar el pedido.
5. Al finalizar, DevFlux muestra la carpeta, los archivos creados y los próximos pasos.

### Continuar un proyecto

Desde el menú principal elegí **Continuar proyecto**. DevFlux muestra proyectos recientes como tarjetas con:

- Nombre del proyecto.
- Cantidad de archivos funcionales.
- Fecha de la última sesión.
- Acción para continuar.

Al continuar, se restaura la carpeta activa y, si hay archivos, se muestra el inspector.

### Pedir una mejora

Cuando un proyecto está listo o activo, usá **Ctrl+R** para pedir una mejora. DevFlux vuelve al input principal, conserva la carpeta activa y pregunta:

```text
¿Qué querés cambiar de este proyecto?
```

El siguiente pedido se aplica como modificación del proyecto activo, no como un proyecto nuevo.

### Hacer preguntas

También podés escribir preguntas como:

```text
¿Qué archivos tiene este proyecto y para qué sirve cada uno?
```

Las preguntas se responden como conversación y no ejecutan el pipeline de escritura.

## Menú principal

El menú principal se mantiene intencionalmente pequeño:

- **Nuevo proyecto**: iniciar una creación guiada.
- **Continuar proyecto**: reabrir un proyecto reciente.
- **Ajustes**: cambiar proveedor, modelo o API key.
- **Diagnóstico**: ver detalles técnicos solo cuando sean necesarios para soporte.

## Atajos útiles

| Atajo | Acción |
| --- | --- |
| `Enter` | Enviar mensaje o aplicar una confirmación activa. |
| `Esc` | Cancelar menú/confirmación o volver al input. |
| `Ctrl+S` | Abrir/cerrar menú. |
| `Ctrl+D` | Mostrar/ocultar Diagnóstico. |
| `Ctrl+E` | Mostrar el inspector de código. |
| `Ctrl+O` | Abrir la carpeta del proyecto activo. |
| `Ctrl+R` | Pedir una mejora sobre el proyecto activo. |
| `Ctrl+T` | Cambiar tema visual. |
| `Ctrl+C` | Solicitar cancelación segura de la generación en curso. |

En el inspector de código:

| Tecla | Acción |
| --- | --- |
| `j` / `↓` | Siguiente archivo. |
| `k` / `↑` | Archivo anterior. |
| `d` | Alternar entre diff y resultado final cuando exista diff. |
| `c` | Copiar el contenido del archivo seleccionado. |
| `o` | Abrir el archivo seleccionado con la aplicación del sistema. |

## Ajustes y proveedores

**Ajustes** abre una pantalla completa con listas navegables:

- `Tab` cambia de sección.
- `↑/↓` navega opciones.
- `Enter` selecciona.
- **Guardar cambios** persiste proveedor/modelo/API key nueva.
- **Cancelar** o `Esc` descarta el borrador.

Para **Ollama Cloud**, el campo secreto sirve únicamente para reemplazar una API key. La clave existente nunca se precarga ni se revela. Para **Ollama Local**, no se solicita API key.

## Cómo trabaja internamente

Cada creación o modificación confirmada recorre internamente el equipo-dev completo:

```text
analista → arquitecto → planificador → backend → frontend → QA → reviewer → integrador
```

La interfaz no muestra esos roles como decisiones de usuario. Esta arquitectura prioriza calidad y revisión, aunque puede tardar más que una generación directa.

Los bugs explícitos usan el flujo de equipo-bugs. Las preguntas se responden en el chat sin crear ni modificar archivos.

## Archivos generados e inspector

DevFlux muestra solo archivos funcionales del proyecto. El inspector permite:

- Navegar carpetas y archivos como árbol.
- Ver estado por archivo: `Nuevo`, `Modificado` o `Revisado`.
- Alternar entre diff y resultado final.
- Copiar contenido.
- Abrir archivos o la carpeta activa.

DevFlux filtra artefactos internos como `PRD.md`, `architecture.md`, `plan.md`, `plan.yaml`, `plan.yml`, `main.md`, `output.html`, Markdown y diagramas Mermaid. Esos documentos no se escriben ni se muestran como resultado funcional.

## Privacidad y archivos internos

Los diagnósticos, respuestas crudas y checkpoints por rol (`state.json`) no se guardan dentro del proyecto generado. Se aíslan en:

```text
~/.devflux/runs/<run-id>/
```

El chat normal no expone URLs internas, tokens, stack traces, nombres de roles, prompts ni API keys.

## Desarrollo

Instalación de desarrollo:

```bash
python -m pip install -e .[test]
```

Validaciones recomendadas antes de abrir un cambio:

```bash
python -m pytest -q
python -m compileall -q devflux
python -m build
```

## Estructura del proyecto

```text
devflux/
├── main.py              # Entrypoint y asistente inicial
├── core/
│   ├── config.py        # Configuración persistente
│   ├── credentials.py   # Almacenamiento privado de credenciales
│   ├── client.py        # Cliente LLM compatible con APIs estilo OpenAI
│   ├── context.py       # Inventario seguro y contexto del proyecto
│   ├── orchestrator.py  # Enrutamiento conversacional y selección de flujo
│   ├── runner.py        # Ejecución de roles y escritura segura de archivos
│   └── sessions.py      # Registro de sesiones y proyectos recientes
├── tui/
│   ├── app.py           # Interfaz Textual principal
│   └── styles.tcss      # Estilos y temas
├── prompts/             # Plantillas Jinja2 por equipo/rol
└── tests/               # Pruebas de lógica, UX y endurecimiento
```

## Documentación adicional

- [`CHANGELOG.md`](CHANGELOG.md): cambios notables por versión.
- [`PENDIENTES.md`](PENDIENTES.md): estado del rediseño de producto y criterios de cierre.
- [`PRD.md`](PRD.md): definición histórica de producto.
- [`docs/agents/contextual-confirmation.md`](docs/agents/contextual-confirmation.md): contrato de mantenimiento para agentes.

## Estado del rediseño

El rediseño guiado está documentado como completo en `PENDIENTES.md`: creación, preparación, inspector, mejoras, proyectos recientes, ajustes/temas y validación final.
