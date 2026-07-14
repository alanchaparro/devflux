# PRD: DevFlux v1.0

> **Fecha:** 2026-07-08
> **Autor:** Alan Chaparro
> **Stack:** Python 3.11+ | Textual | httpx | Jinja2 | PyYAML | dataclasses

---

## 1. Visión

DevFlux es una **TUI (Terminal User Interface)** para personas que recién empiezan a programar. El usuario describe su idea en un chat, y un **orquestador** automáticamente encadena equipos de agentes IA que entienden la intención, eligen un stack, desarrollan el proyecto, lo prueban, corrigen bugs, y entregan el resultado.

**Cero comandos. Cero configuraciones técnicas. Solo chat.**

```
Usuario: "Quiero una web de recetas de cocina"
   ↓
Orquestador entiende la intención
   ↓
equipo-dev (8 roles) → crea el proyecto
   ↓
equipo-bugs (9 roles) → revisa y corrige
   ↓
Usuario ve su proyecto listo
```

---

## 2. Principios

1. **TUI-first.** No existe CLI. Todo es interfaz visual con paneles, colores, y teclado.
2. **Chat como entrada.** El usuario escribe en lenguaje natural, no comandos.
3. **Orquestador inteligente.** Clasifica la intención, elige el equipo correcto, encadena automáticamente.
4. **UX simple; pipeline interno completo.** El usuario confirma un cambio en lenguaje claro; DevFlux ejecuta internamente los ocho roles sin exponer sus nombres, tiempos ni tokens.
5. **Configuración mínima.** Solo provider (Ollama local o Ollama Cloud) + API key. Nada más.
6. **Código visible.** Panel derecho muestra archivos generados con syntax highlighting y diffs.
7. **Protección anti-errores.** No sobrescribir sin diff, no generar basura, validar outputs.

---

## 3. Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                    DEVLUX TUI                          │
│  ┌───────────────────────┐  ┌─────────────────────────┐│
│  │   Panel Izquierdo     │  │   Panel Derecho         ││
│  │   (Chat + Pipeline)   │  │   (Código + Diffs)      ││
│  │                       │  │                         ││
│  │  "Quiero una web..."  │  │  index.html  [tab]      ││
│  │                       │  │  style.css   [tab]      ││
│  │  Conectando con el    │  │  index.html  [tab]      ││
│  │  modelo...            │  │  style.css   [tab]      ││
│  │                       │  │  script.js   [tab]      ││
│  │  Listo.               │  │  <html>                 ││
│  │                       │  │                         ││
│  │  📁 Tu proyecto está  │  │                         ││
│  │     en ~/mi-web/      │  │                         ││
│  └───────────────────────┘  └─────────────────────────┘│
│  Estado: listo                                           │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Equipos de Agentes

### 4.1 equipo-dev (8 roles) — Crear y modificar proyectos

```
Analista → Arquitecto → Planificador → Backend → Frontend → QA → Reviewer → Integrador
```

| Rol | Función | Entrega |
|-----|---------|---------|
| Analista | Define QUÉ construir | PRD con requisitos, casos de uso, casos borde |
| Arquitecto | Define CÓMO construir | Stack, estructura de archivos, módulos, flujo |
| Planificador | Divide en tareas | Lista de tareas con archivos a crear/modificar |
| Backend | Implementa lógica | Código de backend (o NO_BACKEND si no aplica) |
| Frontend | Implementa interfaz | Código de frontend con HTML/CSS/JS |
| QA | Intenta romper el sistema | Reporte de bugs críticos, warnings, verificación PRD |
| Reviewer | Revisa calidad | Hallazgos críticos/medios/menores |
| Integrador | Une todo y verifica | Cambios aplicados, estado final |

Para cada creación o modificación, esta secuencia es obligatoria y usa un único provider/modelo con prompts especializados en cada paso. Los entregables de análisis, arquitectura, plan, QA y review son internos: se guardan como checkpoints en `~/.devflux/runs/<run-id>/` y nunca se crean en el proyecto. Sólo el integrador puede materializar archivos funcionales candidatos, con protección contra reemplazos destructivos (mínimo 30% del contenido existente).

### 4.2 equipo-bugs (9 roles) — Corregir errores

```
Bug Intake → Reproductor → Logs → Diagnóstico → Fixer → Regression Guard → QA → Reviewer → Integrador
```

