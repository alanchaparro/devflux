from __future__ import annotations

from pathlib import Path

from devflux.core.client import LLMResponse
from devflux.core.config import DevFluxConfig
from devflux.core.context import _list_project_files, load_context_for_prompt
from devflux.core.runner import PipelineRunner


class CapturingClient:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        self.messages.append(messages)
        return LLMResponse(content="NO_BACKEND", tokens=1, elapsed=0.01)


def test_dotenv_files_are_excluded_from_project_context(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("API_KEY=super-secret", encoding="utf-8")
    (tmp_path / ".env.local").write_text("TOKEN=another-secret", encoding="utf-8")
    (tmp_path / "settings.env").write_text("PASSWORD=third-secret", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('safe')", encoding="utf-8")
    (tmp_path / "build" / "lib").mkdir(parents=True)
    (tmp_path / "build" / "lib" / "duplicate.py").write_text("print('duplicate')", encoding="utf-8")

    files = _list_project_files(tmp_path)
    names = {name for name, _size in files}

    assert names == {"app.py"}
    prompt_context = load_context_for_prompt(tmp_path)
    assert ".env" not in prompt_context
    assert "settings.env" not in prompt_context


def test_pipeline_never_sends_dotenv_contents_to_the_llm(tmp_path: Path) -> None:
    canary = "devflux-test-" + "value-must-not-leak"
    (tmp_path / ".env").write_text("IGNORED_KEY=hidden-file", encoding="utf-8")
    (tmp_path / "settings.env").write_text(f"API_KEY={canary}", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('safe')", encoding="utf-8")
    client = CapturingClient()

    PipelineRunner(client, DevFluxConfig()).run(
        ["backend"], "agrega una funcion", cwd=tmp_path
    )

    serialized_messages = "\n".join(
        message["content"] for call in client.messages for message in call
    )
    assert canary not in serialized_messages
    assert "API_KEY=" not in serialized_messages
