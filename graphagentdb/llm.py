"""LLM access: Gemini for generation and embeddings, plus an optional local agent harness.

Every method degrades gracefully. With no API key and the harness disabled, `generate*`
returns None and `embed` returns a deterministic pseudo-embedding, so callers can fall
back to offline behaviour.
"""

import json
import logging
import os
import re
import subprocess
from typing import TypeVar

import numpy as np
from pydantic import BaseModel, ValidationError

from .config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def strip_code_fences(text: str) -> str:
    """Extracts the JSON payload from a reply that may be wrapped in ```json fences."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned)
    return cleaned.strip()


def fallback_embedding(text: str, dimensions: int) -> list[float]:
    """Deterministic unit vector seeded from the text. Identical text gives identical vectors."""
    seed = sum(ord(c) * (i + 1) for i, c in enumerate(text))
    vector = np.random.default_rng(seed).standard_normal(dimensions)
    return (vector / np.linalg.norm(vector)).tolist()


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = None
        if settings.gemini_api_key:
            from google import genai

            self._client = genai.Client(api_key=settings.gemini_api_key)

    @property
    def gemini_available(self) -> bool:
        return self._client is not None

    # -- embeddings -------------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        if self._client is not None:
            from google.genai import types

            try:
                response = self._client.models.embed_content(
                    model=self.settings.embed_model,
                    contents=text,
                    config=types.EmbedContentConfig(output_dimensionality=self.settings.embed_dim),
                )
                if response.embeddings:
                    return list(response.embeddings[0].values)
            except Exception:
                logger.warning("Gemini embedding failed, using offline fallback", exc_info=True)
        return fallback_embedding(text, self.settings.embed_dim)

    # -- generation -------------------------------------------------------------------------

    def generate(self, prompt: str) -> str | None:
        """Free-text generation. Tries the harness (if enabled), then Gemini."""
        if self.settings.use_agent_harness:
            reply = self._call_harness(prompt)
            if reply:
                return reply
        if self._client is not None:
            try:
                response = self._client.models.generate_content(
                    model=self.settings.gemini_model, contents=prompt
                )
                return response.text
            except Exception:
                logger.warning("Gemini generation failed", exc_info=True)
        return None

    def generate_json(self, prompt: str, schema: type[T]) -> T | None:
        """Structured generation validated against a pydantic schema."""
        if self.settings.use_agent_harness:
            reply = self._call_harness(prompt)
            if reply:
                try:
                    return schema.model_validate_json(strip_code_fences(reply))
                except ValidationError:
                    logger.warning("Harness returned JSON that does not match %s", schema.__name__)
        if self._client is not None:
            from google.genai import types

            try:
                response = self._client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=0.1,
                    ),
                )
                return schema.model_validate_json(response.text)
            except Exception:
                logger.warning("Gemini structured generation failed", exc_info=True)
        return None

    def _call_harness(self, prompt: str) -> str | None:
        """Sends the prompt to a local `agentapi` CLI and returns its reply text."""
        env = os.environ.copy()
        env.setdefault("ANTIGRAVITY_PROJECT_ID", "GraphAgentDB")
        try:
            result = subprocess.run(
                ["agentapi", "new-conversation", "--model=flash", prompt],
                capture_output=True,
                text=True,
                env=env,
                timeout=self.settings.agent_harness_timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("Agent harness unavailable: %s", exc)
            return None

        if result.returncode != 0:
            logger.warning(
                "Agent harness exited with %s: %s", result.returncode, result.stderr.strip()
            )
            return None
        stdout = result.stdout.strip()
        if not stdout:
            return None
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return stdout
        resp = data.get("response") if isinstance(data, dict) else None
        if isinstance(resp, dict) and "text" in resp:
            return resp["text"]
        return str(resp) if resp is not None else stdout
