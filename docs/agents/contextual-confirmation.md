# Guía para agentes: UX KISS, rutas y límites de exposición

**Estado:** verificado contra `devflux/tui/app.py`, `devflux/core/orchestrator.py`, `devflux/core/runner.py`, `tests/test_user_experience.py` y `tests/test_tui_logic.py` el 2026-07-13.

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
- Al iniciar una ejecución, el único progreso inicial es `Conectando con el modelo...`. No anunciar escritura, actualización ni verificación hasta tener evidencia real de esos pasos.
- Cuando una respuesta contiene archivos funcionales, mostrar `Preparando actualización...` y `Actualizando <archivos reales>...`; después de una escritura con archivos, mostrar una única vez `Verificando cambios...` y finalmente `Listo.`.
- Ante un fallo recuperable, mostrar exactamente el error humano y en una línea separada `> [Enter] Reintentar    [Esc] Cancelar`. Enter relanza una sola vez el último pedido; Esc elimina ese pedido pendiente y devuelve el foco al input.

No introducir en el chat términos internos: nombres de equipos/roles, complejidad, tokens, URL, reintentos automáticos, stack traces, PRD, arquitectura o planes. Los detalles de soporte se registran en diagnóstico; el mensaje de error visible debe seguir `DevFluxApp.human_model_error()` y ofrecer un reintento humano. La conversación no debe decir que se actualizan archivos antes de recibirlos ni incluir tiempos, tokens, URLs o errores técnicos al completar.

## Selector de modelo y proveedor

El asistente inicial y **Ajustes** usan un selector navegable: **↑/↓** cambia la opción y **Enter** la confirma. El asistente inicial cancela al selector de proveedor. **Ajustes** es un `SettingsScreen` modal a pantalla completa: **Esc** o **Cancelar** lo cierran y descartan todo el borrador. Sus listas de proveedor y modelo son `OptionList` desplazables; el proveedor y modelo vigentes deben abrirse resaltados, y **Tab** mueve el foco entre secciones. Las únicas etiquetas visibles son **Ollama Cloud** y **Ollama Local**; no reemplazarlas por claves de configuración ni habilitar un campo de texto para proveedor o modelo.

- **Ollama Cloud** muestra una API key como único campo manual. Es un campo secreto vacío destinado solo a reemplazar la clave existente; jamás precargarla, mostrarla ni registrarla.
- **Ollama Local** no solicita API key y pasa directamente al selector de modelo.
- Al abrir **Ajustes**, el proveedor y modelo en uso deben quedar preseleccionados. No mutar configuración, credenciales ni cliente mientras se navega el borrador: solo **Guardar cambios** persiste proveedor/base URL/modelo, guarda una nueva API key si se ingresó, recrea el cliente y muestra `Ajustes guardados.`.
- Si no se puede cargar un catálogo, ocultar su lista y mostrar un mensaje humano sin detalles técnicos con **Reintentar** y **Volver**; volver descarta el borrador.
- La API key es secreta: no registrarla, interpolarla en mensajes, mostrarla en diagnóstico ni incluirla en pruebas, capturas o documentación. Solo se puede informar si está configurada.

El estado persistido de instalaciones previas debe seguir funcionando aunque contenga variantes tipográficas de guiones; la interfaz continúa usando exclusivamente los nombres humanos anteriores.

## Enrutamiento conversacional

`Orchestrator.route_conversation()` recibe:

1. `conversation`: `conversation_turns` completos y cronológicos.
2. `active_thread`: `none`, `modify`, `bugs` o `question`.
3. `project_context`: contexto seguro preparado por `load_context_for_prompt(Path.cwd())`.
4. `latest_user_message`: el texto recién enviado.

Hace una llamada con `temperature=0`, `max_tokens=128` y `timeout=10`. Acepta `MODIFY`, `BUG`, `QUESTION` o `CLARIFY`, incluido JSON directo/fenced o etiqueta explícita y contenido de campos OpenAI-compatibles como `reasoning_content` o `reasoning`. No añadir fallbacks por palabras aisladas: una ruta mencionada dentro de prosa no es una decisión.

| Ruta | Resultado |
| --- | --- |
| `MODIFY` | Prepara una confirmación única; usa `modify` si existen archivos de proyecto y `create` si no. |
| `BUG` | Prepara una confirmación única para corregir el problema. |
| `QUESTION` | Responde por `_answer_question()`; no ejecuta pipeline. |
| `CLARIFY` | Pide un detalle concreto sin iniciar trabajo. |

Antes de llamar al router se actualiza `conversation_turns`. El hilo activo persiste: una aclaración concreta en un hilo de modificación debe volver a preparar la confirmación y no abrir otro ciclo de preguntas.

Si el router falla, vence el timeout o devuelve una salida inválida, no se muestra el error técnico ni se vuelve a llamar al router. Con un hilo activo se aplica el fallback semántico; sin hilo activo se prepara la confirmación normal. En todos los casos el efecto de escritura sigue requiriendo Enter explícito.

