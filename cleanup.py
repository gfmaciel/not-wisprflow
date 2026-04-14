from __future__ import annotations
from typing import Optional

_ENDINGS = (".", "?", "!")

_SYS_BASE = (
    "You are a transcription cleanup assistant. Clean up the transcription "
    "by fixing punctuation, grammar, and capitalization, and removing filler words "
    "(uh, um, like, etc.). Do not rephrase, summarize, or add anything. "
    "Return only the cleaned text with no explanation.\n\n"
    "Detect the language of the input and respond in that same language."
)


def ends_with_sentence(text: str) -> bool:
    return text.rstrip().endswith(_ENDINGS)


class CleanupProcessor:
    """Buffers incomplete sentence fragments; calls LLM only on complete sentences."""

    def __init__(self, groq_client, model: str, languages: list[str], prompt: str = _SYS_BASE):
        self._client = groq_client
        self._model = model
        self._languages = languages
        self._prompt = prompt
        self._fragment = ""

    def process(self, transcript: str) -> Optional[str]:
        """Returns cleaned text if sentence is complete, else None."""
        combined = (self._fragment + " " + transcript).strip() if self._fragment else transcript
        if not ends_with_sentence(combined):
            self._fragment = combined
            return None
        self._fragment = ""
        return self._call_llm(combined)

    def flush(self) -> Optional[str]:
        """Force-emit any held fragment (call at recording end)."""
        if not self._fragment:
            return None
        text, self._fragment = self._fragment, ""
        return self._call_llm(text)

    def _call_llm(self, text: str) -> str:
        system = self._prompt
        if self._languages:
            langs = ", ".join(self._languages)
            system += f"\nThe user may speak any of the following languages: {langs}."
        r = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
        )
        return r.choices[0].message.content.strip()
