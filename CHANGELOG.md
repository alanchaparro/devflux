# Changelog

Todos los cambios notables de DevFlux se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado sigue [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added
- Pipeline obligatorio de equipo-dev para cada creación o modificación: `analista → arquitecto → planificador → backend → frontend → qa → reviewer → integrador`, con el mismo provider/modelo y prompts secuenciales por rol.
- Checkpoints y capturas internas por ejecución en `~/.devflux/runs/<run-id>/state.json`; no se escriben PRD, arquitectura, plan, QA, review ni diagnósticos dentro del proyecto.
- Pruebas de regresión post-E2E para respuestas de proveedor en `message.reasoning`, el pipeline de ocho roles, protección contra reemplazos destructivos y aislamiento de diagnósticos fuera del proyecto.
- Rediseño UX KISS orientado a usuario final: menú con **Nuevo proyecto**, **Continuar proyecto**, **Ajustes** y **Diagnóstico**, y chat como entrada principal.
- Confirmación humana única para cambios: **[Enter] Aplicar · [Esc] Cambiar pedido**.
- Atajo **Ctrl+D** para consultar diagnóstico sin contaminar la conversación normal.
- Pruebas de experiencia de usuario para confirmación, preguntas sin pipeline, errores recuperables, reintentos y filtrado de archivos internos.
- Selector navegable de proveedor y modelo con **↑/↓**, **Enter** y **Esc** durante el asistente inicial y en Ajustes.
- Pruebas del asistente de proveedor/modelo, incluido el flujo sin API key de **Ollama Local** y la selección preestablecida en Ajustes.
- Editor de **Ajustes** a pantalla completa, con listas de proveedor y catálogo de modelos navegables/desplazables, modelo activo resaltado y controles de guardar o cancelar.
- Pruebas de la pantalla completa de Ajustes: cancelación sin persistencia, guardado de proveedor/modelo/API key secreta, catálogo extenso y error recuperable al cargar modelos.

### Changed
- El router reserva 128 tokens para completar su decisión JSON y reconoce respuestas de proveedores que ponen el contenido de razonamiento en `message.reasoning` o `message.reasoning_content`.
- Toda creación o modificación, incluso una app web estática pequeña, usa los ocho roles completos; se elimina la ruta productiva de implementador único y cualquier garantía de dos llamadas al modelo.
- Sólo el integrador materializa candidatos funcionales al proyecto; las propuestas de backend/frontend permanecen internas hasta entonces y se rechazan reemplazos demasiado cortos o fragmentarios.
- Los diagnósticos, respuestas crudas y checkpoints de cada ejecución se aíslan bajo `~/.devflux/runs/<run-id>/`, fuera del directorio del proyecto.
- Las preguntas se responden como chat; las decisiones internas de router, equipos, roles y complejidad ya no se muestran como opciones de interfaz.
- Los roles internos no se exponen en la UX KISS aunque el pipeline completo sea obligatorio; las preguntas no ejecutan roles y los bugs explícitos mantienen su flujo equipo-bugs.
- El panel derecho solo muestra archivos funcionales y sus diffs.
- README y guía de agentes describen el contrato KISS, los límites de exposición y las validaciones de mantenimiento.
- El asistente inicial y Ajustes muestran los nombres humanos **Ollama Cloud** y **Ollama Local**; proveedor y modelo ya no se escriben como texto libre.
- **Ollama Cloud** solicita únicamente la API key como campo manual y luego presenta el selector de modelo; **Ollama Local** pasa directamente al selector de modelo.
- **Ajustes** conserva los cambios como borrador hasta **Guardar cambios**; al guardar reconstruye el cliente con la configuración confirmada y avisa `Ajustes guardados.`. **Esc** y **Cancelar** descartan el borrador.

### Fixed
- Se bloquean también `plan.yaml`, `plan.yml` y `output.html` como artefactos internos: nunca se escriben ni se muestran como resultado funcional.
- Los fallos de conexión o ejecución se muestran como un mensaje humano con reintento, sin URLs, tokens, stack traces o detalles del provider en el chat.
- El progreso ya no anuncia una actualización antes de recibir archivos reales: la secuencia visible es **Conectando con el modelo...**, los archivos concretos a actualizar, **Verificando cambios...** y **Listo.**
- Tras un fallo recuperable, **Enter** reintenta una sola vez el último pedido y **Esc** lo cancela; una ejecución exitosa desarma el reintento para impedir repeticiones accidentales.
- `PRD.md`, `architecture.md`, `plan.md`, `main.md`, Markdown, Mermaid, documentación y otros artefactos internos se filtran antes de escribir y antes de mostrar resultados.
- Una ejecución que escribe archivos limpia el reintento pendiente, evitando que Enter vacío repita accidentalmente un cambio exitoso.
- Las configuraciones previas con variantes de guiones Unicode se conservan al iniciar y se actualizan de forma segura, sin pedir de nuevo los datos de acceso.

### Previous conversational routing work
- Router LLM conversacional con historial, hilo activo y fallback semántico recuperable; las rutas `MODIFY` y `BUG` siempre requieren confirmación explícita antes de escribir.
