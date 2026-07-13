# Guía para agentes: UX KISS, rutas y límites de exposición

**Estado:** verificado contra `devflux/tui/app.py`, `devflux/core/orchestrator.py`, `devflux/core/runner.py` y `tests/test_user_experience.py` el 2026-07-13.

## Contrato visible para la persona usuaria

DevFlux es una conversación, no un selector de equipos. El menú solo ofrece **Nuevo proyecto**, **Continuar proyecto**, **Ajustes** y **Diagnóstico**. Cada pedido de cambio llega a una sola confirmación humana:

```text
[Enter] Aplicar · [Esc] Cambiar pedido
```

- El primer Enter envía el mensaje y puede consultar el router; nunca inicia un pipeline por sí solo.
- El segundo Enter aplica el único cambio propuesto.
- Esc cancela la confirmación y conserva el chat para reformular el pedido.
- Una pregunta se responde en el chat sin crear `PipelineRunner`.
- Ctrl+D es el único acceso normal al panel de diagnóstico.

No introducir en el chat ni en el menú términos internos: nombres de equipos/roles, complejidad, tokens, proveedor, modelo, URL, reintentos automáticos, stack traces, PRD, arquitectura o planes. Los detalles de soporte se registran en diagnóstico; el mensaje de error visible debe seguir `DevFluxApp.human_model_error()` y ofrecer un reintento humano.

## Enrutamiento conversacional

`Orchestrator.route_conversation()` recibe:

1. `conversation`: `conversation_turns` completos y cronológicos.
2. `active_thread`: `none`, `modify`, `bugs` o `question`.
3. `project_context`: contexto seguro preparado por `load_context_for_prompt(Path.cwd())`.
4. `latest_user_message`: el texto recién enviado.

Hace una llamada con `temperature=0`, `max_tokens=32` y `timeout=10`. Acepta `MODIFY`, `BUG`, `QUESTION` o `CLARIFY`, incluido JSON directo/fenced o etiqueta explícita y contenido de campos OpenAI/DeepSeek como `reasoning_content`. No añadir fallbacks por palabras aisladas: una ruta mencionada dentro de prosa no es una decisión.

| Ruta | Resultado |
| --- | --- |
| `MODIFY` | Prepara una confirmación única; usa `modify` si existen archivos de proyecto y `create` si no. |
| `BUG` | Prepara una confirmación única para corregir el problema. |
| `QUESTION` | Responde por `_answer_question()`; no ejecuta pipeline. |
| `CLARIFY` | Pide un detalle concreto sin iniciar trabajo. |

Antes de llamar al router se actualiza `conversation_turns`. El hilo activo persiste: una aclaración concreta en un hilo de modificación debe volver a preparar la confirmación y no abrir otro ciclo de preguntas.

Si el router falla, vence el timeout o devuelve una salida inválida, no se muestra el error técnico ni se vuelve a llamar al router. Con un hilo activo se aplica el fallback semántico; sin hilo activo se prepara la confirmación normal. En todos los casos el efecto de escritura sigue requiriendo Enter explícito.

## Ruta de implementación proporcional

`Orchestrator.select_user_action(user_input, action)` decide el trabajo interno después de la confirmación:

- Un `modify` sin señales de alcance amplio usa `teams=["dev"]`, `Complexity.SIMPLE` y el único rol `implementer`.
- Pedidos amplios o explícitamente complejos conservan el flujo de desarrollo normal.
- Los bugs usan el flujo de bugs.

No convertir esta decisión en una opción de UI ni mostrar roles o etapas al usuario. El prompt `dev/implementer.j2` debe pedir solo el mínimo de archivos funcionales necesario y no planes, documentación o diagnósticos.

`_last_retry` se arma antes de ejecutar un cambio y permite Enter vacío solo tras un fallo recuperable. Toda ejecución que escribe archivos debe limpiarlo antes de completar, para que un Enter vacío posterior nunca repita un cambio exitoso.

## Archivos funcionales y panel derecho

`is_functional_project_file()` es la política única para resultados generados y UI. Un archivo debe ser una ruta relativa segura, no estar dentro de `docs`/`documentation`, no tener extensión `.md`, `.mermaid` o `.mmd`, y no llamarse `prd.md`, `architecture.md`, `plan.md`, `main.md`, `qa_report.md`, `review.md` o `integration.md`.

`PipelineRunner.run()` aplica esta política antes de escribir. `DevFluxApp._update_code_panel()` la aplica otra vez antes de mostrar archivos o diffs. Mantener ambas barreras: una salida de modelo no puede escribir ni enseñar documentación o artefactos internos.

## Zonas de cambio y validación

| Responsabilidad | Archivo | Evidencia |
| --- | --- | --- |
| Chat, confirmación, diagnóstico y reintento | `devflux/tui/app.py` | `tests/test_user_experience.py`, `tests/test_tui_logic.py` |
| Rutas y fast path | `devflux/core/orchestrator.py` | `tests/test_user_experience.py` |
| Filtrado y escritura | `devflux/core/runner.py` | `tests/test_user_experience.py`, pruebas de hardening |
| Prompt de edición rápida | `devflux/prompts/dev/implementer.j2` | build de paquete |
| Distribución de prompts | `pyproject.toml` | `python3 -m build` |

Antes de entregar cambios en este flujo ejecutar:

```bash
python3 -m pytest -q
python3 -m compileall -q devflux
python3 -m build
git diff --check
```

Mantener pruebas para: una sola confirmación; Enter/Esc; preguntas sin pipeline; Ctrl+D; errores humanos sin detalles del provider; desarme del reintento tras éxito; fast path; y filtrado de Markdown, Mermaid, PRD, arquitectura y planes al escribir y mostrar.
