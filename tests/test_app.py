from streamlit.testing.v1 import AppTest

from api_assistant.assistant import IntegrationAssistant
from api_assistant.config import PROJECT_ROOT, Settings
from api_assistant.models import Answer
from api_assistant.store import KnowledgeStore


def test_ui_requires_ingestion(settings, monkeypatch):
    monkeypatch.setattr(Settings, "from_env", lambda: settings)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    assert not app.exception
    assert app.chat_input[0].disabled
    assert "ingest" in app.warning[0].value


def test_ui_preserves_followup_context_and_resets_examples(settings, records, monkeypatch):
    monkeypatch.setattr(Settings, "from_env", lambda: settings)
    monkeypatch.setattr(
        KnowledgeStore, "load", lambda self: (records, {"workflow_count": 2, "operation_count": 3})
    )
    calls = []

    def invoke(self, question, history=None):
        calls.append((question, history))
        return Answer(
            status="needs_clarification",
            message="Please specify the customer type.",
            trace={"test": "UI test double; no model called"},
        )

    monkeypatch.setattr(IntegrationAssistant, "invoke", invoke)
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run()
    app.chat_input[0].set_value("Open an account").run()
    app.chat_input[0].set_value("A new individual, USD").run()
    assert not app.exception
    assert calls[-1][1][0] == {"role": "user", "content": "Open an account"}
    assert len(app.session_state.messages) == 4
    next(button for button in app.button if button.label == "Business account").click().run()
    assert not app.exception
    assert calls[-1][1] == []
    assert len(app.chat_message) == 2
    assert len(app.session_state.messages) == 2
    next(button for button in app.button if button.label == "New conversation").click().run()
    assert not app.exception
    assert not app.session_state.messages
