# Changelog

Todos los cambios notables de DevFlux se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el versionado sigue [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

### Added
- Rediseño UX KISS orientado a usuario final: menú con **Nuevo proyecto**, **Continuar proyecto**, **Ajustes** y **Diagnóstico**, y chat como entrada principal.
- Confirmación humana única para cambios: **[Enter] Aplicar · [Esc] Cambiar pedido**.
- Atajo **Ctrl+D** para consultar diagnóstico sin contaminar la conversación normal.
- Ruta rápida `implementer` para cambios pequeños de proyectos existentes, con prompt empaquetado en la distribución.
- Pruebas de experiencia de usuario para confirmación, preguntas sin pipeline, errores recuperables, ruta rápida, reintentos y filtrado de archivos internos.
- Selector navegable de proveedor y modelo con **↑/↓**, **Enter** y **Esc** durante el asistente inicial y en Ajustes.
- Pruebas del asistente de proveedor/modelo, incluido el flujo sin API key de **Ollama Local** y la selección preestablecida en Ajustes.

### Changed
- Las preguntas se responden como chat; las decisiones internas de router, equipos, roles y complejidad ya no se muestran como opciones de interfaz.
- Los cambios simples se resuelven con una implementación proporcional, sin análisis, arquitectura ni planificación visibles o innecesarios.
- El panel derecho solo muestra archivos funcionales y sus diffs.
- README y guía de agentes describen el contrato KISS, los límites de exposición y las validaciones de mantenimiento.
- El asistente inicial y Ajustes muestran los nombres humanos **Ollama Cloud** y **Ollama Local**; proveedor y modelo ya no se escriben como texto libre.
- **Ollama Cloud** solicita únicamente la API key como campo manual y luego presenta el selector de modelo; **Ollama Local** pasa directamente al selector de modelo.

### Fixed
- Los fallos de conexión o ejecución se muestran como un mensaje humano con reintento, sin URLs, tokens, stack traces o detalles del provider en el chat.
- `PRD.md`, `architecture.md`, `plan.md`, `main.md`, Markdown, Mermaid, documentación y otros artefactos internos se filtran antes de escribir y antes de mostrar resultados.
- Una ejecución que escribe archivos limpia el reintento pendiente, evitando que Enter vacío repita accidentalmente un cambio exitoso.
- Las configuraciones previas con variantes de guiones Unicode se conservan al iniciar y se actualizan de forma segura, sin pedir de nuevo los datos de acceso.

### Previous conversational routing work
- Router LLM conversacional con historial, hilo activo y fallback semántico recuperable; las rutas `MODIFY` y `BUG` siempre requieren confirmación explícita antes de escribir.
