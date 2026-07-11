"""DevFlux TUI — ALL UI in one file (KISS).

Lessons applied:
1. NO _render() override — shadows Widget._render() in Textual 8.x, causes black screen
2. NO _context attribute — shadows MessagePump._context(), kills message pump
3. TabPane: pass child as constructor arg, NOT .mount() before pane is in DOM
4. Menu with Static + on_key (NOT OptionList — consumes Enter)
5. Binding(priority=True) to intercept Enter before widgets
6. can_focus=True on Static subclasses for on_key to work
7. call_from_thread for ALL UI updates from worker threads
8. Spinner with ASCII puro ([o...], [.o..], etc) — NO unicode
9. CSS_PATH absolute: str(Path(__file__).parent / "styles.tcss")
10. NO display=False — use visible=False
11. PipelineRunner.run() accepts arbitrary role list (SIMPLE=2, MEDIUM=6, COMPLEX=8)
12. Complexity enum in orchestrator.py with COMPLEXITY_ROLES and COMPLEXITY_TOKENS
13. Garbage filter: reject output.text, output.txt, output.md, README.md, markdown-only blocks
14. Protection 30% only for dev team, NOT for bugs team
15. reasoning_content fallback: merge into content if empty
16. Don't run in devflux's own source dir (anti-destruction)
17. Files in Path.cwd(), run dirs in ~/.devflux/runs/
18. MarkupError: [[ produces literal [ in Rich — use [[[ for color tags inside brackets

BUG 1 FIX: Second request not generating files
- Root cause: LLMClient httpx.Client connection reuse + is_running flag not resetting
  on all error paths + pipeline log not cleared between runs
- Fix: Create fresh LLMClient per pipeline run, clear pipeline log, ensure
  is_running resets in ALL code paths, add error logging

FEATURE 1: Simplified menu (3 options only)
- "Generar codigo" — enables chat panel for writing idea
- "Ajustes" — submenu with config, provider, API key, sessions, last run
- "Temas" — cycle through color themes

FEATURE 2: Intelligent orchestrator
- Classifies intent (CODE / QUESTION / CHAT) before executing
- Shows preview: "Equipo: dev | Complejidad: SIMPLE | 3 roles"
- General questions answered directly without pipeline
"""

from __future__ import annotations

import difflib
import time
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    Static,
    Input,
    RichLog,
)
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax

from ..core.config import DevFluxConfig, PROVIDERS, CONFIG_PATH, DEVFLUX_DIR
from ..core.credentials import CredentialsStore
from ..core.client import LLMClient
from ..core.orchestrator import (
    Orchestrator,
    Complexity,
    IntentType,
    COMPLEXITY_ROLES,
    COMPLEXITY_TOKENS,
)
from ..core.runner import PipelineRunner
from ..core.sessions import SessionRecord

# Lesson 9: CSS_PATH absolute
CSS_PATH = str(Path(__file__).parent / "styles.tcss")

BANNER = """
 ____  _____ _____ _   _ ____
|  _ \\| ____|_   _| | | / ___|
| |_) |  _|   | | | |_| \\___ \\
|  __/| |___  | | |  _|  ___) |
|_|   |_____| |_| |_| |_| |____/  v1.0
"""

# FEATURE 1: Simplified menu — only 3 options
MENU_ITEMS = [
    "Generar codigo",
    "Ajustes",
    "Temas",
]

# FEATURE 1: Settings submenu
SETTINGS_ITEMS = [
    "Ver config actual",
    "Cambiar provider",
    "Agregar/modificar API key",
    "Borrar API key",
    "Ver sesiones anteriores",
    "Ver ultimo run",
    "Volver",
]

# FEATURE 1: Theme cycling
THEMES = ["neon", "dracula", "monokai", "nord", "gruvbox", "tokyo-night"]

# Lesson 8: ASCII-only spinner frames
SPINNER_FRAMES = ["[o...]", "[.o..]", "[..o.]", "[...o]"]


class MenuWidget(Static):
    """Menu using Static + on_key (Lesson 4: NOT OptionList).

    Lesson 6: can_focus=True on Static subclass for on_key to work.
    """

    can_focus = True

    def __init__(self, items: list[str], title: str = "Menu", on_select=None) -> None:
        super().__init__()
        self._items = items
        self._title = title
        self._on_select = on_select
        self._selected = 0

    def render(self) -> str:
        """Render menu items. Lesson 1: override render() (NOT _render())."""
        lines = [f"[bold]$ {self._title}[/bold]"]
        for i, item in enumerate(self._items):
            marker = ">" if i == self._selected else " "
            if i == self._selected:
                # Lesson 18: use [[[ for color tags inside brackets context
                lines.append(f"[{marker}] [bold cyan]{item}[/bold cyan]")
            else:
                lines.append(f" {marker} {item}")
        return "\n".join(lines)

    def on_key(self, event) -> None:  # type: ignore[override]
        """Handle key events directly (Lesson 4)."""
        from textual.events import Key
        if not isinstance(event, Key):
            return
        key = event.key
        if key == "up":
            self._selected = (self._selected - 1) % len(self._items)
            self.refresh()
            event.prevent_default()
            event.stop()
        elif key == "down":
            self._selected = (self._selected + 1) % len(self._items)
            self.refresh()
            event.prevent_default()
            event.stop()
        elif key == "enter":
            if self._on_select:
                self._on_select(self._items[self._selected])
            event.prevent_default()
            event.stop()
        elif key == "escape":
            if self._on_select:
                self._on_select(None)
            event.prevent_default()
            event.stop()


