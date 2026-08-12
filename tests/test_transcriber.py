from unittest.mock import MagicMock
import pytest
from transcriber import Transcriber

WAV = b"\x00" * 44


def _provider(return_value="transcript text"):
    provider = MagicMock()
    provider.transcribe.return_value = return_value
    return provider


def test_transcribe_primary_success():
    provider = _provider("Hello.")
    t = Transcriber(provider, "whisper-large-v3-turbo")
    assert t.transcribe(WAV) == "Hello."
    provider.transcribe.assert_called_once_with(WAV, "whisper-large-v3-turbo", None)


def test_transcribe_no_fallback_raises():
    provider = _provider()
    provider.transcribe.side_effect = RuntimeError("API error")
    t = Transcriber(provider, "whisper-large-v3-turbo")
    with pytest.raises(RuntimeError, match="API error"):
        t.transcribe(WAV)


def test_transcribe_fallback_used_on_primary_failure(capsys):
    primary = _provider()
    primary.transcribe.side_effect = RuntimeError("rate limit")
    fallback = _provider("Fallback result.")

    t = Transcriber(
        primary,
        "whisper-large-v3-turbo",
        fallback_provider=fallback,
        fallback_model="whisper-1",
    )
    result = t.transcribe(WAV)

    assert result == "Fallback result."
    primary.transcribe.assert_called_once()
    fallback.transcribe.assert_called_once_with(WAV, "whisper-1", None)
    captured = capsys.readouterr()
    assert "fallback" in captured.out.lower()


def test_transcribe_fallback_preserves_language():
    primary = _provider()
    primary.transcribe.side_effect = RuntimeError("err")
    fallback = _provider("ok")

    t = Transcriber(
        primary,
        "primary-model",
        "pt",
        fallback_provider=fallback,
        fallback_model="fallback-model",
    )
    t.transcribe(WAV)

    fallback.transcribe.assert_called_once_with(WAV, "fallback-model", "pt")
