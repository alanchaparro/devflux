# Guía para agentes: confirmación contextual

**Estado:** verificado contra `devflux/tui/app.py`, `devflux/core/orchestrator.py` y `tests/test_tui_logic.py` el 2026-07-13.

## Propósito y flujo

Después de que la persona usuaria envía texto, `DevFluxApp._handle_chat_submit()` clasifica la intención y abre el modo de confirmación. No debe iniciarse un pipeline ni una consulta directa hasta que se seleccione una opción.

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

1. `IntentType.QUESTION` o `IntentType.CHAT` → `question`.
2. Si la intención restante es código y `Orchestrator.is_bug_request(text)` es verdadera → `bugs`.
3. Si el inventario seguro `load_context_files(Path.cwd())` contiene archivos → `modify`.
4. En cualquier otro caso → `create`.

El inventario debe continuar excluyendo metadatos, cachés y secretos; `.git` o `.devflux` por sí solos no convierten un directorio vacío en un proyecto existente.

## Teclado y cancelación

Durante `_confirm_mode`:

- **↑** y **↓** cambian `_confirm_selected` con recorrido circular y vuelven a dibujar el menú.
- **Enter** ejecuta la opción resaltada. El binding prioritario `action_submit_input()` también delega a `_handle_confirm_select()` para que Enter funcione aunque el foco siga en el input.
- **Esc** llama a `_cancel_confirmation()`: sale de confirmación, no ejecuta trabajo y devuelve el foco al chat.

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

Además, verificar de forma headless que ↑/↓ cambia la opción, Enter ejecuta la resaltada y Esc cancela sin iniciar un pipeline. Documentar cualquier cambio de orden, atajo o prioridad de selección en `README.md` y `CHANGELOG.md`.