class FileListWidget(Static):
    """File list for the code panel — NO TabbedContent, NO dynamic IDs.

    Uses j/k or up/down to navigate, Enter to select.
    Lesson 6: can_focus=True for on_key to work.
    """

    can_focus = True

    def __init__(self) -> None:
        super().__init__()
        self._files: list[str] = []
        self._selected = 0

    def set_files(self, files: list[str]) -> None:
        """Update the file list. Preserve selection if possible."""
        self._files = files
        if self._selected >= len(files):
            self._selected = max(0, len(files) - 1)
        self.refresh()

    def render(self) -> str:
        if not self._files:
            return "[dim](sin archivos)[/dim]"
        lines = ["[bold]Archivos:[/bold]"]
        for i, fname in enumerate(self._files):
            marker = ">" if i == self._selected else " "
            if i == self._selected:
                lines.append(f"{marker} [bold cyan]{fname}[/bold cyan]")
            else:
                lines.append(f"{marker} {fname}")
        return "\n".join(lines)

    def on_key(self, event) -> None:  # type: ignore[override]
        from textual.events import Key
        if not isinstance(event, Key):
            return
        key = event.key
        if key in ("up", "k"):
            if self._files:
                self._selected = (self._selected - 1) % len(self._files)
                self.refresh()
                app = self.app
                if hasattr(app, '_show_selected_file'):
                    app._show_selected_file()
            event.prevent_default()
            event.stop()
        elif key in ("down", "j"):
            if self._files:
                self._selected = (self._selected + 1) % len(self._files)
                self.refresh()
                app = self.app
                if hasattr(app, '_show_selected_file'):
                    app._show_selected_file()
            event.prevent_default()
            event.stop()
        elif key == "enter":
            event.prevent_default()
            event.stop()


