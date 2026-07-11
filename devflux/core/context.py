"""Session memory — .devflux/context.md in the working directory.

Saves what was generated after each pipeline run, and loads it before
answering questions or running a new pipeline so the LLM has context.

FEATURE: Memoria de sesion
- After pipeline: save_context() writes .devflux/context.md
- Before question: load_context() reads it and returns a system-prompt snippet
- Before pipeline: load_context_files() returns existing files list for the analyst
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def _devflux_dir(cwd: Path | None = None) -> Path:
    """Return the .devflux directory path inside the working directory."""
    base = cwd if cwd is not None else Path.cwd()
    return base.resolve() / ".devflux"


def _context_path(cwd: Path | None = None) -> Path:
    """Return the path to .devflux/context.md."""
    return _devflux_dir(cwd) / "context.md"


def _format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def _detect_stack(files: dict[str, str]) -> str:
    """Detect the technology stack from file extensions."""
    if not files:
        return "(sin detectar)"

    exts = set()
    for fname in files:
        ext = Path(fname).suffix.lstrip(".").lower()
        if ext:
            exts.add(ext)

    stacks: list[str] = []
    if {"html"} & exts:
        if {"css"} & exts:
            if {"js"} & exts:
                stacks.append("HTML + CSS + JavaScript")
            else:
                stacks.append("HTML + CSS")
        elif {"js"} & exts:
            stacks.append("HTML + JavaScript")
        else:
            stacks.append("HTML")
    if {"py"} & exts:
        stacks.append("Python")
    if {"ts", "tsx"} & exts:
        stacks.append("TypeScript")
    elif {"js", "jsx"} & exts and not ({"html"} & exts):
        stacks.append("JavaScript")
    if {"css"} & exts and not ({"html"} & exts):
        stacks.append("CSS")
    if {"json"} & exts:
        stacks.append("JSON")
    if {"yaml", "yml"} & exts:
        stacks.append("YAML")
    if {"sql"} & exts:
        stacks.append("SQL")
    if {"go"} & exts:
        stacks.append("Go")
    if {"rs"} & exts:
        stacks.append("Rust")
    if {"java"} & exts:
        stacks.append("Java")
    if {"c", "cpp", "h"} & exts:
        stacks.append("C/C++")
    if {"php"} & exts:
        stacks.append("PHP")
    if {"rb"} & exts:
        stacks.append("Ruby")

    if not stacks:
        return f"Archivos: {', '.join(sorted(exts))}"

    return " + ".join(stacks)


def _list_project_files(cwd: Path | None = None) -> list[tuple[str, int]]:
    """List all non-hidden files in the working directory (name, size_bytes).

    Returns a list of (relative_path, size_in_bytes) tuples, sorted by name.
    Skips hidden dirs (.devflux, .git, __pycache__, etc.) and binary files.
    """
    base = (cwd if cwd is not None else Path.cwd()).resolve()
    files: list[tuple[str, int]] = []
    if not base.exists():
        return files
    for fpath in base.rglob("*"):
        if not fpath.is_file():
            continue
        rel = fpath.relative_to(base)
        # Skip hidden files/dirs and __pycache__
        if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            continue
        try:
            size = fpath.stat().st_size
        except OSError:
            continue
        rel_str = str(rel).replace("\\", "/")
        files.append((rel_str, size))
    files.sort(key=lambda x: x[0])
    return files


def save_context(
    user_input: str,
    generated_files: dict[str, str] | list[str] | None = None,
    cwd: Path | None = None,
) -> Path:
    """Save or update .devflux/context.md after a pipeline run.

    Args:
        user_input: What the user asked for (the prompt).
        generated_files: Dict of {filename: content} or list of filenames
                         that were generated/modified in this run.
        cwd: Working directory. Defaults to Path.cwd().

    Returns:
        Path to the written context.md file.

    The context file accumulates history across runs — each call appends
    a new entry to the "## Historial" section and updates the file list
    and stack detection.
    """
    base = (cwd if cwd is not None else Path.cwd()).resolve()
    ctx_path = _context_path(cwd)
    devflux_dir = _devflux_dir(cwd)
    devflux_dir.mkdir(parents=True, exist_ok=True)

    # Normalize generated_files to a list of filenames
    if generated_files is None:
        gen_list: list[str] = []
    elif isinstance(generated_files, dict):
        gen_list = list(generated_files.keys())
    else:
        gen_list = list(generated_files)

    # List ALL files currently in the project (not just generated ones)
    all_files = _list_project_files(cwd)

    # Detect stack from all project files
    # Read file contents for stack detection (only need extensions, but
    # _detect_stack works on dict[str, str] — pass a minimal dict)
    ext_dict: dict[str, str] = {fname: "" for fname, _ in all_files}
    stack = _detect_stack(ext_dict)

    # Load existing context to preserve history
    existing_history: list[str] = []
    created_ts: str | None = None
    if ctx_path.exists():
        try:
            old_content = ctx_path.read_text(encoding="utf-8")
            # Extract created timestamp
            for line in old_content.splitlines():
                if line.startswith("- Creado:"):
                    created_ts = line.replace("- Creado:", "").strip()
                    break
            # Extract existing history entries
            in_history = False
            for line in old_content.splitlines():
                if line.strip().startswith("## Historial"):
                    in_history = True
                    continue
                if in_history:
                    if line.strip().startswith("## "):
                        in_history = False
                        break
                    if line.strip() and line.strip()[0].isdigit():
                        existing_history.append(line.strip())
        except Exception:
            pass

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    if created_ts is None:
        created_ts = now_str

    # Build file list section
    file_lines: list[str] = []
    for fname, size in all_files:
        # Try to get a 1-line description from the file content
        desc = _get_file_description(base / fname)
        file_lines.append(f"- {fname} ({_format_size(size)}) — {desc}")

    # Build history entry
    files_str = ", ".join(gen_list) if gen_list else "(sin archivos)"
    history_entry = f"{len(existing_history) + 1}. \"{user_input}\" → genero {files_str}"
    existing_history.append(history_entry)

    # Write context.md
    lines: list[str] = [
        "# DevFlux Context",
        "",
        "## Proyecto",
        f"- Creado: {created_ts}",
        f"- Ultima modificacion: {now_str}",
        "",
        "## Archivos",
    ]
    if file_lines:
        lines.extend(file_lines)
    else:
        lines.append("(sin archivos)")
    lines.append("")
    lines.append("## Stack")
    lines.append(f"- {stack}")
    lines.append("")
    lines.append("## Historial")
    lines.extend(existing_history)
    lines.append("")

    ctx_path.write_text("\n".join(lines), encoding="utf-8")
    return ctx_path


def _get_file_description(fpath: Path) -> str:
    """Extract a 1-line description from a file.

    For code files, tries to find a docstring or comment on the first line.
    For HTML, tries <title>. For others, returns a generic description based on extension.
    """
    ext = fpath.suffix.lstrip(".").lower()
    try:
        content = fpath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return "archivo binario"

    # Limit to first 500 chars for speed
    snippet = content[:500].strip()

    if not snippet:
        return "archivo vacio"

    # Python: look for docstring
    if ext == "py":
        if snippet.startswith('"""') or snippet.startswith("'''"):
            end = snippet.find('"""', 3) if '"""' in snippet[3:8] else snippet.find("'''", 3)
            if end > 0:
                doc = snippet[3:end].strip().split("\n")[0].strip()
                return doc[:80] if doc else "modulo Python"
        if snippet.startswith("#"):
            return snippet.split("\n")[0].lstrip("# ").strip()[:80] or "modulo Python"
        return "modulo Python"

    # HTML: look for <title>
    if ext == "html":
        import re
        m = re.search(r"<title[^>]*>(.*?)</title>", snippet, re.IGNORECASE | re.DOTALL)
        if m:
            title = m.group(1).strip()
            return title[:80] if title else "pagina HTML"
        return "pagina HTML"

    # CSS
    if ext == "css":
        return "hoja de estilos CSS"

    # JS/TS
    if ext in ("js", "ts", "jsx", "tsx"):
        if snippet.startswith("/*") or snippet.startswith("//"):
            first = snippet.split("\n")[0].lstrip("/* ").rstrip("*/").strip()
            return first[:80] if first else f"archivo {ext.upper()}"
        return f"archivo {ext.upper()}"

    # JSON
    if ext == "json":
        return "datos JSON"

    # YAML
    if ext in ("yaml", "yml"):
        return "configuracion YAML"

    # Markdown
    if ext == "md":
        # Use first heading
        for line in snippet.split("\n"):
            line = line.strip()
            if line.startswith("#"):
                return line.lstrip("# ").strip()[:80] or "documento Markdown"
        return "documento Markdown"

    # SQL
    if ext == "sql":
        return "script SQL"

    # Default
    return f"archivo {ext}" if ext else "archivo"


