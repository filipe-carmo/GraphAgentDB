import pytest

from graphagentdb.config import Settings
from graphagentdb.store import KnowledgeStore


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Isolated, fully offline settings: no API key, no harness, data under tmp_path."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return Settings(
        _env_file=None,
        gemini_api_key=None,
        use_agent_harness=False,
        data_dir=tmp_path / "data",
    )


@pytest.fixture
def store(settings):
    s = KnowledgeStore(settings)
    yield s
    s.close()
