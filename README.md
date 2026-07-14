# DevFlux

DevFlux es una TUI para crear, continuar, revisar y entender proyectos mediante una conversación simple. Escribí lo que necesitás; DevFlux prepara una propuesta clara y vos decidís cuándo aplicarla.

## Requisitos

- Python 3.11 o superior: verificá con `python --version` o `python3 --version`.
- `pip` disponible: verificá con `python -m pip --version`.
- Una terminal compatible con aplicaciones TUI.
- Un proveedor para el modelo: **Ollama Cloud** con API key u **Ollama Local** funcionando en tu equipo.

## Instalación

### Opción recomendada: pipx

`pipx` instala aplicaciones Python aisladas y deja el comando `devflux` disponible en la terminal.

```bash
pipx install devflux
```

Si tu sistema no reconoce `pipx`, instalalo primero:

```bash
python -m pip install --user pipx
python -m pipx ensurepath
```

Después cerrá y abrí la terminal. Verificá:

```bash
pipx --version
```

> En algunas instalaciones el comando de Python es `python3` en lugar de `python`. Si `python` no existe, usá `python3 -m pip ...`.

### Alternativa sin pipx

Si no podés usar `pipx`, instalá DevFlux en un entorno virtual:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install devflux
devflux
```

En Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install devflux
devflux
```

### Instalación para desarrollo

```bash
git clone <repo-url>
cd devflux
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## Uso

```bash
devflux
```

En el primer inicio, el asistente muestra un selector navegable para elegir entre **Ollama Cloud** y **Ollama Local**. Usá **↑/↓** para recorrer las opciones, **Enter** para confirmar y **Esc** para cancelar la selección.

- Con **Ollama Cloud**, pegá la API key cuando se solicite; es el único dato que se escribe manualmente. Después elegí el modelo con el selector.
- Con **Ollama Local**, elegí directamente el modelo con el selector; no se solicita API key.
- **Ajustes** abre un editor a pantalla completa: el proveedor y modelo actuales quedan preseleccionados en listas navegables y desplazables. Usá **Tab** para cambiar de sección, **↑/↓** para recorrer las listas y **Enter** para elegir.
- En **Ajustes**, **Guardar cambios** aplica proveedor y modelo y confirma `Ajustes guardados.`; **Cancelar** o **Esc** cierra el editor sin cambiar la configuración. Para Cloud, el campo secreto solo sirve para reemplazar la API key: la existente nunca se revela.

La API key se guarda de forma privada y DevFlux no la muestra en la interfaz.

## Experiencia de uso

El menú principal contiene solo:

- **Nuevo proyecto**
- **Continuar proyecto**
- **Ajustes**
- **Diagnóstico**

También podés escribir directamente en el chat para crear, modificar, corregir un problema o hacer una pregunta. Las preguntas se responden como conversación y no inician una ejecución de archivos.

Cuando DevFlux entiende un cambio, muestra una única confirmación en lenguaje claro:

```text
Entendí: actualizaré el proyecto actual según tu pedido: ...
[Enter] Aplicar · [Esc] Cambiar pedido
```

- **Enter** aplica el cambio confirmado.
- **Esc** vuelve al chat para cambiar el pedido.
- Al ejecutar un cambio, DevFlux muestra primero `Conectando con el modelo...`. Solo después de recibir archivos reales informa cuáles actualizará, luego muestra `Verificando cambios...` y termina con `Listo.`.
- Si el modelo no está disponible, DevFlux explica el problema sin detalles técnicos y muestra `> [Enter] Reintentar    [Esc] Cancelar`. **Enter** relanza una sola vez el último pedido fallido; **Esc** lo descarta y devuelve el foco al chat. Al terminar correctamente, ese reintento queda desarmado.
- **Ctrl+D** abre el panel de **Diagnóstico** para soporte. Ahí se consultan los detalles técnicos; el chat normal no muestra providers, modelos, URLs, tokens, roles internos, reintentos ni stack traces.

Cada creación o modificación confirmada recorre internamente el equipo-dev completo, en este orden: **analista → arquitecto → planificador → backend → frontend → QA → reviewer → integrador**. DevFlux usa un único proveedor/modelo y cambia el prompt en cada etapa. Es una garantía deliberada de calidad, aunque implica más tiempo y costo que una implementación directa; la interfaz sigue siendo simple y no expone roles, planificación ni arquitectura como decisiones de la persona usuaria. Los pedidos que son preguntas se responden en el chat sin ejecutar roles, y los bugs explícitos usan equipo-bugs.

## Archivos y panel derecho

El panel derecho muestra los archivos funcionales creados o modificados y sus diferencias. DevFlux filtra documentos e insumos internos como `PRD.md`, `architecture.md`, `plan.md`, `plan.yaml`, `plan.yml`, `main.md`, `output.html`, Markdown y diagramas Mermaid: no los escribe ni los muestra como resultado del pedido.

Atajos útiles al terminar: **Ctrl+O** abre la carpeta activa, **Ctrl+E** muestra el inspector de código y **Ctrl+R** pide una mejora sobre el proyecto activo sin perder la carpeta.

Los diagnósticos, respuestas crudas y checkpoints por rol (`state.json`) no se guardan dentro del proyecto: se aíslan en `~/.devflux/runs/<run-id>/`. El chat normal no expone esos detalles internos.

## Desarrollo y validación

```bash
python3 -m pytest -q
python3 -m compileall -q devflux
python3 -m build
```

## Stack

- Python 3.11+
- Textual (TUI)
- httpx (cliente HTTP)
- Jinja2 (plantillas de prompts)
- PyYAML (configuración)

## Arquitectura

```text
devflux/
├── main.py              # Entrypoint + wizard
├── core/
│   ├── config.py        # DevFluxConfig
│   ├── client.py        # Cliente LLM compatible con OpenAI
│   ├── context.py       # Inventario y contexto seguro del proyecto
│   ├── orchestrator.py  # Enrutamiento conversacional y equipo-dev de 8 roles
│   ├── runner.py        # Checkpoints aislados y escritura segura del integrador
│   └── sessions.py      # Registro de sesiones
├── tui/
│   ├── app.py           # Chat, confirmación y diagnóstico
│   └── styles.tcss      # Estilos
├── prompts/             # Plantillas Jinja2 por equipo/rol
└── tests/               # Pruebas de lógica, UX y endurecimiento
```

Para el contrato de mantenimiento destinado a agentes, consultá [`docs/agents/contextual-confirmation.md`](docs/agents/contextual-confirmation.md).
