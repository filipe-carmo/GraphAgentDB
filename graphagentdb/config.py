"""Runtime configuration, loaded from environment variables and an optional `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings can be overridden with `GRAPHAGENTDB_<NAME>` environment variables.

    The Gemini key is also read from the conventional `GEMINI_API_KEY` variable.
    Without a key, every LLM call falls back to deterministic offline behaviour,
    so the whole pipeline (and the test suite) runs with no network access.
    """

    model_config = SettingsConfigDict(
        env_prefix="GRAPHAGENTDB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GRAPHAGENTDB_GEMINI_API_KEY"),
    )
    gemini_model: str = "gemini-2.5-flash"
    embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768

    data_dir: Path = Path("data")
    conflict_similarity_threshold: float = 0.85
    context_filename: str = "GEMINI.md"

    # Optional bridge to a local `agentapi` CLI (an IDE agent harness). Off by default.
    use_agent_harness: bool = False
    agent_harness_timeout: int = 40

    @property
    def kuzu_path(self) -> Path:
        return self.data_dir / "graph.kuzu"

    @property
    def lancedb_path(self) -> Path:
        return self.data_dir / "vectors.lance"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
