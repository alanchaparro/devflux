# Changelog

Todos los cambios notables de DevFlux se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado sigue [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added
- Menú contextual de confirmación con cinco acciones explícitas antes de ejecutar una solicitud: crear proyecto, modificar el proyecto actual, buscar/corregir bugs, responder como pregunta y reescribir la idea.
- Navegación de confirmación mediante **↑/↓**, selección mediante **Enter** y cancelación mediante **Esc**.
- Selección predeterminada según intención y contexto: pregunta/conversación, solicitud de bug, proyecto existente o directorio vacío.
- Pruebas para las cinco acciones, las selecciones predeterminadas y el envío con Enter.
- Gate conservador para modificaciones y bugs en proyectos existentes: clasifica cada pedido como `ACTIONABLE_CHANGE` o `NEEDS_CLARIFICATION` con el contexto seguro del proyecto, `temperature=0`, hasta 4 tokens y 5 s de espera.
- Estado pendiente de aclaración que conserva la acción elegida y, al recibir un pedido concreto, vuelve a abrir el selector con esa acción preseleccionada.

### Changed
- La confirmación fuerza el equipo elegido por la persona usuaria: `equipo-dev` para crear o modificar y `equipo-bugs` para corregir errores.
- La opción de modificación añade instrucciones para reutilizar el proyecto y su contexto, evitando archivos duplicados innecesarios.
- Las solicitudes vagas de modificación o bugs ahora solicitan qué agregar, cambiar o corregir antes de consumir el presupuesto de `PipelineRunner`; la ejecución sigue requiriendo confirmación explícita.

### Fixed
- Ante ausencia o error del LLM, timeout o una salida distinta de `ACTIONABLE_CHANGE`, el gate aplica el fallback seguro `NEEDS_CLARIFICATION` y no inicia un pipeline.

- **Esc** ahora cancela correctamente la confirmación contextual pese al binding prioritario global de la TUI.
- El **primer Enter** que envía una idea ahora solo abre la confirmación; ya no puede confirmar esa misma selección y arrancar `equipo-dev` automáticamente. El **segundo Enter** confirma la acción resaltada.
- Cuando hay un proyecto existente y el texto pide continuar, seguir o retomar ese proyecto, se preselecciona **Modificar proyecto actual** y `is_running` permanece en `false` hasta la confirmación explícita.
