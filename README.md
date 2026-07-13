# DevFlux

TUI multi-agente para crear proyectos y trabajar sobre proyectos existentes. Escribí tu idea en el chat y DevFlux clasifica la intención; antes de ejecutar, muestra un menú contextual para que confirmes o corrijas la acción.

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

En el primer inicio, un wizard guía la configuración del provider (Ollama local u Ollama Cloud).

## Menú contextual de confirmación

Al enviar un mensaje con **Enter**, DevFlux no inicia un pipeline de inmediato: presenta cinco acciones y resalta una selección contextual. Usá:

- **↑ / ↓** para mover la selección (la navegación vuelve del último elemento al primero).
- **Enter** para ejecutar la opción resaltada.
- **Esc** para cancelar y volver al chat sin ejecutar nada.

| Acción | Resultado |
| --- | --- |
| **Crear proyecto nuevo** | Ejecuta `equipo-dev` para crear un proyecto desde cero. |
| **Modificar proyecto actual** | Ejecuta `equipo-dev` sobre el proyecto existente, incluyendo la instrucción de reutilizar los archivos y `.devflux/context.md` cuando exista. |
| **Buscar/corregir bugs** | Ejecuta `equipo-bugs` sobre los archivos existentes. |
| **Responder como pregunta** | Consulta al LLM directamente con el contexto disponible; no ejecuta pipeline. |
| **Reescribir mi idea** | Restaura el texto en el chat para editarlo y volver a enviarlo. |

### Selección contextual predeterminada

La lista completa siempre está disponible; DevFlux solo preselecciona la opción más probable:

1. Si la intención clasificada es una **pregunta** o conversación, preselecciona **Responder como pregunta**.
2. En una petición de código que describe explícitamente un error o bug, preselecciona **Buscar/corregir bugs**.
3. En una petición de código con archivos de proyecto visibles, preselecciona **Modificar proyecto actual**.
4. En un directorio sin archivos de proyecto visibles, preselecciona **Crear proyecto nuevo**.

La detección de proyecto existente usa el inventario de contexto de DevFlux, que excluye metadatos y archivos no confiables como `.git`, `.devflux`, cachés y secretos. La selección sigue siendo una confirmación: podés elegir cualquiera de las cinco acciones antes de que se haga una llamada al LLM o se ejecute un pipeline.

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
│   ├── config.py        # DevFluxConfig (dataclass + YAML)
│   ├── credentials.py   # CredentialsStore (API keys, chmod 600)
│   ├── client.py        # LLMClient (httpx, OpenAI-compatible)
│   ├── context.py       # Inventario y contexto seguro del proyecto
│   ├── orchestrator.py  # Clasificación de intención, complejidad y equipos
│   ├── runner.py        # PipelineRunner (roles, retry, extracción y protección)
│   └── sessions.py      # SessionRecord + save/list
├── tui/
│   ├── app.py           # DevFluxApp y menú contextual de confirmación
│   └── styles.tcss      # Estilos
├── prompts/             # Plantillas Jinja2 por equipo/rol
└── tests/               # Pruebas de lógica y endurecimiento
```

Para detalles de implementación y validación del menú contextual, ver [`docs/agents/contextual-confirmation.md`](docs/agents/contextual-confirmation.md).
