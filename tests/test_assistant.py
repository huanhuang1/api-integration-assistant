import pytest

from api_assistant.assistant import IntegrationAssistant, render_markdown
from api_assistant.models import Narration, Selection


class StubStore:
    """Orchestration test double, never used by the application or live tests."""

    def __init__(self, records):
        self.records = records
        self.query = None

    def load(self):
        return self.records, {}

    def search(self, query, records, manifest):
        self.query = query
        return [{"workflow_id": key} for key in records["workflows"]]


class StubModel:
    def __init__(self, **overrides):
        self.selection = Selection(
            **{
                "goal": "open_account",
                "customer_type": "PERSONAL",
                "customer_status": "NEW",
                "currency": "USD",
                "verification_status": "UNKNOWN",
                "workflow_id": "open_personal_account",
                **overrides,
            }
        )
        self.explained = False

    def select(self, question, history, candidates):
        return self.selection

    def explain(self, question, workflow, plan):
        self.explained = True
        return Narration(overview="Example integration guide.")


@pytest.mark.parametrize(
    "overrides,status",
    [
        (
            {"customer_type": "UNKNOWN", "customer_status": "UNKNOWN", "currency": "UNKNOWN"},
            "needs_clarification",
        ),
        ({"currency": "UNKNOWN"}, "needs_clarification"),
        ({"customer_status": "EXISTING"}, "unsupported"),
        ({"goal": "other"}, "unsupported"),
        ({"currency": "GBP"}, "unsupported"),
        ({"workflow_id": "made_up_workflow"}, "model_error"),
        ({"workflow_id": "open_business_account"}, "model_error"),
    ],
)
def test_unresolved_or_inconsistent_selection_never_publishes_plan(
    settings, records, overrides, status
):
    model = StubModel(**overrides)
    answer = IntegrationAssistant(settings, store=StubStore(records), language_model=model).invoke(
        "Request"
    )
    assert answer.status == status
    assert not answer.steps
    assert not model.explained


def test_blocked_gate_is_visible_in_rendered_answer(settings, records):
    model = StubModel(verification_status="FAILED")
    answer = IntegrationAssistant(settings, store=StubStore(records), language_model=model).invoke(
        "Request"
    )
    assert answer.status == "matched"
    assert answer.trace["validation"]["gate"] == "blocked"
    assert answer.steps[-1]["request"] is None
    markdown = render_markdown(answer)
    assert "No account-creation request is provided" in markdown
    assert markdown.count("**Example request**") == 2


def test_retrieval_uses_user_clarifications_not_assistant_descriptions(settings, records):
    store = StubStore(records)
    history = [
        {"role": "user", "content": "Open an account"},
        {"role": "assistant", "content": "Are you a personal or business customer?"},
    ]
    answer = IntegrationAssistant(settings, store=store, language_model=StubModel()).invoke(
        "New individual, USD", history
    )
    assert answer.status == "matched"
    assert store.query == "Open an account\nNew individual, USD"
    assert answer.trace["exact_lookups"]["operation_ids"] == [
        "createCustomer",
        "verifyIdentity",
        "createAccount",
    ]
