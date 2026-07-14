from __future__ import annotations

import pytest

from devflux.core.client import LLMResponse
from devflux.core.config import DevFluxConfig
from devflux.core.runner import PipelineRunner, extract_files, render_prompt, template_for_role


def test_routes_bug_and_repo_roles_to_specialized_templates() -> None:
    assert template_for_role("diagnostico") == "bugs/diagnostico.j2"
    assert template_for_role("repo-inventory") == "repo/inventory.j2"


def test_missing_template_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="Plantilla no encontrada"):
        render_prompt("bugs/no-existe.j2", user_input="test")


def test_extract_files_preserves_safe_nested_paths() -> None:
    files = extract_files(
        "Archivo: src/services/auth.py\n```python\nprint('auth service works')\n```",
        role="backend",
    )

    assert files == {"src/services/auth.py": "print('auth service works')"}


@pytest.mark.parametrize("filename", ["../secret.py", "/tmp/secret.py", "C:\\secret.py"])
def test_extract_files_rejects_unsafe_paths(filename: str) -> None:
    content = f"Archivo: {filename}\n```python\nprint('unsafe path content')\n```"

    assert extract_files(content, role="backend") == {}


def test_pipeline_truncates_large_existing_files_before_prompting(tmp_path) -> None:
    marker = "END-OF-OVERSIZED-FILE"
    (tmp_path / "large.py").write_text("x" * 30_000 + marker, encoding="utf-8")

    class Client:
        def __init__(self) -> None:
            self.messages = []

        def chat(self, messages):
            self.messages.append(messages)
            return LLMResponse(content="NO_BACKEND", tokens=0, elapsed=0.0)

    client = Client()
    PipelineRunner(client, DevFluxConfig()).run(["backend"], "test", cwd=tmp_path)
    prompt = client.messages[0][1]["content"]
    system = client.messages[0][0]["content"]

    assert marker not in prompt
    assert "dato no confiable" in system


def test_pipeline_stops_before_next_role_when_cancelled(tmp_path) -> None:
    calls: list[object] = []
    events: list[tuple[str, str]] = []

    class Client:
        def chat(self, _messages):
            calls.append(_messages)
            return LLMResponse(content="NO_BACKEND", tokens=0, elapsed=0.0)

    runner = PipelineRunner(
        Client(),
        DevFluxConfig(),
        callback=lambda role, status, _data: events.append((role, status)),
        cancelled=lambda: True,
    )

    assert runner.run(["backend"], "test", cwd=tmp_path) == {}
    assert calls == []
    assert events == [("__pipeline__", "cancelled")]
