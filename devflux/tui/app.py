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
"""

from __future__ import annotations

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
    TabbedContent,
    TabPane,
    RichLog,
)
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax

from ..core.config import DevFluxConfig, PROVIDERS, CONFIG_PATH, DEVFLUX_DIR
from ..core.credentials import CredentialsStore
from ..core.client import LLMClient
from ..core.orchestrator import Orchestrator, Complexity, COMPLEXITY_ROLES, COMPLEXITY_TOKENS
from ..core.runner import PipelineRunner
from ..core.sessions import SessionRecord

# Lesson 9: CSS_PATH absolute
CSS_PATH = str(Path(__file__).parent / "styles.tcss")

BANNER = r"""
 ____             _____
|  _ \  ___  ___ |  ___|__  _ __ __ _  ___
| | | |/ _ \/ __|| |_ / _ \| '__/ _` |/ _ \
| |_| |  __/ (__ |  _| (_) | | | (_| |  __/
|____/ \___|\___||_|  \___/|_|  \__, |\___|
                                 |___/    v1.0
"""

MENU_ITEMS = [
    "Desarrollar",
    "Corregir bug",
    "Analizar repo",
    "Ajustes",
]

SETTINGS_ITEMS = [
    "Ver config",
    "Cambiar provider",
    "Cambiar model",
    "Ver sesiones",
    "Ver ultimo run",
    "Desinstalar",
    "Volver",
]

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
            # Right Panel (60%) — code with tabs
            Vertical(
                Static("[bold]Codigo / Diffs[/bold]", id="code-header"),
                TabbedContent(id="code-tabs"),
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
            log.write("")
            log.write("[dim]Escribi tu idea o presiona Ctrl+S para el menu[/dim]")

            # Pipeline log placeholder
            plog = self.query_one("#pipeline-log", RichLog)
            plog.write("[dim]Pipeline: esperando...[/dim]")

            # Hide menu widget initially (Lesson 10: visible, not display)
            menu = self.query_one("#menu-widget", Static)
            menu.visible = False

    # --- Wizard handling ---

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter on input fields."""
        if self._config is None:
            # Wizard mode
            self._handle_wizard(event.value)
        else:
            # Normal mode — submit chat
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

    # Override on_input_submitted to handle wizard steps
    def on_input_submitted_wizard(self, event: Input.Submitted) -> None:
        """Extended handler for wizard steps."""
        if not hasattr(self, "_wizard_step"):
            self._wizard_step = "provider"

        if self._wizard_step == "api_key":
            self._handle_wizard_api_key(event.value)
        elif self._wizard_step == "model":
            self._handle_wizard_model(event.value)

    # --- Chat handling ---

    def _handle_chat_submit(self, text: str) -> None:
        """Handle chat input submit."""
        if not text.strip():
            return
        if self.is_running:
            self._log_chat("[yellow]Pipeline en ejecucion. Espera...[/yellow]")
            return

        # Clear input
        self.query_one("#chat-input", Input).value = ""

        # Log user message
        self._log_chat(f"[bold blue]> {text}[/bold blue]")

        # Classify intent
        teams, complexity = self._orchestrator.classify(text)
        roles = self._orchestrator.get_roles()

        self._log_chat(f"[dim]Orquestador: {self._orchestrator.summary()}[/dim]")
        self._log_chat(f"[dim]Roles a ejecutar: {', '.join(roles)}[/dim]")

        # Start pipeline worker
        self.is_running = True
        self._run_pipeline(text, teams, complexity, roles)

    @work(thread=True)
    def _run_pipeline(
        self,
        user_input: str,
        teams: list[str],
        complexity: Complexity,
        roles: list[str],
    ) -> None:
        """Run the pipeline in a background thread.

        Lesson 7: call_from_thread for ALL UI updates from worker threads.
        Lesson 16: don't run in devflux's own source dir.
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
                self.call_from_thread(
                    self._log_pipeline,
                    f"[green]  [OK] {role} ({elapsed:.1f}s, {tokens} tokens, {len(files)} archivos)[/green]"
                )
                # Update code panel if files were generated
                if files:
                    self.call_from_thread(self._update_code_panel, files)
            elif status == "garbage":
                fname = data.get("file", "?") if data else "?"
                self.call_from_thread(
                    self._log_pipeline,
                    f"[red]  [SKIP] {role}: basura filtrada ({fname})[/red]"
                )

        # Create runner
        runner = PipelineRunner(
            self._client,  # type: ignore[arg-type]
            self._config,  # type: ignore[arg-type]
            callback=callback,
        )

        # Run pipeline (Lesson 11: arbitrary role list)
        try:
            files = runner.run(roles, user_input, teams=teams, cwd=cwd)
        except Exception as exc:
            self.call_from_thread(
                self._log_chat,
                f"[bold red]ERROR en pipeline: {exc}[/bold red]"
            )
            self.call_from_thread(self._pipeline_done, 0, 0.0, [])
            return

        elapsed = time.time() - start_time

        # Save session
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
        """Called when pipeline finishes (on UI thread)."""
        self.is_running = False

    def _update_code_panel(self, filenames: list[str]) -> None:
        """Update the right panel with code tabs."""
        if not self._config:
            return

        # Get the runner's files from the pipeline
        # We need to read from CWD where files were written
        cwd = Path.cwd()
        tabs = self.query_one("#code-tabs", TabbedContent)

        for fname in filenames:
            fpath = cwd / fname
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
            except Exception:
                continue

            # Determine lexer for syntax highlighting
            ext = fpath.suffix.lstrip(".")
            lexer_map = {
                "py": "python", "js": "javascript", "ts": "typescript",
                "html": "html", "css": "css", "json": "json",
                "yaml": "yaml", "yml": "yaml", "sh": "bash",
                "md": "markdown", "txt": "text",
            }
            lexer = lexer_map.get(ext, "text")

            try:
                syntax = Syntax(content, lexer, theme="monokai", line_numbers=True)
            except Exception:
                syntax = Syntax(content, "text", theme="monokai", line_numbers=False)

            # Lesson 3: TabPane with child as constructor arg
            # Sanitize ID: Textual IDs can't contain dots (index.html → index_html)
            safe_id = f"code-{fname.replace('.', '_')}"
            code_log = RichLog(id=safe_id, wrap=False)
            code_log.write(syntax)

            pane = TabPane(fname, code_log)
            tabs.add_pane(pane)

    # --- Menu handling ---

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
            # Actually we need to mount the MenuWidget
            # Let's update the existing widget
            menu_widget.update(self._menu_widget.render())
            menu_widget.focus()
        else:
            menu_widget.visible = False
            menu_widget.update("")

    def action_close_menu(self) -> None:
        """Close menu (Escape)."""
        self.show_menu = False
        self.show_settings = False
        menu_widget = self.query_one("#menu-widget", Static)
        menu_widget.visible = False
        menu_widget.update("")
        # Return focus to chat input
        self.query_one("#chat-input", Input).focus()

    def _on_menu_select(self, item: str | None) -> None:
        """Handle menu selection."""
        self.show_menu = False
        menu_widget = self.query_one("#menu-widget", Static)
        menu_widget.visible = False
        menu_widget.update("")

        if item is None:
            self.query_one("#chat-input", Input).focus()
            return

        if item == "Desarrollar":
            self._log_chat("[cyan]Escribe tu idea en el chat para desarrollar...[/cyan]")
        elif item == "Corregir bug":
            self._log_chat("[cyan]Describe el bug que queres corregir...[/cyan]")
        elif item == "Analizar repo":
            self._log_chat("[cyan]Describe que queres analizar del repo...[/cyan]")
        elif item == "Ajustes":
            self._show_settings()

        self.query_one("#chat-input", Input).focus()

    def _show_settings(self) -> None:
        """Show settings menu."""
        self.show_settings = True
        menu_widget = self.query_one("#menu-widget", Static)
        menu_widget.visible = True
        self._settings_menu = MenuWidget(SETTINGS_ITEMS, "Ajustes", on_select=self._on_settings_select)
        menu_widget.update(self._settings_menu.render())
        menu_widget.focus()

    def _on_settings_select(self, item: str | None) -> None:
        """Handle settings selection."""
        self.show_settings = False
        menu_widget = self.query_one("#menu-widget", Static)
        menu_widget.visible = False
        menu_widget.update("")

        if item is None or item == "Volver":
            self.query_one("#chat-input", Input).focus()
            return

        if item == "Ver config":
            self._show_config()
        elif item == "Cambiar provider":
            self._change_provider()
        elif item == "Cambiar model":
            self._change_model()
        elif item == "Ver sesiones":
            self._show_sessions()
        elif item == "Ver ultimo run":
            self._show_last_run()
        elif item == "Desinstalar":
            self._uninstall()

        self.query_one("#chat-input", Input).focus()

    def _show_config(self) -> None:
        """Show current configuration."""
        cfg = self._config
        if cfg is None:
            self._log_chat("[yellow]No hay configuracion[/yellow]")
            return
        self._log_chat(
            f"[bold]Configuracion actual:[/bold]\n"
            f"  Provider: {cfg.provider}\n"
            f"  Model: {cfg.model}\n"
            f"  Base URL: {cfg.base_url}\n"
            f"  Temperature: {cfg.temperature}\n"
            f"  Max tokens: {cfg.max_tokens}"
        )

    def _change_provider(self) -> None:
        """Change provider."""
        self._log_chat("[cyan]Cambio de provider: escribe el nuevo provider en el chat[/cyan]")
        self._log_chat(f"Disponibles: {', '.join(PROVIDERS.keys())}")

    def _change_model(self) -> None:
        """Change model."""
        if self._config:
            self._log_chat(f"[cyan]Modelo actual: {self._config.model}[/cyan]")
            self._log_chat("[cyan]Escribe el nuevo modelo en el chat[/cyan]")

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

    def _uninstall(self) -> None:
        """Uninstall DevFlux — delete config and credentials."""
        DevFluxConfig.delete()
        self._log_chat("[bold red]DevFlux desinstalado. Reinicia para reconfigurar.[/bold red]")

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