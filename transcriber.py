from __future__ import annotations
from typing import Optional


class Transcriber:
    """Sends a WAV chunk to the configured provider, with optional fallback."""

    def __init__(
        self,
        provider,
        model: str,
        language: Optional[str] = None,
        *,
        fallback_provider=None,
        fallback_model: Optional[str] = None,
    ):
        self._provider = provider
        self._model = model
        self._language = language
        self._fallback_provider = fallback_provider
        self._fallback_model = fallback_model

    def transcribe(self, wav_bytes: bytes) -> str:
        try:
            return self._provider.transcribe(wav_bytes, self._model, self._language)
        except Exception as exc:
            if self._fallback_provider is None:
                raise
            print(
                f"[not-wisprflow] Transcription primary provider failed ({exc}); "
                "retrying with fallback provider."
            )
            return self._fallback_provider.transcribe(
                wav_bytes,
                self._fallback_model or self._model,
                self._language,
            )
