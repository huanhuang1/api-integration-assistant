"""Opt-in checks against real Ollama embeddings, Chroma, and the real chat model."""

from dataclasses import replace

import pytest

from api_assistant.assistant import IntegrationAssistant, render_markdown
from api_assistant.config import Settings
from api_assistant.store import KnowledgeStore, ingest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_settings(tmp_path_factory):
    settings = replace(Settings.from_env(), store_dir=tmp_path_factory.mktemp("live-index"))
    manifest = ingest(settings)
    assert manifest["embedding_dimension"] > 0
    return settings


def test_real_vectors_return_personal_and_business_candidates(live_settings):
    store = KnowledgeStore(live_settings)
    records, manifest = store.load()
    for kind, question in [
        ("personal", "Open a personal USD account for a first-time individual customer"),
        ("business", "Open a corporate EUR account for a new business company"),
    ]:
        hits = store.search(question, records, manifest)
        assert hits[0]["workflow_id"] == f"open_{kind}_account", hits
        assert 0 <= hits[0]["cosine_distance"] <= 2


@pytest.mark.parametrize(
    "question,status,workflow,blocked",
    [
        (
            "Open a USD account for a new individual customer.",
            "matched",
            "open_personal_account",
            False,
        ),
        ("Open a EUR account for a new company.", "matched", "open_business_account", False),
        ("I want to open an account.", "needs_clarification", None, False),
        ("Open an account for a new individual customer.", "needs_clarification", None, False),
        ("Transfer USD to another account.", "unsupported", None, False),
        (
            "I am an existing individual customer. Open another USD account.",
            "unsupported",
            None,
            False,
        ),
        ("Open a GBP account for a new individual customer.", "unsupported", None, False),
        (
            "Open a USD account for a new individual customer, but identity verification failed.",
            "matched",
            "open_personal_account",
            True,
        ),
        (
            "Open a EUR account for a new company. Verification is pending.",
            "matched",
            "open_business_account",
            True,
        ),
    ],
)
def test_live_scenarios(live_settings, question, status, workflow, blocked):
    answer = IntegrationAssistant(live_settings).invoke(question)
    assert answer.status == status, answer.model_dump()
    assert answer.workflow_id == workflow, answer.model_dump()
    assert len(answer.trace["candidates"]) == 2
    assert answer.trace["embedding_dimension"] > 0
    if workflow:
        assert answer.steps[-1]["blocked"] is blocked, answer.model_dump()
        if not blocked:
            expected_currency = "EUR" if "EUR" in question else "USD"
            assert answer.steps[-1]["request"]["currency"] == expected_currency
        else:
            assert answer.steps[-1]["request"] is None


def test_live_clarification_and_latest_correction(live_settings):
    assistant = IntegrationAssistant(live_settings)
    initial = "I want to open an account."
    answer = assistant.invoke(initial)
    assert answer.status == "needs_clarification", answer.model_dump()
    history = [
        {"role": "user", "content": initial},
        {"role": "assistant", "content": render_markdown(answer)},
    ]
    clarification = "A new individual customer, in USD."
    answer = assistant.invoke(clarification, history)
    assert answer.status == "matched", answer.model_dump()
    assert answer.workflow_id == "open_personal_account"
    history.extend(
        [
            {"role": "user", "content": clarification},
            {"role": "assistant", "content": render_markdown(answer)},
        ]
    )
    corrected = assistant.invoke("Actually use EUR instead.", history)
    assert corrected.status == "matched", corrected.model_dump()
    assert corrected.steps[-1]["request"]["currency"] == "EUR"
