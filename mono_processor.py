from __future__ import annotations

from typing import Callable, Optional

from providers import MonoResult


class MonoProcessor:
    """Sequential, context-aware mono-mode audio processor.

    Each chunk is transcribed + cleaned by the same multimodal model. Chunks are
    expected to be submitted to a single-worker executor so the previous
    unfinished text can be supplied as context to the next request.
    """

    def __init__(
        self,
        provider,
        model: str,
        prompt: str,
        paste_fn: Callable[[str], None],
        *,
        paste_threshold: float = 0.90,
        context_chars: int = 500,
        temperature: float = 0.0,
        should_skip: Optional[Callable[[str], bool]] = None,
        log_scores: bool = False,
    ) -> None:
        self._provider = provider
        self._model = model
        self._prompt = prompt
        self._paste = paste_fn
        self._paste_threshold = paste_threshold
        self._context_chars = context_chars
        self._temperature = temperature
        self._should_skip = should_skip or (lambda _: False)
        self._log_scores = log_scores
        self._pending_text = ""

    @property
    def pending_text(self) -> str:
        return self._pending_text

    def _context(self) -> str:
        if self._context_chars <= 0:
            return ""
        return self._pending_text[-self._context_chars :]

    @staticmethod
    def _join(left: str, right: str) -> str:
        return " ".join(part.strip() for part in (left, right) if part and part.strip())

    def process(self, wav_bytes: bytes) -> MonoResult:
        result = self._provider.process_audio(
            wav_bytes,
            self._model,
            self._prompt,
            previous_context=self._context(),
            temperature=self._temperature,
        )

        text = result.text.strip()
        if not text or self._should_skip(text):
            if self._log_scores:
                print(
                    f"[not-wisprflow] mono score={result.completion_score:.3f} "
                    "skipped=true"
                )
            return result

        self._pending_text = self._join(self._pending_text, text)
        should_paste = result.completion_score >= self._paste_threshold

        if self._log_scores:
            print(
                f"[not-wisprflow] mono score={result.completion_score:.3f} "
                f"threshold={self._paste_threshold:.3f} paste={should_paste} "
                f"buffer_chars={len(self._pending_text)}"
            )

        if should_paste:
            self._paste(self._pending_text.rstrip() + " ")
            self._pending_text = ""

        return result

    def flush(self) -> Optional[str]:
        """Paste any remaining low-confidence text when recording ends."""
        text = self._pending_text.strip()
        self._pending_text = ""
        if not text:
            return None
        self._paste(text + " ")
        return text

    def reset(self) -> None:
        self._pending_text = ""
