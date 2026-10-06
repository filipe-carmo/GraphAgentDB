import pytest

from graphagentdb.config import Settings
from graphagentdb.store import KnowledgeStore


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Isolated, fully offline settings: no API key, hash embeddings, data under tmp_path."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return Settings(
        _env_file=None,
        anthropic_api_key=None,
        embed_provider="hash",
        data_dir=tmp_path / "data",
    )


@pytest.fixture
def store(settings):
    s = KnowledgeStore(settings)
    yield s
    s.close()
