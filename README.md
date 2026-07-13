# DevFlux

DevFlux es una TUI para crear, continuar, revisar y entender proyectos mediante una conversación simple. Escribí lo que necesitás; DevFlux prepara una propuesta clara y vos decidís cuándo aplicarla.

## Instalación

```bash
pipx install devflux
# o, para desarrollo
pip install -e .
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

Los cambios pequeños del proyecto actual usan una ruta rápida. DevFlux elige internamente el flujo proporcional; no expone roles, planificación ni arquitectura como decisiones de la persona usuaria.

## Archivos y panel derecho

El panel derecho muestra los archivos funcionales creados o modificados y sus diferencias. DevFlux filtra documentos e insumos internos como `PRD.md`, `architecture.md`, `plan.md`, `main.md`, Markdown y diagramas Mermaid: no los escribe ni los muestra como resultado del pedido.

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
│   ├── orchestrator.py  # Enrutamiento conversacional y ruta proporcional
│   ├── runner.py        # Escritura segura de archivos funcionales
│   └── sessions.py      # Registro de sesiones
├── tui/
│   ├── app.py           # Chat, confirmación y diagnóstico
│   └── styles.tcss      # Estilos
├── prompts/             # Plantillas Jinja2 por equipo/rol
└── tests/               # Pruebas de lógica, UX y endurecimiento
```

Para el contrato de mantenimiento destinado a agentes, consultá [`docs/agents/contextual-confirmation.md`](docs/agents/contextual-confirmation.md).
