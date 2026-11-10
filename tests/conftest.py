import shutil

import pytest

from api_assistant.config import PROJECT_ROOT, Settings
from api_assistant.knowledge import load_sources


@pytest.fixture
def settings(tmp_path):
    source = tmp_path / "source"
    shutil.copytree(PROJECT_ROOT / "data/source", source)
    return Settings(source_dir=source, store_dir=tmp_path / "generated")


@pytest.fixture
def records(settings):
    return load_sources(settings.source_dir)
