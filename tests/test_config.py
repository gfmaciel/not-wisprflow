import os
import pytest
from unittest.mock import patch
from config import Config


def test_config_loads_from_env():
    env = {
        "GROQ_API_KEY": "gsk_test", "LANGUAGES": "Portuguese,English",
        "SILENCE_THRESHOLD": "1", "SILENCE_DURATION": "2.0",
        "MIN_CHUNK_DURATION": "3.0", "HOTKEY": "ctrl+shift+space",
        "TRANSCRIPTION_MODEL": "whisper-large-v3-turbo",
        "CLEANUP_MODEL": "openai/gpt-oss-20b",
    }
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()
    assert c.groq_api_key == "gsk_test"
    assert c.languages == ["Portuguese", "English"]
    assert c.silence_aggressiveness == 1
    assert c.silence_duration == 2.0


def test_config_raises_without_api_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            Config.from_env()


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
    assert c.hotkey == "ctrl+shift+space"
