from __future__ import annotations
import io
from typing import Optional


class Transcriber:
    """Sends a WAV chunk to Whisper (primary provider, with optional fallback); returns the transcript string."""

    def __init__(
        self,
        client,
        model: str,
        language: Optional[str] = None,
        *,
        fallback_client=None,
        fallback_model: Optional[str] = None,
    ):
        self._client = client
        self._model = model
        self._language = language
        self._fallback_client = fallback_client
        self._fallback_model = fallback_model

    def transcribe(self, wav_bytes: bytes) -> str:
        kwargs: dict = dict(
            file=("audio.wav", io.BytesIO(wav_bytes), "audio/wav"),
            model=self._model,
            response_format="text",
        )
        if self._language:
            kwargs["language"] = self._language
        try:
            result = self._client.audio.transcriptions.create(**kwargs)
            return result.strip() if isinstance(result, str) else result.text.strip()
        except Exception as exc:
            if self._fallback_client is None:
                raise
            print(
                f"[not-wisprflow] Transcription primary provider failed ({exc}); "
                "retrying with fallback provider."
            )
            # Re-wrap BytesIO — the original was consumed by the failed primary call
            kwargs["file"] = ("audio.wav", io.BytesIO(wav_bytes), "audio/wav")
            kwargs["model"] = self._fallback_model or self._model
            result = self._fallback_client.audio.transcriptions.create(**kwargs)
            return result.strip() if isinstance(result, str) else result.text.strip()