## Pipeline interno obligatorio para creaciones y modificaciones

`Orchestrator.select_user_action(user_input, action)` decide el trabajo interno después de la confirmación:

- Cada `create` o `modify`, sin excepción por tamaño, usa `teams=["dev"]` y la secuencia exacta `analista → arquitecto → planificador → backend → frontend → qa → reviewer → integrador`.
- El mismo provider/modelo atiende los ocho pasos; el runner cambia el prompt y pasa las entregas internas entre roles secuenciales. La complejidad puede ajustar presupuestos, pero nunca acortar, sustituir o reordenar responsabilidades.
- Las preguntas se responden por conversación y no seleccionan ni ejecutan roles. Los bugs explícitos usan equipo-bugs, no equipo-dev.
- No reintroducir `implementer` como ruta productiva ni prometer una cantidad máxima de llamadas, incluso para HTML/CSS/JavaScript o `localStorage`.

No convertir esta decisión en una opción de UI ni mostrar roles o etapas al usuario. La UX KISS conserva la única confirmación humana y acepta conscientemente el mayor tiempo/costo del pipeline completo.

`_last_retry` se arma antes de ejecutar un cambio. `_retry_pending` es el único permiso para que Enter vacío lo relance y se activa exclusivamente tras un fallo recuperable. Al iniciar el reintento se desarma de inmediato, por lo que dos Enter seguidos no duplican la ejecución. Esc limpia ambos estados y enfoca el input. Toda ejecución que escribe archivos limpia ambos antes de completar, para que un Enter vacío posterior nunca repita un cambio exitoso.

## Archivos funcionales y panel derecho

`is_functional_project_file()` es la política única para resultados generados y UI. Un archivo debe ser una ruta relativa segura, no estar dentro de `docs`/`documentation`, no tener extensión `.md`, `.mermaid` o `.mmd`, y no llamarse `prd.md`, `architecture.md`, `plan.md`, `plan.yaml`, `plan.yml`, `main.md`, `qa_report.md`, `review.md`, `integration.md` u `output.html`.

`PipelineRunner.run()` aplica esta política antes de escribir. `DevFluxApp._update_code_panel()` la aplica otra vez antes de mostrar archivos o diffs. Mantener ambas barreras: una salida de modelo no puede escribir ni enseñar documentación o artefactos internos. Sólo el integrador materializa los candidatos funcionales; los demás roles dejan entregas internas. Rechazar un reemplazo con menos de 50 caracteres, más de 50% de líneas vacías o menos de 30% del contenido existente cuando éste tiene tamaño suficiente.

Las respuestas crudas, entregas de cada rol y el checkpoint `state.json` viven exclusivamente en `~/.devflux/runs/<run-id>/`; no crear `.devflux` ni PRD/arquitectura/plan/QA/review/debug dentro del proyecto ni exponer esas rutas en el chat.

## Zonas de cambio y validación

| Responsabilidad | Archivo | Evidencia |
| --- | --- | --- |
| Chat, confirmación, diagnóstico y reintento | `devflux/tui/app.py` | `tests/test_user_experience.py`, `tests/test_tui_logic.py` |
| Selector inicial y modal fullscreen de Ajustes, más compatibilidad de configuración | `devflux/tui/app.py`, `devflux/tui/styles.tcss`, `devflux/core/config.py`, `devflux/core/credentials.py` | `tests/test_provider_wizard.py`, `tests/test_settings_modal.py` |
| Rutas y secuencia obligatoria de 8 roles | `devflux/core/orchestrator.py` | `tests/test_e2e_regressions.py`, `tests/test_eight_role_pipeline.py` |
| Checkpoints, filtrado y escritura exclusiva del integrador | `devflux/core/runner.py` | `tests/test_e2e_regressions.py`, `tests/test_eight_role_pipeline.py`, pruebas de hardening |
| Prompts especializados | `devflux/prompts/dev/{analista,arquitecto,planificador,backend,frontend,qa,reviewer,integrador}.j2` | `tests/test_eight_role_pipeline.py`, build de paquete |
| Distribución de prompts | `pyproject.toml` | `python3 -m build` |

Antes de entregar cambios en este flujo ejecutar:

```bash
python3 -m pytest -q
python3 -m compileall -q devflux
python3 -m build
git diff --check
```

Mantener pruebas para: una sola confirmación; Enter/Esc; preguntas sin pipeline; Ctrl+D; errores humanos sin detalles del provider; la secuencia de progreso sin anuncios falsos; un Enter de reintento sin duplicación; cancelación del reintento; desarme del reintento tras éxito; los ocho roles en orden para create/modify; `NO_BACKEND`/`NO_FRONTEND`; checkpoints sólo bajo `~/.devflux/runs`; escritura exclusiva del integrador con protección de 30%; filtrado de Markdown, Mermaid, PRD, arquitectura, planes, QA y review al escribir y mostrar; y Ajustes fullscreen (preselección, catálogo largo navegable, cancelación sin persistencia, guardado y error de catálogo recuperable).
