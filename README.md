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

El flujo usa dos pulsaciones de **Enter** separadas: el **primer Enter** añade el turno a la conversación y lo enruta con un LLM, pero **nunca** inicia un pipeline; el **segundo Enter** ejecuta la opción que esté resaltada. Usá:

- **↑ / ↓** para mover la selección (la navegación vuelve del último elemento al primero).
- **Enter** (una vez abierto el menú) para ejecutar la opción resaltada.
- **Esc** para cancelar y volver al chat sin ejecutar nada.

| Acción | Resultado |
| --- | --- |
| **Crear proyecto nuevo** | Ejecuta `equipo-dev` para crear un proyecto desde cero. |
| **Modificar proyecto actual** | Cuando el router devuelve `MODIFY` y hay archivos de proyecto, abre `equipo-dev` tras la confirmación; el prompt pide reutilizar los archivos y `.devflux/context.md` cuando exista. |
| **Buscar/corregir bugs** | Cuando el router devuelve `BUG`, abre `equipo-bugs` tras la confirmación. |
| **Responder como pregunta** | Consulta al LLM directamente con el contexto disponible; no ejecuta pipeline. |
| **Reescribir mi idea** | Restaura el texto en el chat para editarlo y volver a enviarlo. |

### Router conversacional y garantías anti-loop

Cada envío llama a `Orchestrator.route_conversation()` con cuatro fuentes: todos los `conversation_turns` de la sesión, `active_thread` (`none`, `modify`, `bugs` o `question`), el resumen seguro de `.devflux/context.md` y el inventario de archivos, y el último mensaje. El router devuelve solo `MODIFY`, `BUG`, `QUESTION` o `CLARIFY` (JSON estricto o etiqueta simple), con `temperature=0`, hasta 32 tokens y espera máxima de 10 s.

- **`MODIFY`** abre la confirmación de modificación si existe un proyecto, o de creación en un directorio vacío. Un detalle posterior concreto —por ejemplo, «que el fondo tenga burbujas animadas que al clicar cambien de color»— se reconoce como `MODIFY` dentro del hilo `modify`; no repite la aclaración.
- **`BUG`** abre la confirmación de `equipo-bugs`; **`QUESTION`** responde directamente sin `PipelineRunner`.
- **`CLARIFY`** se reserva para mensajes sin una modificación implementable ni una pregunta contestable, como «quiero continuar» sin detalles. Conserva el hilo `modify` o `bugs` y solicita precisión sin lanzar equipos.
- Si el router no tiene cliente, vence el tiempo, falla o devuelve una salida inválida, DevFlux muestra alternativas explícitas **Modify** y **Question**. No reintenta el router, no entra en un loop de aclaración y no inicia automáticamente un pipeline.

La selección sigue siendo una confirmación: salvo preguntas, ningún equipo se ejecuta hasta un Enter posterior sobre la opción resaltada. El inventario excluye `.git`, `.devflux`, cachés y secretos, por lo que esos metadatos no convierten un directorio vacío en proyecto existente.

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
