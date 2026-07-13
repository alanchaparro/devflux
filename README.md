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

El flujo usa dos pulsaciones de **Enter** separadas: el **primer Enter** envía la idea y abre el menú de confirmación, sin iniciar un pipeline ni una consulta al LLM; el **segundo Enter** ejecuta la opción que esté resaltada. Usá:

- **↑ / ↓** para mover la selección (la navegación vuelve del último elemento al primero).
- **Enter** (una vez abierto el menú) para ejecutar la opción resaltada.
- **Esc** para cancelar y volver al chat sin ejecutar nada.

| Acción | Resultado |
| --- | --- |
| **Crear proyecto nuevo** | Ejecuta `equipo-dev` para crear un proyecto desde cero. |
| **Modificar proyecto actual** | Primero verifica que el pedido describa un cambio concreto; solo entonces, tras confirmar, ejecuta `equipo-dev` sobre el proyecto existente e incluye la instrucción de reutilizar los archivos y `.devflux/context.md` cuando exista. |
| **Buscar/corregir bugs** | Primero verifica que se haya descrito un error concreto; solo entonces, tras confirmar, ejecuta `equipo-bugs` sobre los archivos existentes. |
| **Responder como pregunta** | Consulta al LLM directamente con el contexto disponible; no ejecuta pipeline. |
| **Reescribir mi idea** | Restaura el texto en el chat para editarlo y volver a enviarlo. |

### Selección contextual predeterminada

La lista completa siempre está disponible; DevFlux solo preselecciona la opción más probable:

1. En una petición de código que describe explícitamente un error o bug, preselecciona **Buscar/corregir bugs**.
2. Si hay archivos de proyecto visibles y el texto pide explícitamente continuar, seguir o retomar un proyecto, preselecciona **Modificar proyecto actual**, incluso si el clasificador lo considera conversación.
3. Si la intención clasificada es una **pregunta** o conversación que no pide continuar un proyecto, preselecciona **Responder como pregunta**.
4. En una petición de código con archivos de proyecto visibles, preselecciona **Modificar proyecto actual**.
5. En un directorio sin archivos de proyecto visibles, preselecciona **Crear proyecto nuevo**.

La detección de proyecto existente usa el inventario de contexto de DevFlux, que excluye metadatos y archivos no confiables como `.git`, `.devflux`, cachés y secretos. La selección sigue siendo una confirmación: tras el primer Enter podés elegir cualquiera de las cinco acciones antes de que se haga una llamada al LLM o se ejecute un pipeline.

### Gate de modificaciones y protección anti-gasto

Al confirmar **Modificar proyecto actual** o **Buscar/corregir bugs**, DevFlux evalúa si el texto es una solicitud implementable:

- **`ACTIONABLE_CHANGE`**: identifica algo para agregar, cambiar, quitar o corregir (por ejemplo, «cambiá el botón principal a verde» o «el contador no incrementa»). DevFlux abre o conserva la confirmación correspondiente; solo el siguiente **Enter** inicia el equipo.
- **`NEEDS_CLARIFICATION`**: el pedido solo expresa intención de continuar, modificar, mejorar o avanzar, sin indicar qué trabajo realizar (por ejemplo, «quiero continuar mi proyecto»). DevFlux pide detalle y queda pendiente: no crea ni ejecuta `PipelineRunner`.

El clasificador recibe el inventario seguro del proyecto y usa una consulta acotada y conservadora (`temperature=0`, hasta 4 tokens y 5 s de espera). Si no hay cliente LLM, falla la consulta o la respuesta no es exactamente `ACTIONABLE_CHANGE`, toma la decisión segura `NEEDS_CLARIFICATION`. Así se evita gastar el presupuesto del pipeline en una tarea ambigua. La respuesta concreta posterior se vuelve a validar, reabre el selector con **Modificar proyecto actual** (o **Buscar/corregir bugs**) seleccionado y todavía requiere una confirmación explícita antes de ejecutar el pipeline.

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
