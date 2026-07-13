from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from devflux.core.config import DevFluxConfig
from devflux.core.orchestrator import DEV_EIGHT_ROLE_SEQUENCE, Orchestrator
from devflux.core.runner import PipelineRunner, extract_files


class EightRoleClient:
    def __init__(self) -> None:
        self.messages: list[list[dict[str, str]]] = []
        self.outputs = iter([
            "# PRD: Demo\n## Objetivo\nUna landing\n## Casos Borde\nSin JavaScript.",
            "# Arquitectura: Demo\n## Stack\nHTML y CSS.",
            "# Plan de Implementación\n## Tarea 1: Landing\n- Archivos a crear/modificar: index.html",
            "NO_BACKEND",
            "**index.html**\n```html\n<!doctype html><html><head><title>Demo</title></head><body><main>Hola DevFlux</main></body></html>\n```",
            "# QA Report\n## Bugs Críticos (BLOQUEANTES)\n- Ninguno\n## Warnings (Mejoras)\n- Ninguno\n## Verificación PRD\n- OK",
            "# Code Review\n## Crítico\n- Ninguno\n## Medio\n- Ninguno\n## Menor\n- Ninguno",
            "# Integración\n## Cambios aplicados\n- Ninguno\n## Estado final\n- Válido",
        ])

    def chat(self, messages, **_kwargs):
        self.messages.append(messages)
        return SimpleNamespace(content=next(self.outputs), tokens=7, elapsed=0.01)


def test_eight_role_pipeline_keeps_internal_outputs_outside_project_and_passes_context(tmp_path, monkeypatch) -> None:
    import devflux.core.runner as runner_module

    runs_dir = tmp_path / "runs"
    monkeypatch.setattr(runner_module, "RUNS_DIR", runs_dir)
    project = tmp_path / "project"
    project.mkdir()
    events: list[tuple[str, str]] = []
    client = EightRoleClient()
    runner = PipelineRunner(client, DevFluxConfig(), callback=lambda role, status, _data: events.append((role, status)))

    files = runner.run(DEV_EIGHT_ROLE_SEQUENCE, "Crear una landing estática", teams=["dev"], cwd=project, run_id="eight-role-test")

    assert [role for role, status in events if status == "start"] == DEV_EIGHT_ROLE_SEQUENCE
    assert (project / "index.html").exists()
    assert "Hola DevFlux" in (project / "index.html").read_text(encoding="utf-8")
    assert files["index.html"].startswith("<!doctype html>")
    assert not (project / "PRD.md").exists()
    assert not (project / "plan.md").exists()
    assert not (project / "qa_report.md").exists()
    assert not (project / "review.md").exists()
    assert not (project / ".devflux").exists()

    run_dir = runs_dir / "eight-role-test"
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "completed"
    assert state["completed_roles"] == DEV_EIGHT_ROLE_SEQUENCE
    captures = sorted(path.name for path in run_dir.glob("[0-9][0-9]-*.txt"))
    assert captures == [f"{index:02d}-{role}.txt" for index, role in enumerate(DEV_EIGHT_ROLE_SEQUENCE, 1)]

    backend_prompt = client.messages[3][1]["content"]
    frontend_prompt = client.messages[4][1]["content"]
    qa_prompt = client.messages[5][1]["content"]
    reviewer_prompt = client.messages[6][1]["content"]
    integrator_prompt = client.messages[7][1]["content"]
    assert "NO_BACKEND" not in frontend_prompt
    assert "index.html" in qa_prompt and "# PRD: Demo" in qa_prompt
    assert "index.html" in reviewer_prompt
    assert "# QA Report" in integrator_prompt and "# Code Review" in integrator_prompt
    assert "# Plan de Implementación" in backend_prompt


def test_question_classification_does_not_select_development_roles() -> None:
    class QuestionClient:
        def chat(self, *_args, **_kwargs):
            return SimpleNamespace(content="QUESTION", tokens=1, elapsed=0.01)

    orchestrator = Orchestrator(QuestionClient())
    assert orchestrator.classify_intent("¿Qué hace este proyecto?").value == "question"
    assert orchestrator.get_roles() == []


def test_integrator_rejects_destructive_fragment_for_existing_file(tmp_path, monkeypatch) -> None:
    import devflux.core.runner as runner_module

    monkeypatch.setattr(runner_module, "RUNS_DIR", tmp_path / "runs")
    project = tmp_path / "project"
    project.mkdir()
    original = "<!doctype html><html><body>" + ("contenido completo " * 20) + "</body></html>"
    (project / "index.html").write_text(original, encoding="utf-8")

    class FragmentClient:
        def chat(self, *_args, **_kwargs):
            return SimpleNamespace(content="**index.html**\n```html\n<p>fragmento</p>\n```", tokens=1, elapsed=0.01)

    PipelineRunner(FragmentClient(), DevFluxConfig()).run(["integrador"], "Ajustar", teams=["dev"], cwd=project)
    assert (project / "index.html").read_text(encoding="utf-8") == original


def test_integrator_never_turns_unfenced_report_text_into_a_project_file() -> None:
    report = "# Integración\n## Cambios aplicados\nEl archivo queda válido.\n```python\ndef ejemplo(): pass\n"
    assert extract_files(report, role="integrador", allow_fallback=False) == {}
