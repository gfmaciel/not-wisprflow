import os
from unittest.mock import patch

import pytest

from config import Config


def test_mono_incremental_defaults():
    env = {
        "PROCESSING_MODE": "mono",
        "MONO_MODEL": "openai:gpt-audio-mini",
        "OPENAI_API_KEY": "sk_test",
    }
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()

    assert c.mono_paste_threshold == 0.90
    assert c.mono_context_chars == 500
    assert c.mono_temperature == 0.0
    assert c.mono_log_scores is False


def test_mono_incremental_settings_load_from_env():
    env = {
        "PROCESSING_MODE": "mono",
        "MONO_MODEL": "gemini:gemini-3.6-flash",
        "GEMINI_API_KEY": "gem_test",
        "MONO_PASTE_THRESHOLD": "0.84",
        "MONO_CONTEXT_CHARS": "320",
        "MONO_TEMPERATURE": "0.1",
        "MONO_LOG_SCORES": "true",
    }
    with patch.dict(os.environ, env, clear=True):
        c = Config.from_env()

    assert c.mono_paste_threshold == 0.84
    assert c.mono_context_chars == 320
    assert c.mono_temperature == 0.1
    assert c.mono_log_scores is True


@pytest.mark.parametrize("value", ["-0.1", "1.1"])
def test_invalid_mono_threshold_rejected(value):
    env = {
        "PROCESSING_MODE": "mono",
        "MONO_MODEL": "openai:gpt-audio-mini",
        "OPENAI_API_KEY": "sk_test",
        "MONO_PASTE_THRESHOLD": value,
    }
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="MONO_PASTE_THRESHOLD"):
            Config.from_env()
