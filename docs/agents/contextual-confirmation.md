# Guía para agentes: router conversacional y confirmación

**Estado:** verificado contra `devflux/tui/app.py`, `devflux/core/orchestrator.py` y `tests/test_tui_logic.py` el 2026-07-13.

## Contrato del router

`Orchestrator.route_conversation()` es la fuente de verdad para enrutar cada envío de chat en un proyecto existente. Recibe:

1. `conversation`: todos los `conversation_turns` acumulados, en orden cronológico.
2. `active_thread`: `none`, `modify`, `bugs` o `question`.
3. `project_context`: resumen seguro de `.devflux/context.md` e inventario preparado por `load_context_for_prompt(Path.cwd())`.
4. `latest_user_message`: el último texto enviado.

Usa una única llamada LLM con `temperature=0`, `max_tokens=32` y `timeout=10`. La instrucción exige JSON `{"route":"MODIFY|BUG|QUESTION|CLARIFY"}`. Para proveedores compatibles con DeepSeek/OpenAI, el parser reúne `content`, `reasoning` y campos de `raw` como `choices[0].message.reasoning_content`; acepta JSON directo, JSON dentro de bloques Markdown y etiquetas explícitas (por ejemplo, `Final: MODIFY`). No agregar heurísticas de palabras clave como fallback: una palabra de ruta mencionada incidentalmente en prosa no decide la conversación.

`RouterResult` contiene una ruta válida (`ConversationRoute`) o un `error` recuperable. Las rutas son:

| Ruta | Efecto en `DevFluxApp` |
| --- | --- |
| `MODIFY` | Con archivos existentes, abre confirmación con `modify` seleccionado; en directorio vacío, selecciona `create`. Marca el hilo `modify`. |
| `BUG` | Abre confirmación con `bugs` seleccionado y marca el hilo `bugs`. |
| `QUESTION` | Marca el hilo `question` y llama `_answer_question()`; no crea `PipelineRunner`. |
| `CLARIFY` | Mantiene/abre el hilo `modify` (o `bugs` si era el activo), muestra `_show_clarification()` y no inicia trabajo. |

## Invariantes conversacionales

- `conversation_turns` se actualiza **antes** de llamar al router. Una aclaración concreta conserva el pedido anterior en el transcript.
- `active_thread` persiste entre turnos. Por ello, tras «quiero hacer modificaciones en mi proyecto», una respuesta como «que el fondo tenga burbujas animadas que al clicar cambien de color» debe resolver `MODIFY`, abrir el selector **Modificar proyecto actual** y no volver a pedir aclaración.
- `CLARIFY` solo corresponde si no hay un objetivo implementable ni una pregunta contestable. No usarlo solo porque falte un verbo técnico.
- El primer **Enter** puede consultar el router, pero no inicia un pipeline. Para `MODIFY` y `BUG`, un segundo Enter sobre la confirmación sigue siendo obligatorio.
- `QUESTION` es la única ruta que responde directamente; no debe iniciar equipos ni `PipelineRunner`.

## Garantías de fallo y anti-loop

Si no existe cliente LLM, vence el timeout, ocurre una excepción o la salida no es una ruta válida, `route_conversation()` devuelve `RouterResult(error=...)`; el detalle técnico solo se registra para diagnóstico. `_apply_conversation_route()` debe entonces:

1. Si hay `active_thread`, aplicar el fallback semántico sin volver a clasificar: `modify` → `MODIFY`, `bugs` → `BUG`, `question` → `QUESTION`.
2. Para `modify` o `bugs`, abrir **una** confirmación con la acción del hilo resaltada; para `question`, responder directamente sin `PipelineRunner`.
3. Si el hilo es `none`, abrir el selector contextual normal. No mostrar el error técnico, habilitar `_router_error_mode` ni forzar al usuario a repetir la selección.

La confirmación sigue siendo obligatoria para los efectos de `modify` y `bugs`: el primer Enter que envía el mensaje solo abre el menú, y el Enter posterior ejecuta la opción resaltada. Esta recuperación no reintenta el router, no entra en un loop de aclaración/selector y no lanza equipos automáticamente. `_debug_log_router()` guarda por turno la respuesta cruda y las partes analizadas en `.devflux/debug_classify.txt`; un fallo de ese log nunca afecta la interacción.

## Acciones de confirmación

`confirmation_for_intent()` conserva cinco acciones y sus etiquetas visibles: `create`, `modify`, `bugs`, `question` y `rewrite`. La acción confirmada, no una clasificación secundaria, determina el equipo:

- `create` y `modify` fuerzan `equipo-dev`.
- `bugs` fuerza `equipo-bugs`.
- `question` usa `_answer_question()` sin pipeline.
- `rewrite` restaura el texto sin llamar LLM ni pipeline.

El inventario de proyecto debe excluir `.git`, `.devflux`, cachés y secretos; esos directorios por sí solos no habilitan `modify`.

## Archivos y validación obligatoria

- Router, `ConversationRoute` y `RouterResult`: `devflux/core/orchestrator.py`.
- Estado de sesión, aplicación de rutas y confirmación: `devflux/tui/app.py`.
- Cobertura de comportamiento: `tests/test_tui_logic.py`.

Al cambiar este flujo, ejecutar:

```bash
python3 -m pytest -q
python3 -m compileall -q devflux
python3 -m build
```

Además de la suite, mantener casos para: envío de conversación/contexto al router; respuestas DeepSeek en `reasoning`/`reasoning_content`, JSON fenced y etiquetas explícitas sin falsos positivos por palabras aisladas; el seguimiento concreto que no repite `CLARIFY`; fallback por hilo `modify`/`bugs`/`question` sin error técnico ni pipeline; fallo sin hilo que muestra el selector normal; primer Enter sin pipeline; segundo Enter con acción explícita; y `Esc` sin trabajo.