| Rol | Función | Entrega |
|-----|---------|---------|
| Bug Intake | Clasifica el bug | Tipo, módulo, prioridad, info faltante |
| Reproductor | Reproduce el error | Pasos exactos, resultado esperado vs actual |
| Logs | Busca evidencia | Logs, stack traces, errores HTTP |
| Diagnóstico | Encuentra causa raíz | Archivo, función, por qué ocurre |
| Fixer | Aplica el fix mínimo | Archivos modificados, cambio, cómo probar |
| Regression Guard | Crea test para evitar regresión | Test que cubre el caso |
| QA | Prueba el fix | Bug corregido, regresiones, pendientes |
| Reviewer | Revisa calidad del fix | Hallazgos, riesgos |
| Integrador | Aplica y verifica | Cambios finales, estado |

### 4.3 equipo-repo (2 roles) — Entender proyectos existentes

```
Repo Inventory → Repo Docs
```

| Rol | Función | Entrega |
|-----|---------|---------|
| Repo Inventory | Inventaría el proyecto | Lenguajes, frameworks, entrypoints, estructura |
| Repo Docs | Documenta para agentes | Mapa de módulos, zonas seguras/peligrosas, guía |

---

## 5. Orquestador

El orquestador es el cerebro. No desarrolla, no corrige bugs, no documenta. **Decide y encadena.**

### 5.1 Flujo de decisión

```
Usuario escribe su pedido
   ↓
INTAKE: entender intención
   ↓
CLASIFICAR:
   ├─ "crear", "hacer", "desarrollar" → equipo-dev → equipo-bugs
   ├─ "bug", "error", "no funciona"   → equipo-bugs
   ├─ "documentar", "analizar repo"   → equipo-repo
   └─ ambiguo                          → preguntar al usuario
   ↓
EJECUTAR equipo(s) en orden
   ↓
CONSOLIDAR resultado
   ↓
ENTREGAR al usuario
```

### 5.2 Encadenamiento automático

- **Feature nueva:** equipo-dev → equipo-bugs (revisión automática)
- **Bug en proyecto existente:** equipo-repo (si no hay memoria) → equipo-bugs
- **Feature en repo desconocido:** equipo-repo → equipo-dev → equipo-bugs

### 5.3 Contexto mínimo

El orquestador no pasa todo el repo a cada agente. Prepara paquetes de contexto mínimo:
- Para equipo-dev: solo el PRD del usuario
- Para equipo-bugs: archivos relevantes + reporte de bug
- Para equipo-repo: estructura del proyecto

---

## 6. Experiencia de Usuario — DevFlux Simple

### 6.1 Regla central

**Una pantalla, una decisión, una acción obvia.** DevFlux no expone equipos de agentes, proveedores, modelos, tokens, rutas internas ni logs como parte del flujo principal. Esos detalles viven en Diagnóstico y sólo aparecen cuando el usuario los pide.

La TUI es una superficie **Command / Inspect**: el teclado hace todo, pero cada estado tiene una única acción primaria inequívoca.

### 6.2 Estados del producto

| Estado | Lo que ve el usuario | Acción primaria |
|---|---|---|
| **Inicio** | Una bienvenida, un campo de idea y proyectos recientes | `Crear proyecto` |
| **Preparar** | Su idea, nombre/carpeta sugeridos y un plan humano de 3 puntos | `Empezar a crear` |
| **Crear** | Progreso humano de cuatro pasos y Cancelar | `Ver detalles` opcional |
| **Listo** | Celebración, ubicación, verificación y tres acciones siguientes | `Abrir proyecto` |

### 6.3 Inicio

```
                         DevFlux
                  De una idea a un proyecto.

              ¿Qué querés crear hoy?

     [ Una app para organizar mis recetas                  ]

     Ej: “Una web simple para mostrar mi cafetería”

                                      [ Crear proyecto → ]

     Recientes
     • Recetas de Sofi          Continuar
     • Landing de cafetería     Continuar
```

No se muestran paneles de código, pipeline, modelo ni menús técnicos antes de que el usuario tenga un proyecto.

### 6.4 Preparar

Después de una idea, DevFlux presenta una confirmación humana, no una clasificación interna:

```
Crear proyecto

“Una app para organizar mis recetas”

Se va a crear:
• Una interfaz para guardar y buscar recetas
• Una estructura simple para crecer después
• Una primera versión que puedas abrir y usar

Carpeta: ~/DevFlux/recetas

[ Cambiar carpeta ]                         [ Empezar a crear → ]
```

