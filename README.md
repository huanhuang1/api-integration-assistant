# API Integration Assistant

A local prototype that helps developers integrate with account-opening APIs. Describe a scenario to get the API sequence, relevant fields, value sources, and schema-checked JSON examples.

It uses **LangChain, real Ollama embeddings, Chroma, and a Streamlit chat interface**. All API contracts, customers, rules, and examples in the guide are fictional.

## Run it

Requirements: Python 3.11–3.13, [uv](https://docs.astral.sh/uv/getting-started/installation/), and a running [Ollama](https://docs.ollama.com/quickstart) installation. No cloud API key is needed. Run these commands from this repository:

```bash
uv sync --locked
source .venv/bin/activate
ollama pull nomic-embed-text:v1.5
ollama pull qwen2.5:3b
api-assistant validate
api-assistant ingest
streamlit run app.py --server.address 127.0.0.1
```

Open **http://localhost:8501**. If Ollama is not running, start its desktop app or run `ollama serve` in another terminal. Downloads need internet access; inference uses the local Ollama service.

Try:

- “Open a USD account for a new individual customer.”
- “Open a EUR account for a new company.”
- “I want to open an account.” Then answer the clarification.
- “Open a USD account for a new individual customer, but identity verification failed.”

Example buttons start a fresh conversation. **New conversation** clears the context. Expand **Inspect retrieval and backend lookups** below an answer to see actual vector distances, candidates, selected facts, exact record IDs, and validation results.

The CLI exposes the same pipeline:

```bash
api-assistant ask "Open a USD account for a new individual customer." --trace
api-assistant ask "Open a EUR account for a new company." --json
```

CLI `ask` is single-turn; the chat UI preserves context. Clarifications and unsupported scenarios are normal responses. Store/model errors return exit code 1.

## Ingestion: what goes into the backend?

**It ingests documents, not live API responses.** Seven source YAML files contain three OpenAPI specs, two workflows, and two scenario rule records.

```text
API specs + workflow definitions + scenario rules
    → Parse YAML and validate references, order, bindings, and examples
    ├─ Complete records → operations.json / workflows.json / rules.json
    └─ Workflow descriptions + example questions
       → Ollama embeddings → persistent Chroma index
```

`api-assistant ingest` reads API methods, paths, operation IDs, JSON schemas, server URLs, and authentication metadata. It checks that workflow APIs and rules exist, dependencies point to earlier steps, and scenario examples satisfy their API schemas, including personal/business `oneOf` branches. Invalid inputs stop ingestion.

Complete records are saved under `data/generated/`. One description per workflow is embedded with `nomic-embed-text:v1.5`; its document/query prefixes are applied by the embedding adapter. A manifest records source/record hashes, the model, vector dimension, and counts. Changed sources require re-ingestion before answering.

**Workflow files supply API order.** Ingestion validates that order; neither vector search nor the LLM invents it. In a real deployment, workflow owners would confirm these definitions.

## RAG: how does a user prompt become a guide?

```text
Question + recent user messages
    → Embed text → Chroma top-2 workflow search
    → LLM extracts user facts; code matches them against retrieved candidates
    → Missing facts? Clarify. Unsupported scenario? Say so.
    → Exact workflow ID lookup in workflows.json
    → Read api_sequence, bindings, gate, and rule_id
    → Exact API/rule lookups in operations.json and rules.json
    → Build examples from rules + user currency + earlier example response IDs
    → Validate JSON schemas and verification condition
    → LLM writes a brief introduction; code renders the complete guide
```

For “Open a EUR account for a new company,” the selected workflow is `open_business_account`. Its stored sequence is `createCustomer → verifyIdentity → createAccount`. Code loads these full contracts and `business_account_rules`. The customer request uses `legalName` and `companyRegistrationNumber`; the personal-only `fullName` is omitted. Verification uses `COMPANY_REGISTRATION`. The account request uses `EUR` from the user and IDs from earlier illustrative responses.

`createAccount` requires `verifyIdentity.response.status == PASSED`. If the user reports `FAILED` or `PENDING`, the guide marks account creation as blocked and omits its request. Without a reported result, the guide uses an explicitly synthetic success response to demonstrate the happy path; it does not establish that verification actually passed.

The LLM extracts goal, customer type, new/existing status, currency, and any reported verification outcome from user messages only. It must also quote the user words supporting each scenario field. Code checks these quotes against the user messages; missing or invented evidence resets that field to `UNKNOWN`. The extraction model does not see workflow descriptions. Code then matches the extracted facts to retrieved candidates by customer type/status. Missing type, status, or currency prompts clarification. Transfers, existing-customer onboarding, and unsupported currencies have no workflow in this demo. Quote checks establish that evidence exists; they cannot guarantee that the model interpreted it correctly.

| Backend store | Content | Lookup |
| --- | --- | --- |
| Chroma | Embedded workflow descriptions, example questions, IDs and source metadata | Vector similarity search |
| `workflows.json` | Complete API order, bindings, gate, rule reference | Exact workflow ID |
| `operations.json` | Parsed API schemas and operation metadata | Exact operation ID |
| `rules.json` | Relevant fields, fixed values, synthetic examples and step explanations | Exact rule ID |

**API specs do not need to be embedded in this prototype:** the workflow already references the exact operations. Search identifies candidates; the complete stored contracts supply facts.

For simplicity, each request loads the small JSON snapshot into memory first. The exact lookups above are dictionary lookups within that snapshot, rather than separate database calls.

With only two workflows, top-2 search returns both in actual vector-distance order. The application still needs the LLM-extracted user facts to match a scenario or ask for clarification. Distances are diagnostics, not calibrated confidence scores. The nearest result alone does not prove applicability.

## Code map

```text
app.py                          Streamlit chat and retrieval inspector
src/api_assistant/
├── config.py                   Paths and local model settings
├── knowledge.py                Parsing, validation, and example assembly
├── store.py                    Ingestion, JSON records, and Chroma search
├── providers.py                LangChain Ollama adapters and structured outputs
├── assistant.py                LangChain flow and answer rendering
├── models.py                   Structured selection and answer types
└── cli.py                      validate / ingest / ask commands
data/source/apis/               Three dummy OpenAPI specs
data/source/workflows/          Personal and business workflow registry entries
data/source/rules/              Scenario rules and synthetic examples
data/generated/                Generated records/index; ignored by Git
tests/                          Offline and opt-in real-model tests
deliverables/                   English proposal and diagram
```

Start by reading `data/source/workflows/personal.yaml`, then `data/source/rules/personal.yaml`, and finally `assistant.py`. LangChain `RunnableLambda` composition provides the fixed retrieval/answer flow; its Ollama and Chroma integrations handle models and search. This first demonstration does not need autonomous tool loops, MCP, or a separate workflow service.

## Configuration and prototype limits

Copy `.env.example` to `.env` to override model names, Ollama URL, and source/generated directories. Rerun ingestion after editing source data. To change the embedding model, use a fresh `ASSISTANT_STORE_DIR` for its index. Changing only the chat model does not require re-ingestion.

The parser supports **OpenAPI 3.1, inline schemas, JSON request bodies, and one JSON success response per operation**. `$ref` and non-body parameters are explicitly rejected. Nested destination bindings, multiple API versions, and arbitrary workflow branching are outside this demo. Operation IDs must be globally unique; duplicates fail ingestion. This is a simplification of the earlier versioned enterprise design.

Step instructions and JSON examples come from stored scenario rules and code. The LLM interprets the request and writes the introduction; code selects a retrieved workflow using the interpreted facts. This keeps detailed field choices, order, and bindings grounded when the small local model produces weak prose. Natural-language interpretation can still be wrong; inspect the selection trace. Passing the test scenarios is not a production accuracy guarantee.

This is a guide generator for two new-customer scenarios and USD/EUR accounts, not a general API-documentation chatbot. It has no production access control, API execution, enterprise document connector, concurrent ingestion, or workflow approval UI. All data is local and fictional.

## Tests

```bash
uv run pytest -q
uv run ruff check src tests app.py
# Requires both models and creates a separate temporary Chroma index:
uv run pytest -q -m integration tests/test_live.py
```

Offline tests cover invalid references, wrong scenario fields, binding/order errors, verification blocking, stale stores, and invalid model selections. Live tests use **real embeddings, persistent Chroma retrieval, and the configured LLM**, including multi-turn clarification and corrections. Test doubles are limited to offline orchestration/UI checks.

## Design documents

- [Prototype proposal (Markdown)](deliverables/Technical-Proposal.md)
- [Prototype proposal (Word)](deliverables/API-Integration-Assistant-Technical-Proposal.docx)
- [Architecture diagram](deliverables/assets/pipeline-simple-en.png)

The proposal describes the design; this README describes the implementation on `codex/agent-prototype`. `codex/english-docs` preserves the English documents; `main` preserves the original bilingual material.

References: [LangChain Ollama chat](https://docs.langchain.com/oss/python/integrations/chat/ollama), [Ollama embeddings](https://docs.langchain.com/oss/python/integrations/embeddings/ollama), [Chroma integration](https://docs.langchain.com/oss/python/integrations/vectorstores/chroma), and [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
