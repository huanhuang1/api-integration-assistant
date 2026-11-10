from api_assistant.models import GroundedIntent
from api_assistant.providers import LocalLanguageModel


class StubStructuredChat:
    def with_structured_output(self, schema, **kwargs):
        return self

    def invoke(self, messages):
        return GroundedIntent.model_validate(
            {
                "evidence": {
                    "customer_type": "individual",
                    "customer_status": "new",
                    "currency": "USD",
                    "verification_status": "passed",
                },
                "facts": {
                    "goal": "open_account",
                    "customer_type": "PERSONAL",
                    "customer_status": "NEW",
                    "currency": "USD",
                    "verification_status": "PASSED",
                },
            }
        )


def test_model_cannot_fill_missing_user_facts_from_invented_quotes(settings):
    model = LocalLanguageModel(settings)
    model.chat = StubStructuredChat()
    candidates = [
        {
            "workflow_id": "open_personal_account",
            "customer_type": "PERSONAL",
            "customer_status": "NEW",
        }
    ]
    # Neither the candidate metadata nor assistant text is evidence of what the user said.
    history = [{"role": "assistant", "content": "new individual USD passed"}]
    result = model.select("Open an account", history, candidates)
    assert result.customer_type == "UNKNOWN"
    assert result.customer_status == "UNKNOWN"
    assert result.currency == "UNKNOWN"
    assert result.verification_status == "UNKNOWN"
    assert result.workflow_id == "NONE"


def test_user_evidence_can_be_carried_from_a_previous_turn(settings):
    model = LocalLanguageModel(settings)
    model.chat = StubStructuredChat()
    candidates = [
        {
            "workflow_id": "open_personal_account",
            "customer_type": "PERSONAL",
            "customer_status": "NEW",
        }
    ]
    result = model.select(
        "Use USD", [{"role": "user", "content": "Open an account for a new individual"}], candidates
    )
    assert result.workflow_id == "open_personal_account"
    assert result.currency == "USD"
    assert result.verification_status == "UNKNOWN"
