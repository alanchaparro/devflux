# DevFlux — Pendientes de producto

> Documento de continuidad para terminar el rediseño de DevFlux como una experiencia guiada y simple.
>
> Última actualización: 2026-07-14

## Objetivo de UX

El recorrido principal debe sentirse así:

```text
Inicio → Preparar → Crear → Listo
```

Regla: **una pantalla, una decisión, una acción obvia**.

La experiencia principal no debe exigir que la persona entienda roles, proveedores, modelos, tokens, logs, terminal ni rutas internas. Ese detalle queda disponible únicamente bajo Diagnóstico o Ajustes avanzados.

---

## Ya terminado

### Inicio y preparación

- Inicio enfocado en una sola pregunta: “¿Qué querés crear?”.
- El panel de código y los diagnósticos no distraen al iniciar.
- El wizard inicial entra directamente a DevFlux después de elegir proveedor y modelo; no requiere reinicio.
- Para proyectos nuevos se propone una carpeta segura a partir de la idea.
- La carpeta se muestra antes de crear y pasa a ser el proyecto activo.

### Creación

- Progreso resumido y humano durante la generación.
- Cancelación cooperativa entre etapas: conserva archivos ya creados y no inicia la siguiente etapa.
- Logs técnicos disponibles sólo como diagnóstico opt-in.

### Cierre e inspector

- El cierre muestra archivos creados, carpeta y próximos pasos.
- `Ctrl+O` abre la carpeta del proyecto activo.
- `Ctrl+E` revela y enfoca el inspector de código.
- El inspector explica si el archivo es nuevo/actualizado o si muestra cambios respecto a la versión previa.

### Calidad y protección existente

- Contexto acotado y filtrado de secretos/artefactos.
- Rutas de archivos generados protegidas contra traversal y paths absolutos.
- Templates explícitos por rol y defensa básica frente a instrucciones insertadas en archivos del proyecto.

---

## Pendiente — prioridad de implementación

## 1. Completar el inspector de código

**Meta:** que un usuario no técnico pueda entender qué se creó y navegarlo sin conocer la estructura interna.

- [x] Reemplazar la lista plana por árbol de archivos y carpetas.
- [x] Mostrar estado por archivo: `Nuevo`, `Modificado`, `Revisado`.
- [x] Permitir alternar claramente entre resultado final y diff cuando ambos existan.
- [x] Agregar acciones seguras y explícitas: copiar contenido y abrir archivo/carpeta.
- [x] Mantener el inspector oculto hasta que haya archivos reales.

**Archivos probables:**

- `devflux/tui/app.py`
- `devflux/tui/styles.tcss`
- `tests/test_user_experience.py`

**Validación:** tests Textual para árbol, selección, estado y alternancia de versión; luego `python -m pytest -q`.

---

## 2. Convertir “Pedir una mejora” en una acción real

**Meta:** que el cierre de un proyecto tenga un siguiente paso directo.

- [x] Agregar acción/atajo visible para `Pedir una mejora`.
- [x] Volver al input principal sin perder la carpeta activa.
- [x] Enfocar el input y mostrar un copy concreto, por ejemplo: “¿Qué querés cambiar de este proyecto?”.
- [x] Enviar la instrucción como modificación del proyecto activo, no como proyecto nuevo.

**Archivos probables:**

- `devflux/tui/app.py`
- `tests/test_user_experience.py`

**Validación:** prueba de que la acción enfoca el input, conserva `_active_project_dir` y clasifica el siguiente pedido como modificación.

---

## 3. Proyectos recientes utilizables

**Meta:** reemplazar sesiones técnicas por una lista de proyectos que se pueda continuar.

- [x] Diseñar una tarjeta/lista de recientes con nombre, cantidad de archivos y fecha.
- [x] Agregar acción `Continuar`.
- [x] Al continuar, restaurar la carpeta activa y mostrar el inspector sólo si hay archivos.
- [x] Mantener detalles de sesión internos fuera de la vista principal.

**Archivos a investigar/modificar:**

- `devflux/core/sessions.py`
- `devflux/tui/app.py`
- `tests/test_user_experience.py`
- pruebas de sesiones existentes bajo `tests/`

**Decisión requerida al implementar:** definir si una sesión representa una carpeta existente, un snapshot, o ambas cosas. No inventar una fuente de verdad adicional.

---

## 4. Ajustes y temas

**Meta:** que Ajustes no compita con el flujo de crear.

- [x] Mantener proveedor/modelo/diagnóstico bajo una superficie avanzada discreta.
- [x] Revisar el selector de temas: implementar 2–3 temas que cambien realmente la interfaz o retirar temporalmente la opción.
- [x] Eliminar opciones nominales o redundantes del menú principal.
- [x] Verificar navegación keyboard-first y retorno claro a Inicio.

**Archivos probables:**

- `devflux/tui/app.py`
- `devflux/tui/styles.tcss`
- pruebas TUI correspondientes

---

## 5. Validación final del producto

**Meta:** verificar el recorrido completo, no sólo funciones aisladas.

- [x] Prueba guiada: Inicio → Preparar → Crear → Listo.
- [x] Prueba de cancelación durante Crear.
- [x] Prueba de abrir proyecto y ver código.
- [x] Prueba de pedir una mejora sobre el proyecto activo.
- [x] Prueba de reabrir un proyecto reciente.
- [x] Revisión visual manual de la TUI antes de declarar terminado el rediseño.
- [x] Ejecutar `python -m pytest -q` y `python -m compileall -q devflux`.

---

## Criterio de terminado

El rediseño se considera terminado cuando una persona puede:

1. Contar qué quiere crear en lenguaje natural.
2. Ver y confirmar claramente dónde se creará.
3. Entender el progreso sin leer logs técnicos.
4. Cancelar sin miedo a perder lo ya hecho.
5. Abrir, explorar y modificar el proyecto generado.
6. Reabrir un proyecto reciente.

Todo sin tener que aprender cómo funciona el pipeline interno.