class DevFluxApp(App):
    """DevFlux TUI — all UI in one file (KISS)."""

    CSS_PATH = CSS_PATH
    TITLE = "DevFlux v1.0"
    SUB_TITLE = "TUI multi-agente"

    BINDINGS = [
        # Lesson 5: priority=True to intercept Enter before widgets
        Binding("enter", "submit_input", "Enviar", priority=True),
        Binding("escape", "close_menu", "Cerrar", priority=True),
        Binding("ctrl+s", "toggle_menu", "Menu", priority=True),
        Binding("ctrl+q", "quit", "Salir", priority=True),
        # File navigation in code panel (no priority — only when focused on file list)
        Binding("j", "next_file", "Sig. archivo"),
        Binding("k", "prev_file", "Prev archivo"),
    ]

    # Reactive state (NOT using _context — Lesson 2)
    is_running: reactive[bool] = reactive(False)
    show_menu: reactive[bool] = reactive(False)
    show_settings: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self._config: DevFluxConfig | None = DevFluxConfig.load()
        self._creds = CredentialsStore()
        self._client: LLMClient | None = None
        self._orchestrator = Orchestrator()
        self._spinner_idx = 0
        self._menu_widget: MenuWidget | None = None
        # FEATURE 1: Theme state
        self._theme_idx = 0
        self._current_theme = THEMES[0]
        # BUG 1 fix: track pipeline run count for debugging
        self._pipeline_count = 0
        # Settings state: track if we're waiting for input (provider/model/key)
        self._settings_input_mode: str | None = None
        # BUG 2 DEFINITIVE FIX: NO TabbedContent — use file list + RichLog
        # Store file contents keyed by filename for display
        self._code_files: dict[str, Any] = {}  # fname -> (display_content, is_diff)
        self._code_file_order: list[str] = []  # ordered list of filenames

    def compose(self) -> ComposeResult:
        """Compose the main layout."""
        # Header
        yield Header(show_clock=False)

        if self._config is None:
            # Wizard mode
            yield from self._compose_wizard()
        else:
            # Normal mode
            yield from self._compose_main()

        yield Footer()

    def _compose_wizard(self) -> ComposeResult:
        """Compose setup wizard."""
        yield Vertical(
            Static(BANNER, id="banner"),
            Static(
                "[bold yellow]Bienvenido a DevFlux![/bold yellow]\n\n"
                "No tenes configuracion. Vamos a configurar.\n\n"
                "Escribi 'ollama-local' o 'ollama-cloud' y presiona Enter:",
                id="wizard-content",
            ),
            Input(placeholder="ollama-local | ollama-cloud", id="wizard-input"),
            id="wizard",
        )

    def _compose_main(self) -> ComposeResult:
        """Compose main UI with left/right panels."""
        # Left panel: banner + chat log + input + menu + pipeline log
        yield Horizontal(
            # Left Panel (40%)
            Vertical(
                Static(BANNER, id="banner"),
                RichLog(id="chat-log", wrap=True, markup=True),
                Input(placeholder="Escribi tu idea...", id="chat-input"),
                Static("", id="menu-widget"),
                RichLog(id="pipeline-log", wrap=True, markup=True),
                id="left-panel",
            ),
            # Right Panel (60%) — file list + code viewer (NO TabbedContent)
            Vertical(
                Static("[bold]Codigo / Diffs[/bold]", id="code-header"),
                FileListWidget(),
                RichLog(id="code-viewer", wrap=False, markup=True),
                id="right-panel",
            ),
            id="main-layout",
        )

    def on_mount(self) -> None:
        """Called when app is mounted."""
        if self._config is not None:
            self._client = LLMClient(self._config, self._creds)
            # Welcome message
            log = self.query_one("#chat-log", RichLog)
            log.write(f"[green]DevFlux v1.0 listo![/green]")
            log.write(f"Modelo: [bold]{self._config.model}[/bold]")
            log.write(f"Provider: [bold]{self._config.provider}[/bold]")
            log.write(f"CWD: {Path.cwd()}")
            log.write(f"Tema: [bold]{self._current_theme}[/bold]")
            log.write("")
            log.write("[dim]Escribi tu idea o presiona Ctrl+S para el menu[/dim]")

            # Pipeline log placeholder
            plog = self.query_one("#pipeline-log", RichLog)
            plog.write("[dim]Pipeline: esperando...[/dim]")

            # Hide menu widget initially (Lesson 10: visible, not display)
            menu = self.query_one("#menu-widget", Static)
            menu.visible = False

    # --- Wizard handling ---

    def action_submit_input(self) -> None:
        """Handle Enter key — BUG FIX: this method was MISSING.

        The binding Binding("enter", "submit_input", priority=True) maps to
        action_submit_input, but it didn't exist, so Enter was silently
        swallowed by the App's binding handler before it could reach the
        Input widget's on_input_submitted. This is the root cause of the
        "TUI se queda colgado" bug.

        Now we read the input value directly and dispatch it.
        """
        # Determine which input widget is active
        if self._config is None:
            # Wizard mode
            try:
                wizard_input = self.query_one("#wizard-input", Input)
            except Exception:
                return
            value = wizard_input.value
            if not value.strip():
                return
            wizard_input.value = ""
            self._handle_wizard(value)
            return

        # Check if we're in settings input mode (waiting for provider/model/key)
        if self._settings_input_mode:
            try:
                chat_input = self.query_one("#chat-input", Input)
            except Exception:
                return
            value = chat_input.value
            chat_input.value = ""
            self._handle_settings_input(value)
            return

        # Normal mode — submit chat
        try:
            chat_input = self.query_one("#chat-input", Input)
        except Exception:
            return
        value = chat_input.value
        if not value.strip():
            return
        # _handle_chat_submit clears input and logs the message itself
        self._handle_chat_submit(value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter on input fields (fallback if binding doesn't intercept).

        With priority=True binding, action_submit_input handles Enter first.
        But if focus changes or binding doesn't fire, this is the safety net.
        """
        # Delegate to action_submit_input to avoid double-processing
        # event.value is already available, use it directly
        if self._settings_input_mode and self._config is not None:
            self._handle_settings_input(event.value)
            return

        if self._config is None:
            self._handle_wizard(event.value)
        else:
            # If we got here, the binding didn't fire, so handle it.
            # _handle_chat_submit clears input and logs the message itself.
            self._handle_chat_submit(event.value)

    def _handle_wizard(self, value: str) -> None:
        """Handle wizard input."""
        provider = value.strip().lower()
        if provider not in PROVIDERS:
            content = self.query_one("#wizard-content", Static)
            content.update(
                "[bold red]Provider invalido![/bold red]\n\n"
                "Escribi 'ollama-local' o 'ollama-cloud':"
            )
            self.query_one("#wizard-input", Input).value = ""
            return

        # Create config
        info = PROVIDERS[provider]
        config = DevFluxConfig(
            provider=provider,
            base_url=info["base_url"],
            model=info["models"][0],
        )

        if info["needs_key"]:
            # Ask for API key
            content = self.query_one("#wizard-content", Static)
            content.update(
                f"[bold yellow]Configurar {info['label']}[/bold yellow]\n\n"
                f"Pegá tu API key y presiona Enter:"
            )
            wizard_input = self.query_one("#wizard-input", Input)
            wizard_input.value = ""
            wizard_input.placeholder = "sk-..."

            # Store provider and wait for next input
            self._pending_provider = provider
            self._pending_config = config
            self._wizard_step = "api_key"
            return

        # No key needed — save and restart
        config.save()
        content = self.query_one("#wizard-content", Static)
        content.update(
            f"[bold green]Configurado![/bold green]\n\n"
            f"Provider: {provider}\n"
            f"Modelo: {config.model}\n\n"
            "Reinicia DevFlux para empezar."
        )

    def _handle_wizard_api_key(self, key: str) -> None:
        """Handle API key input in wizard."""
        provider = self._pending_provider
        config = self._pending_config
        self._creds.set(provider, key)

        # Ask for model selection
        info = PROVIDERS[provider]
        models_list = "\n".join(f"  {i}. {m}" for i, m in enumerate(info["models"]))
        content = self.query_one("#wizard-content", Static)
        content.update(
            f"[bold yellow]Elegí modelo[/bold yellow]\n\n"
            f"{models_list}\n\n"
            f"Escribe el nombre del modelo:"
        )
        wizard_input = self.query_one("#wizard-input", Input)
        wizard_input.value = ""
        wizard_input.placeholder = info["models"][0]
        self._wizard_step = "model"

    def _handle_wizard_model(self, model: str) -> None:
        """Handle model selection in wizard."""
        config = self._pending_config
        if model.strip():
            config.model = model.strip()
        config.save()

        content = self.query_one("#wizard-content", Static)
        content.update(
            f"[bold green]Configurado![/bold green]\n\n"
            f"Provider: {config.provider}\n"
            f"Modelo: {config.model}\n"
            f"Base URL: {config.base_url}\n\n"
            "Reinicia DevFlux para empezar."
        )

    # --- Chat handling ---

    def _handle_chat_submit(self, text: str) -> None:
        """Handle chat input submit.

        BUG 1 FIX: Reset all state, clear pipeline log, create fresh client.
        FEATURE 2: Classify intent first, show preview, skip pipeline for questions.
        """
        if not text.strip():
            return
        if self.is_running:
            self._log_chat("[yellow]Pipeline en ejecucion. Espera...[/yellow]")
            return

        # Clear input
        self.query_one("#chat-input", Input).value = ""

        # Log user message
        self._log_chat(f"[bold blue]> {text}[/bold blue]")

        # FEATURE 2: Classify intent BEFORE anything else
        intent = self._orchestrator.classify_intent(text)

        if intent == IntentType.QUESTION:
            # General question — answer directly with LLM, NO pipeline
            self._log_chat("[dim yellow]Orquestador: Pregunta detectada. Respondiendo directamente...[/dim yellow]")
            # Update pipeline-log so user sees feedback
            try:
                plog = self.query_one("#pipeline-log", RichLog)
                plog.clear()
                plog.write("[dim]Pipeline: no se ejecuta (pregunta detectada). Consultando LLM directamente...[/dim]")
            except Exception:
                pass
            # Run LLM call in background thread (network I/O — don't block UI)
            self.is_running = True
            self._answer_question(text)
            return

        # Intent is CHAT or CODE — run pipeline normally
        # (CHAT is NOT blocked: "hola mundo" should generate code via pipeline)

        # Intent is CODE — classify team and complexity
        teams, complexity = self._orchestrator.classify(text)
        roles = self._orchestrator.get_roles()

        # FEATURE 2: Show preview BEFORE executing
        self._log_chat(f"[bold magenta]Orquestador: {self._orchestrator.preview()}[/bold magenta]")
        self._log_chat(f"[dim]Roles: {', '.join(roles)}[/dim]")

        # BUG 1 FIX: Clear pipeline log for new run
        try:
            plog = self.query_one("#pipeline-log", RichLog)
            plog.clear()
            plog.write(f"[dim]Pipeline #{self._pipeline_count + 1}: iniciando...[/dim]")
        except Exception:
            pass

        # Start pipeline worker
        self.is_running = True
        self._pipeline_count += 1
        self._run_pipeline(text, teams, complexity, roles)

    @work(thread=True)
    def _answer_question(self, user_input: str) -> None:
        """Answer a general question directly with the LLM — NO pipeline, NO roles.

        Called when classify_intent() returns IntentType.QUESTION.
        Makes a single chat() call and displays the response in the chat log.
        Lesson 7: call_from_thread for ALL UI updates from worker threads.
        """
        # Create fresh client for this call (avoid connection reuse issues)
        try:
            client = LLMClient(self._config, self._creds)  # type: ignore[arg-type]
        except Exception as exc:
            self.call_from_thread(
                self._log_chat,
                f"[bold red]ERROR creando cliente LLM: {exc}[/bold red]"
            )
            self.call_from_thread(self._question_done)
            return

        # Simple system prompt — DevFlux context but no pipeline roles
        messages = [
            {
                "role": "system",
                "content": (
                    "Sos DevFlux, un asistente de desarrollo de software. "
                    "Respondes preguntas de forma clara y concisa. "
                    "Si el usuario pide codigo o un proyecto, decile que "
                    "reformule como peticion de codigo para ejecutar el pipeline."
                ),
            },
            {"role": "user", "content": user_input},
        ]

        try:
            response = client.chat(messages)
        except Exception as exc:
            self.call_from_thread(
                self._log_chat,
                f"[bold red]ERROR consultando LLM: {exc}[/bold red]"
            )
            try:
                client.close()
            except Exception:
                pass
            self.call_from_thread(self._question_done)
            return

        # Close client after use
        try:
            client.close()
        except Exception:
            pass

        # Display the answer in the chat log
        answer = response.content if response.content else "(sin respuesta)"
        self.call_from_thread(
            self._log_chat,
            f"[bold green]DevFlux:[/bold green] {answer}"
        )
        self.call_from_thread(
            self._log_chat,
            f"[dim]({response.tokens} tokens, {response.elapsed:.1f}s)[/dim]"
        )

        # Update pipeline log
        self.call_from_thread(self._question_done)

    def _question_done(self) -> None:
        """Called when a direct question answer finishes (on UI thread)."""
        self.is_running = False
        try:
            plog = self.query_one("#pipeline-log", RichLog)
            plog.write(
                "[bold green]Pregunta respondida directamente (sin pipeline).[/bold green]"
            )
        except Exception:
            pass

    @work(thread=True)
    def _run_pipeline(
        self,
        user_input: str,
        teams: list[str],
        complexity: Complexity,
        roles: list[str],
        _is_retry: bool = False,
    ) -> None:
        """Run the pipeline in a background thread.

        Lesson 7: call_from_thread for ALL UI updates from worker threads.
        Lesson 16: don't run in devflux's own source dir.
        BUG 1 FIX: Create fresh LLMClient per run (avoid httpx connection reuse issues).
        BUG 1 FIX: Ensure is_running resets in ALL error paths.

        FEATURE: Auto-retry if 0 files generated (max 1 retry).
        If pipeline finishes without errors but generates 0 files, re-run once.
        If still 0 files after retry, show user-facing message.
        """
        start_time = time.time()

        # Lesson 16: anti-destruction check
        cwd = Path.cwd()
        from ..core.runner import DEVFLUX_SRC_DIR
        if str(DEVFLUX_SRC_DIR) in str(cwd.resolve()):
            self.call_from_thread(
                self._log_chat,
                "[bold red]ERROR: No se puede ejecutar en el directorio de DevFlux.[/bold red]"
            )
            self.call_from_thread(self._pipeline_done, 0, 0.0, [])
            return

        # BUG 1 FIX: Create fresh LLMClient per pipeline run
        # This avoids httpx.Client connection pool issues on second run
        try:
            fresh_client = LLMClient(self._config, self._creds)  # type: ignore[arg-type]
        except Exception as exc:
            self.call_from_thread(
                self._log_chat,
                f"[bold red]ERROR creando cliente LLM: {exc}[/bold red]"
            )
            self.call_from_thread(self._pipeline_done, 0, 0.0, [])
            return

        # Spinner animation (Lesson 8: ASCII only)
        self._spinner_idx = 0

        def callback(role: str, status: str, data: dict[str, Any] | None) -> None:
            """Callback for pipeline progress updates."""
            # Lesson 7: call_from_thread for ALL UI updates
            if status == "start":
                spinner = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
                self._spinner_idx += 1
                self.call_from_thread(
                    self._log_pipeline,
                    f"[yellow]{spinner} {role}...[/yellow]"
                )
            elif status == "done":
                tokens = data.get("tokens", 0) if data else 0
                elapsed = data.get("elapsed", 0.0) if data else 0.0
                files = data.get("files", []) if data else []
                file_contents = data.get("file_contents", {}) if data else {}
                file_diffs = data.get("file_diffs", {}) if data else {}
                msg = data.get("message", "") if data else ""
                # FEATURE 2: equipo-bugs done message
                if role == "equipo-bugs":
                    self.call_from_thread(
                        self._log_pipeline,
                        f"[green]  [BUGS] {msg or 'Integridad verificada'}[/green]"
                    )
                else:
                    self.call_from_thread(
                        self._log_pipeline,
                        f"[green]  [OK] {role} ({elapsed:.1f}s, {tokens} tokens, {len(files)} archivos)[/green]"
                    )
                # Update code panel if files were generated
                if files:
                    self.call_from_thread(self._update_code_panel, files, file_contents, role, file_diffs)
            elif status == "garbage":
                fname = data.get("file", "?") if data else "?"
                self.call_from_thread(
                    self._log_pipeline,
                    f"[red]  [SKIP] {role}: basura filtrada ({fname})[/red]"
                )
            # BUG FIX: Handle error status from _call_with_retry
            elif status == "error":
                msg = data.get("message", "error desconocido") if data else "error desconocido"
                self.call_from_thread(
                    self._log_pipeline,
                    f"[bold red]  [ERROR] LLM: {msg}[/bold red]"
                )
            # FEATURE 2: equipo-bugs integrity check callbacks
            elif status == "info":
                msg = data.get("message", "") if data else ""
                self.call_from_thread(
                    self._log_pipeline,
                    f"[cyan]  [BUGS] {msg}[/cyan]"
                )
            elif status == "issues":
                issues = data.get("issues", []) if data else []
                self.call_from_thread(
                    self._log_pipeline,
                    f"[bold red]  [BUGS] Problemas de integridad encontrados ({len(issues)}):[/bold red]"
                )
                for issue in issues:
                    self.call_from_thread(
                        self._log_pipeline,
                        f"[red]    - {issue.get('file', '?')}: {issue.get('type', '?')} — {issue.get('detail', '')}[/red]"
                    )

        # BUG 1 FIX: Create fresh runner per pipeline run
        runner = PipelineRunner(
            fresh_client,
            self._config,  # type: ignore[arg-type]
            callback=callback,
        )

        # Run pipeline (Lesson 11: arbitrary role list)
        try:
            files = runner.run(roles, user_input, teams=teams, cwd=cwd)
        except Exception as exc:
            # BUG 1 FIX: Log the actual error for debugging
            self.call_from_thread(
                self._log_chat,
                f"[bold red]ERROR en pipeline: {exc}[/bold red]"
            )
            self.call_from_thread(
                self._log_pipeline,
                f"[bold red]ERROR: {exc}[/bold red]"
            )
            self.call_from_thread(self._pipeline_done, 0, 0.0, [])
            # BUG 1 FIX: Close the fresh client on error
            try:
                fresh_client.close()
            except Exception:
                pass
            return

        elapsed = time.time() - start_time

        # BUG 1 FIX: Close the fresh client after pipeline completes
        try:
            fresh_client.close()
        except Exception:
            pass

        # FEATURE: Auto-retry if 0 files generated (max 1 retry)
        if not files and not _is_retry:
            self.call_from_thread(
                self._log_chat,
                "[yellow]Pipeline completo pero 0 archivos generados. "
                "Reintentando (1/1)...[/yellow]"
            )
            self.call_from_thread(
                self._log_pipeline,
                "[yellow]Reintentando pipeline (no se generaron archivos)...[/yellow]"
            )
            # Re-run with _is_retry=True to prevent infinite loop
            self._run_pipeline(user_input, teams, complexity, roles, _is_retry=True)
            return

        if not files and _is_retry:
            # Already retried, still 0 files — save session and inform user
            session = SessionRecord(
                user_input=user_input,
                teams=teams,
                complexity=complexity.value,
                roles=roles,
                files=list(files.keys()),
                tokens=runner.total_tokens,
                elapsed=elapsed,
                model=self._config.model if self._config else "unknown",
            )
            session.save()

            self.call_from_thread(
                self._log_chat,
                f"[bold yellow]Pipeline completo (0 archivos despues de 2 intentos).[/bold yellow]\n"
                f"Tokens: {runner.total_tokens}\n"
                f"Tiempo: {elapsed:.1f}s\n"
                f"Proba con una descripcion mas detallada."
            )
            self.call_from_thread(self._pipeline_done, runner.total_tokens, elapsed, [])
            return

        # Files generated — save session and show normal summary
        session = SessionRecord(
            user_input=user_input,
            teams=teams,
            complexity=complexity.value,
            roles=roles,
            files=list(files.keys()),
            tokens=runner.total_tokens,
            elapsed=elapsed,
            model=self._config.model if self._config else "unknown",
        )
        session.save()

        # Final message
        if _is_retry:
            self.call_from_thread(
                self._log_chat,
                f"[bold green]Pipeline completo (reintento exitoso)![/bold green]\n"
                f"Archivos: {len(files)}\n"
                f"Tokens: {runner.total_tokens}\n"
                f"Tiempo: {elapsed:.1f}s\n"
                f"Directorio: {cwd}"
            )
        else:
            self.call_from_thread(
                self._log_chat,
                f"[bold green]Pipeline completo![/bold green]\n"
                f"Archivos: {len(files)}\n"
                f"Tokens: {runner.total_tokens}\n"
                f"Tiempo: {elapsed:.1f}s\n"
                f"Directorio: {cwd}"
            )

        if files:
            files_list = ", ".join(files.keys())
            self.call_from_thread(
                self._log_chat,
                f"[cyan]Archivos generados: {files_list}[/cyan]"
            )

        self.call_from_thread(self._pipeline_done, runner.total_tokens, elapsed, list(files.keys()))

    def _pipeline_done(self, tokens: int, elapsed: float, files: list[str]) -> None:
        """Called when pipeline finishes (on UI thread).

        BUG 1 FIX: Always reset is_running, regardless of success/failure.
        """
        self.is_running = False
        try:
            plog = self.query_one("#pipeline-log", RichLog)
            plog.write(
                f"[bold green]Pipeline: completado ({tokens} tokens, {elapsed:.1f}s, "
                f"{len(files)} archivos)[/bold green]"
            )
        except Exception:
            pass

    def _update_code_panel(
        self,
        filenames: list[str],
        file_contents: dict[str, str] | None = None,
        role: str = "",
        file_diffs: dict[str, str] | None = None,
    ) -> None:
        """Update the right panel with code content.

        BUG 2 DEFINITIVE FIX: NO TabbedContent, NO TabPane, NO dynamic IDs.
        Uses a simple file list (FileListWidget) + a single RichLog (code-viewer).
        Files are stored in _code_files dict and displayed on selection.
        This completely avoids Textual's auto-generated ID collision.
        """
        if not self._config:
            return

        file_contents = file_contents or {}
        file_diffs = file_diffs or {}
        cwd = Path.cwd()

        for fname in filenames:
            new_content = file_contents.get(fname, "")
            if not new_content:
                # Fallback: try reading from disk
                fpath = cwd / fname
                if fpath.exists():
                    try:
                        new_content = fpath.read_text(encoding="utf-8")
                    except Exception:
                        continue
                else:
                    continue

            # Determine lexer for syntax highlighting
            fpath = cwd / fname
            ext = fpath.suffix.lstrip(".")
            lexer_map = {
                "py": "python", "js": "javascript", "ts": "typescript",
                "html": "html", "css": "css", "json": "json",
                "yaml": "yaml", "yml": "yaml", "sh": "bash",
                "md": "markdown", "txt": "text",
            }
            lexer = lexer_map.get(ext, "text")

            # Check if we have an old version to diff against
            old_content = file_diffs.get(fname)
            if old_content is not None and old_content != new_content:
                display_content = self._build_diff(old_content, new_content)
                is_diff = True
                try:
                    plog = self.query_one("#pipeline-log", RichLog)
                    plog.write(f"[dim]  [DIFF] {fname}: mostrando diff ({len(old_content.splitlines())} -> {len(new_content.splitlines())} lineas)[/dim]")
                except Exception:
                    pass
            else:
                try:
                    display_content = Syntax(
                        new_content, lexer, theme="monokai", line_numbers=True
                    )
                except Exception:
                    display_content = Syntax(
                        new_content, "text", theme="monokai", line_numbers=False
                    )
                is_diff = False

            # Store content in dict — NO widget IDs, NO TabPane
            self._code_files[fname] = (display_content, is_diff)
            if fname not in self._code_file_order:
                self._code_file_order.append(fname)

        # Update the file list widget
        try:
            file_list = self.query_one(FileListWidget)
            file_list.set_files(self._code_file_order)
            # Select the last added file
            if filenames:
                last_fname = filenames[-1]
                if last_fname in self._code_file_order:
                    file_list._selected = self._code_file_order.index(last_fname)
                    file_list.refresh()
        except Exception:
            pass

        # Show the last file in the RichLog
        if filenames:
            self._show_file(filenames[-1])

    def _show_file(self, fname: str) -> None:
        """Display a specific file in the code-viewer RichLog."""
        if fname not in self._code_files:
            return
        display_content, is_diff = self._code_files[fname]
        try:
            viewer = self.query_one("#code-viewer", RichLog)
            viewer.clear()
            viewer.write(display_content)
            # Auto-scroll to first changed line in diffs
            if is_diff and isinstance(display_content, Text):
                scroll_line = 0
                for i, line in enumerate(display_content.plain.split("\n")):
                    if line.startswith("@@") or line.startswith("+") or line.startswith("-"):
                        if not line.startswith("+++") and not line.startswith("---"):
                            scroll_line = i
                            break
                if scroll_line > 0:
                    try:
                        viewer.scroll_relative(y=scroll_line, animate=False)
                    except Exception:
                        pass
        except Exception:
            pass

    def _show_selected_file(self) -> None:
        """Show the currently selected file in the file list."""
        try:
            file_list = self.query_one(FileListWidget)
            if file_list._files and 0 <= file_list._selected < len(file_list._files):
                self._show_file(file_list._files[file_list._selected])
        except Exception:
            pass

    def action_next_file(self) -> None:
        """Navigate to next file in code panel."""
        try:
            file_list = self.query_one(FileListWidget)
            if file_list._files:
                file_list._selected = (file_list._selected + 1) % len(file_list._files)
                file_list.refresh()
                self._show_selected_file()
        except Exception:
            pass

    def action_prev_file(self) -> None:
        """Navigate to previous file in code panel."""
        try:
            file_list = self.query_one(FileListWidget)
            if file_list._files:
                file_list._selected = (file_list._selected - 1) % len(file_list._files)
                file_list.refresh()
                self._show_selected_file()
        except Exception:
            pass

    def _build_diff(self, old: str, new: str) -> Text:
        """Build a Rich Text with diff highlighting (green=added, red=removed)."""
        old_lines = old.splitlines(keepends=False)
        new_lines = new.splitlines(keepends=False)
        diff = difflib.unified_diff(
            old_lines, new_lines, lineterm="", n=3
        )
        text = Text()
        for line in diff:
            if line.startswith("+++") or line.startswith("---"):
                text.append(line + "\n", style="bold")
            elif line.startswith("@@"):
                text.append(line + "\n", style="bold cyan")
            elif line.startswith("+"):
                text.append(line + "\n", style="green")
            elif line.startswith("-"):
                text.append(line + "\n", style="red")
            else:
                text.append(line + "\n", style="dim")
        return text

    # --- Menu handling (FEATURE 1: simplified to 3 options) ---

    def action_toggle_menu(self) -> None:
        """Toggle the menu (Ctrl+S)."""
        if self.show_settings:
            return  # Already in settings menu
        self.show_menu = not self.show_menu
        menu_widget = self.query_one("#menu-widget", Static)

        if self.show_menu:
            # Create menu widget (Lesson 4: Static + on_key)
            self._menu_widget = MenuWidget(MENU_ITEMS, "Menu", on_select=self._on_menu_select)
            # Replace the static with our menu
            menu_widget.visible = True
            menu_widget.display = True
            menu_widget.update(self._menu_widget.render())
            menu_widget.focus()
        else:
            menu_widget.visible = False
            menu_widget.update("")

    def action_close_menu(self) -> None:
        """Close menu (Escape)."""
        self.show_menu = False
        self.show_settings = False
        self._settings_input_mode = None  # Cancel any settings input mode
        menu_widget = self.query_one("#menu-widget", Static)
        menu_widget.visible = False
        menu_widget.update("")
        # Return focus to chat input
        self.query_one("#chat-input", Input).focus()

    def _on_menu_select(self, item: str | None) -> None:
        """Handle menu selection. FEATURE 1: only 3 options."""
        self.show_menu = False
        menu_widget = self.query_one("#menu-widget", Static)
        menu_widget.visible = False
        menu_widget.update("")

        if item is None:
            self.query_one("#chat-input", Input).focus()
            return

        if item == "Generar codigo":
            self._log_chat("[cyan]Escribe tu idea en el chat para generar codigo...[/cyan]")
        elif item == "Ajustes":
            self._show_settings()
        elif item == "Temas":
            self._cycle_theme()

        self.query_one("#chat-input", Input).focus()

    # --- Theme handling (FEATURE 1: Temas) ---

    def _cycle_theme(self) -> None:
        """Cycle to next theme in the THEMES list."""
        self._theme_idx = (self._theme_idx + 1) % len(THEMES)
        self._current_theme = THEMES[self._theme_idx]
        self._log_chat(f"[bold cyan]Tema: {self._current_theme}[/bold cyan]")
        self._log_chat(f"[dim]Temas disponibles: {', '.join(THEMES)}[/dim]")

    # --- Settings handling (FEATURE 1: expanded Ajustes submenu) ---

    def _show_settings(self) -> None:
        """Show settings menu."""
        self.show_settings = True
        menu_widget = self.query_one("#menu-widget", Static)
        menu_widget.visible = True
        self._settings_menu = MenuWidget(SETTINGS_ITEMS, "Ajustes", on_select=self._on_settings_select)
        menu_widget.update(self._settings_menu.render())
        menu_widget.focus()

    def _on_settings_select(self, item: str | None) -> None:
        """Handle settings selection. FEATURE 1: expanded options."""
        self.show_settings = False
        menu_widget = self.query_one("#menu-widget", Static)
        menu_widget.visible = False
        menu_widget.update("")

        if item is None or item == "Volver":
            self.query_one("#chat-input", Input).focus()
            return

        if item == "Ver config actual":
            self._show_config()
        elif item == "Cambiar provider":
            self._change_provider()
        elif item == "Agregar/modificar API key":
            self._add_api_key()
        elif item == "Borrar API key":
            self._delete_api_key()
        elif item == "Ver sesiones anteriores":
            self._show_sessions()
        elif item == "Ver ultimo run":
            self._show_last_run()

        self.query_one("#chat-input", Input).focus()

    def _show_config(self) -> None:
        """Show current configuration."""
        cfg = self._config
        if cfg is None:
            self._log_chat("[yellow]No hay configuracion[/yellow]")
            return
        has_key = self._creds.has_key(cfg.provider) if self._config else False
        self._log_chat(
            f"[bold]Configuracion actual:[/bold]\n"
            f"  Provider: {cfg.provider}\n"
            f"  Model: {cfg.model}\n"
            f"  Base URL: {cfg.base_url}\n"
            f"  Temperature: {cfg.temperature}\n"
            f"  Max tokens: {cfg.max_tokens}\n"
            f"  API key: {'configurada' if has_key else 'no configurada'}"
        )

    def _change_provider(self) -> None:
        """Change provider — enter settings input mode."""
        available = ", ".join(PROVIDERS.keys())
        self._log_chat(f"[cyan]Providers disponibles: {available}[/cyan]")
        self._log_chat("[cyan]Escribe el nombre del provider en el chat:[/cyan]")
        self._settings_input_mode = "provider"

    def _add_api_key(self) -> None:
        """Add or modify API key — enter settings input mode."""
        if not self._config:
            self._log_chat("[yellow]No hay configuracion[/yellow]")
            return
        provider = self._config.provider
        has_key = self._creds.has_key(provider)
        if has_key:
            self._log_chat(f"[cyan]API key ya configurada para {provider}. Escribe la nueva key para reemplazarla:[/cyan]")
        else:
            self._log_chat(f"[cyan]No hay API key para {provider}. Escribe la key:[/cyan]")
        self._settings_input_mode = "api_key"

    def _delete_api_key(self) -> None:
        """Delete API key for current provider."""
        if not self._config:
            self._log_chat("[yellow]No hay configuracion[/yellow]")
            return
        provider = self._config.provider
        if not self._creds.has_key(provider):
            self._log_chat(f"[yellow]No hay API key configurada para {provider}[/yellow]")
            return
        # Delete the key
        key_field = f"{provider}_key"
        if key_field in self._creds._data:
            del self._creds._data[key_field]
            self._creds.save()
            self._log_chat(f"[bold red]API key borrada para {provider}[/bold red]")
        else:
            # Try other possible key names
            for field in ["api_key", provider]:
                if field in self._creds._data:
                    del self._creds._data[field]
                    self._creds.save()
                    self._log_chat(f"[bold red]API key borrada para {provider}[/bold red]")
                    return
            self._log_chat(f"[yellow]No se encontro la key para borrar[/yellow]")

    def _handle_settings_input(self, value: str) -> None:
        """Handle input when in settings input mode (provider or API key)."""
        mode = self._settings_input_mode
        self._settings_input_mode = None
        self.query_one("#chat-input", Input).value = ""

        if mode == "provider":
            provider = value.strip().lower()
            if provider not in PROVIDERS:
                self._log_chat(f"[bold red]Provider invalido: {provider}[/bold red]")
                self._log_chat(f"Disponibles: {', '.join(PROVIDERS.keys())}")
                return
            info = PROVIDERS[provider]
            if self._config:
                self._config.provider = provider
                self._config.base_url = info["base_url"]
                self._config.model = info["models"][0]
                self._config.save()
                # Recreate client with new config
                try:
                    if self._client:
                        self._client.close()
                except Exception:
                    pass
                self._client = LLMClient(self._config, self._creds)
                self._log_chat(f"[bold green]Provider cambiado a: {provider}[/bold green]")
                self._log_chat(f"Modelo: {self._config.model}")
                self._log_chat(f"Base URL: {self._config.base_url}")
                if info["needs_key"] and not self._creds.has_key(provider):
                    self._log_chat("[yellow]Este provider necesita API key. Usa Ajustes > Agregar/modificar API key[/yellow]")
        elif mode == "api_key":
            key = value.strip()
            if not key:
                self._log_chat("[yellow]Key vacia, no se guardo[/yellow]")
                return
            if self._config:
                provider = self._config.provider
                self._creds.set(provider, key)
                # Recreate client with new credentials
                try:
                    if self._client:
                        self._client.close()
                except Exception:
                    pass
                self._client = LLMClient(self._config, self._creds)
                self._log_chat(f"[bold green]API key guardada para {provider}[/bold green]")

    def _show_sessions(self) -> None:
        """Show saved sessions."""
        sessions = SessionRecord.list_all()
        if not sessions:
            self._log_chat("[yellow]No hay sesiones guardadas[/yellow]")
            return
        self._log_chat(f"[bold]Sesiones ({len(sessions)}):[/bold]")
        for s in sessions[:10]:
            self._log_chat(
                f"  {s.get('timestamp', '?')[:19]} | "
                f"{', '.join(s.get('teams', []))} | "
                f"{s.get('tokens', 0)} tokens | "
                f"{len(s.get('files', []))} archivos"
            )

    def _show_last_run(self) -> None:
        """Show last run details."""
        last = SessionRecord.load_last()
        if last is None:
            self._log_chat("[yellow]No hay runs anteriores[/yellow]")
            return
        self._log_chat(last.summary())

    # --- Logging helpers ---

    def _log_chat(self, message: str) -> None:
        """Log to chat panel."""
        try:
            log = self.query_one("#chat-log", RichLog)
            log.write(message)
        except Exception:
            pass  # Widget not ready yet

    def _log_pipeline(self, message: str) -> None:
        """Log to pipeline panel."""
        try:
            log = self.query_one("#pipeline-log", RichLog)
            log.write(message)
        except Exception:
            pass  # Widget not ready yet