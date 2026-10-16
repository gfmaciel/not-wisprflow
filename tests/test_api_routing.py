from types import SimpleNamespace
from unittest.mock import MagicMock

from cleanup import CleanupProcessor
from config import Config, parse_model_spec
from providers import OpenAIProvider
from transcriber import Transcriber


def _provider():
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = MagicMock()
    provider.client.audio.transcriptions.create.return_value = SimpleNamespace(
        text="Pergunta ditada?"
    )
    return provider


def test_gpt_transcribe_uses_openai_transcription_endpoint_and_languages():
    provider = _provider()
    result = provider.transcribe(b"WAVE", "gpt-transcribe", "pt")
    assert result == "Pergunta ditada?"
    kwargs = provider.client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-transcribe"
    assert kwargs["languages"] == ["pt"]
    assert "language" not in kwargs
    assert kwargs["file"][0] == "audio.wav"
    provider.client.chat.completions.create.assert_not_called()


def test_other_openai_models_retain_singular_language_hint():
    provider = _provider()
    provider.transcribe(b"WAVE", "whisper-1", "pt")
    kwargs = provider.client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["language"] == "pt"
    assert "languages" not in kwargs


def test_installed_openai_sdk_supports_gpt_transcribe_language_hints():
    """Ensure a locally preinstalled older SDK cannot break the API at runtime."""
    from inspect import signature
    from openai.resources.audio.transcriptions import Transcriptions

    assert "languages" in signature(Transcriptions.create).parameters


def test_gpt_transcribe_multilingual_hints_are_forwarded_without_changing_cleanup():
    provider = _provider()
    provider.transcribe(b"WAVE", "gpt-transcribe", ["pt", "en"])
    kwargs = provider.client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["languages"] == ["pt", "en"]
    assert "language" not in kwargs
    config = Config(openai_api_key="sk_test", groq_api_key="gsk_test")
    assert config.transcription_languages == ["pt", "en"]
    assert config.cleanup_model == "openai/gpt-oss-20b"


def test_legacy_cleanup_model_is_never_silently_replaced():
    from pipeline import Pipeline

    config = Config(
        processing_mode="dual", primary_provider="groq",
        cleanup_model="openai/gpt-oss-20b",
    )
    pipeline = Pipeline.__new__(Pipeline)
    groq, openai = object(), object()
    pipeline._providers = {"groq": groq, "openai": openai}
    stage = pipeline._resolve_dual_stage(config, "cleanup")
    assert stage["provider"] is groq
    assert stage["model"] == config.cleanup_model
    assert stage["fallback_provider"] is None
    config.cleanup_model = "openai:gpt-4o-mini"
    stage = pipeline._resolve_dual_stage(config, "cleanup")
    assert stage["provider"] is openai
    assert stage["model"] == "gpt-4o-mini"
