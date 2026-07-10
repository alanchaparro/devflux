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

GARBAGE_FILES = {"output", "output.text", "output.txt", "output.md", "readme.md", "result", "result.txt"}
GARBAGE_PATTERNS = [
    # Only markdown without code blocks
    re.compile(r"^[^`]*$", re.MULTILINE),  # no backticks at all
]


def is_garbage(filename: str, content: str) -> bool:
    """Check if a file is garbage and should be rejected (Lesson 13)."""
    fname_lower = filename.lower().strip()

    # Reject known garbage filenames
    if fname_lower in GARBAGE_FILES:
        return True

    # Reject empty content
    if not content.strip():
        return True

    # Reject markdown-only blocks (just description, no actual code)
    # If it's a .md file with only text and no code fences, it might be ok (docs)
    # But if it claims to be code and has only markdown...
    stripped = content.strip()

    # Reject if it's just placeholder text
    if stripped.lower() in ("todo", "placeholder", "lorem ipsum", "n/a"):
        return True

    return False


# --- Code extraction ---

CODE_BLOCK_RE = re.compile(
    r"```(?:[a-zA-Z0-9_+-]+)?\s*\n(.*?)```",
    re.DOTALL,
)

FILE_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,3}\s*)?(?:File|Archivo|Fichero)\s*:\s*([^\n]+)",
    re.IGNORECASE,
)


def extract_files(content: str) -> dict[str, str]:
    """Extract code files from LLM output.

    Looks for 'Archivo: <name>' or 'File: <name>' followed by a fenced code block.
    Returns dict[filename -> content].
    """
    files: dict[str, str] = {}

    # Pattern: optional "Archivo: name" or "File: name" header, then a code fence
    # We split on code fences first, then look backwards for the filename
    lines = content.split("\n")
    current_filename: str | None = None
    in_block = False
    block_lines: list[str] = []
    block_lang = ""

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detect start of code fence
        if stripped.startswith("```") and not in_block:
            in_block = True
            block_lang = stripped[3:].strip()
            block_lines = []
            # Look backwards for filename (up to 10 lines)
            for j in range(i - 1, max(i - 15, -1), -1):
                prev = lines[j].strip()
                # Match "Archivo: name" or "File: name" or "Fichero: name"
                m = re.match(r"(?:#{0,3}\s*)?(?:Archivo|File|Fichero)\s*:\s*(.+)", prev, re.IGNORECASE)
                if m:
                    fname = m.group(1).strip()
                    fname = fname.replace("\\", "/").split("/")[-1]
                    fname = fname.replace("`", "").strip()
                    if fname and fname.lower() not in GARBAGE_FILES:
                        current_filename = fname
                    break
            continue

        # Detect end of code fence
        if stripped.startswith("```") and in_block:
            in_block = False
            block_content = "\n".join(block_lines).strip()
            if current_filename and block_content:
                files[current_filename] = block_content
            elif not current_filename and block_content:
                # No filename found — auto-generate from language
                ext_map = {
                    "python": "py", "py": "py",
                    "javascript": "js", "js": "js",
                    "html": "html", "css": "css",
                    "bash": "sh", "sh": "sh", "shell": "sh",
                    "json": "json", "yaml": "yaml", "yml": "yaml",
                    "typescript": "ts", "ts": "ts",
                    "xml": "xml", "sql": "sql",
                    "java": "java", "c": "c", "cpp": "cpp",
                    "go": "go", "rust": "rs", "php": "php",
                    "ruby": "rb", "markdown": "md", "md": "md",
                }
                # First try mapping language to extension
                lang_lower = block_lang.lower().strip()
                ext = ext_map.get(lang_lower)
                if ext:
                    fname = f"main.{ext}"
                elif lang_lower:
                    # Use language name directly as extension if unknown
                    fname = f"main.{lang_lower}"
                else:
                    fname = "main.txt"
                if fname.lower() not in GARBAGE_FILES and not is_garbage(fname, block_content):
                    files[fname] = block_content
            current_filename = None
            block_lang = ""
            block_lines = []
            continue

        if in_block:
            block_lines.append(line)

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

        # BUG FIX: Load existing files from disk so the LLM knows what to modify.
        # This is critical for second runs where the user asks for modifications.
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

        # Build context for each role, starting with files already on disk
        context: dict[str, Any] = {
            "user_input": user_input,
            "previous_roles": [],
            "accumulated_files": dict(existing_on_disk),
        }

        for role in roles:
            self._callback(role, "start", None)

            # Render prompt for this role
            prompt = render_prompt(
                f"dev/{role}.j2",
                user_input=user_input,
                previous_summary=self._summarize_context(context),
                existing_files=dict(context["accumulated_files"]),
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

            # Extract files from response
            new_files = extract_files(response.content)

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

            # BUG FIX: Write files to disk AFTER EACH ROLE (not just at the end).
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
            self._callback(role, "done", {
                "tokens": response.tokens,
                "elapsed": response.elapsed,
                "files": list(filtered.keys()),
                "file_contents": dict(filtered),
                "content_preview": response.content[:200],
            })

        self.files = context["accumulated_files"]
        return self.files

    def _call_with_retry(self, messages: list[dict[str, str]], max_retries: int = 2) -> LLMResponse:
        """Call LLM with up to 2 retries and backoff."""
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return self._client.chat(messages)
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    time.sleep(1.0 * (attempt + 1))  # backoff: 1s, 2s
                    continue
                # Last attempt failed — return empty response
                return LLMResponse(content="", tokens=0, elapsed=0.0)
        return LLMResponse(content="", tokens=0, elapsed=0.0)

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