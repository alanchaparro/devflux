from types import SimpleNamespace

import pytest

from devflux.core.config import DevFluxConfig
from devflux.core.orchestrator import (
    ConversationRoute,
    IntentType,
    Orchestrator,
    RouterResult,
)
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
    app._orchestrator = SimpleNamespace(
        route_conversation=lambda *_args: RouterResult(route=ConversationRoute.MODIFY)
    )
    app.query_one = lambda *_args: SimpleNamespace(value="")  # type: ignore[method-assign]
    app._log_chat = lambda _message: None  # type: ignore[method-assign]
    app._show_confirmation = lambda: None  # type: ignore[method-assign]

    app._handle_chat_submit("Crea una pagina")

    assert app._confirm_options[app._confirm_selected][2] == "create"


def test_chat_submission_defaults_to_modify_with_existing_file(tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<main>actual</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._orchestrator = SimpleNamespace(
        route_conversation=lambda *_args: RouterResult(route=ConversationRoute.MODIFY)
    )
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
    app._orchestrator = SimpleNamespace(
        select_team=lambda _text, team: ([team], "simple"),
        get_roles=lambda: ["bug-intake"],
        preview=lambda: "equipo-dev",
    )
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

    # The stub does not call _pipeline_done; emulate completion before a
    # separate user request so the duplicate-run guard remains realistic.
    app.is_running = False
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
async def test_vague_modify_request_asks_for_clarification_without_running_pipeline(
    tmp_path, monkeypatch
) -> None:
    """A vague continuation must not spend tokens by launching equipo-dev."""
    (tmp_path / "index.html").write_text("<main>actual</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._config = DevFluxConfig()
    pipeline_calls: list[tuple[str, list[str], object, list[str]]] = []
    app._run_pipeline = lambda prompt, teams, complexity, roles: pipeline_calls.append(  # type: ignore[method-assign]
        (prompt, teams, complexity, roles)
    )
    pipeline_log: list[str] = []
    app._log_pipeline = pipeline_log.append  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        app._orchestrator = SimpleNamespace(
            route_conversation=lambda *_args: RouterResult(route=ConversationRoute.CLARIFY),
            select_team=lambda _text, team: ([team], "simple"),
            get_roles=lambda: ["analyst"],
            preview=lambda: "equipo-dev",
        )
        chat_input = app.query_one("#chat-input")
        chat_input.value = "quiero continuar mi proyecto"

        await pilot.press("enter")

        assert app._confirm_mode is False
        assert app.pending_modify_clarification is True
        assert app.is_running is False
        assert pipeline_calls == []
        assert any("¿Qué querés agregar, cambiar o corregir" in message for message in pipeline_log)


@pytest.mark.asyncio
async def test_clarification_follow_up_offers_modify_and_waits_for_confirmation(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "index.html").write_text("<main>actual</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._config = DevFluxConfig()
    pipeline_calls: list[tuple[str, list[str], object, list[str]]] = []
    app._run_pipeline = lambda prompt, teams, complexity, roles: pipeline_calls.append(  # type: ignore[method-assign]
        (prompt, teams, complexity, roles)
    )
    pipeline_log: list[str] = []
    app._log_pipeline = pipeline_log.append  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        app._orchestrator = SimpleNamespace(
            route_conversation=lambda *_args: RouterResult(route=ConversationRoute.MODIFY),
            select_team=lambda _text, team: ([team], "simple"),
            get_roles=lambda: ["analyst"],
            preview=lambda: "equipo-dev",
        )
        app.pending_modify_clarification = True
        chat_input = app.query_one("#chat-input")
        chat_input.value = "agrega burbujas animadas al fondo"

        await pilot.press("enter")

        assert app.pending_modify_clarification is False
        assert app._confirm_mode is True
        assert app._confirm_options[app._confirm_selected][2] == "modify"
        assert pipeline_calls == []

        await pilot.press("enter")

        assert app._confirm_mode is False
        assert app.is_running is True
        assert len(pipeline_calls) == 1


def test_modify_action_runs_when_llm_marks_request_actionable() -> None:
    app = DevFluxApp()
    app._orchestrator = SimpleNamespace(
        select_team=lambda _text, team: ([team], "simple"),
        get_roles=lambda: ["analyst"],
        preview=lambda: "equipo-dev",
    )
    app._log_chat = lambda _message: None  # type: ignore[method-assign]
    app.query_one = lambda *_args: (_ for _ in ()).throw(RuntimeError())  # type: ignore[method-assign]
    calls: list[object] = []
    app._run_pipeline = lambda *args: calls.append(args)  # type: ignore[method-assign]
    app._confirm_mode = True
    app._confirm_text = "Cambia el boton principal a verde"
    app._confirm_options, app._confirm_selected = confirmation_for_intent(
        IntentType.CODE, has_existing_project=True
    )

    app._handle_confirm_select()

    assert len(calls) == 1


def test_conversational_router_sends_full_thread_and_project_context_to_llm() -> None:
    calls: list[tuple[object, object]] = []

    class Client:
        def chat(self, messages, **kwargs):
            calls.append((messages, kwargs))
            return SimpleNamespace(content='{"route": "MODIFY"}', tokens=1)

    result = Orchestrator(Client()).route_conversation(
        conversation=[
            {"role": "user", "content": "quiero hacer modificaciones en mi proyecto"},
            {"role": "user", "content": "que el fondo tenga burbujas animadas"},
        ],
        active_thread="modify",
        project_context="Resumen: sitio HTML; archivos: index.html, styles.css",
        latest_user_message="que el fondo tenga burbujas animadas",
    )

    assert result == RouterResult(route=ConversationRoute.MODIFY)
    messages, kwargs = calls[0]
    assert "quiero hacer modificaciones" in messages[1]["content"]
    assert "burbujas animadas" in messages[1]["content"]
    assert "index.html" in messages[1]["content"]
    assert kwargs == {"temperature": 0, "max_tokens": 128, "timeout": 10}


def test_conversational_router_parses_clarify_and_reports_llm_error_without_fallback() -> None:
    class ClarifyClient:
        def chat(self, _messages, **_kwargs):
            return SimpleNamespace(content="CLARIFY", tokens=1)

    class FailingClient:
        def chat(self, _messages, **_kwargs):
            raise TimeoutError("router timed out")

    clarify = Orchestrator(ClarifyClient()).route_conversation([], "none", "", "quiero continuar")
    failed = Orchestrator(FailingClient()).route_conversation([], "modify", "context", "burbujas")

    assert clarify == RouterResult(route=ConversationRoute.CLARIFY)
    assert failed.route is None
    assert "router timed out" in (failed.error or "")


def test_conversational_router_parses_deepseek_reasoning_and_markdown_json(tmp_path, monkeypatch) -> None:
    """DeepSeek-compatible APIs can put the final JSON in reasoning_content."""
    monkeypatch.chdir(tmp_path)

    class DeepSeekClient:
        def chat(self, _messages, **_kwargs):
            return SimpleNamespace(
                content="",
                reasoning=(
                    "Analizo el hilo activo y la solicitud.\n"
                    "```json\n{\"route\": \"modify\"}\n```"
                ),
                raw={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": (
                                    "Analizo el hilo activo y la solicitud.\n"
                                    "```json\n{\"route\": \"modify\"}\n```"
                                ),
                            }
                        }
                    ]
                },
                tokens=9,
            )

    result = Orchestrator(DeepSeekClient()).route_conversation(
        [{"role": "user", "content": "Fondo de burbujas animadas"}],
        "modify",
        "index.html existe",
        "Fondo de burbujas animadas",
    )

    assert result == RouterResult(route=ConversationRoute.MODIFY)
    # Router diagnostics are runtime state, never a hidden artifact in the
    # user's project workspace.
    assert not (tmp_path / ".devflux").exists()


