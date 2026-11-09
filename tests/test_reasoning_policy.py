"""Every generation route must disable reasoning or reject the model early."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from config import Config
from providers import GeminiProvider, GroqProvider, OpenAIProvider
from reasoning_policy import text_generation_options


def test_default_cleanup_disables_reasoning_without_groq_key():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "fake"}, clear=True):
        config = Config.from_env()
    assert config.cleanup_model == "openai:gpt-6-luna"
    assert text_generation_options("openai", "gpt-6-luna") == {
        "reasoning_effort": "none"
    }


@pytest.mark.parametrize("model", ["openai/gpt-oss-20b", "openai/gpt-oss-120b"])
def test_groq_gpt_oss_rejected_instead_of_hiding_reasoning(model):
    with pytest.raises(ValueError, match="GPT-OSS"):
        text_generation_options("groq", model)


def test_groq_qwen_disables_reasoning():
    assert text_generation_options("groq", "qwen/qwen3.8-27b") == {
        "reasoning_effort": "none", "include_reasoning": False
    }


@pytest.mark.parametrize("model", ["gemini-3.6-flash", "gemini-2.5-pro"])
def test_gemini_models_without_zero_thinking_are_rejected(model):
    with pytest.raises(ValueError, match="cannot be guaranteed"):
        text_generation_options("gemini", model)


@pytest.mark.parametrize("model", ["gemini-2.5-flash", "gemini-2.5-flash-lite"])
def test_gemini_flash_explicitly_uses_zero_thinking(model):
    assert text_generation_options("gemini", model) == {"thinking_budget": 0}


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-sol", "o3"])
def test_openai_models_without_none_are_rejected(model):
    with pytest.raises(ValueError, match="no verified"):
        text_generation_options("openai", model)


def test_groq_cleanup_and_stream_always_send_none():
    provider = GroqProvider.__new__(GroqProvider)
    provider.client = MagicMock()
    provider.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Ok."))]
    )
    assert provider.cleanup("raw", "qwen/qwen3.8-27b", "prompt") == "Ok."
    kwargs = provider.client.chat.completions.create.call_args.kwargs
    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["include_reasoning"] is False

    provider.client.chat.completions.create.return_value = [
        SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content="Ok.")
        )])
    ]
    assert list(provider.stream_cleanup("raw", "qwen/qwen3.8-27b", "prompt")) == ["Ok."]
    kwargs = provider.client.chat.completions.create.call_args.kwargs
    assert kwargs["stream"] is True
    assert kwargs["reasoning_effort"] == "none"


def test_groq_gpt_oss_refused_before_api_call():
    provider = GroqProvider.__new__(GroqProvider)
    provider.client = MagicMock()
    with pytest.raises(ValueError, match="GPT-OSS"):
        provider.cleanup("raw", "openai/gpt-oss-20b", "prompt")
    with pytest.raises(ValueError, match="GPT-OSS"):
        list(provider.stream_cleanup("raw", "openai/gpt-oss-20b", "prompt"))
    provider.client.chat.completions.create.assert_not_called()


def test_openai_cleanup_and_stream_always_send_none():
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = MagicMock()
    provider.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Ok."))]
    )
    assert provider.cleanup("raw", "gpt-6-luna", "prompt") == "Ok."
    kwargs = provider.client.chat.completions.create.call_args.kwargs
    assert kwargs["reasoning_effort"] == "none"
    provider.client.chat.completions.create.return_value = [
        SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content="Ok.")
        )])
    ]
    assert list(provider.stream_cleanup("raw", "gpt-6-luna", "prompt")) == ["Ok."]
    kwargs = provider.client.chat.completions.create.call_args.kwargs
    assert kwargs["stream"] is True
    assert kwargs["reasoning_effort"] == "none"


def test_gemini_cleanup_uses_thinking_budget_zero():
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.client = MagicMock()
    provider.client.models.generate_content.return_value = SimpleNamespace(text="Ok.")
    provider._types = lambda: SimpleNamespace(
        ThinkingConfig=lambda **kw: kw,
        GenerateContentConfig=lambda **kw: kw,
    )
    assert provider.cleanup("raw", "gemini-2.5-flash", "prompt") == "Ok."
    kwargs = provider.client.models.generate_content.call_args.kwargs
    assert kwargs["config"]["thinking_config"] == {"thinking_budget": 0}


def test_unsupported_config_is_rejected_at_startup():
    with patch.dict(os.environ, {
        "GROQ_API_KEY": "fake",
        "TRANSCRIPTION_MODEL": "whisper-large-v3-turbo",
        "CLEANUP_MODEL": "openai/gpt-oss-20b",
    }, clear=True):
        with pytest.raises(ValueError, match="GPT-OSS"):
            Config.from_env()
