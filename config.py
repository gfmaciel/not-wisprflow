from __future__ import annotations
import os
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from cleanup import _SYS_BASE, with_cleanup_policy
from reasoning_policy import text_generation_options


_LANG_CODES = {
    "portuguese": "pt", "english": "en", "spanish": "es",
    "french": "fr", "german": "de", "italian": "it",
}
_KNOWN_PROVIDERS = {"groq", "openai", "gemini"}


def parse_model_spec(spec: str, default_provider: Optional[str] = None) -> tuple[str, str]:
    """Resolve `provider:model`; infer Gemini/OpenAI for common raw model names."""
    raw = spec.strip()
    if ":" in raw:
        provider, model = raw.split(":", 1)
        provider = provider.strip().lower()
        model = model.strip()
        if provider in _KNOWN_PROVIDERS and model:
            return provider, model

    lower = raw.lower()
    if lower.startswith("gemini-"):
        return "gemini", raw
    if lower.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai", raw
    if default_provider:
        return default_provider, raw
    raise ValueError(
        f"Cannot infer provider for model {spec!r}. Use provider:model "
        "(for example openai:gpt-audio-mini or gemini:gemini-3.6-flash)."
    )


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true/false, got: {raw!r}")


@dataclass
class Config:
    groq_api_key: Optional[str] = None
    transcription_model: str = "openai:gpt-transcribe"
    cleanup_model: str = "openai:gpt-6-luna"
    cleanup_prompt: str = field(default_factory=lambda: _SYS_BASE)
    languages: list[str] = field(default_factory=lambda: ["Portuguese", "English"])
    hotkey: str = "alt+\\"
    silence_aggressiveness: int = 1
    silence_duration: float = 0.7
    min_chunk_duration: float = 3.0
    max_chunk_duration: float = 12.0
    chunk_overlap_duration: float = 0.8
    primary_provider: str = "groq"
    openai_api_key: Optional[str] = None
    openai_transcription_model: str = "whisper-1"
    openai_cleanup_model: str = "gpt-4o-mini"
    gemini_api_key: Optional[str] = None
    processing_mode: str = "dual"
    mono_model: str = "openai:gpt-audio-mini"
    mono_paste_threshold: float = 0.90
    mono_context_chars: int = 500
    mono_temperature: float = 0.0
    mono_log_scores: bool = False

    @classmethod
    def from_env(cls) -> Config:
        mode = os.getenv("PROCESSING_MODE", "dual").strip().lower()
        if mode not in ("dual", "mono"):
            raise ValueError(
                f"PROCESSING_MODE must be 'dual' or 'mono', got: {mode!r}"
            )

        primary = os.getenv("PRIMARY_PROVIDER", "groq").strip().lower()
        if primary not in ("groq", "openai"):
            raise ValueError(
                f"PRIMARY_PROVIDER must be 'groq' or 'openai', got: {primary!r}"
            )

        groq_api_key = os.getenv("GROQ_API_KEY", "").strip() or None
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
        gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip() or None

        transcription_model = os.getenv("TRANSCRIPTION_MODEL", "openai:gpt-transcribe")
        cleanup_model = os.getenv("CLEANUP_MODEL", "openai:gpt-6-luna")
        mono_model = os.getenv("MONO_MODEL", "openai:gpt-audio-mini")
        mono_paste_threshold = float(os.getenv("MONO_PASTE_THRESHOLD", "0.90"))
        mono_context_chars = int(os.getenv("MONO_CONTEXT_CHARS", "500"))
        mono_temperature = float(os.getenv("MONO_TEMPERATURE", "0.0"))
        mono_log_scores = _env_bool("MONO_LOG_SCORES", False)
        silence_duration = float(os.getenv("SILENCE_DURATION", "0.7"))
        min_chunk_duration = float(os.getenv("MIN_CHUNK_DURATION", "3.0"))
        max_chunk_duration = float(os.getenv("MAX_CHUNK_DURATION", "12.0"))
        chunk_overlap_duration = float(os.getenv("CHUNK_OVERLAP_DURATION", "0.8"))

        durations = {
            "SILENCE_DURATION": silence_duration,
            "MIN_CHUNK_DURATION": min_chunk_duration,
            "MAX_CHUNK_DURATION": max_chunk_duration,
            "CHUNK_OVERLAP_DURATION": chunk_overlap_duration,
        }
        for key, value in durations.items():
            if not math.isfinite(value) or (value <= 0 if key != "CHUNK_OVERLAP_DURATION" else value < 0):
                raise ValueError(f"{key} must be finite and non-negative (positive except overlap)")
        if max_chunk_duration < min_chunk_duration:
            raise ValueError("MAX_CHUNK_DURATION must be >= MIN_CHUNK_DURATION")
        if chunk_overlap_duration >= max_chunk_duration:
            raise ValueError("CHUNK_OVERLAP_DURATION must be shorter than MAX_CHUNK_DURATION")

        if not 0.0 <= mono_paste_threshold <= 1.0:
            raise ValueError("MONO_PASTE_THRESHOLD must be between 0 and 1")
        if mono_context_chars < 0:
            raise ValueError("MONO_CONTEXT_CHARS must be >= 0")
        if not 0.0 <= mono_temperature <= 2.0:
            raise ValueError("MONO_TEMPERATURE must be between 0 and 2")

        keys = {
            "groq": groq_api_key,
            "openai": openai_api_key,
            "gemini": gemini_api_key,
        }

        if mode == "mono":
            mono_provider, _ = parse_model_spec(mono_model)
            if mono_provider == "groq":
                raise ValueError(
                    "PROCESSING_MODE=mono supports OpenAI or Gemini audio-capable models, not Groq."
                )
            if not keys[mono_provider]:
                raise ValueError(
                    f"{mono_provider.upper()}_API_KEY is required by MONO_MODEL={mono_model!r}"
                )
            text_generation_options(mono_provider, parse_model_spec(mono_model)[1])
        else:
            for label, spec in (
                ("TRANSCRIPTION_MODEL", transcription_model),
                ("CLEANUP_MODEL", cleanup_model),
            ):
                if ":" in spec or spec.lower().startswith(("gemini-", "gpt-", "o1", "o3", "o4")):
                    provider, _ = parse_model_spec(spec, primary)
                    if not keys[provider]:
                        raise ValueError(
                            f"{provider.upper()}_API_KEY is required by {label}={spec!r}"
                        )

            def _explicit(spec: str) -> bool:
                lower = spec.lower()
                return (
                    ":" in spec
                    or lower.startswith("gemini-")
                    or lower.startswith(("gpt-", "o1", "o3", "o4"))
                )

            # Never silently substitute a different cleanup model merely because
            # the API key for its configured provider is absent.
            if not _explicit(cleanup_model) and not keys[primary]:
                raise ValueError(
                    f"{primary.upper()}_API_KEY is required by CLEANUP_MODEL={cleanup_model!r}. "
                    "The cleanup model will not be changed automatically."
                )
            cleanup_provider, cleanup_model_id = (
                parse_model_spec(cleanup_model, primary)
                if _explicit(cleanup_model) else (primary, cleanup_model)
            )
            text_generation_options(cleanup_provider, cleanup_model_id)
            if not _explicit(transcription_model) and not keys[primary]:
                raise ValueError(
                    f"{primary.upper()}_API_KEY is required by TRANSCRIPTION_MODEL="
                    f"{transcription_model!r}. Select the intended provider explicitly."
                )

        return cls(
            groq_api_key=groq_api_key,
            transcription_model=transcription_model,
            cleanup_model=cleanup_model,
            cleanup_prompt=with_cleanup_policy(os.getenv("CLEANUP_SYSTEM_PROMPT")),
            languages=[
                l.strip()
                for l in os.getenv("LANGUAGES", "Portuguese,English").split(",")
                if l.strip()
            ],
            hotkey=os.getenv("HOTKEY", "alt+\\").lower(),
            silence_aggressiveness=int(float(os.getenv("SILENCE_THRESHOLD", "1"))),
            silence_duration=silence_duration,
            min_chunk_duration=min_chunk_duration,
            max_chunk_duration=max_chunk_duration,
            chunk_overlap_duration=chunk_overlap_duration,
            primary_provider=primary,
            openai_api_key=openai_api_key,
            openai_transcription_model=os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1"),
            openai_cleanup_model=os.getenv("OPENAI_CLEANUP_MODEL", "gpt-4o-mini"),
            gemini_api_key=gemini_api_key,
            processing_mode=mode,
            mono_model=mono_model,
            mono_paste_threshold=mono_paste_threshold,
            mono_context_chars=mono_context_chars,
            mono_temperature=mono_temperature,
            mono_log_scores=mono_log_scores,
        )

    @property
    def whisper_language(self) -> Optional[str]:
        if len(self.languages) == 1:
            return _LANG_CODES.get(self.languages[0].lower())
        return None

    @property
    def transcription_languages(self) -> list[str]:
        """Known language hints for gpt-transcribe (which supports multiple languages)."""
        codes = (_LANG_CODES.get(value.lower()) for value in self.languages)
        return list(dict.fromkeys(code for code in codes if code))



def load_config(dotenv_path: str | Path | None = None) -> Config:
    """Load this app's .env before applying Config's code defaults.

    Shell environment values remain higher priority than .env (python-dotenv's
    default). An explicit path makes tests independent of any personal .env.
    """
    from dotenv import load_dotenv

    path = Path(dotenv_path) if dotenv_path is not None else Path(__file__).resolve().with_name(".env")
    load_dotenv(dotenv_path=path, override=False)
    return Config.from_env()
