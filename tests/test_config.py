import os
import pytest
from unittest.mock import patch
from config import Config, parse_model_spec, load_config


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
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            Config.from_env()


def test_cleanup_does_not_switch_models_if_groq_key_is_missing():
    env = {"OPENAI_API_KEY": "sk_test"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="GROQ_API_KEY.*CLEANUP_MODEL"):
            Config.from_env()


def test_config_openai_primary_missing_key_fails_instead_of_switching():
    env = {"PRIMARY_PROVIDER": "openai", "GROQ_API_KEY": "gsk_test",
           "TRANSCRIPTION_MODEL": "whisper-large-v3-turbo"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            Config.from_env()


def test_config_openai_primary_with_key():
    env = {"PRIMARY_PROVIDER": "openai", "OPENAI_API_KEY": "sk_test"}
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.primary_provider == "openai"
    assert c.openai_api_key == "sk_test"
    assert c.groq_api_key is None


def test_config_groq_no_openai_key():
    env = {"GROQ_API_KEY": "gsk_test", "TRANSCRIPTION_MODEL": "whisper-large-v3-turbo"}
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.openai_api_key is None


def test_config_invalid_primary_provider():
    env = {"PRIMARY_PROVIDER": "azure", "GROQ_API_KEY": "x"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="PRIMARY_PROVIDER"):
            Config.from_env()


def test_whisper_language_single():
    with patch.dict(os.environ, {"GROQ_API_KEY": "x", "LANGUAGES": "Portuguese", "TRANSCRIPTION_MODEL": "whisper-large-v3-turbo"}, clear=True):
        c = Config.from_env()
    assert c.whisper_language == "pt"


def test_config_defaults():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "x", "GROQ_API_KEY": "y"}, clear=True):
        c = Config.from_env()
    assert c.transcription_model == "openai:gpt-transcribe"
    assert c.hotkey == "alt+\\"
    assert c.processing_mode == "dual"


def test_parse_model_spec_explicit_and_inferred():
    assert parse_model_spec("openai:gpt-audio-mini") == ("openai", "gpt-audio-mini")
    assert parse_model_spec("gemini:gemini-3.6-flash") == ("gemini", "gemini-3.6-flash")
    assert parse_model_spec("gemini-3.6-flash") == ("gemini", "gemini-3.6-flash")
    assert parse_model_spec("gpt-audio-mini") == ("openai", "gpt-audio-mini")


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


def test_default_multilingual_hints_and_legacy_single_hint():
    with patch.dict(os.environ, {
        "OPENAI_API_KEY": "sk_test", "GROQ_API_KEY": "gsk_test",
        "LANGUAGES": "Portuguese,English,Portuguese"
    }, clear=True):
        config = Config.from_env()
    assert config.transcription_languages == ["pt", "en"]
    assert config.whisper_language is None


def test_local_dotenv_overrides_code_defaults_without_real_secrets(tmp_path):
    """Only read the synthetic file we created, never the user's .env."""
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "OPENAI_API_KEY=sk_fake\n"
        "TRANSCRIPTION_MODEL=openai:gpt-4o-mini-transcribe\n"
        "CLEANUP_MODEL=openai:gpt-4o-mini\n"
        "HOTKEY=ctrl+shift+x\n"
        "LANGUAGES=Portuguese\n",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {}, clear=True):
        config = load_config(dotenv)
        assert config.transcription_model == "openai:gpt-4o-mini-transcribe"
        assert config.cleanup_model == "openai:gpt-4o-mini"
        assert config.hotkey == "ctrl+shift+x"
        assert config.whisper_language == "pt"
        assert config.processing_mode == "dual"

    # An explicit process variable takes priority over the .env, as documented.
    with patch.dict(os.environ, {"CLEANUP_MODEL": "openai:gpt-4o"}, clear=True):
        config = load_config(dotenv)
        assert config.cleanup_model == "openai:gpt-4o"
        assert config.transcription_model == "openai:gpt-4o-mini-transcribe"
