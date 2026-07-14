from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from devflux.core.config import DevFluxConfig
from devflux.core.orchestrator import Complexity, ConversationRoute, RouterResult
from devflux.core.runner import PipelineRunner, is_functional_project_file
from devflux.tui.app import (
    DevFluxApp,
    FileListWidget,
    human_confirmation,
    inspector_header,
    project_ready_message,
    suggest_project_directory,
)


def test_existing_project_visual_change_gets_one_human_confirmation_and_fast_path(tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<main>Hola</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._orchestrator = SimpleNamespace(
        route_conversation=lambda *_args: RouterResult(route=ConversationRoute.MODIFY),
        select_user_action=lambda _text, _action: (["dev"], "fast", ["implementer"]),
    )
    app.query_one = lambda *_args: SimpleNamespace(value="")  # type: ignore[method-assign]
    app._log_chat = lambda _message: None  # type: ignore[method-assign]
    app._show_confirmation = lambda: None  # type: ignore[method-assign]

    app._handle_chat_submit("agrega burbujas al fondo")

    assert app._confirm_mode is True
    assert app._confirm_options == [("apply", human_confirmation("agrega burbujas al fondo", True), "modify")]
    assert "rol" not in app._confirm_options[0][1].lower()
    assert "PRD" not in app._confirm_options[0][1]


def test_only_functional_files_are_eligible_for_writing_or_display() -> None:
    assert is_functional_project_file("index.html")
    assert is_functional_project_file("assets/app.css")
    assert not is_functional_project_file("PRD.md")
    assert not is_functional_project_file("architecture.md")
    assert not is_functional_project_file("docs/plan.md")
    assert not is_functional_project_file("design.mermaid")


def test_timeout_is_presented_as_human_retry_message() -> None:
    assert DevFluxApp.human_model_error(TimeoutError("http://model:11434 timed out")) == (
        "No pude conectar con el modelo. Probá de nuevo en unos segundos."
    )


def test_inspector_header_explains_file_state() -> None:
    assert inspector_header("src/app.py", is_diff=False) == "Archivo: src/app.py · Nuevo o actualizado"
    assert inspector_header("src/app.py", is_diff=True) == "Archivo: src/app.py · Cambios respecto a tu versión"


def test_file_list_renders_tree_statuses_and_safe_actions() -> None:
    widget = FileListWidget()
    widget.set_files(
        ["src/app.py", "src/views/home.py", "README.txt"],
        {"src/app.py": "Modificado", "src/views/home.py": "Nuevo", "README.txt": "Revisado"},
    )

    rendered = str(widget.render())

    assert "▾ src/" in rendered
    assert "▾ views/" in rendered
    assert "app.py · Estado: Modificado" in rendered
    assert "home.py · Estado: Nuevo" in rendered
    assert "README.txt · Estado: Revisado" in rendered
    assert "D: diff/final" in rendered
    assert "C: copiar" in rendered
    assert "O: abrir" in rendered


def test_toggle_file_view_switches_between_diff_and_final() -> None:
    app = DevFluxApp()
    app._code_file_versions = {
        "src/app.py": {
            "final": "FINAL",
            "diff": "DIFF",
            "show_diff": True,
            "plain": "print('hola')",
        }
    }
    shown: list[str] = []
    app._selected_code_file = lambda: "src/app.py"  # type: ignore[method-assign]
    app._show_file = shown.append  # type: ignore[method-assign]

    app.action_toggle_file_view()

    assert app._code_file_versions["src/app.py"]["show_diff"] is False
    assert shown == ["src/app.py"]


def test_copy_file_uses_final_plain_content() -> None:
    app = DevFluxApp()
    app._code_file_versions = {"index.html": {"plain": "<main>Hola</main>"}}
    copied: list[str] = []
    messages: list[str] = []
    app._selected_code_file = lambda: "index.html"  # type: ignore[method-assign]
    app.copy_to_clipboard = copied.append  # type: ignore[method-assign]
    app._log_chat = messages.append  # type: ignore[method-assign]

    app.action_copy_file()

    assert copied == ["<main>Hola</main>"]
    assert "Contenido copiado" in messages[0]


def test_show_code_reveals_the_inspector_when_files_exist() -> None:
    app = DevFluxApp()
    app._code_files = {"index.html": ("<main>Hola</main>", False)}
    app._code_file_order = ["index.html"]
    calls: list[str] = []
    app._show_selected_file = lambda: calls.append("shown")  # type: ignore[method-assign]
    app.query_one = lambda *_args: SimpleNamespace(visible=False, focus=lambda: calls.append("focused"))  # type: ignore[method-assign]

    app.action_show_code()

    assert calls == ["focused", "shown"]


def test_suggest_project_directory_uses_a_safe_human_slug(tmp_path) -> None:
    assert suggest_project_directory("Una app para recetas de Sofi!", tmp_path) == tmp_path / "app-para-recetas-de-sofi"


def test_project_ready_message_offers_clear_next_steps(tmp_path) -> None:
    message = project_ready_message(["index.html", "styles.css"], tmp_path)

    assert "Tu proyecto está listo" in message
    assert "2 archivos creados" in message
    assert "Abrir proyecto" in message
    assert "Ver código" in message
    assert "Pedir una mejora" in message
    assert "Ctrl+R" in message


@pytest.mark.asyncio
async def test_new_session_starts_in_a_distraction_free_home_view() -> None:
    app = DevFluxApp()
    app._config = DevFluxConfig()

    async with app.run_test():
        assert app.has_class("home")
        assert app.query_one("#right-panel").visible is False
        assert app.query_one("#pipeline-log").visible is False
        assert app.query_one("#progress-summary").visible is False
        assert "¿Qué querés crear?" in str(app.query_one("#home-title").render())


@pytest.mark.asyncio
async def test_progress_summary_is_human_and_visible_while_creating() -> None:
    app = DevFluxApp()
    app._config = DevFluxConfig()

    async with app.run_test():
        app._set_progress_summary("[bold]Creando tu proyecto[/bold]\n● Preparando la estructura")
        summary = app.query_one("#progress-summary")
        assert summary.visible is True
        assert "Preparando la estructura" in str(summary.render())


def test_create_confirmation_uses_the_suggested_project_folder(tmp_path, monkeypatch) -> None:
    app = DevFluxApp()
    monkeypatch.chdir(tmp_path)
    app._show_confirmation = lambda: None  # type: ignore[method-assign]
    app._orchestrator = SimpleNamespace(
        select_user_action=lambda _text, _action: (["dev"], Complexity.SIMPLE, ["backend"])
    )
    app._start_pipeline = lambda *_args: None  # type: ignore[method-assign]

    app._prepare_confirmation("Una app para recetas", "create")
    app._handle_confirm_select()

    assert app._active_project_dir == tmp_path / "app-para-recetas"
    assert app._active_project_dir.exists()


def test_create_confirmation_mentions_the_project_folder(tmp_path) -> None:
    app = DevFluxApp()
    messages: list[str] = []
    app._prepared_project_dir = tmp_path / "recetas"
    app._confirm_options = [("apply", "Entendí tu idea.", "create")]
    app._log_chat = messages.append  # type: ignore[method-assign]
    app.query_one = lambda *_args: SimpleNamespace(focus=lambda: None)  # type: ignore[method-assign]

    app._show_confirmation()

    assert any("Carpeta" in message and "recetas" in message for message in messages)


def test_cancel_pipeline_requests_a_safe_stop() -> None:
    app = DevFluxApp()
    messages: list[str] = []
    app.is_running = True
    app._log_chat = messages.append  # type: ignore[method-assign]

    app.action_cancel_pipeline()

    assert app._cancel_requested is True
    assert messages == ["[yellow]Cancelando cuando termine la etapa actual...[/yellow]"]


def test_open_project_uses_the_current_workspace(monkeypatch, tmp_path) -> None:
    app = DevFluxApp()
    opened: list[Path] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("devflux.tui.app.os.startfile", lambda path: opened.append(Path(path)))

    app.action_open_project()

    assert opened == [tmp_path]


def test_successful_pipeline_disarms_empty_enter_retry() -> None:
    app = DevFluxApp()
    app._last_retry = ("cambia el color", ["dev"], Complexity.SIMPLE, ["implementer"])
    app._log_pipeline = lambda _message: None  # type: ignore[method-assign]
    app._log_chat = lambda _message: None  # type: ignore[method-assign]
    app._pipeline_done(1, 0.1, ["index.html"])

    assert app._last_retry is None


@pytest.mark.asyncio
async def test_connection_failure_shows_only_human_retry_ui_before_any_file_progress() -> None:
    """A failed first LLM call must not imply that files were touched."""
    app = DevFluxApp()
    app._config = DevFluxConfig()
    messages: list[str] = []

    async with app.run_test():
        app._log_chat = messages.append  # type: ignore[method-assign]
        app._last_retry = ("cambia el fondo", ["dev"], Complexity.SIMPLE, ["implementer"])
        app._pipeline_failed(TimeoutError("http://model.internal timed out"))

    assert messages == [
        "No pude conectar con el modelo. Probá de nuevo en unos segundos.",
        "> [Enter] Reintentar    [Esc] Cancelar",
    ]
    assert not any("Actualizando" in message for message in messages)
    assert app._retry_pending is True
    assert app.is_running is False


@pytest.mark.asyncio
async def test_enter_on_retry_relaunches_the_same_request_once() -> None:
    app = DevFluxApp()
    app._config = DevFluxConfig()
    calls: list[tuple[object, ...]] = []

    async with app.run_test() as pilot:
        app._last_retry = ("cambia el fondo", ["dev"], Complexity.SIMPLE, ["implementer"])
        app._retry_pending = True
        app._run_pipeline = lambda *args: calls.append(args)  # type: ignore[method-assign]

        await pilot.press("enter")
        await pilot.press("enter")

    assert calls == [("cambia el fondo", ["dev"], Complexity.SIMPLE, ["implementer"])]
    assert app.is_running is True
    assert app._retry_pending is False


@pytest.mark.asyncio
async def test_escape_cancels_retry_and_returns_focus_to_input_without_running() -> None:
    app = DevFluxApp()
    app._config = DevFluxConfig()
    calls: list[tuple[object, ...]] = []

    async with app.run_test() as pilot:
        app._last_retry = ("cambia el fondo", ["dev"], Complexity.SIMPLE, ["implementer"])
        app._retry_pending = True
        app._run_pipeline = lambda *args: calls.append(args)  # type: ignore[method-assign]

        await pilot.press("escape")

        assert app.focused is app.query_one("#chat-input")

    assert calls == []
    assert app._last_retry is None
    assert app._retry_pending is False


@pytest.mark.asyncio
async def test_successful_response_uses_human_progress_order_and_clears_retry() -> None:
    app = DevFluxApp()
    app._config = DevFluxConfig()
    messages: list[str] = []

    async with app.run_test():
        app._log_chat = messages.append  # type: ignore[method-assign]
        app._last_retry = ("cambia el fondo", ["dev"], Complexity.SIMPLE, ["implementer"])
        app._retry_pending = True
        app._start_pipeline("cambia el fondo", ["dev"], Complexity.SIMPLE, ["implementer"])
        app._show_files_ready(["index.html", "style.css"])
        app._announce_verification()
        app._pipeline_done(2, 0.1, ["index.html", "style.css"])

    assert messages[:4] == [
        "[yellow]Conectando con el modelo...[/yellow]",
        "[yellow]Preparando actualización...[/yellow]",
        "[yellow]Actualizando index.html y style.css...[/yellow]",
        "[yellow]Verificando cambios...[/yellow]",
    ]
    assert "Tu proyecto está listo" in messages[4]
    assert "Pedir una mejora" in messages[4]
    assert app._last_retry is None
    assert app._retry_pending is False


@pytest.mark.asyncio
async def test_question_is_answered_as_chat_without_pipeline_ui(tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<main>Hola</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._config = DevFluxConfig()
    answered: list[str] = []
    async with app.run_test() as pilot:
        app._orchestrator = SimpleNamespace(
            route_conversation=lambda *_args: RouterResult(route=ConversationRoute.QUESTION)
        )
        app._answer_question = answered.append  # type: ignore[method-assign]
        app.query_one("#chat-input").value = "¿Qué hace este proyecto?"
        await pilot.press("enter")

    assert answered == ["¿Qué hace este proyecto?"]
    assert app._confirm_mode is False


class DocumentationProducingClient:
    def chat(self, _messages, **_kwargs):
        return SimpleNamespace(
            content="Archivo: PRD.md\n```markdown\n# Plan interno de implementación\n```",
            tokens=1,
            elapsed=0.01,
        )


def test_runner_never_writes_internal_documentation(tmp_path: Path) -> None:
    files = PipelineRunner(DocumentationProducingClient(), DevFluxConfig()).run(
        ["analista"], "cambia el color", cwd=tmp_path
    )

    assert files == {}
    assert not (tmp_path / "PRD.md").exists()


def test_request_improvement_focuses_input_and_keeps_active_project(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<main>Hola</main>", encoding="utf-8")
    app = DevFluxApp()
    app._active_project_dir = tmp_path
    messages: list[str] = []
    chat_input = SimpleNamespace(value="texto anterior", placeholder="", focus=lambda: messages.append("focused"))
    app.query_one = lambda *_args: chat_input  # type: ignore[method-assign]
    app._log_chat = messages.append  # type: ignore[method-assign]

    app.action_request_improvement()

    assert app._active_project_dir == tmp_path
    assert app.active_thread == "modify"
    assert chat_input.placeholder == "¿Qué querés cambiar de este proyecto?"
    assert chat_input.value == ""
    assert "focused" in messages


def test_recent_project_continue_restores_folder_and_inspector(tmp_path) -> None:
    project = tmp_path / "recetas"
    project.mkdir()
    (project / "index.html").write_text("<main>Recetas</main>", encoding="utf-8")
    app = DevFluxApp()
    app._recent_projects = [{"name": "recetas", "project_dir": project, "files": ["index.html"], "timestamp": "2026-07-14T00:00"}]
    calls: list[object] = []
    chat_input = SimpleNamespace(value="1", placeholder="", focus=lambda: calls.append("focused"))
    app.query_one = lambda *_args, **_kwargs: chat_input  # type: ignore[method-assign]
    app._update_code_panel = lambda files, contents: calls.append((files, contents))  # type: ignore[method-assign]
    app.action_show_code = lambda: calls.append("show_code")  # type: ignore[method-assign]
    app._log_chat = calls.append  # type: ignore[method-assign]

    assert app._continue_recent_project(0) is True

    assert app._active_project_dir == project
    assert app.active_thread == "modify"
    assert (["index.html"], {"index.html": "<main>Recetas</main>"}) in calls
    assert "show_code" in calls
    assert chat_input.placeholder == "¿Qué querés cambiar de este proyecto?"


def test_theme_cycle_applies_real_css_class() -> None:
    app = DevFluxApp()
    classes: list[tuple[str, str]] = []
    messages: list[str] = []
    app.remove_class = lambda name: classes.append(("remove", name))  # type: ignore[method-assign]
    app.add_class = lambda name: classes.append(("add", name))  # type: ignore[method-assign]
    app._log_chat = messages.append  # type: ignore[method-assign]

    app.action_cycle_theme()

    assert ("remove", "theme-claro") in classes
    assert ("add", "theme-noche") in classes
    assert "Tema aplicado" in messages[0]
