from __future__ import annotations
import io
from typing import Optional


class Transcriber:
    """Sends a WAV chunk to Groq Whisper; returns the transcript string."""

    def __init__(self, groq_client, model: str, language: Optional[str] = None):
        self._client = groq_client
        self._model = model
        self._language = language

    def transcribe(self, wav_bytes: bytes) -> str:
        kwargs: dict = dict(
            file=("audio.wav", io.BytesIO(wav_bytes), "audio/wav"),
            model=self._model,
            response_format="text",
        )
        if self._language:
            kwargs["language"] = self._language
        result = self._client.audio.transcriptions.create(**kwargs)
        # Groq returns a plain string when response_format="text"
        return result.strip() if isinstance(result, str) else result.text.strip()
