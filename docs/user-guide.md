# DevFlux — Guía de usuario

DevFlux es una aplicación de terminal para crear, continuar, revisar y mejorar proyectos de software conversando en lenguaje natural. La persona usuaria describe lo que necesita; DevFlux confirma la intención, ejecuta su flujo interno y entrega archivos funcionales en una carpeta de proyecto.

## Flujo principal

```text
Inicio → Preparar → Crear → Listo
```

La interfaz evita exponer roles internos, tokens, prompts, rutas técnicas o detalles del proveedor durante el uso normal.

## Requisitos

- Python 3.11 o superior. Verificá con `python --version` o `python3 --version`.
- `pip` disponible. Verificá con `python -m pip --version`.
- Una terminal compatible con aplicaciones TUI.
- Ollama Cloud con API key u Ollama Local disponible.

## Instalación

### Instalación recomendada con pipx

```bash
pipx install devflux
```

Si tu sistema responde `pipx: command not found` o no reconoce `pipx`, instalalo antes:

```bash
python -m pip install --user pipx
python -m pipx ensurepath
```

Cerrá y abrí la terminal, y verificá:

```bash
pipx --version
```

Si tu sistema usa `python3` en vez de `python`, reemplazá los comandos anteriores por `python3 -m pip ...` y `python3 -m pipx ...`.

### Alternativa sin pipx

Si no podés usar `pipx`, instalá DevFlux en un entorno virtual:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install devflux
devflux
```

En Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install devflux
devflux
```

### Desarrollo local

```bash
git clone <repo-url>
cd devflux
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

En Windows, activá el entorno con `.venv\\Scripts\\activate`.

## Primer inicio

1. Ejecutá `devflux`.
2. Elegí **Ollama Cloud** u **Ollama Local** con `↑/↓`.
3. Confirmá con `Enter`.
4. Si elegiste Cloud, pegá la API key.
5. Elegí el modelo.
6. DevFlux entra a la pantalla principal.

La API key se guarda de forma privada y no se muestra en la interfaz ni en diagnósticos.

## Uso básico

### Crear un proyecto

Escribí una idea, por ejemplo:

```text
Quiero una web simple para registrar recetas familiares
```

DevFlux muestra una confirmación clara y la carpeta donde creará el proyecto. Presioná `Enter` para aplicar o `Esc` para cambiar el pedido.

### Continuar un proyecto

Elegí **Continuar proyecto** en el menú principal. DevFlux muestra proyectos recientes con nombre, cantidad de archivos, fecha y acción para continuar. Al continuar, restaura la carpeta activa y el inspector si hay archivos.

### Pedir una mejora

Con un proyecto activo, usá `Ctrl+R`. DevFlux conserva la carpeta activa y pregunta:

```text
¿Qué querés cambiar de este proyecto?
```

El siguiente pedido se trata como modificación del proyecto activo.

### Hacer preguntas

Podés preguntar por el proyecto sin ejecutar escritura de archivos, por ejemplo:

```text
¿Qué archivos tiene este proyecto y para qué sirve cada uno?
```

## Atajos

| Atajo | Acción |
| --- | --- |
| `Enter` | Enviar mensaje o aplicar confirmación. |
| `Esc` | Cancelar menú/confirmación o volver al input. |
| `Ctrl+S` | Abrir/cerrar menú. |
| `Ctrl+D` | Mostrar/ocultar Diagnóstico. |
| `Ctrl+E` | Mostrar inspector de código. |
| `Ctrl+O` | Abrir carpeta activa. |
| `Ctrl+R` | Pedir mejora sobre el proyecto activo. |
| `Ctrl+T` | Cambiar tema visual. |
| `Ctrl+C` | Solicitar cancelación segura de una generación. |

En el inspector: `j`/`↓` y `k`/`↑` navegan archivos, `d` alterna diff/final, `c` copia contenido y `o` abre el archivo seleccionado.

## Privacidad y diagnósticos

Los diagnósticos, respuestas crudas y checkpoints por rol se guardan fuera del proyecto en `~/.devflux/runs/<run-id>/`. El chat normal no expone URLs internas, tokens, stack traces, prompts ni API keys.

## Desarrollo y validación

```bash
python -m pytest -q
python -m compileall -q devflux
```
