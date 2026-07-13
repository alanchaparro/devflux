# Guía para agentes: confirmación contextual

**Estado:** verificado contra `devflux/tui/app.py`, `devflux/core/orchestrator.py` y `tests/test_tui_logic.py` el 2026-07-13.

## Propósito y flujo

El primer **Enter** envía el texto a `DevFluxApp._handle_chat_submit()`, que clasifica la intención y abre el modo de confirmación. Ese mismo evento no puede confirmar la selección recién abierta: no debe iniciarse un pipeline ni una consulta directa hasta un segundo **Enter** (u otra confirmación explícita) sobre el menú.

La función fuente de verdad para la lista y el valor inicial es `confirmation_for_intent()` en `devflux/tui/app.py`. Mantener las cinco acciones, sus etiquetas y el orden sincronizados con esta guía, README, CHANGELOG y pruebas.

## Las cinco acciones

| Acción interna | Etiqueta visible | Efecto real |
| --- | --- | --- |
| `create` | Crear proyecto nuevo | Fuerza `equipo-dev`; conserva el texto original como prompt. |
| `modify` | Modificar proyecto actual | Fuerza `equipo-dev`; antepone instrucciones para modificar archivos existentes, reutilizar `.devflux/context.md` y no crear duplicados innecesarios. |
| `bugs` | Buscar/corregir bugs | Fuerza `equipo-bugs`; sus roles incluyen `bug-intake`. |
| `question` | Responder como pregunta | Llama a `_answer_question()` con el contexto disponible; no arranca `PipelineRunner`. |
| `rewrite` | Reescribir mi idea | No ejecuta LLM ni pipeline; restaura el texto en `#chat-input` para que se edite. |

`Orchestrator.select_team()` conserva el cálculo de complejidad, pero la acción explícita de confirmación determina el equipo. No modificar esa regla sin actualizar pruebas y documentación.

## Selección contextual

Todas las opciones se muestran siempre. La selección inicial se resuelve en este orden:

1. `Orchestrator.is_bug_request(text)` → `bugs`.
2. Si `load_context_files(Path.cwd())` contiene archivos y `is_project_continuation_request(text)` detecta «continuar», «continua», «seguir» o «retomar» junto con «proyecto» → `modify`, incluso si el clasificador devuelve `IntentType.CHAT`.
3. `IntentType.QUESTION` o `IntentType.CHAT` sin petición explícita de continuación → `question`.
4. Si el inventario seguro contiene archivos → `modify`.
5. En cualquier otro caso → `create`.

El inventario debe continuar excluyendo metadatos, cachés y secretos; `.git` o `.devflux` por sí solos no convierten un directorio vacío en un proyecto existente.

## Teclado y cancelación

Durante `_confirm_mode` (es decir, después del primer Enter):

- **↑** y **↓** cambian `_confirm_selected` con recorrido circular y vuelven a dibujar el menú.
- El **segundo Enter** ejecuta la opción resaltada. El binding prioritario `action_submit_input()` delega a `_handle_confirm_select()` solo cuando `_confirm_mode` ya era verdadero al recibir el evento; `on_key()` no procesa Enter, evitando que el Enter de envío se reutilice como confirmación.
- **Esc** llama a `_cancel_confirmation()`: sale de confirmación, no ejecuta trabajo y devuelve el foco al chat.

Al abrir la confirmación, `_handle_chat_submit()` deja `is_running` sin cambios (`False` cuando no había trabajo en curso). `_handle_confirm_select()` es el único paso que lo pone en `True` para `create`, `modify`, `bugs` o `question`; `rewrite` y `Esc` no arrancan trabajo.

## Archivos y validación mínima

- Lógica de interfaz y despacho: `devflux/tui/app.py`.
- Detección de bug y equipo explícito: `devflux/core/orchestrator.py`.
- Cobertura principal: `tests/test_tui_logic.py`.

Al cambiar este flujo, ejecutar como mínimo:

```bash
uv run pytest -q
python3 -m compileall devflux
uv build
```

Además, verificar de forma headless que ↑/↓ cambia la opción, el primer Enter abre la confirmación sin iniciar un pipeline, el segundo Enter ejecuta la resaltada y Esc cancela sin iniciar un pipeline. Cubrir el caso de «quiero continuar mi proyecto» con un `index.html` existente: debe preseleccionar `modify` y mantener `is_running == False` hasta el segundo Enter. Documentar cualquier cambio de orden, atajo o prioridad de selección en `README.md` y `CHANGELOG.md`.
