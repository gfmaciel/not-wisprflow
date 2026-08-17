import os
from unittest.mock import patch

from config import Config


def test_safe_paste_target_defaults_on():
    with patch.dict(os.environ, {"GROQ_API_KEY": "x"}, clear=True):
        config = Config.from_env()
    assert config.safe_paste_target is True


def test_safe_paste_target_can_restore_legacy_behavior():
    env = {"GROQ_API_KEY": "x", "SAFE_PASTE_TARGET": "false"}
    with patch.dict(os.environ, env, clear=True):
        config = Config.from_env()
    assert config.safe_paste_target is False