Si el pedido es una pregunta, la acción primaria es `Responder ahora`. Si es ambiguo, DevFlux pregunta una sola aclaración en lenguaje natural.

### 6.5 Crear

```
Creando “Recetas”

✓ Entendí tu idea
✓ Preparé la estructura
● Estoy construyendo la primera versión
○ Voy a revisarla antes de entregártela

[ Ver detalles técnicos ]                         [ Cancelar ]
```

Los detalles técnicos pueden mostrar logs, modelo, archivos, diffs y diagnósticos, pero están ocultos por defecto. Cancelar conserva los archivos ya escritos y detiene las etapas restantes de forma segura.

### 6.6 Listo

```
🎉 Tu proyecto está listo

12 archivos creados · Verificación completada
Carpeta: ~/DevFlux/recetas

[ Abrir proyecto ]   [ Ver código ]   [ Pedir una mejora ]
```

`Pedir una mejora` devuelve al chat con el contexto del proyecto activo. El usuario nunca tiene que recordar comandos ni rutas.

### 6.7 Código y detalles

El código aparece sólo después de existir un proyecto. El inspector muestra:
- ruta del archivo y estado (`nuevo`, `modificado`, `revisado`);
- árbol de archivos navegable;
- alternancia entre versión final y diff;
- acciones `Copiar`, `Abrir carpeta` y `Volver al proyecto`.

### 6.8 Configuración y diagnóstico

- Configuración es una pantalla separada, con selector de provider/modelo, campo de clave enmascarado y `Probar conexión`.
- Diagnóstico es opt-in (`Ctrl+D`); allí viven tokens, modelo, errores y logs completos.
- Temas deben cambiar visualmente de verdad o no se ofrecen.
- Todos los flujos se navegan con Tab, flechas, Enter y Escape; los atajos visibles nunca son requisito para entender la interfaz.

### 6.9 Criterios de experiencia

1. Un usuario nuevo puede llegar a `Crear proyecto` sin abrir un menú.
2. La pantalla principal no contiene vocabulario técnico.
3. Cada estado tiene una única acción visual primaria.
4. Ningún mensaje de error muestra una excepción cruda sin una acción humana (`Reintentar`, `Volver` o `Ver detalles`).
5. El progreso evita nombres de agentes y métricas internas.
6. El final siempre ofrece una siguiente acción clara.

---

## 7. Configuración

### 7.1 Providers soportados

| Provider | URL | API Key |
|----------|-----|---------|
| Ollama (local) | `http://localhost:11434/v1` | No requiere |
| Ollama Cloud | `https://ollama.com/v1` | API key |

### 7.2 Archivo de configuración

```yaml
# ~/.devflux/config.yaml (chmod 600)
provider: ollama-cloud
model: deepseek-v4-pro
base_url: https://ollama.com/v1
temperature: 0.7
max_tokens: 4096
```

### 7.3 Primer uso (wizard)

Si no hay configuración, la TUI muestra un wizard:
1. "¿Usás Ollama local o Ollama Cloud?"
2. Si Cloud: "Pegá tu API key"
3. "¿Qué modelo querés usar?" (lista de disponibles)
4. ¡Listo!

---

## 8. Stack Técnico

| Componente | Tecnología | Justificación |
|------------|-----------|---------------|
| Lenguaje | Python 3.11+ | Ecosistema rico, fácil de mantener |
| TUI | Textual | Mejor framework TUI para Python, paneles, tabs, CSS |
| HTTP | httpx | Async, follow_redirects, moderno |
| Templates | Jinja2 | Prompts dinámicos con variables |
| Config | PyYAML + dataclasses | Simple, sin dependencias pesadas |
| Auth | YAML chmod 600 | Sin keyring, sin Fernet, directo |
| CLI entry | argparse | Stdlib, sin Typer |
| Syntax highlight | Pygments (vía Rich) | Ya integrado con Textual |

**Dependencias:** `textual`, `rich`, `httpx`, `jinja2`, `pyyaml` (5 paquetes)

---

## 9. Estructura del Proyecto

