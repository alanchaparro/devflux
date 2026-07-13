from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from devflux.core.client import LLMClient
from devflux.core.config import DevFluxConfig
from devflux.core.orchestrator import ConversationRoute, Orchestrator
from devflux.core.runner import PipelineRunner


REAL_ROUTER_PAYLOAD = {
    "choices": [
        {
            "message": {
                "content": "",
                "reasoning": 'Análisis breve. {"route":"QUESTION"}',
            }
        }
    ],
    "usage": {"total_tokens": 424},
}


def test_client_recovers_real_provider_reasoning_field_when_content_is_empty() -> None:
    client = LLMClient(DevFluxConfig(), SimpleNamespace(get=lambda _provider: None))
    client._client = SimpleNamespace(  # type: ignore[assignment]
        post=lambda *_args, **_kwargs: SimpleNamespace(status_code=200, json=lambda: REAL_ROUTER_PAYLOAD)
    )

    response = client.chat([{"role": "user", "content": "test"}])

    assert response.content == 'Análisis breve. {"route":"QUESTION"}'
    assert response.reasoning == response.content
    assert response.tokens == 424


def test_real_e2e_reasoning_payload_routes_question_without_keyword_fallback(tmp_path, monkeypatch) -> None:
    import devflux.core.orchestrator as orchestrator_module

    monkeypatch.setattr(orchestrator_module, "RUNS_DIR", tmp_path / "runtime-runs")
    response = SimpleNamespace(
        content="",
        reasoning="",
        raw=REAL_ROUTER_PAYLOAD,
        tokens=424,
    )
    client = SimpleNamespace(chat=lambda *_args, **_kwargs: response)

    result = Orchestrator(client).route_conversation(
        [{"role": "user", "content": "¿Qué archivos tiene este proyecto y qué hace?"}],
        "none",
        "Archivos: index.html, style.css",
        "¿Qué archivos tiene este proyecto y qué hace?",
    )

    assert result.route is ConversationRoute.QUESTION
    assert not (tmp_path / ".devflux").exists()
    assert list((tmp_path / "runtime-runs").rglob("debug_classify.txt"))


def test_features_and_modifications_always_use_the_complete_eight_role_team() -> None:
    orchestrator = Orchestrator()
    prompts = [
        "Creá una lista de tareas en HTML/CSS/JS que permita agregar, completar y borrar tareas y guarde el estado en localStorage.",
        "Agregá burbujas animadas al fondo de la página actual.",
    ]
    expected = ["analista", "arquitecto", "planificador", "backend", "frontend", "qa", "reviewer", "integrador"]

    for prompt, action in zip(prompts, ("create", "modify"), strict=True):
        teams, _complexity, roles = orchestrator.select_user_action(prompt, action)
        assert teams == ["dev"]
        assert roles == expected


class InternalAndFunctionalOutputClient:
    def chat(self, _messages, **_kwargs):
        return SimpleNamespace(
            content=(
                "Archivo: plan.yaml\n```yaml\ninternal: true\n```\n"
                "Archivo: PRD.md\n```markdown\n# internal document that should never be written\n```\n"
                "Archivo: index.html\n```html\n<!doctype html><html><body><main>Functional output</main></body></html>\n```"
            ),
            tokens=1,
            elapsed=0.01,
        )


def test_runner_writes_only_functional_files_and_debug_only_to_runtime_runs(tmp_path, monkeypatch) -> None:
    import devflux.core.runner as runner_module

    runs_dir = tmp_path / "runtime-runs"
    monkeypatch.setattr(runner_module, "RUNS_DIR", runs_dir)
    project = tmp_path / "project"
    project.mkdir()

    files = PipelineRunner(InternalAndFunctionalOutputClient(), DevFluxConfig()).run(
        ["backend"], "Crea una página HTML", teams=["dev"], cwd=project
    )

    assert files == {"index.html": "<!doctype html><html><body><main>Functional output</main></body></html>"}
    assert (project / "index.html").exists()
    for forbidden in (".devflux", "plan.yaml", "PRD.md", "architecture.md", "main.md", "output.html"):
        assert not (project / forbidden).exists()
    assert list(runs_dir.rglob("debug_backend_response.txt"))