def test_conversational_router_parses_explicit_text_labels_without_keyword_fallback() -> None:
    assert Orchestrator._parse_conversation_route("La etiqueta es **bug**.") is ConversationRoute.BUG
    assert Orchestrator._parse_conversation_route("Ruta seleccionada: question") is ConversationRoute.QUESTION
    assert Orchestrator._parse_conversation_route("El usuario mencionó BUG pero no hay etiqueta.") is None


@pytest.mark.asyncio
async def test_pending_modify_uses_conversational_router_and_does_not_repeat_clarification(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "index.html").write_text("<main>actual</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._config = DevFluxConfig()
    app.pending_modify_clarification = True
    app.active_thread = "modify"
    app.conversation_turns = [
        {"role": "user", "content": "quiero hacer modificaciones en mi proyecto"}
    ]
    routed: list[tuple[object, str, str, str]] = []
    app._orchestrator = SimpleNamespace(
        route_conversation=lambda conversation, active_thread, project_context, latest: (
            routed.append((conversation, active_thread, project_context, latest))
            or RouterResult(route=ConversationRoute.MODIFY)
        )
    )
    clarification_messages: list[str] = []
    async with app.run_test() as pilot:
        app._orchestrator = SimpleNamespace(
            route_conversation=lambda conversation, active_thread, project_context, latest: (
                routed.append((conversation, active_thread, project_context, latest))
                or RouterResult(route=ConversationRoute.MODIFY)
            )
        )
        chat_input = app.query_one("#chat-input")
        chat_input.value = "que el fondo tenga burbujas animadas que al clicar cambien de color"
        await pilot.press("enter")

    assert app.pending_modify_clarification is False
    assert app._confirm_mode is True
    assert app._confirm_options[app._confirm_selected][2] == "modify"
    assert clarification_messages == []
    assert routed[0][1] == "modify"
    assert "quiero hacer modificaciones" in str(routed[0][0])


@pytest.mark.asyncio
async def test_router_failure_in_active_modify_thread_uses_modify_confirmation_without_user_error(tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<main>actual</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._config = DevFluxConfig()
    app.active_thread = "modify"
    app._orchestrator = SimpleNamespace(
        route_conversation=lambda *_args: RouterResult(error="invalid deepseek router format")
    )
    messages: list[str] = []
    pipeline_calls: list[tuple[object, ...]] = []

    async with app.run_test() as pilot:
        app._log_chat = messages.append  # type: ignore[method-assign]
        app._log_pipeline = messages.append  # type: ignore[method-assign]
        app._run_pipeline = lambda *args: pipeline_calls.append(args)  # type: ignore[method-assign]
        chat_input = app.query_one("#chat-input")
        chat_input.value = "Fondo de burbujas animadas que explotan si lo clickeo"
        await pilot.press("enter")

    assert app.pending_modify_clarification is False
    assert app._confirm_mode is True
    assert app._confirm_options[app._confirm_selected][2] == "modify"
    assert pipeline_calls == []
    assert not any("error del router" in message.lower() for message in messages)
    assert not any("invalid deepseek router format" in message for message in messages)


@pytest.mark.asyncio
async def test_router_failure_without_active_thread_shows_normal_selector_without_technical_error(tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<main>actual</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._config = DevFluxConfig()
    app._orchestrator = SimpleNamespace(route_conversation=lambda *_args: RouterResult(error="router unavailable"))
    messages: list[str] = []

    async with app.run_test() as pilot:
        app._log_chat = messages.append  # type: ignore[method-assign]
        app._log_pipeline = messages.append  # type: ignore[method-assign]
        chat_input = app.query_one("#chat-input")
        chat_input.value = "quiero hacer modificaciones en mi proyecto"
        await pilot.press("enter")

    assert app.active_thread == "none"
    assert app._confirm_mode is True
    assert app._confirm_options[app._confirm_selected][2] == "modify"
    assert not any("router" in message.lower() for message in messages)


def test_router_failure_uses_the_active_thread_semantic_fallback() -> None:
    bug_app = DevFluxApp()
    bug_app.active_thread = "bugs"
    bug_app._show_confirmation = lambda: None  # type: ignore[method-assign]
    bug_app._apply_conversation_route("la pantalla falla", RouterResult(error="bad router reply"))

    assert bug_app._confirm_mode is True
    assert bug_app._confirm_options[bug_app._confirm_selected][2] == "bugs"
    assert bug_app.active_thread == "bugs"

    question_app = DevFluxApp()
    question_app.active_thread = "question"
    answered: list[str] = []
    question_app._answer_question = answered.append  # type: ignore[method-assign]
    question_app._apply_conversation_route("¿cómo funciona esto?", RouterResult(error="bad router reply"))

    assert answered == ["¿cómo funciona esto?"]
    assert question_app.active_thread == "question"
    assert question_app._confirm_mode is False


@pytest.mark.asyncio
async def test_question_route_inside_modify_thread_answers_directly(tmp_path, monkeypatch) -> None:
    (tmp_path / "index.html").write_text("<main>actual</main>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = DevFluxApp()
    app._config = DevFluxConfig()
    app.active_thread = "modify"
    answered: list[str] = []

    async with app.run_test() as pilot:
        app._orchestrator = SimpleNamespace(
            route_conversation=lambda *_args: RouterResult(route=ConversationRoute.QUESTION)
        )
        app._answer_question = lambda text: answered.append(text)  # type: ignore[method-assign]
        chat_input = app.query_one("#chat-input")
        chat_input.value = "¿qué archivos tendríamos que tocar para eso?"
        await pilot.press("enter")

    assert answered == ["¿qué archivos tendríamos que tocar para eso?"]
    assert app.active_thread == "question"
    assert app._confirm_mode is False
