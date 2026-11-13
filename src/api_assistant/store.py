"""Complete JSON records plus a persistent Chroma workflow index."""

import json
import os
from pathlib import Path

from chromadb.config import Settings as ChromaSettings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from api_assistant.config import Settings
from api_assistant.knowledge import digest, load_sources, source_fingerprint, validate_records
from api_assistant.models import KnowledgeError
from api_assistant.providers import LocalEmbeddings

COLLECTION = "api_integration_workflows"


def _vector_store(settings: Settings, embeddings, create: bool = False):
    """Open the local Chroma collection. Ingestion can create it on the first run."""
    return Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=str(settings.store_dir / "chroma"),
        client_settings=ChromaSettings(anonymized_telemetry=False),
        collection_configuration={"hnsw": {"space": "cosine"}},
        create_collection_if_not_exists=create,
    )


def _write_json(path: Path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def ingest(settings: Settings, embeddings=None) -> dict:
    source_hash = source_fingerprint(settings.source_dir)
    records = load_sources(settings.source_dir)
    # Each group of records is keyed by ID, for example:
    # records["operations"]["createAccount"]
    # records["workflows"]["open_personal_account"]
    # records["rules"]["personal_account_rules"]
    embeddings = embeddings or LocalEmbeddings(settings)
    documents, ids = [], []
    for workflow_id, workflow in records["workflows"].items():
        text = "\n".join(
            [
                workflow["title"],
                workflow["description"],
                f"Customer type: {workflow['customer_type']}. Status: {workflow['customer_status']}.",
                *workflow["example_questions"],
            ]
        )
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "workflow_id": workflow_id,
                    "document_type": "workflow",
                    "source": workflow["source"],
                    "source_hash": source_hash,
                },
            )
        )
        ids.append(workflow_id)
    settings.store_dir.mkdir(parents=True, exist_ok=True)
    store = _vector_store(settings, embeddings, create=True)
    # Upsert deterministic IDs, then remove stale workflows. An interrupted update fails
    # the manifest/metadata checks on the next query, rather than mixing old and new data.
    # LangChain embeds each workflow document and saves it in Chroma.
    store.add_documents(documents, ids=ids)
    stale = set(store.get()["ids"]) - set(ids)
    if stale:
        store.delete(ids=list(stale))
    if source_fingerprint(settings.source_dir) != source_hash:
        raise KnowledgeError("Source files changed during ingestion. Rerun ingestion.")
    # Write the full operation, workflow, and rule records to separate JSON files.
    for name, value in records.items():
        _write_json(settings.store_dir / f"{name}.json", value)
    # Record the fingerprints and index configuration for the next lookup.
    manifest = {
        "source_hash": source_hash,
        "records_hash": digest(records),
        "embedding_model": settings.embedding_model,
        "embedding_dimension": getattr(embeddings, "dimension", None),
        "workflow_count": len(ids),
        "operation_count": len(records["operations"]),
        "rule_count": len(records["rules"]),
        "collection": COLLECTION,
    }
    _write_json(settings.store_dir / "manifest.json", manifest)
    return manifest


class KnowledgeStore:
    def __init__(self, settings: Settings, embeddings=None):
        self.settings = settings
        self.embeddings = embeddings or LocalEmbeddings(settings)

    def load(self) -> tuple[dict, dict]:
        try:
            manifest = json.loads((self.settings.store_dir / "manifest.json").read_text())
            records = {
                name: json.loads((self.settings.store_dir / f"{name}.json").read_text())
                for name in ("operations", "workflows", "rules")
            }
        except (OSError, ValueError) as exc:
            raise KnowledgeError(
                "The knowledge store is missing or unreadable. Run api-assistant ingest."
            ) from exc
        if manifest.get("records_hash") != digest(records):
            raise KnowledgeError("Stored records changed or are incomplete. Rerun ingestion.")
        if manifest.get("source_hash") != source_fingerprint(self.settings.source_dir):
            raise KnowledgeError("Source files changed. Rerun ingestion before asking questions.")
        if manifest.get("embedding_model") != self.settings.embedding_model:
            raise KnowledgeError("Embedding model differs from the index. Rerun ingestion.")
        validate_records(records)
        return records, manifest

    def search(self, query: str, records: dict, manifest: dict) -> list[dict]:
        try:
            store = _vector_store(self.settings, self.embeddings)
        except Exception as exc:
            raise KnowledgeError("Cannot open the vector index. Rerun ingestion.") from exc
        if set(store.get()["ids"]) != set(records["workflows"]):
            raise KnowledgeError("Vector index and registry disagree. Rerun ingestion.")
        hits = store.similarity_search_with_score(query, k=min(2, len(records["workflows"])))
        result = []
        for rank, (document, distance) in enumerate(hits, 1):
            key = document.metadata.get("workflow_id")
            if (
                key not in records["workflows"]
                or document.metadata.get("source_hash") != manifest["source_hash"]
            ):
                raise KnowledgeError("Retrieved index entry is stale or invalid. Rerun ingestion.")
            workflow = records["workflows"][key]
            result.append(
                {
                    "rank": rank,
                    "workflow_id": key,
                    "cosine_distance": float(distance),
                    "description": workflow["description"],
                    "customer_type": workflow["customer_type"],
                    "customer_status": workflow["customer_status"],
                    "source": workflow["source"],
                }
            )
        if not result:
            raise KnowledgeError("Vector search returned no indexed workflows. Rerun ingestion.")
        return result
