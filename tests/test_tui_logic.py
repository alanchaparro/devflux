from types import SimpleNamespace

import pytest

from devflux.core.config import DevFluxConfig
from devflux.core.orchestrator import IntentType, Orchestrator
from devflux.tui.app import DevFluxApp, confirmation_for_intent


def actions_for(intent: IntentType, **kwargs: object) -> tuple[list[str], int]:
    options, selected = confirmation_for_intent(intent, **kwargs)
    return [action for _number, _description, action in options], selected


def test_confirmation_menu_offers_all_explicit_actions() -> None:
    actions, _selected = actions_for(IntentType.CODE)

    assert actions == ["create", "modify", "bugs", "question", "rewrite"]


def test_empty_code_project_defaults_to_create() -> None:
    actions, selected = actions_for(IntentType.CODE, has_existing_project=False)

    assert actions[selected] == "create"


def test_existing_code_project_defaults_to_modify() -> None:
    actions, selected = actions_for(IntentType.CODE, has_existing_project=True)

    assert actions[selected] == "modify"


def test_question_confirmation_defaults_to_direct_answer() -> None:
    actions, selected = actions_for(IntentType.QUESTION, has_existing_project=True)

    assert actions[selected] == "question"


def test_bug_request_defaults_to_bug_pipeline() -> None:
    actions, selected = actions_for(
        IntentType.CODE, has_existing_project=True, is_bug_request=True
    )

    assert actions[selected] == "bugs"


def test_orchestrator_detects_bug_requests_for_confirmation() -> None:
    assert Orchestrator.is_bug_request("Corregi el error: index.html no carga")
    assert not Orchestrator.is_bug_request("Agrega un boton de contacto")


def test_chat_submission_defaults_to_create_in_empty_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._orchestrator = SimpleNamespace(classify_intent=lambda _text: IntentType.CODE)
    app.query_one = lambda *_args: SimpleNamespace(value="")  # type: ignore[method-assign]
    app._log_chat = lambda _message: None  # type: ignore[method-assign]
    app._show_confirmation = lambda: None  # type: ignore[method-assign]

    app._handle_chat_submit("Crea una pagina")

    assert app._confirm_options[app._confirm_selected][2] == "create"


def test_chat_submission_defaults_to_modify_with_existing_file(tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<main>actual</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._orchestrator = SimpleNamespace(classify_intent=lambda _text: IntentType.CODE)
    app.query_one = lambda *_args: SimpleNamespace(value="")  # type: ignore[method-assign]
    app._log_chat = lambda _message: None  # type: ignore[method-assign]
    app._show_confirmation = lambda: None  # type: ignore[method-assign]

    app._handle_chat_submit("Agrega un boton")

    assert app._confirm_options[app._confirm_selected][2] == "modify"


def test_enter_binding_selects_highlighted_confirmation_option() -> None:
    app = DevFluxApp()
    app._confirm_mode = True
    selected: list[bool] = []
    app._handle_confirm_select = lambda: selected.append(True)  # type: ignore[method-assign]

    app.action_submit_input()

    assert selected == [True]


def test_escape_binding_cancels_confirmation() -> None:
    app = DevFluxApp()
    app._confirm_mode = True
    app._log_chat = lambda _message: None  # type: ignore[method-assign]
    app.query_one = lambda *_args: SimpleNamespace(  # type: ignore[method-assign]
        visible=False, update=lambda _value: None, focus=lambda: None
    )

    app.action_close_menu()

    assert not app._confirm_mode


def test_modify_and_bug_actions_force_the_selected_pipeline() -> None:
    app = DevFluxApp()
    app._log_chat = lambda _message: None  # type: ignore[method-assign]
    app.query_one = lambda *_args: (_ for _ in ()).throw(RuntimeError())  # type: ignore[method-assign]
    calls: list[tuple[str, list[str], object, list[str]]] = []
    app._run_pipeline = lambda prompt, teams, complexity, roles: calls.append(  # type: ignore[method-assign]
        (prompt, teams, complexity, roles)
    )

    app._confirm_mode = True
    app._confirm_text = "Agrega un boton al formulario"
    app._confirm_options, app._confirm_selected = confirmation_for_intent(
        IntentType.CODE, has_existing_project=True
    )
    app._handle_confirm_select()

    modify_prompt, modify_teams, _complexity, _roles = calls.pop()
    assert modify_teams == ["dev"]
    assert "modifica los archivos existentes" in modify_prompt
    assert "no crees archivos duplicados innecesarios" in modify_prompt

    app._confirm_mode = True
    app._confirm_text = "El formulario no carga"
    app._confirm_options, app._confirm_selected = confirmation_for_intent(
        IntentType.CODE, is_bug_request=True
    )
    app._handle_confirm_select()

    _bug_prompt, bug_teams, _complexity, bug_roles = calls.pop()
    assert bug_teams == ["bugs"]
    assert "bug-intake" in bug_roles


@pytest.mark.asyncio
async def test_first_enter_only_opens_modify_confirmation_and_second_confirms(
    tmp_path, monkeypatch
) -> None:
    """A new submission must never consume its own confirmation Enter key."""
    (tmp_path / "index.html").write_text("<main>actual</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._config = DevFluxConfig()
    pipeline_calls: list[tuple[str, list[str], object, list[str]]] = []
    app._run_pipeline = lambda prompt, teams, complexity, roles: pipeline_calls.append(  # type: ignore[method-assign]
        (prompt, teams, complexity, roles)
    )

    async with app.run_test() as pilot:
        app._orchestrator = SimpleNamespace(
            classify_intent=lambda _text: IntentType.CHAT,
            select_team=lambda _text, team: ([team], "simple"),
            get_roles=lambda: ["analyst"],
            preview=lambda: "equipo-dev",
        )
        chat_input = app.query_one("#chat-input")
        chat_input.value = "quiero continuar mi proyecto"

        await pilot.press("enter")

        assert app._confirm_mode is True
        assert app._confirm_options[app._confirm_selected][2] == "modify"
        assert app.is_running is False
        assert pipeline_calls == []

        await pilot.press("enter")

        assert app._confirm_mode is False
        assert app.is_running is True
        assert len(pipeline_calls) == 1
