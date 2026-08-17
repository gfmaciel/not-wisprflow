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
    gemini_api_key: Optional[str] = None
    processing_mode: str = "dual"
    mono_model: str = "openai:gpt-audio-mini"
    mono_paste_threshold: float = 0.90
    mono_context_chars: int = 500
    mono_temperature: float = 0.0
    mono_log_scores: bool = False
    safe_paste_target: bool = True

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

        transcription_model = os.getenv("TRANSCRIPTION_MODEL", "whisper-large-v3-turbo")
        cleanup_model = os.getenv("CLEANUP_MODEL", "openai/gpt-oss-20b")
        mono_model = os.getenv("MONO_MODEL", "openai:gpt-audio-mini")
        mono_paste_threshold = float(os.getenv("MONO_PASTE_THRESHOLD", "0.90"))
        mono_context_chars = int(os.getenv("MONO_CONTEXT_CHARS", "500"))
        mono_temperature = float(os.getenv("MONO_TEMPERATURE", "0.0"))
        mono_log_scores = _env_bool("MONO_LOG_SCORES", False)
        safe_paste_target = _env_bool("SAFE_PASTE_TARGET", True)

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

            legacy_needed = not _explicit(transcription_model) or not _explicit(cleanup_model)
            if legacy_needed:
                if not groq_api_key and not openai_api_key:
                    raise ValueError(
                        "No API key configured for a legacy dual-mode stage. Set GROQ_API_KEY "
                        "and/or OPENAI_API_KEY, or use provider:model for that stage."
                    )
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
            transcription_model=transcription_model,
            cleanup_model=cleanup_model,
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
            gemini_api_key=gemini_api_key,
            processing_mode=mode,
            mono_model=mono_model,
            mono_paste_threshold=mono_paste_threshold,
            mono_context_chars=mono_context_chars,
            mono_temperature=mono_temperature,
            mono_log_scores=mono_log_scores,
            safe_paste_target=safe_paste_target,
        )

    @property
    def whisper_language(self) -> Optional[str]:
        if len(self.languages) == 1:
            return _LANG_CODES.get(self.languages[0].lower())
        return None