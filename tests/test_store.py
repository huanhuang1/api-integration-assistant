import json

import pytest

from api_assistant.knowledge import digest, source_fingerprint
from api_assistant.models import KnowledgeError
from api_assistant.store import KnowledgeStore


def write_records(settings, records):
    settings.store_dir.mkdir()
    for name, value in records.items():
        (settings.store_dir / f"{name}.json").write_text(json.dumps(value))
    manifest = {
        "source_hash": source_fingerprint(settings.source_dir),
        "records_hash": digest(records),
        "embedding_model": settings.embedding_model,
    }
    (settings.store_dir / "manifest.json").write_text(json.dumps(manifest))


def test_changed_source_requires_reingestion(settings, records):
    write_records(settings, records)
    source = settings.source_dir / "workflows/personal.yaml"
    source.write_text(source.read_text() + "\n# Updated by workflow owner\n")
    with pytest.raises(KnowledgeError, match="Source files changed"):
        KnowledgeStore(settings).load()


def test_partial_or_modified_records_are_not_served(settings, records):
    write_records(settings, records)
    (settings.store_dir / "operations.json").write_text("{}")
    with pytest.raises(KnowledgeError, match="incomplete"):
        KnowledgeStore(settings).load()


def test_missing_store_is_an_ingestion_error(settings):
    with pytest.raises(KnowledgeError, match="ingest"):
        KnowledgeStore(settings).load()
