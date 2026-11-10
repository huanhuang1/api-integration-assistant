"""Small, explicit configuration for the local prototype."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    source_dir: Path
    store_dir: Path
    base_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen2.5:3b"
    embedding_model: str = "nomic-embed-text:v1.5"
    timeout: float = 120

    @classmethod
    def from_env(cls):
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        return cls(
            source_dir=(PROJECT_ROOT / os.getenv("ASSISTANT_SOURCE_DIR", "data/source")).resolve(),
            store_dir=(PROJECT_ROOT / os.getenv("ASSISTANT_STORE_DIR", "data/generated")).resolve(),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            chat_model=os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:3b"),
            embedding_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:v1.5"),
            timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")),
        )
