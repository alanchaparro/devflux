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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Header,
    Footer,
    Static,
    Input,
    OptionList,
    RichLog,
)
from textual.widgets.option_list import Option
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel
from rich.syntax import Syntax

from ..core.config import (
    DevFluxConfig,
    PROVIDERS,
    CONFIG_PATH,
    DEVFLUX_DIR,
    normalize_provider,
)
from ..core.credentials import CredentialsStore
from ..core.client import LLMClient
from ..core.orchestrator import (
    Orchestrator,
    Complexity,
    ConversationRoute,
    IntentType,
    RouterResult,
    COMPLEXITY_ROLES,
    COMPLEXITY_TOKENS,
)
from ..core.runner import PipelineRunner, is_functional_project_file
from ..core.sessions import SessionRecord
from ..core.context import save_context, load_context_for_prompt, load_context_files

# Lesson 9: CSS_PATH absolute
CSS_PATH = str(Path(__file__).parent / "styles.tcss")

BANNER = "[bold cyan]DevFlux[/bold cyan] [dim]v1.0[/dim]"

# Product menu: implementation choices are deliberately absent.
MENU_ITEMS = [
    "Nuevo proyecto",
    "Continuar proyecto",
    "Ajustes",
    "Diagnóstico",
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

# The interface exposes friendly labels only. Canonical keys stay internal.
PROVIDER_CHOICES = [("Ollama Cloud", "ollama-cloud"), ("Ollama Local", "ollama-local")]


@dataclass(frozen=True)
class SettingsResult:
    """A fully selected configuration, returned only when the user saves."""

    provider: str
    model: str
    api_key: str | None = None


class SettingsScreen(ModalScreen[SettingsResult | None]):
    """Fullscreen configuration editor that keeps all edits local until save."""

    BINDINGS = [Binding("escape", "cancel", "Cancelar", priority=True)]

    def __init__(self, config: DevFluxConfig, has_existing_key: bool) -> None:
        super().__init__()
        self.draft_provider = config.provider
        self.draft_model = config.model
        self._has_existing_key = has_existing_key
        self._models: list[str] = []

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold]Ajustes[/bold]", id="settings-title"),
            Static(
                "Usá Tab para cambiar de sección, ↑/↓ para navegar y Enter para elegir.",
                id="settings-help",
            ),
            Horizontal(
                Vertical(
                    Static("[bold]Provider[/bold]", classes="settings-label"),
                    OptionList(
                        *[Option(label) for label, _provider in PROVIDER_CHOICES],
                        id="settings-provider",
                    ),
                    id="settings-provider-pane",
                ),
                Vertical(
                    Static("[bold]Modelo[/bold]", classes="settings-label"),
                    OptionList(id="settings-model"),
                    id="settings-model-pane",
                ),
                id="settings-selection-row",
            ),
            Vertical(
                Static(id="settings-provider-note"),
                Static("API key", id="settings-api-key-label"),
                Input(
                    placeholder="Pegá una nueva API key (no se muestra la existente)",
                    password=True,
                    id="settings-api-key",
                ),
                id="settings-credential-pane",
            ),
            Static(id="settings-model-error"),
            Horizontal(
                Button("Reintentar", id="settings-retry", variant="warning"),
                Button("Volver", id="settings-back"),
                Button("Cancelar", id="settings-cancel"),
                Button("Guardar cambios", id="settings-save", variant="success"),
                id="settings-actions",
            ),
            id="settings-panel",
        )

    def on_mount(self) -> None:
        provider_list = self.query_one("#settings-provider", OptionList)
        provider_list.highlighted = [key for _label, key in PROVIDER_CHOICES].index(self.draft_provider)
        self._load_models()
        provider_list.focus()

    def _load_models(self) -> None:
        """Populate the wide, scrollable model list without leaking failures."""
        model_list = self.query_one("#settings-model", OptionList)
        error = self.query_one("#settings-model-error", Static)
        retry = self.query_one("#settings-retry", Button)
        back = self.query_one("#settings-back", Button)
        try:
            models = list(PROVIDERS[self.draft_provider]["models"])
            if not models:
                raise RuntimeError("empty model catalog")
        except Exception:
            self._models = []
            model_list.clear_options()
            model_list.visible = False
            error.update("No pudimos cargar los modelos. Podés reintentar o volver sin guardar.")
            error.visible = True
            retry.visible = True
            back.visible = True
            return

        self._models = models
        if self.draft_model not in models:
            self.draft_model = models[0]
        model_list.clear_options()
        model_list.add_options([Option(model) for model in models])
        model_list.highlighted = models.index(self.draft_model)
        model_list.visible = True
        error.visible = False
        retry.visible = False
        back.visible = False
        self._update_provider_details()

    def _update_provider_details(self) -> None:
        info = PROVIDERS[self.draft_provider]
        key_input = self.query_one("#settings-api-key", Input)
        key_label = self.query_one("#settings-api-key-label", Static)
        note = self.query_one("#settings-provider-note", Static)
        cloud = bool(info["needs_key"])
        key_input.visible = cloud
        key_label.visible = cloud
        if cloud:
            note.update(
                "Ollama Cloud. "
                + ("Hay una API key configurada; podés reemplazarla." if self._has_existing_key else "Agregá una API key para conectarte.")
            )
        else:
            note.update("Ollama Local. Elegí el modelo para usar con tu instancia local; no requiere API key.")

    @on(OptionList.OptionSelected, "#settings-provider")
    def select_provider(self, event: OptionList.OptionSelected) -> None:
        self.draft_provider = PROVIDER_CHOICES[event.option_index][1]
        self.draft_model = PROVIDERS[self.draft_provider]["models"][0]
        self._load_models()
        self.query_one("#settings-model", OptionList).focus()

    @on(OptionList.OptionSelected, "#settings-model")
    def select_model(self, event: OptionList.OptionSelected) -> None:
        if self._models:
            self.draft_model = self._models[event.option_index]

    @on(Button.Pressed)
    def press_button(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-save":
            self.action_save()
        elif event.button.id in {"settings-cancel", "settings-back"}:
            self.action_cancel()
        elif event.button.id == "settings-retry":
            self._load_models()

    def activate_focused(self) -> None:
        """Honor the app-wide priority Enter binding while this modal is open."""
        provider_list = self.query_one("#settings-provider", OptionList)
        model_list = self.query_one("#settings-model", OptionList)
        if provider_list.has_focus and provider_list.highlighted is not None:
            self.draft_provider = PROVIDER_CHOICES[provider_list.highlighted][1]
            self.draft_model = PROVIDERS[self.draft_provider]["models"][0]
            self._load_models()
            model_list.focus()
            return
        if model_list.has_focus and model_list.highlighted is not None and self._models:
            self.draft_model = self._models[model_list.highlighted]
            return
        for button in self.query(Button):
            if button.has_focus:
                if button.id == "settings-save":
                    self.action_save()
                elif button.id in {"settings-cancel", "settings-back"}:
                    self.action_cancel()
                elif button.id == "settings-retry":
                    self._load_models()
                return

    def action_save(self) -> None:
        if not self._models:
            return
        key = self.query_one("#settings-api-key", Input).value.strip()
        self.dismiss(SettingsResult(self.draft_provider, self.draft_model, key or None))

    def action_cancel(self) -> None:
        self.dismiss(None)


def is_project_continuation_request(text: str) -> bool:
    """Return whether the user explicitly wants to continue an existing project."""
    normalized = text.casefold()
    continuation_words = ("continuar", "continua", "seguir", "retomar")
    return "proyecto" in normalized and any(
        word in normalized for word in continuation_words
    )


def confirmation_for_intent(
    intent: IntentType,
    *,
    has_existing_project: bool = False,
    is_bug_request: bool = False,
    is_continuation_request: bool = False,
) -> tuple[list[tuple[str, str, str]], int]:
    """Return every confirmation action and its context-sensitive default.

    ``has_existing_project`` must come from ``load_context_files`` so hidden
    metadata (for example ``.devflux`` and ``.git``) cannot make an empty
    directory look like an existing project.
    """
    options = [
        ("1", "Crear proyecto nuevo — equipo-dev para un proyecto nuevo", "create"),
        (
            "2",
            "Modificar proyecto actual — equipo-dev con contexto y archivos existentes",
            "modify",
        ),
        ("3", "Buscar/corregir bugs — equipo-bugs sobre archivos existentes", "bugs"),
        ("4", "Responder como pregunta — LLM directo con contexto del proyecto", "question"),
        ("5", "Reescribir mi idea", "rewrite"),
    ]

    if is_bug_request:
        return options, 2
    if has_existing_project and is_continuation_request:
        return options, 1
    if intent in (IntentType.QUESTION, IntentType.CHAT):
        return options, 3
    if has_existing_project:
        return options, 1
    return options, 0


def human_confirmation(text: str, has_existing_project: bool) -> str:
    """Describe the proposed outcome without leaking routing implementation."""
    normalized = text.strip().rstrip(".")
    if "burbuja" in normalized.casefold():
        target = "al proyecto actual" if has_existing_project else "al proyecto nuevo"
        return f"Entendí: agregaré un fondo de burbujas animadas {target}."
    verb = "actualizaré" if has_existing_project else "crearé"
    target = "el proyecto actual" if has_existing_project else "un proyecto"
    return f"Entendí: {verb} {target} según tu pedido: {normalized}."


class MenuWidget(Static):
    """Menu using Static + on_key (Lesson 4: NOT OptionList).

    Lesson 6: can_focus=True on Static subclass for on_key to work.
    """

    can_focus = True

    def __init__(
        self,
        items: list[str] | None = None,
        title: str = "Menu",
        on_select=None,
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._items = items or []
        self._title = title
        self._on_select = on_select
        self._selected = 0

    def set_menu(self, items: list[str], title: str, on_select, selected: int = 0) -> None:
        """Reuse this mounted keyboard selector for a new list of choices."""
        self._items = items
        self._title = title
        self._on_select = on_select
        self._selected = max(0, min(selected, len(items) - 1)) if items else 0
        self.refresh()

    def select_current(self) -> None:
        """Confirm the highlighted choice (used by the priority Enter binding)."""
        if self._items and self._on_select:
            self._on_select(self._items[self._selected])

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
            self.select_current()
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
    SUB_TITLE = "Asistente para tu proyecto"

    BINDINGS = [
        # Lesson 5: priority=True to intercept Enter before widgets
        Binding("enter", "submit_input", "Enviar", priority=True),
        Binding("escape", "close_menu", "Cerrar", priority=True),
        Binding("ctrl+s", "toggle_menu", "Menú", priority=True),
        Binding("ctrl+d", "toggle_diagnostics", "Diagnóstico", priority=True),
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
        # Explicit wizard state prevents API-key/model input from being treated
        # as a provider after Enter.
        self._wizard_step = "provider"
        self._pending_provider: str | None = None
        self._pending_config: DevFluxConfig | None = None
        # BUG 2 DEFINITIVE FIX: NO TabbedContent — use file list + RichLog
        # Store file contents keyed by filename for display
        self._code_files: dict[str, Any] = {}  # fname -> (display_content, is_diff)
        self._code_file_order: list[str] = []  # ordered list of filenames
        # FEATURE: Memoria de sesion — track last user input for context saving
        self._last_user_input: str = ""

        # FEATURE: Confirmacion interactiva antes de ejecutar el pipeline
        self._confirm_mode: bool = False
        self._confirm_options: list[tuple[str, str, str]] = []  # (label, description, action)
        self._confirm_selected: int = 0
        self._confirm_intent: IntentType = IntentType.CODE
        self._confirm_text: str = ""
        # Conversational router state persists the current thread across turns.
        self.conversation_turns: list[dict[str, str]] = []
        self.active_thread: str = "none"  # none | modify | bugs | question
        self._router_error_mode: bool = False
        self._diagnostics_visible: bool = False
        self._last_retry: tuple[str, list[str], Complexity, list[str]] | None = None
        self._retry_pending = False
        self._files_progress_announced = False
        self._verification_announced = False
        # A vague modification must receive a concrete follow-up before a team runs.
        self.pending_modify_clarification: bool = False
        self._pending_clarification_action: str | None = None

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
                "Elegí cómo querés usar el modelo con ↑/↓ y Enter:",
                id="wizard-content",
            ),
            MenuWidget(
                [label for label, _key in PROVIDER_CHOICES],
                "Proveedor",
                on_select=self._select_wizard_provider,
                id="wizard-selector",
            ),
            Input(placeholder="Pegá tu API key", password=True, id="wizard-input"),
            id="wizard",
        )

    def _compose_main(self) -> ComposeResult:
        """Compose main UI with left/right panels."""
        # Left panel: banner + chat log + input + menu + pipeline log
        yield Horizontal(
            # Left Panel (40%)
            Vertical(
                Static(BANNER, id="banner"),
                Static(
                    "[bold]¿Qué querés crear?[/bold]\n"
                    "[dim]Contalo como se lo contarías a alguien. DevFlux se ocupa de lo técnico.[/dim]",
                    id="home-title",
                ),
                RichLog(id="chat-log", wrap=True, markup=True),
                Input(placeholder="Escribi tu idea...", id="chat-input"),
                MenuWidget(id="menu-widget"),
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
        if self._config is None:
            self.query_one("#wizard-input", Input).visible = False
            self.query_one("#wizard-selector", MenuWidget).focus()
            return

        # A new user starts with one clear surface: their idea. Code and
        # diagnostics only appear once there is something concrete to inspect.
        self.add_class("home")
        self.query_one("#right-panel").visible = False

        self._client = LLMClient(self._config, self._creds)
        # REFACTOR: Pass LLM client to orchestrator for intent classification
        self._orchestrator = Orchestrator(self._client)
        # Keep the first impression conversational. Provider, model and cwd
        # remain available only in Ctrl+D diagnostics.
        log = self.query_one("#chat-log", RichLog)
        log.write("[bold green]Hola, soy DevFlux.[/bold green]")
        log.write("Contame qué querés crear, cambiar, revisar o entender de tu proyecto.")

        diagnostics = self.query_one("#pipeline-log", RichLog)
        diagnostics.write("[bold]Diagnóstico[/bold]")
        diagnostics.write(f"Modelo: {self._config.model} | Provider: {self._config.provider}")
        diagnostics.write(f"Directorio: {Path.cwd()}")
        diagnostics.visible = False
        viewer = self.query_one("#code-viewer", RichLog)
        viewer.write("[dim]Todavía no hay cambios para mostrar.[/dim]")

        # Hide menu widget initially (Lesson 10: visible, not display)
        menu = self.query_one("#menu-widget", MenuWidget)
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

        FEATURE 3: In confirmation mode, the priority Enter binding explicitly
        selects the highlighted action.
        """
        # FEATURE 3: In confirm mode, Enter selects the highlighted option
        if self._confirm_mode:
            self._handle_confirm_select()
            return

        # The app owns a priority Enter binding. Explicitly hand it to the
        # fullscreen modal so OptionList and visible action buttons remain
        # entirely keyboard-driven.
        if isinstance(self.screen, SettingsScreen):
            self.screen.activate_focused()
            return

        # A selector owns Enter while visible. The app-level binding has
        # priority, so dispatch it explicitly instead of treating its state as
        # free-form text input.
        if self._config is None and self._wizard_step in {"provider", "model"}:
            self.query_one("#wizard-selector", MenuWidget).select_current()
            return
        if self._settings_input_mode in {"provider_selector", "model_selector"}:
            self.query_one("#menu-widget", MenuWidget).select_current()
            return
        if self.show_menu or self.show_settings:
            self.query_one("#menu-widget", MenuWidget).select_current()
            return

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
            self._submit_wizard(value)
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
            if self._retry_pending and self._last_retry and not self.is_running:
                prompt, teams, complexity, roles = self._last_retry
                self._start_pipeline(prompt, teams, complexity, roles)
            return
        # _handle_chat_submit clears input and logs the message itself
        self._handle_chat_submit(value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter on input fields (fallback if binding doesn't intercept).

        With priority=True binding, action_submit_input handles Enter first.
        But if focus changes or binding doesn't fire, this is the safety net.

        FEATURE 3: In confirmation mode, the priority Enter binding explicitly
        selects the highlighted action.
        """
        # FEATURE 3: Don't process Enter if in confirm mode
        if self._confirm_mode:
            return

        # Delegate to action_submit_input to avoid double-processing
        # event.value is already available, use it directly
        if self._settings_input_mode and self._config is not None:
            self._handle_settings_input(event.value)
            return

        if self._config is None:
            if self._wizard_step == "api_key":
                self._submit_wizard(event.value)
        else:
            # If we got here, the binding didn't fire, so handle it.
            # _handle_chat_submit clears input and logs the message itself.
            self._handle_chat_submit(event.value)

    def _submit_wizard(self, value: str) -> None:
        """Only the API-key step accepts text input in the wizard."""
        if self._wizard_step == "api_key":
            self._handle_wizard_api_key(value)

    def _select_wizard_provider(self, label: str | None) -> None:
        """Begin a provider-specific flow from the visible selector."""
        provider = dict(PROVIDER_CHOICES).get(label or "")
        if provider is None:
            return
        info = PROVIDERS[provider]
        self._pending_provider = provider
        self._pending_config = DevFluxConfig(
            provider=provider, base_url=info["base_url"], model=info["models"][0]
        )
        if info["needs_key"]:
            self.query_one("#wizard-content", Static).update(
                f"[bold yellow]Configurar {info['label']}[/bold yellow]\n\nPegá tu API key y presioná Enter:"
            )
            selector = self.query_one("#wizard-selector", MenuWidget)
            selector.visible = False
            wizard_input = self.query_one("#wizard-input", Input)
            wizard_input.value = ""
            wizard_input.visible = True
            self._wizard_step = "api_key"
            wizard_input.focus()
            return
        self._show_wizard_model_selector()

    def _show_wizard_model_selector(self) -> None:
        """Models are selected with the same keyboard widget, never typed."""
        config = self._pending_config
        if config is None:
            return
        selector = self.query_one("#wizard-selector", MenuWidget)
        selector.set_menu(PROVIDERS[config.provider]["models"], "Modelo", self._select_wizard_model)
        selector.visible = True
        self.query_one("#wizard-input", Input).visible = False
        self.query_one("#wizard-content", Static).update(
            "[bold yellow]Elegí un modelo[/bold yellow]\n\nUsá ↑/↓ y Enter."
        )
        self._wizard_step = "model"
        selector.focus()

    # Kept only as a compatibility seam for callers of the old API. The UI
    # neither renders nor accepts a provider text field.
    def _handle_wizard(self, value: str) -> None:
        provider = normalize_provider(value)
        labels = {key: label for label, key in PROVIDER_CHOICES}
        self._select_wizard_provider(labels.get(provider, ""))

    def _handle_wizard_api_key(self, key: str) -> None:
        provider = self._pending_provider
        if provider is None or not key.strip():
            self.query_one("#wizard-content", Static).update(
                "[bold red]La API key no puede estar vacía.[/bold red]\n\nPegá tu API key y presioná Enter:"
            )
            self.query_one("#wizard-input", Input).focus()
            return
        self._creds.set(provider, key.strip())
        self.query_one("#wizard-input", Input).value = ""
        self._show_wizard_model_selector()

    def _select_wizard_model(self, model: str | None) -> None:
        config = self._pending_config
        if config is None or not model:
            return
        config.model = model
        config.save()
        self.query_one("#wizard-content", Static).update(
            f"[bold green]Configurado![/bold green]\n\n"
            f"Proveedor: {PROVIDERS[config.provider]['label']}\n"
            f"Modelo: {config.model}\n\nReiniciá DevFlux para empezar."
        )
        self.query_one("#wizard-selector", MenuWidget).visible = False
        self._wizard_step = "done"

    def _handle_wizard_model(self, model: str) -> None:
        self._select_wizard_model(model)

    # --- Chat handling ---

    def _handle_chat_submit(self, text: str) -> None:
        """Handle chat input submit.

        BUG 1 FIX: Reset all state, clear pipeline log, create fresh client.
        FEATURE 2: Classify intent first, show preview, skip pipeline for questions.
        FEATURE 3: Confirmacion interactiva — muestra opciones antes de ejecutar.
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

        # Preserve every turn before routing so a clarification reply is evaluated
        # with its original request, active thread, context summary and inventory.
        self.conversation_turns.append({"role": "user", "content": text})
        router_result = self._orchestrator.route_conversation(
            self.conversation_turns,
            self.active_thread,
            load_context_for_prompt(Path.cwd()),
            text,
        )
        self._apply_conversation_route(text, router_result)

    def _apply_conversation_route(self, text: str, result: RouterResult) -> None:
        """Apply a structured LLM route without reclassifying by keywords."""
        self._last_user_input = text
        if result.error:
            # The active thread is the semantic fallback: a malformed, timed-out
            # or unavailable router must never force the user to classify again.
            # route_conversation already recorded the technical warning/debug raw.
            fallback_routes = {
                "modify": ConversationRoute.MODIFY,
                "bugs": ConversationRoute.BUG,
                "question": ConversationRoute.QUESTION,
            }
            fallback_route = fallback_routes.get(self.active_thread)
            self._router_error_mode = False
            if fallback_route is not None:
                result = RouterResult(route=fallback_route)
            else:
                # With no established thread, retain the ordinary selector but do
                # not expose router internals or leave the UI in an error mode.
                self._prepare_confirmation(text, "modify" if load_context_files(Path.cwd()) else "create")
                return

        route = result.route
        if route is None:
            # RouterResult is intentionally recoverable. This guard keeps a bad
            # custom client from producing a technical error in the TUI.
            self._prepare_confirmation(text, "modify" if load_context_files(Path.cwd()) else "create")
            return
        if route is ConversationRoute.CLARIFY:
            action = "bugs" if self.active_thread == "bugs" else "modify"
            self.active_thread = "bugs" if action == "bugs" else "modify"
            self._pending_clarification_action = action
            self.pending_modify_clarification = action == "modify"
            self._show_clarification(action)
            return

        self.pending_modify_clarification = False
        self._pending_clarification_action = None
        self._router_error_mode = False
        if route is ConversationRoute.QUESTION:
            self.active_thread = "question"
            self.is_running = True
            self._log_chat("[dim yellow]Orquestador: Respondiendo pregunta directamente...[/dim yellow]")
            self._answer_question(text)
            return

        has_existing_project = bool(load_context_files(Path.cwd()))
        if route is ConversationRoute.BUG:
            action = "bugs"
        elif self.active_thread == "modify":
            # Once the user explicitly selected Modify, preserve that semantic
            # thread even if project inventory is temporarily unavailable.
            action = "modify"
        else:
            action = "modify" if has_existing_project else "create"
        self.active_thread = "bugs" if action == "bugs" else "modify"
        self._prepare_confirmation(text, action)

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
            self.call_from_thread(self._log_pipeline, f"Cliente LLM: {exc}")
            self.call_from_thread(self._log_chat, self.human_model_error(exc))
            self.call_from_thread(self._question_done)
            return

        # FEATURE: Memoria de sesion — load context before answering
        context_snippet = load_context_for_prompt()

        # System prompt WITH project context so the LLM knows what was generated
        system_content = (
            "Sos DevFlux, un asistente de desarrollo de software. "
            "Respondes preguntas de forma clara y concisa. "
            "Si el usuario pide codigo o un proyecto, decile que "
            "reformule como peticion de codigo para ejecutar el pipeline.\n\n"
            f"{context_snippet}"
        )

        messages = [
            {
                "role": "system",
                "content": system_content,
            },
            {"role": "user", "content": user_input},
        ]

        try:
            response = client.chat(messages)
        except Exception as exc:
            self.call_from_thread(self._log_pipeline, f"Consulta LLM: {exc}")
            self.call_from_thread(self._log_chat, self.human_model_error(exc))
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

        # Display the answer in BOTH chat log and pipeline log
        answer = response.content if response.content else "(sin respuesta)"
        self.call_from_thread(
            self._log_chat,
            f"[bold green]DevFlux:[/bold green] {answer}"
        )
        self.call_from_thread(self._log_pipeline, f"Respuesta: {answer}")
        self.call_from_thread(
            self._log_pipeline,
            f"Uso: {response.tokens} tokens, {response.elapsed:.1f}s",
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

    def _start_pipeline(
        self,
        prompt: str,
        teams: list[str],
        complexity: Complexity,
        roles: list[str],
    ) -> None:
        """Start one request without claiming any file has been changed yet."""
        if self.is_running:
            return
        self.is_running = True
        self._retry_pending = False
        self._files_progress_announced = False
        self._verification_announced = False
        self._pipeline_count += 1
        self._log_chat("[yellow]Conectando con el modelo...[/yellow]")
        self._run_pipeline(prompt, teams, complexity, roles)

    def _show_files_ready(self, files: list[str]) -> None:
        """Announce writes only after an LLM response yielded concrete files."""
        if self._files_progress_announced or not files:
            return
        self._files_progress_announced = True
        # Reveal code only once the user has something real to inspect.
        self.remove_class("home")
        self.query_one("#right-panel").visible = True
        self._log_chat("[yellow]Preparando actualización...[/yellow]")
        names = ", ".join(files[:-1]) + (" y " if len(files) > 1 else "") + files[-1]
        self._log_chat(f"[yellow]Actualizando {names}...[/yellow]")

    def _announce_verification(self) -> None:
        """Keep the last human progress step singular and meaningful."""
        if self._verification_announced:
            return
        self._verification_announced = True
        self._log_chat("[yellow]Verificando cambios...[/yellow]")

    def _pipeline_failed(self, exc: Exception) -> None:
        """Expose a retry affordance while retaining technical detail in Ctrl+D only."""
        self.is_running = False
        self._retry_pending = self._last_retry is not None
        self._log_pipeline(f"Pipeline: {exc}")
        self._log_chat(self.human_model_error(exc))
        if self._retry_pending:
            self._log_chat("> [Enter] Reintentar    [Esc] Cancelar")
        try:
            self.query_one("#chat-input", Input).focus()
        except Exception:
            pass

    def _cancel_retry(self) -> None:
        """Disarm a failed request; Escape must never cause a later implicit retry."""
        self._retry_pending = False
        self._last_retry = None
        self.is_running = False
        self._log_chat("[dim]Reintento cancelado.[/dim]")
        try:
            self.query_one("#chat-input", Input).focus()
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
            self.call_from_thread(self._log_pipeline, f"Cliente LLM: {exc}")
            self.call_from_thread(self._pipeline_failed, exc)
            return

        # Spinner animation (Lesson 8: ASCII only)
        self._spinner_idx = 0

        def callback(role: str, status: str, data: dict[str, Any] | None) -> None:
            """Callback for pipeline progress updates."""
            # Lesson 7: call_from_thread for ALL UI updates
            if status == "start":
                spinner = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
                self._spinner_idx += 1
                self.call_from_thread(self._log_pipeline, f"{spinner} {role} inició")
                if role == "equipo-bugs":
                    self.call_from_thread(self._announce_verification)
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
                # A write can only be announced once the response includes real files.
                if files:
                    self.call_from_thread(self._show_files_ready, files)
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
            # Preserve technical detail in the hidden diagnostics log; the chat
            # receives only the actionable, human retry state.
            self.call_from_thread(self._log_pipeline, f"Pipeline: {exc}")
            self.call_from_thread(self._pipeline_failed, exc)
            # Close the fresh client on error
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

        # Final message stays human-facing; token, timing and cwd information
        # remain in Ctrl+D diagnostics instead of the conversation.
        self.call_from_thread(self._log_pipeline, f"Archivos generados: {', '.join(files.keys())}")

        self.call_from_thread(self._pipeline_done, runner.total_tokens, elapsed, list(files.keys()))

    def _pipeline_done(self, tokens: int, elapsed: float, files: list[str]) -> None:
        """Called when pipeline finishes (on UI thread).

        BUG 1 FIX: Always reset is_running, regardless of success/failure.
        FEATURE: Memoria de sesion — save context after pipeline run.
        """
        self.is_running = False
        # A completed write must not leave an invisible retry armed: pressing
        # Enter on an empty chat input is reserved for an explicitly failed run.
        if files:
            self._last_retry = None
            self._retry_pending = False
            self._announce_verification()
        self._log_pipeline(f"Completado: {len(files)} archivos, {tokens} tokens, {elapsed:.1f}s")
        if files:
            self._log_chat("[bold green]Listo.[/bold green]")
        elif self._last_retry is None:
            self._log_chat("[bold green]Listo.[/bold green]")

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

        filenames = [name for name in filenames if is_functional_project_file(name)]
        if not filenames:
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
        menu_widget = self.query_one("#menu-widget", MenuWidget)

        if self.show_menu:
            menu_widget.set_menu(MENU_ITEMS, "Menu", self._on_menu_select)
            menu_widget.visible = True
            menu_widget.focus()
        else:
            menu_widget.visible = False

    def action_close_menu(self) -> None:
        """Close a menu or cancel contextual confirmation with Escape."""
        # Escape is a priority binding, so it arrives here before App.on_key.
        if self._screen_stack and isinstance(self.screen, SettingsScreen):
            self.screen.action_cancel()
            return
        if self._confirm_mode:
            self._cancel_confirmation()
            return
        if self._retry_pending:
            self._cancel_retry()
            return
        if self._config is None:
            self._wizard_step = "provider"
            selector = self.query_one("#wizard-selector", MenuWidget)
            selector.set_menu(
                [label for label, _key in PROVIDER_CHOICES], "Proveedor", self._select_wizard_provider
            )
            selector.visible = True
            self.query_one("#wizard-input", Input).visible = False
            self.query_one("#wizard-content", Static).update(
                "Elegí cómo querés usar el modelo con ↑/↓ y Enter:"
            )
            selector.focus()
            return

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

        if item == "Nuevo proyecto":
            self._log_chat("Contame qué querés crear y preparo una propuesta.")
        elif item == "Continuar proyecto":
            self._log_chat("Contame qué querés cambiar o revisar del proyecto actual.")
        elif item == "Ajustes":
            self._open_settings()
        elif item == "Diagnóstico":
            self.action_toggle_diagnostics()

        self.query_one("#chat-input", Input).focus()

    # --- Theme handling (FEATURE 1: Temas) ---

    def _cycle_theme(self) -> None:
        """Cycle to next theme in the THEMES list."""
        self._theme_idx = (self._theme_idx + 1) % len(THEMES)
        self._current_theme = THEMES[self._theme_idx]
        self._log_chat(f"[bold cyan]Tema: {self._current_theme}[/bold cyan]")
        self._log_chat(f"[dim]Temas disponibles: {', '.join(THEMES)}[/dim]")

    # --- Settings handling ---

    def _open_settings(self) -> None:
        """Open the configuration editor above the whole application, not the menu."""
        if self._config is None:
            return
        self.push_screen(
            SettingsScreen(self._config, self._creds.has_key(self._config.provider)),
            self._apply_settings_result,
        )

    def _apply_settings_result(self, result: SettingsResult | None) -> None:
        """Persist a confirmed draft and restore the chat without changing its thread."""
        if result is None or self._config is None:
            try:
                self.query_one("#chat-input", Input).focus()
            except Exception:
                pass
            return

        info = PROVIDERS[result.provider]
        self._config.provider = result.provider
        self._config.base_url = info["base_url"]
        self._config.model = result.model
        self._config.save()
        if result.api_key:
            self._creds.set(result.provider, result.api_key)
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass
        self._client = LLMClient(self._config, self._creds)
        self._log_chat("[bold green]Ajustes guardados.[/bold green]")
        try:
            self.query_one("#chat-input", Input).focus()
        except Exception:
            pass

    def _show_settings(self) -> None:
        """Compatibility alias for callers of the previous embedded settings UI."""
        self._open_settings()

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
            return
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
            f"[bold]Configuración actual:[/bold]\n"
            f"  Proveedor: {PROVIDERS[cfg.provider]['label']}\n"
            f"  Modelo: {cfg.model}\n"
            f"  API key: {'configurada' if has_key else 'no configurada'}"
        )

    def _change_provider(self) -> None:
        """Open a preselected provider selector; no canonical keys are typed."""
        if self._config is None:
            return
        labels = [label for label, _key in PROVIDER_CHOICES]
        current_label = {key: label for label, key in PROVIDER_CHOICES}[self._config.provider]
        selector = self.query_one("#menu-widget", MenuWidget)
        selector.set_menu(labels, "Cambiar proveedor", self._select_settings_provider, labels.index(current_label))
        selector.visible = True
        self._settings_input_mode = "provider_selector"
        selector.focus()

    def _select_settings_provider(self, label: str | None) -> None:
        """Continue to a keyboard model selector for the selected provider."""
        provider = dict(PROVIDER_CHOICES).get(label or "")
        if provider is None or self._config is None:
            return
        info = PROVIDERS[provider]
        self._pending_provider = provider
        self._pending_config = DevFluxConfig(
            provider=provider, base_url=info["base_url"], model=info["models"][0]
        )
        selector = self.query_one("#menu-widget", MenuWidget)
        selector.set_menu(info["models"], "Elegir modelo", self._select_settings_model)
        self._settings_input_mode = "model_selector"
        selector.focus()

    def _select_settings_model(self, model: str | None) -> None:
        """Persist both choices after the user confirms the model."""
        config = self._pending_config
        if config is None or not model or self._config is None:
            return
        config.model = model
        self._config.provider = config.provider
        self._config.base_url = config.base_url
        self._config.model = config.model
        self._config.save()
        self._settings_input_mode = None
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass
        self._client = LLMClient(self._config, self._creds)
        self.query_one("#menu-widget", MenuWidget).visible = False
        info = PROVIDERS[config.provider]
        self._log_chat(f"[bold green]Proveedor cambiado a {info['label']}.[/bold green]")
        self._log_chat(f"Modelo: {self._config.model}")
        if info["needs_key"] and not self._creds.has_key(config.provider):
            self._log_chat("[yellow]Este proveedor necesita una API key. Elegí Agregar/modificar API key.[/yellow]")
        self.query_one("#chat-input", Input).focus()

    def _add_api_key(self) -> None:
        """Add or modify API key — enter settings input mode."""
        if not self._config:
            self._log_chat("[yellow]No hay configuracion[/yellow]")
            return
        provider = self._config.provider
        if not PROVIDERS[provider]["needs_key"]:
            self._log_chat("[cyan]Ollama Local no necesita API key.[/cyan]")
            return
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
            provider = normalize_provider(value)
            if provider is None:
                self._log_chat("[bold red]Provider inválido.[/bold red]")
                self._log_chat(f"Disponibles: {', '.join(PROVIDERS.keys())}")
                chat_input = self.query_one("#chat-input", Input)
                chat_input.value = value
                chat_input.focus()
                chat_input.select_all()
                self._settings_input_mode = "provider"
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

    # --- Confirmación humana ---

    def _prepare_confirmation(self, text: str, action: str) -> None:
        self._confirm_mode = True
        self._confirm_text = text
        self._confirm_intent = IntentType.CODE
        self._confirm_selected = 0
        self._confirm_options = [
            ("apply", human_confirmation(text, bool(load_context_files(Path.cwd()))), action)
        ]
        self._show_confirmation()

    def _show_confirmation(self) -> None:
        """Present one friendly action instead of an implementation selector."""
        self._log_chat(f"[bold green]DevFlux:[/bold green] {self._confirm_options[0][1]}")
        self._log_chat("[bold cyan][Enter] Aplicar[/bold cyan]  ·  [dim][Esc] Cambiar pedido[/dim]")
        try:
            self.query_one("#chat-input", Input).focus()
        except Exception:
            pass

    def on_key(self, event) -> None:  # type: ignore[override]
        """Handle key events at the App level.

        When in confirm mode, ↑/↓ navigate the confirmation options. Enter is
        dispatched only by the priority ``action_submit_input`` binding so a
        submission cannot also be interpreted as a confirmation.
        """
        from textual.events import Key

        if not isinstance(event, Key):
            return

        if self._confirm_mode:
            key = event.key
            if key == "up":
                self._confirm_selected = (self._confirm_selected - 1) % len(self._confirm_options)
                self._show_confirmation()
                event.prevent_default()
                event.stop()
            elif key == "down":
                self._confirm_selected = (self._confirm_selected + 1) % len(self._confirm_options)
                self._show_confirmation()
                event.prevent_default()
                event.stop()
            elif key == "escape":
                self._cancel_confirmation()
                event.prevent_default()
                event.stop()

    def _handle_confirm_select(self) -> None:
        """Execute the action chosen by the user in confirm mode."""
        if not self._confirm_options:
            return

        _num, _desc, action = self._confirm_options[self._confirm_selected]
        text = self._confirm_text

        # Exit confirm mode
        self._confirm_mode = False

        # A router failure is recoverable by an explicit user choice. Do not call
        # the router again or turn it into another clarification loop.
        if self._router_error_mode:
            self._router_error_mode = False
            if action == "modify":
                self.active_thread = "modify"
                self._pending_clarification_action = "modify"
                self.pending_modify_clarification = True
                self._show_clarification("modify")
                return
            if action == "question":
                self.active_thread = "question"
                self.is_running = True
                self._answer_question(text)
                return
            self._log_chat("[cyan]Elegí Modify o Question para continuar después del error del router.[/cyan]")
            return

        if action in {"create", "modify", "bugs"}:
            pipeline_text = text
            if action == "modify":
                pipeline_text = (
                    "INSTRUCCIÓN: modifica los archivos existentes que sean funcionales y necesarios; "
                    "no crees archivos duplicados innecesarios, documentación ni archivos internos.\n\n"
                    f"Solicitud del usuario: {text}"
                )

            if hasattr(self._orchestrator, "select_user_action"):
                teams, complexity, roles = self._orchestrator.select_user_action(text, action)
            else:  # Compatibility for embedders that provide the former router API.
                team = "bugs" if action == "bugs" else "dev"
                teams, complexity = self._orchestrator.select_team(text, team)
                roles = self._orchestrator.get_roles()
            self._last_retry = (pipeline_text, teams, complexity, roles)
            self._start_pipeline(pipeline_text, teams, complexity, roles)

        elif action == "question":
            self.is_running = True
            self._answer_question(text)

        elif action == "rewrite":
            # Put the text back in the input for the user to rewrite
            self._log_chat("[cyan]Reescribi tu idea en el chat...[/cyan]")
            try:
                plog = self.query_one("#pipeline-log", RichLog)
                plog.clear()
                plog.write("[dim]Pipeline: esperando nueva idea...[/dim]")
            except Exception:
                pass
            # Restore the text to the input
            try:
                chat_input = self.query_one("#chat-input", Input)
                chat_input.value = text
                chat_input.focus()
            except Exception:
                pass

    def _show_clarification(self, action: str) -> None:
        """Ask for concrete work without invoking a pipeline."""
        if action == "bugs":
            message = (
                "Perfecto. ¿Qué error o comportamiento querés corregir? "
                "Contame qué pasa y, si podés, en qué pantalla o archivo."
            )
        else:
            message = (
                "Perfecto. ¿Qué querés agregar, cambiar o corregir en tu proyecto? "
                "Describímelo y preparo la modificación."
            )
        self._log_chat(f"[cyan]{message}[/cyan]")
        try:
            plog = self.query_one("#pipeline-log", RichLog)
            plog.clear()
        except Exception:
            pass
        self._log_pipeline(f"[cyan]{message}[/cyan]")
        try:
            self.query_one("#chat-input", Input).focus()
        except Exception:
            pass

    def _cancel_confirmation(self) -> None:
        """Cancel confirmation mode and return to normal state."""
        self._confirm_mode = False
        self._log_chat("[dim]Confirmacion cancelada.[/dim]")
        try:
            plog = self.query_one("#pipeline-log", RichLog)
            plog.clear()
            plog.write("[dim]Pipeline: esperando...[/dim]")
        except Exception:
            pass
        try:
            self.query_one("#chat-input", Input).focus()
        except Exception:
            pass

    @staticmethod
    def human_model_error(_exc: Exception) -> str:
        """Never leak endpoints, stack traces or provider details into chat."""
        return "No pude conectar con el modelo. Probá de nuevo en unos segundos."

    def action_toggle_diagnostics(self) -> None:
        """Reveal support details only after the explicit Ctrl+D shortcut."""
        self._diagnostics_visible = not self._diagnostics_visible
        try:
            diagnostics = self.query_one("#pipeline-log", RichLog)
            diagnostics.visible = self._diagnostics_visible
            if self._diagnostics_visible:
                diagnostics.scroll_end(animate=False)
        except Exception:
            pass

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