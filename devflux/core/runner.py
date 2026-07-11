"""PipelineRunner — executes roles sequentially with retry, extraction, garbage filter, and protection."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Callable

import jinja2

from .client import LLMClient, LLMResponse
from .config import DevFluxConfig

# Lesson 16: Never run in the code's own directory
DEVFLUX_SRC_DIR = Path(__file__).resolve().parent.parent  # devflux/ package root

# --- Jinja2 environment ---

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_prompt(template_name: str, **kwargs: Any) -> str:
    """Render a Jinja2 template from prompts/ dir."""
    try:
        tmpl = _jinja_env.get_template(template_name)
        return tmpl.render(**kwargs)
    except jinja2.TemplateNotFound:
        # Fallback: generic prompt if template missing
        role = template_name.replace(".j2", "").split("/")[-1]
        return f"Eres {role}. El usuario pide: {kwargs.get('user_input', '')}\n\nGenera el codigo completo necesario."


# --- Garbage filter (Lesson 13) ---

# BUG FIX: Reduced garbage list — only truly useless filenames.
# Previously rejected .txt, .sh, readme.md, etc. which was too aggressive
# and caused the pipeline to generate 0 files when the LLM produced valid output.
GARBAGE_FILES = {
    "output", "output.text", "output.txt", "output.md",
    "result", "result.txt",
    "main.txt",
    "run.bat", "start.bat",
}
GARBAGE_PATTERNS = [
    # Only markdown without code blocks
    re.compile(r"^[^`]*$", re.MULTILINE),  # no backticks at all
]


def is_garbage(filename: str, content: str) -> bool:
    """Check if a file is garbage and should be rejected (Lesson 13).

    BUG FIX: Relaxed — no longer rejects .txt, .sh, or readme.md wholesale.
    Only rejects truly empty/placeholder content and a few known junk filenames.
    """
    fname_lower = filename.lower().strip()

    # Reject known garbage filenames (reduced list)
    if fname_lower in GARBAGE_FILES:
        return True

    # Reject empty content
    if not content.strip():
        return True

    stripped = content.strip()

    # Reject if it's just placeholder text
    if stripped.lower() in ("todo", "placeholder", "lorem ipsum", "n/a"):
        return True

    # Reject if content is too short to be meaningful (< 20 chars)
    if len(stripped) < 20:
        return True

    return False


# --- Code extraction ---

# BUG FIX: More robust code block regex — handles Windows line endings,
# optional language tag, and trailing whitespace/newlines.
CODE_BLOCK_RE = re.compile(
    r"```(?:[a-zA-Z0-9_+#-]*)?\s*\r?\n(.*?)```",
    re.DOTALL,
)

# BUG FIX: More patterns for filename detection.
# The LLM might use various formats:
#   Archivo: name
#   File: name
#   Fichero: name
#   **name**
#   ### name
#   # name
#   filename: name
FILE_HEADER_PATTERNS = [
    re.compile(r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:Archivo|File|Fichero|Filename|Nombre)\s*:\s*([^\n]+)", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*\*\*([^*\n]+?)\*\*\s*\n", re.MULTILINE),
    re.compile(r"(?:^|\n)\s*#{1,3}\s+([^\n`#]+?)(?:\s*\{[^}]*\})?\s*\n", re.MULTILINE),
]

# Debug directory for raw LLM responses
DEBUG_DIR = Path.home() / ".devflux"
DEBUG_LAST_RESPONSE = DEBUG_DIR / "debug_last_response.txt"


def _save_debug_response(role: str, content: str) -> None:
    """Save raw LLM response to debug file for diagnostics."""
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LAST_RESPONSE, "w", encoding="utf-8") as f:
            f.write(f"=== DevFlux Debug: Last LLM Response ===\n")
            f.write(f"Role: {role}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Content length: {len(content)} chars\n")
            f.write(f"Has code blocks: {'YES' if '```' in content else 'NO'}\n")
            f.write(f"{'='*60}\n\n")
            f.write(content)
            f.write(f"\n\n{'='*60}\n")
            f.write(f"END OF RESPONSE\n")
    except Exception:
        pass  # Debug logging should never crash the pipeline


def _guess_extension_from_content(content: str, role: str = "") -> str:
    """Guess file extension from content heuristics."""
    stripped = content.strip().lower()

    # Check first non-empty line for clues
    first_line = ""
    for line in content.split("\n"):
        line = line.strip()
        if line:
            first_line = line.lower()
            break

    # HTML detection
    if "<!doctype html" in stripped[:200] or "<html" in stripped[:200]:
        return "html"
    if first_line.startswith("<!doctype") or first_line.startswith("<html"):
        return "html"

    # CSS detection
    if "{" in stripped and "}" in stripped and (":" in stripped) and not ("function" in stripped or "def " in stripped):
        # Check if it looks like CSS (selectors with {})
        css_indicators = ["font-", "margin", "padding", "color:", "background", "display:", "flex", "grid"]
        if any(ind in stripped for ind in css_indicators):
            return "css"

    # JS detection
    if any(kw in stripped[:500] for kw in ["const ", "let ", "var ", "function ", "import ", "export ", "require("]):
        return "js"

    # Python detection
    if any(kw in stripped[:500] for kw in ["def ", "class ", "import ", "from ", "print(", "__name__"]):
        return "py"

    # JSON detection
    if stripped.startswith("{") and stripped.endswith("}"):
        return "json"
    if stripped.startswith("[") and stripped.endswith("]"):
        return "json"

    # YAML detection
    if ":" in stripped and not stripped.startswith("{") and not stripped.startswith("<"):
        yaml_lines = [l for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
        if yaml_lines and all(":" in l for l in yaml_lines[:5]):
            return "yaml"

    # Markdown detection
    if stripped.startswith("#") or "**" in stripped[:200]:
        return "md"

    # SQL detection
    if any(kw in stripped[:200] for kw in ["select ", "create table", "insert into", "update ", "delete from"]):
        return "sql"

    # Default: based on role
    role_map = {
        "analista": "md",
        "arquitecto": "md",
        "planificador": "md",
        "frontend": "html",
        "backend": "py",
        "qa": "md",
        "reviewer": "md",
        "integrador": "md",
    }
    return role_map.get(role, "txt")


def _extract_filename_from_header(lines: list[str], block_start_idx: int) -> str | None:
    """Try to extract a filename from headers before a code block."""
    # Look backwards up to 15 lines
    for j in range(block_start_idx - 1, max(block_start_idx - 15, -1), -1):
        prev = lines[j].strip()
        if not prev:
            continue

        # Pattern 1: "Archivo: name" / "File: name" / "Fichero: name" / "Filename: name"
        m = re.match(r"(?:#{0,3}\s*)?(?:Archivo|File|Fichero|Filename|Nombre)\s*:\s*(.+)", prev, re.IGNORECASE)
        if m:
            fname = m.group(1).strip()
            fname = fname.replace("\\", "/").split("/")[-1]
            fname = fname.replace("`", "").strip()
            if fname:
                return fname

        # Pattern 2: "**filename.ext**" (bold markdown)
        m = re.match(r"\*\*([^*\n]+?)\*\*$", prev)
        if m:
            fname = m.group(1).strip()
            if "." in fname and not fname.startswith("."):
                return fname

        # Pattern 3: "# filename" or "## filename" (markdown heading)
        m = re.match(r"#{1,3}\s+([^\n`#]+)$", prev)
        if m:
            fname = m.group(1).strip()
            # Only use as filename if it looks like a filename (has extension)
            if "." in fname and not fname.startswith(".") and len(fname) < 80:
                return fname

    return None


def extract_files(content: str, role: str = "") -> dict[str, str]:
    """Extract code files from LLM output.

    BUG FIX: Completely rewritten for robustness.
    - Handles fenced code blocks with filename headers
    - Falls back to saving entire response as a file if no code blocks found
    - Auto-detects file type from content heuristics
    - Saves debug output to ~/.devflux/debug_last_response.txt

    Returns dict[filename -> content].
    """
    files: dict[str, str] = {}

    if not content or not content.strip():
        return files

    # Save debug response
    _save_debug_response(role, content)

    lines = content.split("\n")
    in_block = False
    block_lines: list[str] = []
    block_lang = ""
    current_filename: str | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect start of code fence
        if stripped.startswith("```") and not in_block:
            in_block = True
            block_lang = stripped[3:].strip().lower()
            block_lines = []
            # Try to find filename from headers before this block
            current_filename = _extract_filename_from_header(lines, i)
            continue

        # Detect end of code fence
        if stripped.startswith("```") and in_block:
            in_block = False
            block_content = "\n".join(block_lines).strip()

            if not block_content:
                current_filename = None
                block_lang = ""
                block_lines = []
                continue

            # Determine filename
            fname: str | None = None

            if current_filename:
                fname = current_filename
            elif block_lang:
                # Auto-generate from language
                ext_map = {
                    "python": "py", "py": "py",
                    "javascript": "js", "js": "js", "jsx": "jsx",
                    "typescript": "ts", "ts": "ts", "tsx": "tsx",
                    "html": "html", "css": "css",
                    "bash": "sh", "sh": "sh", "shell": "sh",
                    "json": "json", "yaml": "yaml", "yml": "yaml",
                    "xml": "xml", "sql": "sql",
                    "java": "java", "c": "c", "cpp": "cpp",
                    "go": "go", "rust": "rs", "php": "php",
                    "ruby": "rb", "markdown": "md", "md": "md",
                    "dockerfile": "dockerfile", "docker": "dockerfile",
                    "makefile": "makefile", "toml": "toml",
                    "ini": "ini", "cfg": "cfg", "conf": "conf",
                    "env": "env", "txt": "txt",
                }
                ext = ext_map.get(block_lang)
                if ext:
                    fname = f"main.{ext}"
                else:
                    fname = f"main.{block_lang}"
            else:
                # No language, no filename — guess from content
                ext = _guess_extension_from_content(block_content, role)
                fname = f"main.{ext}"

            if fname and fname.lower() not in GARBAGE_FILES and not is_garbage(fname, block_content):
                files[fname] = block_content

            current_filename = None
            block_lang = ""
            block_lines = []
            continue

        if in_block:
            block_lines.append(line)

    # BUG FIX: Fallback — if no code blocks found, save entire response as a file.
    # This handles roles like analista/arquitecto that produce markdown documents
    # without code fences.
    if not files:
        ext = _guess_extension_from_content(content, role)
        # Generate a meaningful filename based on role
        role_to_fname = {
            "analista": f"PRD.{ext}",
            "arquitecto": f"architecture.{ext}",
            "planificador": f"plan.{ext}",
            "qa": f"qa_report.{ext}",
            "reviewer": f"review.{ext}",
            "integrador": f"integration.{ext}",
        }
        fname = role_to_fname.get(role, f"output.{ext}")

        if not is_garbage(fname, content):
            files[fname] = content

    return files


# --- Pipeline Runner ---


class PipelineRunner:
    """Runs a pipeline of roles sequentially against an LLM."""

    def __init__(
        self,
        client: LLMClient,
        config: DevFluxConfig,
        callback: Callable[[str, str, dict[str, Any] | None], None] | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._callback = callback or (lambda role, status, data: None)
        self.total_tokens: int = 0
        self.total_elapsed: float = 0.0
        self.files: dict[str, str] = {}

    def run(
        self,
        roles: list[str],
        user_input: str,
        teams: list[str] | None = None,
        cwd: Path | None = None,
    ) -> dict[str, str]:
        """Run a list of roles sequentially.

        Lesson 11: roles is an arbitrary list (SIMPLE=2, MEDIUM=6, COMPLEX=8).
        Lesson 16: never run in devflux's own source dir.
        Lesson 17: files go in Path.cwd(), run dirs in ~/.devflux/runs/.

        BUG FIX: Load existing files from disk at start so the LLM can modify
        them. Write files to disk after EACH role (not just at the end).
        Removed 30% protection — it was a no-op and the concept is wrong:
        when the user asks for modifications, files MUST be overwritten.

        Returns dict of extracted files.
        """
        teams = teams or []

        # Lesson 16: anti-destruction protection
        if cwd is None:
            cwd = Path.cwd()
        cwd_resolved = cwd.resolve()
        if str(DEVFLUX_SRC_DIR) in str(cwd_resolved):
            raise RuntimeError(
                "Negandose a ejecutar en el directorio del codigo fuente de DevFlux "
                f"({DEVFLUX_SRC_DIR}). Use un directorio de trabajo diferente."
            )

        # BUG 1 FIX: Load existing files from disk so the LLM knows what to modify.
        # This is critical for second runs where the user asks for modifications.
        # We also track which files existed BEFORE this run so the callback can
        # show diffs (FEATURE 1).
        existing_on_disk: dict[str, str] = {}
        for fpath in cwd_resolved.rglob("*"):
            if not fpath.is_file():
                continue
            # Skip hidden files, __pycache__, .git, etc.
            rel = fpath.relative_to(cwd_resolved)
            if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
                continue
            # Only load text files (skip binary)
            try:
                content = fpath.read_text(encoding="utf-8")
                existing_on_disk[str(rel).replace("\\", "/")] = content
            except (UnicodeDecodeError, OSError):
                continue

        # Track which files existed before the run (for diff display)
        files_before_run: set[str] = set(existing_on_disk.keys())

        # FEATURE: Memoria de sesion — load .devflux/context.md for history
        session_history: str = ""
        context_md_path = cwd_resolved / ".devflux" / "context.md"
        if context_md_path.exists():
            try:
                session_history = context_md_path.read_text(encoding="utf-8")
            except Exception:
                session_history = ""

        # Build context for each role, starting with files already on disk
        context: dict[str, Any] = {
            "user_input": user_input,
            "previous_roles": [],
            "accumulated_files": dict(existing_on_disk),
            "files_before_run": files_before_run,
            "session_history": session_history,
        }

        for role in roles:
            self._callback(role, "start", None)

            # Render prompt for this role
            prompt = render_prompt(
                f"dev/{role}.j2",
                user_input=user_input,
                previous_summary=self._summarize_context(context),
                existing_files=dict(context["accumulated_files"]),
                session_history=context.get("session_history", ""),
            )

            # Build messages
            messages = [
                {"role": "system", "content": f"Eres el agente '{role}' del equipo DevFlux. Responde en español. Genera codigo completo y funcional."},
                {"role": "user", "content": prompt},
            ]

            # Call LLM with retry (Lesson: max 2 retries with backoff)
            response = self._call_with_retry(messages)

            self.total_tokens += response.tokens
            self.total_elapsed += response.elapsed

            # DEBUG: Save raw LLM response for diagnostics
            debug_dir = cwd_resolved / ".devflux"
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / f"debug_{role}_response.txt"
            try:
                debug_file.write_text(response.content, encoding="utf-8")
            except Exception:
                pass

            # Extract files from response
            new_files = extract_files(response.content, role=role)

            # Apply garbage filter
            filtered: dict[str, str] = {}
            for fname, fcontent in new_files.items():
                if not is_garbage(fname, fcontent):
                    filtered[fname] = fcontent
                else:
                    self._callback(role, "garbage", {"file": fname})

            # Accumulate (overwrite existing files — user asked for modifications)
            context["accumulated_files"].update(filtered)
            context["previous_roles"].append({
                "role": role,
                "tokens": response.tokens,
                "elapsed": response.elapsed,
                "files_extracted": list(filtered.keys()),
            })

            # BUG 1 FIX: Capture old content BEFORE overwriting on disk.
            # FEATURE 1: Pass old content to callback so the TUI can show a diff.
            file_diffs: dict[str, str] = {}  # fname -> old content (if file existed)
            for fname, fcontent in filtered.items():
                fpath = cwd_resolved / fname
                old = None
                if fpath.exists():
                    try:
                        old = fpath.read_text(encoding="utf-8")
                    except Exception:
                        old = None
                if old is not None and old != fcontent:
                    file_diffs[fname] = old

            # Debug: log diff info to callback
            if file_diffs:
                self._callback(role, "info", {"message": f"Diff: {len(file_diffs)} archivo(s) modificado(s): {', '.join(file_diffs.keys())}"})

            # BUG 1 FIX: Write files to disk AFTER EACH ROLE (not just at the end).
            # This ensures:
            # 1. Files survive even if the pipeline crashes later
            # 2. Subsequent roles can read them from disk
            # 3. The TUI can show diffs against the actual disk content
            for fname, fcontent in filtered.items():
                fpath = cwd_resolved / fname
                fpath.parent.mkdir(parents=True, exist_ok=True)
                with open(fpath, "w", encoding="utf-8") as fh:
                    fh.write(fcontent)

            # Callback with results
            # FEATURE 1: include file_diffs so the TUI can show red/green diff
            self._callback(role, "done", {
                "tokens": response.tokens,
                "elapsed": response.elapsed,
                "files": list(filtered.keys()),
                "file_contents": dict(filtered),
                "file_diffs": file_diffs,
                "content_preview": response.content[:200],
            })

        self.files = context["accumulated_files"]

        # FEATURE 2: Chain equipo-bugs integrity check after dev pipeline
        if "dev" in teams and self.files:
            self._callback("equipo-bugs", "start", None)
            self._callback("equipo-bugs", "info", {"message": "Verificando integridad del proyecto..."})
            integrity_issues = self._run_integrity_check(cwd_resolved)
            if integrity_issues:
                self._callback("equipo-bugs", "issues", {"issues": integrity_issues})
            self._callback("equipo-bugs", "done", {
                "message": "Integridad OK" if not integrity_issues else f"Integridad: {len(integrity_issues)} problemas",
            })

        return self.files

    def _run_integrity_check(self, cwd: Path) -> list[dict[str, str]]:
        """FEATURE 2: Run a programmatic integrity check on generated files.

        Checks:
        - Python files: py_compile
        - HTML files: basic tag balance
        - JS files: basic brace balance
        - JSON files: json.loads
        - YAML files: yaml.safe_load

        Returns list of issues found (empty list = all OK).
        """
        import json as json_module
        import py_compile as py_compile_module
        import yaml as yaml_module

        issues: list[dict[str, str]] = []

        for fpath in cwd.rglob("*"):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(cwd)
            # Skip hidden/devflux dirs
            if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
                continue
            rel_str = str(rel).replace("\\", "/")
            ext = fpath.suffix.lstrip(".")

            try:
                content = fpath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # Python: py_compile check
            if ext == "py":
                try:
                    py_compile_module.compile(str(fpath), doraise=True)
                except py_compile_module.PyCompileError as exc:
                    issues.append({
                        "file": rel_str,
                        "type": "python_syntax",
                        "detail": str(exc),
                    })

            # HTML: basic tag balance
            elif ext == "html":
                # Count opening and closing tags for major elements
                open_tags = re.findall(r"<(?:div|span|ul|ol|li|table|tr|td|th|form|select|body|head|html|script|style)\b[^>]*>", content, re.IGNORECASE)
                close_tags = re.findall(r"</(?:div|span|ul|ol|li|table|tr|td|th|form|select|body|head|html|script|style)\s*>", content, re.IGNORECASE)
                if len(open_tags) != len(close_tags):
                    issues.append({
                        "file": rel_str,
                        "type": "html_tag_balance",
                        "detail": f"Tags abiertos: {len(open_tags)}, cerrados: {len(close_tags)}",
                    })
                # Check for unclosed script/style tags
                if content.count("<script") > content.count("</script>"):
                    issues.append({
                        "file": rel_str,
                        "type": "html_unclosed_script",
                        "detail": f"Scripts abiertos: {content.count('<script')}, cerrados: {content.count('</script>')}",
                    })

            # JS: basic brace balance
            elif ext in ("js", "ts", "jsx", "tsx"):
                open_braces = content.count("{")
                close_braces = content.count("}")
                open_parens = content.count("(")
                close_parens = content.count(")")
                if open_braces != close_braces:
                    issues.append({
                        "file": rel_str,
                        "type": "js_brace_balance",
                        "detail": f"Llaves: {open_braces} abiertas, {close_braces} cerradas",
                    })
                if open_parens != close_parens:
                    issues.append({
                        "file": rel_str,
                        "type": "js_paren_balance",
                        "detail": f"Parentesis: {open_parens} abiertos, {close_parens} cerrados",
                    })

            # JSON: json.loads
            elif ext == "json":
                try:
                    json_module.loads(content)
                except json_module.JSONDecodeError as exc:
                    issues.append({
                        "file": rel_str,
                        "type": "json_parse",
                        "detail": str(exc),
                    })

            # YAML: yaml.safe_load
            elif ext in ("yaml", "yml"):
                try:
                    yaml_module.safe_load(content)
                except yaml_module.YAMLError as exc:
                    issues.append({
                        "file": rel_str,
                        "type": "yaml_parse",
                        "detail": str(exc),
                    })

        return issues

    def _call_with_retry(self, messages: list[dict[str, str]], max_retries: int = 2) -> LLMResponse:
        """Call LLM with up to 2 retries and backoff.

        BUG FIX: Surface errors to callback instead of silently returning empty.
        """
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return self._client.chat(messages)
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    time.sleep(1.0 * (attempt + 1))  # backoff: 1s, 2s
                    continue
                # Last attempt failed — surface the error to the UI
                error_msg = str(last_exc)
                self._callback("__error__", "error", {"message": error_msg})
                raise RuntimeError(f"LLM fallo despues de {max_retries + 1} intentos: {error_msg}") from last_exc
        # Should not reach here, but just in case
        error_msg = str(last_exc) if last_exc else "unknown error"
        self._callback("__error__", "error", {"message": error_msg})
        raise RuntimeError(f"LLM fallo: {error_msg}")

    @staticmethod
    def _summarize_context(context: dict[str, Any]) -> str:
        """Build a summary of previous roles for the next role's prompt."""
        lines: list[str] = []
        for entry in context.get("previous_roles", []):
            files_str = ", ".join(entry.get("files_extracted", [])) or "(sin archivos)"
            lines.append(f"- {entry['role']}: {entry['tokens']} tokens, {entry['elapsed']:.1f}s, archivos: {files_str}")
        if not lines:
            return "(sin roles previos)"
        return "\n".join(lines)