def load_context(cwd: Path | None = None) -> str | None:
    """Load .devflux/context.md and return its full text content.

    Returns None if the file doesn't exist (no prior context).
    """
    ctx_path = _context_path(cwd)
    if not ctx_path.exists():
        return None
    try:
        return ctx_path.read_text(encoding="utf-8")
    except Exception:
        return None


def load_context_for_prompt(cwd: Path | None = None) -> str:
    """Load context and format it as a system-prompt snippet for the LLM.

    This is called BEFORE answering a question (IntentType.QUESTION).
    Returns a string that can be appended to the system prompt.

    If no context exists, returns a minimal "no prior context" string.
    Also includes a live file listing of the current directory.
    """
    ctx_text = load_context(cwd)
    files = _list_project_files(cwd)

    parts: list[str] = []

    if ctx_text:
        # Extract key sections from the context file for the prompt
        parts.append("Contexto del proyecto (de memoria de sesion):")
        parts.append(ctx_text.strip())
    else:
        parts.append("No hay memoria de sesion previa (primer uso en este directorio).")

    # Always add live file listing
    if files:
        files_summary = ", ".join(f"{fname} ({_format_size(size)})" for fname, size in files)
        parts.append(f"\nArchivos actuales en el directorio: {files_summary}")
    else:
        parts.append("\nDirectorio vacio (sin archivos).")

    return "\n".join(parts)


def load_context_files(cwd: Path | None = None) -> list[str]:
    """Return a list of existing file names in the working directory.

    This is called BEFORE running a pipeline (IntentType.CODE) so the
    analyst role knows what files already exist.
    """
    files = _list_project_files(cwd)
    return [fname for fname, _ in files]