```
devflux/
├── pyproject.toml
├── README.md
├── devflux/
│   ├── __init__.py
│   ├── main.py              # Entrypoint: devflux → TUI
│   ├── tui/
│   │   ├── __init__.py
│   │   ├── app.py           # DevFluxApp (Textual)
│   │   ├── chat.py          # Panel izquierdo: chat + pipeline log
│   │   ├── code.py          # Panel derecho: código + diffs
│   │   └── styles.tcss      # Estilos CSS de Textual
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        # DevFluxConfig (dataclass + YAML)
│   │   ├── credentials.py   # API keys (YAML chmod 600)
│   │   ├── client.py        # LLMClient (httpx → Ollama/Ollama Cloud)
│   │   ├── orchestrator.py  # Orquestador: clasifica, encadena, consolida
│   │   └── runner.py        # PipelineRunner: ejecuta roles secuencialmente
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── dev_team.py      # equipo-dev: 8 roles
│   │   ├── bug_team.py      # equipo-bugs: 9 roles
│   │   └── repo_team.py     # equipo-repo: 2 roles
│   └── prompts/
│       ├── dev/              # 8 templates Jinja2 (analista, arquitecto, ...)
│       ├── bug/              # 9 templates Jinja2 (bug-intake, fixer, ...)
│       └── repo/             # 2 templates Jinja2 (inventory, docs)
```

---

## 10. Roadmap

### v0.1 — MVP (2-3 días)
- [x] PRD y arquitectura
- [ ] TUI con Textual: panel chat + panel código
- [ ] Orquestador: clasifica intención, encadena equipos
- [ ] equipo-dev: 8 roles con un solo modelo
- [ ] Configuración: Ollama local + Ollama Cloud
- [ ] Wizard primer uso
- [ ] Extracción de código generado a archivos reales

### v0.2 — Bugs y diffs (2-3 días)
- [ ] equipo-bugs: 9 roles
- [ ] Diffs en panel derecho (rojo/verde)
- [ ] Encadenamiento automático feature→bug
- [ ] Syntax highlighting en panel derecho
- [ ] Protección anti-sobrescritura

### v0.3 — Repos existentes (2-3 días)
- [ ] equipo-repo: 2 roles
- [ ] Memoria de contexto (no releer archivos ya vistos)
- [ ] Modo "conectar repo existente"
- [ ] Git auto-commit después de cada cambio

### v1.0 — Pulido (2-3 días)
- [ ] Resumen final consolidado
- [ ] Menú post-pipeline (modificar, abrir, compartir, salir)
- [ ] Comando `devflux` global (pipx)
- [ ] README + docs en español
- [ ] Publicar en PyPI

---

## 11. Lecciones Aprendidas de DevFlow

| Problema en DevFlow | Solución en DevFlux |
|---------------------|---------------------|
| CLI primero, TUI después | **TUI desde el día 1** |
| OptionList de Textual no captura Enter | **Menú manual con Static + on_key** |
| Bubbling de eventos poco confiable | **Binding con priority=True en el widget correcto** |
| display=False no funciona en Textual | **Usar visible=False o remove()** |
| Protección 30% bloqueaba fixes | **Solo proteger en equipo-dev, no en equipo-bugs** |
| reasoning_content vacío en algunos modelos | **Fallback: usar reasoning si content vacío** |
| CSS_PATH relativo no funciona instalado | **Path(__file__).parent / "styles.tcss"** |
| Thread safety con widgets | **query_one() dentro de cada closure, no capturar widgets** |
| Demasiados reintentos (4) | **Máximo 2 reintentos con backoff** |
| Contexto masivo a cada agente | **Paquetes de contexto mínimo por equipo** |

---

## 12. Diferenciadores vs Competidores

| Herramienta | Tipo | DevFlux |
|-------------|------|---------|
| Claude Code | CLI, inglés, técnico | **TUI, español, junior-friendly** |
| OpenCode | CLI, inglés | **TUI visual, sin comandos** |
| Aider | CLI, git-centric | **No requiere git, crea desde cero** |
| Cursor | GUI, editor | **Terminal, no necesita IDE** |
| v0 / bolt.new | Web, un solo modelo | **Multi-agente, orquestador** |

---

## 13. Métricas de Éxito

- Un junior sin experiencia puede crear un proyecto funcional en < 5 minutos
- El pipeline feature→bug tarda < 3 minutos en total
- 90% de los proyectos generados compilan/abren sin errores
- La TUI funciona en terminal estándar (Windows Terminal, GNOME Terminal, iTerm2)
- Instalación en < 2 minutos (pipx install devflux)
