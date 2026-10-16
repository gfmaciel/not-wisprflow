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


def test_default_dual_mode_routes_transcription_separately_from_cleanup():
    config = Config(openai_api_key="sk_test")
    assert config.processing_mode == "dual"
    assert parse_model_spec(config.transcription_model) == ("openai", "gpt-transcribe")
    original_cleanup_model = config.cleanup_model
    provider = _provider()
    transcriber = Transcriber(provider, "gpt-transcribe")
    assert transcriber.transcribe(b"WAVE") == "Pergunta ditada?"
    assert config.cleanup_model == original_cleanup_model
    cleanup = CleanupProcessor(provider, original_cleanup_model, ["Portuguese"])
    provider.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Pergunta ditada?"))]
    )
    assert cleanup.process("Pergunta ditada?") == "Pergunta ditada?"
    assert provider.client.chat.completions.create.call_args.kwargs["model"] == original_cleanup_model


def test_installed_openai_sdk_supports_gpt_transcribe_language_hints():
    """Ensure a locally preinstalled older SDK cannot break the API at runtime."""
    from inspect import signature
    from openai.resources.audio.transcriptions import Transcriptions

    assert "languages" in signature(Transcriptions.create).parameters
