# Changelog

Todos los cambios notables de DevFlux se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado sigue [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added
- Router LLM conversacional para proyectos existentes: recibe el historial `conversation_turns`, `active_thread` (`none|modify|bugs|question`), el contexto seguro del proyecto y el último mensaje; devuelve `MODIFY`, `BUG`, `QUESTION` o `CLARIFY` como JSON o etiqueta simple.
- Cobertura del router para historial/contexto, seguimiento concreto de una aclaración, preguntas dentro de un hilo de modificación y fallos recuperables.
- Documentación humana y guía de agentes del contrato conversacional, selección por hilo y garantías anti-loop/anti-auto-pipeline.
- Menú contextual de confirmación con cinco acciones explícitas antes de ejecutar una solicitud: crear proyecto, modificar el proyecto actual, buscar/corregir bugs, responder como pregunta y reescribir la idea.
- Navegación de confirmación mediante **↑/↓**, selección mediante **Enter** y cancelación mediante **Esc**.

### Changed
- Se reemplazó el gate aislado `ACTIONABLE_CHANGE`/`NEEDS_CLARIFICATION` por enrutamiento conversacional basado en el hilo completo; una petición concreta posterior vuelve a abrir **Modificar proyecto actual** sin repetir aclaración.
- El router usa `temperature=0`, hasta 32 tokens y 10 s de espera; las decisiones `MODIFY` y `BUG` siguen requiriendo confirmación explícita antes de ejecutar un equipo.
- La confirmación fuerza el equipo elegido por la persona usuaria: `equipo-dev` para crear o modificar y `equipo-bugs` para corregir errores.
- La opción de modificación añade instrucciones para reutilizar el proyecto y su contexto, evitando archivos duplicados innecesarios.

### Fixed
- Un error, timeout, ausencia de cliente o salida inválida del router ahora usa el hilo semántico activo: `modify` → **Modificar proyecto actual**, `bugs` → **Buscar/corregir bugs** y `question` → respuesta directa. No expone errores técnicos, no repite el selector y nunca inicia `PipelineRunner` sin el Enter de confirmación; sin hilo activo muestra el selector normal, también sin errores crudos.
- El router es más tolerante con respuestas DeepSeek/OpenAI: extrae `content`, `reasoning` y datos crudos como `reasoning_content`; acepta JSON, JSON fenced y etiquetas explícitas. Cada respuesta del router queda disponible para diagnóstico en `.devflux/debug_classify.txt` sin afectar la interacción.
- El **primer Enter** que envía una idea enruta el turno pero no puede confirmar la selección ni arrancar equipos automáticamente; el **segundo Enter** confirma la acción resaltada.
- **Esc** ahora cancela correctamente la confirmación contextual pese al binding prioritario global de la TUI.
