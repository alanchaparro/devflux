from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from devflux.core.config import DevFluxConfig
from devflux.core.orchestrator import Complexity, ConversationRoute, RouterResult
from devflux.core.runner import PipelineRunner, is_functional_project_file
from devflux.tui.app import DevFluxApp, human_confirmation


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
        "No pude conectar con el modelo. Probá de nuevo en unos segundos. [Enter] Reintentar"
    )


def test_successful_pipeline_disarms_empty_enter_retry() -> None:
    app = DevFluxApp()
    app._last_retry = ("cambia el color", ["dev"], Complexity.SIMPLE, ["implementer"])
    app._log_pipeline = lambda _message: None  # type: ignore[method-assign]
    app._log_chat = lambda _message: None  # type: ignore[method-assign]
    app._pipeline_done(1, 0.1, ["index.html"])

    assert app._last_retry is None


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
