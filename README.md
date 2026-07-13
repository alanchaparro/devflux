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

En el primer inicio, un asistente configura el provider (Ollama local u Ollama Cloud).

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
- Si el modelo no está disponible, DevFlux explica el problema sin detalles técnicos y permite reintentar con **Enter**.
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
