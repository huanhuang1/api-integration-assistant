"""The deliberately fixed LangChain flow from the prototype plan."""

import json
import time

from langchain_core.runnables import RunnableLambda

from api_assistant.config import Settings
from api_assistant.knowledge import build_plan
from api_assistant.models import Answer, KnowledgeError, ProviderError
from api_assistant.providers import LocalLanguageModel
from api_assistant.store import KnowledgeStore


class IntegrationAssistant:
    def __init__(self, settings: Settings, *, store=None, language_model=None):
        self.settings = settings
        self.store = store or KnowledgeStore(settings)
        self.language_model = language_model or LocalLanguageModel(settings)
        # Retrieve candidates, match a workflow, and return the answer.
        self.chain = RunnableLambda(self._retrieve) | RunnableLambda(self._answer)

    def invoke(self, message: str, history: list[dict] | None = None) -> Answer:
        trace = {
            "embedding_model": self.settings.embedding_model,
            "chat_model": self.settings.chat_model,
        }
        if not message.strip():
            return Answer(
                status="needs_clarification", message="What API workflow do you need help with?"
            )
        if len(message) > 4000:
            return Answer(
                status="needs_clarification",
                message="Please keep the request under 4,000 characters.",
            )
        started = time.monotonic()
        try:
            result = self.chain.invoke(
                {"question": message.strip(), "history": history or [], "trace": trace}
            )
        except KnowledgeError as exc:
            result = Answer(status="data_error", message=str(exc), trace=trace)
        except ProviderError as exc:
            result = Answer(status="model_error", message=str(exc), trace=trace)
        except (KeyError, ValueError, TypeError) as exc:
            result = Answer(
                status="data_error",
                message=f"Could not read consistent workflow records: {exc}",
                trace=trace,
            )
        except Exception as exc:
            result = Answer(
                status="model_error",
                message=(
                    f"The local model or vector service could not complete this request ({type(exc).__name__}). "
                    "Check Ollama is running and both configured models are installed."
                ),
                trace=trace,
            )
        result.trace["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return result

    def _retrieve(self, state: dict) -> dict:
        records, manifest = self.store.load()
        # Assistant messages are not embedded: they may mention both workflow candidates.
        previous = [item["content"] for item in state["history"][-8:] if item.get("role") == "user"]
        query = "\n".join(previous + [state["question"]])[-6000:]
        candidates = self.store.search(query, records, manifest)
        state.update(records=records, candidates=candidates)
        state["trace"].update(
            {
                "query": query,
                "candidates": candidates,
                "retrieval": "real Ollama embeddings + Chroma cosine search; lower distance is closer",
                "embedding_dimension": manifest.get("embedding_dimension"),
            }
        )
        return state

    def _answer(self, state: dict) -> Answer:
        question, trace, records = state["question"], state["trace"], state["records"]
        selection = self.language_model.select(question, state["history"], state["candidates"])
        trace["selection"] = selection.model_dump()
        if selection.goal == "other":
            return Answer(
                status="unsupported",
                message="This demo supports account opening for new personal and business customers. It has no workflow for this request.",
                trace=trace,
            )
        if selection.customer_status == "EXISTING":
            return Answer(
                status="unsupported",
                message="The current workflows cover new customers only. An existing-customer workflow has not been provided.",
                trace=trace,
            )
        missing = []
        if selection.goal == "unknown":
            missing.append("whether you want to open an account")
        if selection.customer_type == "UNKNOWN":
            missing.append("whether the customer is an individual or a business")
        if selection.customer_status == "UNKNOWN":
            missing.append("whether this is a new or existing customer")
        if selection.currency == "UNKNOWN":
            missing.append("the account currency (USD or EUR)")
        if missing:
            return Answer(
                status="needs_clarification",
                message="Please specify " + "; ".join(missing) + ".",
                trace=trace,
            )
        currency = selection.currency.upper()
        if currency not in {"USD", "EUR"}:
            return Answer(
                status="unsupported",
                message=f"The dummy account API supports USD and EUR, not {currency}.",
                trace=trace,
            )
        candidate_ids = {candidate["workflow_id"] for candidate in state["candidates"]}
        if selection.workflow_id not in candidate_ids:
            raise ProviderError(
                "The model did not select a valid retrieved workflow. Please restate your request."
            )
        workflow = records["workflows"][selection.workflow_id]
        if any(
            workflow[key] != getattr(selection, key) for key in ("customer_type", "customer_status")
        ):
            raise ProviderError(
                "The model selected a workflow that contradicts the customer conditions."
            )
        plan = build_plan(records, selection.workflow_id, currency, selection.verification_status)
        sources = [workflow["source"], records["rules"][workflow["rule_id"]]["source"]]
        sources += [records["operations"][key]["source"] for key in workflow["api_sequence"]]
        trace.update(
            {
                "selected_workflow": selection.workflow_id,
                "exact_lookups": {
                    "workflow_id": selection.workflow_id,
                    "operation_ids": workflow["api_sequence"],
                    "rule_id": workflow["rule_id"],
                },
                "loaded_sources": sources,
                "validation": {
                    "request_schemas": "passed",
                    "response_schemas": "passed",
                    "bindings": "passed",
                    "gate": "blocked"
                    if any(s["blocked"] for s in plan)
                    else "passed in synthetic example",
                },
            }
        )
        narration = self.language_model.explain(question, workflow, plan)
        overview = narration.overview
        if any(step["blocked"] for step in plan):
            overview = "The account-opening workflow was found, but account creation is blocked by the reported verification result."
        return Answer(
            status="matched",
            message=overview,
            workflow_id=selection.workflow_id,
            steps=plan,
            sources=sources,
            trace=trace,
        )


def render_markdown(answer: Answer) -> str:
    lines = [answer.message]
    if answer.status != "matched":
        return "\n\n".join(lines)
    lines.append(f"**Workflow:** `{answer.workflow_id}`")
    lines.append(
        "These are fictional, schema-checked examples. No APIs have been executed. Replace synthetic customer data and use actual response IDs in an integration. Configure the server and authentication from the API spec."
    )
    for number, step in enumerate(answer.steps, 1):
        lines.append(f"### {number}. {step['operation_id']} — {step['method']} {step['path']}")
        lines.append(step["explanation"])
        if step["precondition"]:
            lines.append(f"**Required before this call:** `{step['precondition']}`.")
        if step["blocked"]:
            lines.append("**Blocked. No account-creation request is provided.**")
            continue
        lines.append(
            "**Example request**\n```json\n" + json.dumps(step["request"], indent=2) + "\n```"
        )
        lines.append(
            "**Illustrative response** (assumed for this example)\n```json\n"
            + json.dumps(step["example_response"], indent=2)
            + "\n```"
        )
        lines.append(
            "| Field | Value source |\n| --- | --- |\n"
            + "\n".join(
                f"| `{field}` | {source} |" for field, source in step["field_sources"].items()
            )
        )
        if step["optional_fields"]:
            lines.append(
                "Optional, omitted from this example: " + ", ".join(step["optional_fields"]) + "."
            )
        if step["not_applicable_fields"]:
            lines.append(
                "Not applicable to this scenario: " + ", ".join(step["not_applicable_fields"]) + "."
            )
        lines.append(f"Source: `{step['source']}` / `{step['operation_id']}`.")
    lines.append("**Sources loaded:** " + ", ".join(f"`{source}`" for source in answer.sources))
    return "\n\n".join(lines)
