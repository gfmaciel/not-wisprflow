import os
import pytest
from unittest.mock import patch
from config import Config, parse_model_spec


def test_config_loads_from_env():
    env = {
        "GROQ_API_KEY": "gsk_test", "LANGUAGES": "Portuguese,English",
        "SILENCE_THRESHOLD": "1", "SILENCE_DURATION": "2.0",
        "MIN_CHUNK_DURATION": "3.0", "HOTKEY": "alt+\\",
        "TRANSCRIPTION_MODEL": "whisper-large-v3-turbo",
        "CLEANUP_MODEL": "openai/gpt-oss-20b",
    }
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.groq_api_key == "gsk_test"
    assert c.languages == ["Portuguese", "English"]
    assert c.silence_aggressiveness == 1
    assert c.silence_duration == 2.0


def test_config_raises_without_any_api_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="No API key"):
            Config.from_env()


def test_config_groq_primary_missing_key_falls_back_to_openai(capsys):
    env = {"OPENAI_API_KEY": "sk_test"}
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.primary_provider == "openai"
    assert c.openai_api_key == "sk_test"
    assert c.groq_api_key is None
    captured = capsys.readouterr()
    assert "GROQ_API_KEY" in captured.out
    assert "openai" in captured.out.lower()


def test_config_openai_primary_missing_key_falls_back_to_groq(capsys):
    env = {"PRIMARY_PROVIDER": "openai", "GROQ_API_KEY": "gsk_test"}
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.primary_provider == "groq"
    assert c.groq_api_key == "gsk_test"
    assert c.openai_api_key is None
    captured = capsys.readouterr()
    assert "OPENAI_API_KEY" in captured.out
    assert "groq" in captured.out.lower()


def test_config_openai_primary_with_key():
    env = {"PRIMARY_PROVIDER": "openai", "OPENAI_API_KEY": "sk_test"}
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.primary_provider == "openai"
    assert c.openai_api_key == "sk_test"
    assert c.groq_api_key is None


def test_config_groq_no_openai_key():
    env = {"GROQ_API_KEY": "gsk_test"}
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.openai_api_key is None


def test_config_invalid_primary_provider():
    env = {"PRIMARY_PROVIDER": "azure", "GROQ_API_KEY": "x"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="PRIMARY_PROVIDER"):
            Config.from_env()


def test_config_openai_model_defaults():
    env = {"GROQ_API_KEY": "x"}
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.openai_transcription_model == "whisper-1"
    assert c.openai_cleanup_model == "gpt-4o-mini"


def test_whisper_language_single():
    with patch.dict(os.environ, {"GROQ_API_KEY": "x", "LANGUAGES": "Portuguese"}, clear=True):
        c = Config.from_env()
    assert c.whisper_language == "pt"


def test_whisper_language_multi():
    with patch.dict(os.environ, {"GROQ_API_KEY": "x", "LANGUAGES": "Portuguese,English"}, clear=True):
        c = Config.from_env()
    assert c.whisper_language is None


def test_config_defaults():
    with patch.dict(os.environ, {"GROQ_API_KEY": "x"}, clear=True):
        c = Config.from_env()
    assert c.transcription_model == "whisper-large-v3-turbo"
    assert c.hotkey == "alt+\\"
    assert c.processing_mode == "dual"


def test_parse_model_spec_explicit_and_inferred():
    assert parse_model_spec("openai:gpt-audio-mini") == ("openai", "gpt-audio-mini")
    assert parse_model_spec("gemini:gemini-3.6-flash") == ("gemini", "gemini-3.6-flash")
    assert parse_model_spec("gemini-3.6-flash") == ("gemini", "gemini-3.6-flash")
    assert parse_model_spec("gpt-audio-mini") == ("openai", "gpt-audio-mini")


def test_mono_openai_loads_from_env():
    env = {
        "PROCESSING_MODE": "mono",
        "MONO_MODEL": "openai:gpt-audio-mini",
        "OPENAI_API_KEY": "sk_test",
    }
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.processing_mode == "mono"
    assert c.mono_model == "openai:gpt-audio-mini"


def test_mono_gemini_loads_from_env():
    env = {
        "PROCESSING_MODE": "mono",
        "MONO_MODEL": "gemini:gemini-3.6-flash",
        "GEMINI_API_KEY": "gem_test",
    }
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.processing_mode == "mono"
    assert c.gemini_api_key == "gem_test"


def test_mono_requires_matching_provider_key():
    env = {
        "PROCESSING_MODE": "mono",
        "MONO_MODEL": "gemini:gemini-3.6-flash",
        "OPENAI_API_KEY": "sk_test",
    }
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            Config.from_env()


def test_dual_can_mix_openai_and_gemini():
    env = {
        "PROCESSING_MODE": "dual",
        "TRANSCRIPTION_MODEL": "openai:gpt-4o-mini-transcribe",
        "CLEANUP_MODEL": "gemini:gemini-3.6-flash",
        "OPENAI_API_KEY": "sk_test",
        "GEMINI_API_KEY": "gem_test",
    }
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.transcription_model.startswith("openai:")
    assert c.cleanup_model.startswith("gemini:")
