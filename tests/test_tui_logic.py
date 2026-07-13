from devflux.core.orchestrator import IntentType
from devflux.tui.app import confirmation_for_intent


def test_question_confirmation_defaults_to_direct_answer() -> None:
    options, selected = confirmation_for_intent(IntentType.QUESTION)

    assert selected == 0
    assert options[0][2] == "question"


def test_code_confirmation_defaults_to_pipeline() -> None:
    options, selected = confirmation_for_intent(IntentType.CODE)

    assert selected == 0
    assert options[0][2] == "pipeline"
