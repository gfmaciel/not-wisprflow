from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv
from cleanup import _SYS_BASE

load_dotenv()

_LANG_CODES = {
    "portuguese": "pt", "english": "en", "spanish": "es",
    "french": "fr", "german": "de", "italian": "it",
}


@dataclass
class Config:
    groq_api_key: Optional[str] = None
    transcription_model: str = "whisper-large-v3-turbo"
    cleanup_model: str = "openai/gpt-oss-20b"
    cleanup_prompt: str = field(default_factory=lambda: _SYS_BASE)
    languages: list[str] = field(default_factory=lambda: ["Portuguese", "English"])
    hotkey: str = "alt+\\"
    silence_aggressiveness: int = 1
    silence_duration: float = 2.0
    min_chunk_duration: float = 3.0
    primary_provider: str = "groq"
    openai_api_key: Optional[str] = None
    openai_transcription_model: str = "whisper-1"
    openai_cleanup_model: str = "gpt-4o-mini"

    @classmethod
    def from_env(cls) -> Config:
        primary = os.getenv("PRIMARY_PROVIDER", "groq").strip().lower()
        if primary not in ("groq", "openai"):
            raise ValueError(
                f"PRIMARY_PROVIDER must be 'groq' or 'openai', got: {primary!r}"
            )

        groq_api_key = os.getenv("GROQ_API_KEY", "").strip() or None
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip() or None

        if not groq_api_key and not openai_api_key:
            raise ValueError(
                "No API key configured. Set GROQ_API_KEY and/or OPENAI_API_KEY in environment / .env"
            )

        # Graceful degradation: if the primary provider's key is missing, promote the fallback
        if primary == "groq" and not groq_api_key:
            print(
                "[not-wisprflow] WARNING: GROQ_API_KEY not set; "
                "switching to OpenAI as primary provider."
            )
            primary = "openai"
        elif primary == "openai" and not openai_api_key:
            print(
                "[not-wisprflow] WARNING: OPENAI_API_KEY not set; "
                "switching to Groq as primary provider."
            )
            primary = "groq"

        return cls(
            groq_api_key=groq_api_key,
            transcription_model=os.getenv("TRANSCRIPTION_MODEL", "whisper-large-v3-turbo"),
            cleanup_model=os.getenv("CLEANUP_MODEL", "openai/gpt-oss-20b"),
            cleanup_prompt=os.getenv("CLEANUP_SYSTEM_PROMPT", _SYS_BASE),
            languages=[
                l.strip()
                for l in os.getenv("LANGUAGES", "Portuguese,English").split(",")
                if l.strip()
            ],
            hotkey=os.getenv("HOTKEY", "alt+\\").lower(),
            silence_aggressiveness=int(float(os.getenv("SILENCE_THRESHOLD", "1"))),
            silence_duration=float(os.getenv("SILENCE_DURATION", "2.0")),
            min_chunk_duration=float(os.getenv("MIN_CHUNK_DURATION", "3.0")),
            primary_provider=primary,
            openai_api_key=openai_api_key,
            openai_transcription_model=os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1"),
            openai_cleanup_model=os.getenv("OPENAI_CLEANUP_MODEL", "gpt-4o-mini"),
        )

    @property
    def whisper_language(self) -> Optional[str]:
        if len(self.languages) == 1:
            return _LANG_CODES.get(self.languages[0].lower())
        return None
