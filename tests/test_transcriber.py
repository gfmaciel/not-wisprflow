from unittest.mock import MagicMock
import pytest
from transcriber import Transcriber

WAV = b"\x00" * 44  # minimal fake WAV bytes


def _make_client(return_value="transcript text"):
    client = MagicMock()
    client.audio.transcriptions.create.return_value = return_value
    return client


def test_transcribe_primary_success():
    client = _make_client("Hello.")
    t = Transcriber(client, "whisper-large-v3-turbo")
    assert t.transcribe(WAV) == "Hello."
    client.audio.transcriptions.create.assert_called_once()


def test_transcribe_no_fallback_raises():
    client = _make_client()
    client.audio.transcriptions.create.side_effect = RuntimeError("API error")
    t = Transcriber(client, "whisper-large-v3-turbo")
    with pytest.raises(RuntimeError, match="API error"):
        t.transcribe(WAV)


def test_transcribe_fallback_used_on_primary_failure(capsys):
    primary = _make_client()
    primary.audio.transcriptions.create.side_effect = RuntimeError("rate limit")
    fallback = _make_client("Fallback result.")

    t = Transcriber(primary, "whisper-large-v3-turbo",
                    fallback_client=fallback, fallback_model="whisper-1")
    result = t.transcribe(WAV)

    assert result == "Fallback result."
    primary.audio.transcriptions.create.assert_called_once()
    fallback.audio.transcriptions.create.assert_called_once()
    captured = capsys.readouterr()
    assert "fallback" in captured.out.lower()


def test_transcribe_fallback_uses_fallback_model():
    primary = _make_client()
    primary.audio.transcriptions.create.side_effect = RuntimeError("err")
    fallback = _make_client("ok")

    t = Transcriber(primary, "whisper-large-v3-turbo",
                    fallback_client=fallback, fallback_model="whisper-1")
    t.transcribe(WAV)

    call_kwargs = fallback.audio.transcriptions.create.call_args[1]
    assert call_kwargs["model"] == "whisper-1"


def test_transcribe_backward_compat():
    """3-positional-arg call (client, model, language) still works."""
    client = _make_client("ok")
    t = Transcriber(client, "model", "en")
    t.transcribe(WAV)
    client.audio.transcriptions.create.assert_called_once()
