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
    groq_api_key: str
    transcription_model: str = "whisper-large-v3-turbo"
    cleanup_model: str = "openai/gpt-oss-20b"
    cleanup_prompt: str = field(default_factory=lambda: _SYS_BASE)
    languages: list[str] = field(default_factory=lambda: ["Portuguese", "English"])
    hotkey: str = "ctrl+shift+space"
    silence_aggressiveness: int = 1
    silence_duration: float = 2.0
    min_chunk_duration: float = 3.0

    @classmethod
    def from_env(cls) -> Config:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise ValueError("GROQ_API_KEY not set in environment / .env")
        return cls(
            groq_api_key=api_key,
            transcription_model=os.getenv("TRANSCRIPTION_MODEL", "whisper-large-v3-turbo"),
            cleanup_model=os.getenv("CLEANUP_MODEL", "openai/gpt-oss-20b"),
            cleanup_prompt=os.getenv("CLEANUP_SYSTEM_PROMPT", _SYS_BASE),
            languages=[
                l.strip()
                for l in os.getenv("LANGUAGES", "Portuguese,English").split(",")
                if l.strip()
            ],
            hotkey=os.getenv("HOTKEY", "ctrl+shift+space").lower(),
            silence_aggressiveness=int(float(os.getenv("SILENCE_THRESHOLD", "1"))),
            silence_duration=float(os.getenv("SILENCE_DURATION", "2.0")),
            min_chunk_duration=float(os.getenv("MIN_CHUNK_DURATION", "3.0")),
        )

    @property
    def whisper_language(self) -> Optional[str]:
        if len(self.languages) == 1:
            return _LANG_CODES.get(self.languages[0].lower())
        return None
