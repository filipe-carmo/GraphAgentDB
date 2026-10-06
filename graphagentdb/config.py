"""Runtime configuration, loaded from environment variables and an optional `.env` file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings can be overridden with `GRAPHAGENTDB_<NAME>` environment variables.

    The Claude key is also read from the conventional `ANTHROPIC_API_KEY` variable.
    Without a key, every LLM call falls back to deterministic offline behaviour,
    so the whole pipeline (and the test suite) runs without calling Claude.
    """

    model_config = SettingsConfigDict(
        env_prefix="GRAPHAGENTDB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "GRAPHAGENTDB_ANTHROPIC_API_KEY"),
    )
    claude_model: str = "claude-opus-5-5"
    claude_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    claude_max_tokens: int = 16000

    # Anthropic has no embeddings endpoint, so embeddings are computed locally with fastembed.
    # "hash" skips the model download and uses deterministic pseudo-embeddings (tests, offline).
    embed_provider: Literal["fastembed", "hash"] = "fastembed"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384

    data_dir: Path = Path("data")
    conflict_similarity_threshold: float = 0.85
    context_filename: str = "CLAUDE.md"

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
