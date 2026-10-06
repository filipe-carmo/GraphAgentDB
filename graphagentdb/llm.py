"""LLM access: Claude for extraction, arbitration and answers; local embeddings via fastembed.

Every method degrades gracefully. Without an Anthropic API key `generate*` returns None,
and if the embedding model can't be loaded `embed` returns a deterministic pseudo-embedding,
so callers can fall back to offline behaviour.
"""

import logging
from typing import Any, TypeVar

import anthropic
import numpy as np
from pydantic import BaseModel

from .config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# If Claude's safety classifiers decline a request, the API retries it on a suitable
# fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def fallback_embedding(text: str, dimensions: int) -> list[float]:
    """Deterministic unit vector seeded from the text. Identical text gives identical vectors."""
    seed = sum(ord(c) * (i + 1) for i, c in enumerate(text))
    vector = np.random.default_rng(seed).standard_normal(dimensions)
    return (vector / np.linalg.norm(vector)).tolist()


class LLMClient:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None):
        self.settings = settings
        self._client = client
        if self._client is None and settings.anthropic_api_key:
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._embedder: Any = None
        self._embed_provider = settings.embed_provider

    @property
    def claude_available(self) -> bool:
        return self._client is not None

    # -- embeddings -------------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        if self._embed_provider == "fastembed":
            try:
                if self._embedder is None:
                    from fastembed import TextEmbedding

                    self._embedder = TextEmbedding(self.settings.embed_model)
                vector = next(iter(self._embedder.embed([text])))
                return [float(x) for x in vector]
            except Exception:
                logger.warning(
                    "Could not load embedding model %s, using offline pseudo-embeddings",
                    self.settings.embed_model,
                    exc_info=True,
                )
                self._embed_provider = "hash"
        return fallback_embedding(text, self.settings.embed_dim)

    # -- generation -------------------------------------------------------------------------

    def _request(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self.settings.claude_model,
            "max_tokens": self.settings.claude_max_tokens,
            "output_config": {"effort": self.settings.claude_effort},
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
            "messages": [{"role": "user", "content": prompt}],
        }

    def generate(self, prompt: str) -> str | None:
        """Free-text generation. Returns None when Claude is unavailable or declines."""
        if self._client is None:
            return None
        try:
            response = self._client.beta.messages.create(**self._request(prompt))
        except anthropic.APIError:
            logger.warning("Claude request failed", exc_info=True)
            return None
        if response.stop_reason == "refusal":
            logger.warning("Claude declined the request: %s", response.stop_details)
            return None
        text = "".join(block.text for block in response.content if block.type == "text")
        return text or None

    def generate_json(self, prompt: str, schema: type[T]) -> T | None:
        """Structured generation, constrained to and validated against a pydantic schema."""
        if self._client is None:
            return None
        try:
            response = self._client.beta.messages.parse(
                **self._request(prompt), output_format=schema
            )
        except anthropic.APIError:
            logger.warning("Claude structured request failed", exc_info=True)
            return None
        if response.stop_reason == "refusal":
            logger.warning("Claude declined the request: %s", response.stop_details)
            return None
        return response.parsed_output
