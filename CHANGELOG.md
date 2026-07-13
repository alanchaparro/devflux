# Changelog

Todos los cambios notables de DevFlux se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado sigue [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added
- Menú contextual de confirmación con cinco acciones explícitas antes de ejecutar una solicitud: crear proyecto, modificar el proyecto actual, buscar/corregir bugs, responder como pregunta y reescribir la idea.
- Navegación de confirmación mediante **↑/↓**, selección mediante **Enter** y cancelación mediante **Esc**.
- Selección predeterminada según intención y contexto: pregunta/conversación, solicitud de bug, proyecto existente o directorio vacío.
- Pruebas para las cinco acciones, las selecciones predeterminadas y el envío con Enter.

### Changed
- La confirmación fuerza el equipo elegido por la persona usuaria: `equipo-dev` para crear o modificar y `equipo-bugs` para corregir errores.
- La opción de modificación añade instrucciones para reutilizar el proyecto y su contexto, evitando archivos duplicados innecesarios.

### Fixed
- **Esc** ahora cancela correctamente la confirmación contextual pese al binding prioritario global de la TUI.
