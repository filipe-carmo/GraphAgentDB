from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx2

from graphagentdb.llm import FALLBACK_BETA, LLMClient, fallback_embedding
from graphagentdb.models import ConflictResolution


def _client(settings, response=None, error=None):
    fake = MagicMock()
    for method in (fake.beta.messages.create, fake.beta.messages.parse):
        method.return_value = response
        method.side_effect = error
    return LLMClient(settings, client=fake), fake


def test_without_a_key_generation_is_offline(settings):
    llm = LLMClient(settings)
    assert not llm.claude_available
    assert llm.generate("hi") is None
    assert llm.generate_json("hi", ConflictResolution) is None


def test_generate_joins_text_blocks_and_sends_model_settings(settings):
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text="Hello "),
            SimpleNamespace(type="text", text="world"),
        ],
    )
    llm, fake = _client(settings, response)

    assert llm.generate("question") == "Hello world"
    kwargs = fake.beta.messages.create.call_args.kwargs
    assert kwargs["model"] == settings.claude_model
    assert kwargs["output_config"] == {"effort": settings.claude_effort}
    assert kwargs["betas"] == [FALLBACK_BETA]
    assert kwargs["fallbacks"] == "default"
    assert kwargs["messages"] == [{"role": "user", "content": "question"}]


def test_generate_json_returns_parsed_output(settings):
    parsed = ConflictResolution(decision="duplicate", target_id="a", reason="same")
    llm, fake = _client(settings, SimpleNamespace(stop_reason="end_turn", parsed_output=parsed))

    assert llm.generate_json("compare", ConflictResolution) == parsed
    assert fake.beta.messages.parse.call_args.kwargs["output_format"] is ConflictResolution


def test_refusal_returns_none(settings):
    refusal = SimpleNamespace(stop_reason="refusal", stop_details=None, content=[])
    llm, _ = _client(settings, refusal)
    assert llm.generate("x") is None
    assert llm.generate_json("x", ConflictResolution) is None


def test_api_errors_return_none(settings):
    error = anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://api.anthropic.com")
    )
    llm, _ = _client(settings, error=error)
    assert llm.generate("x") is None
    assert llm.generate_json("x", ConflictResolution) is None


def test_hash_embeddings_are_deterministic(settings):
    llm = LLMClient(settings)
    assert llm.embed("abc") == fallback_embedding("abc", settings.embed_dim)
    assert len(llm.embed("abc")) == settings.embed_dim


def test_missing_embedding_model_falls_back_to_hash(settings, monkeypatch):
    import fastembed

    def broken(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr(fastembed, "TextEmbedding", broken)
    llm = LLMClient(settings.model_copy(update={"embed_provider": "fastembed"}))
    assert llm.embed("abc") == fallback_embedding("abc", settings.embed_dim)
