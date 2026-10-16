from unittest.mock import MagicMock
import pytest
from cleanup import ends_with_sentence, CleanupProcessor


def test_sentence_boundaries():
    cases = (
        ("Hello.", True), ("How?", True), ("Yes!", True),
        ("hello world", False), ("", False), ("Done.   ", True),
    )
    for text, expected in cases:
        assert ends_with_sentence(text) is expected, text


def _provider(cleaned="Clean text.", deltas=None):
    provider = MagicMock()
    provider.cleanup.return_value = cleaned
    provider.stream_cleanup.return_value = iter(deltas or [])
    return provider


def test_incomplete_held():
    p = CleanupProcessor(_provider(), "m", ["English"])
    assert p.process("hello world") is None


def test_complete_triggers_llm():
    provider = _provider("Hello world.")
    p = CleanupProcessor(provider, "m", ["English"])
    assert p.process("hello world.") == "Hello world."
    provider.cleanup.assert_called_once()


def test_fragment_prepended():
    provider = _provider("In the morning I went.")
    p = CleanupProcessor(provider, "m", ["English"])
    p.process("in the morning")
    p.process("I went.")
    text = provider.cleanup.call_args.args[0]
    assert "in the morning" in text and "I went." in text


def test_flush_emits_held():
    provider = _provider("Hello world")
    p = CleanupProcessor(provider, "m", ["English"])
    p.process("hello world")
    assert p.flush() == "Hello world"


def test_languages_in_system_prompt():
    provider = _provider("Ola.")
    p = CleanupProcessor(provider, "m", ["Portuguese", "English"])
    p.process("ola.")
    system_prompt = provider.cleanup.call_args.args[2]
    assert "Portuguese" in system_prompt and "English" in system_prompt


def test_no_fallback_raises_on_primary_failure():
    primary = _provider()
    primary.cleanup.side_effect = RuntimeError("err")
    p = CleanupProcessor(primary, "model", ["English"])
    with pytest.raises(RuntimeError, match="err"):
        p.process("done.")


def test_stream_yields_deltas():
    provider = _provider(deltas=["Hel", "lo ", "world."])
    p = CleanupProcessor(provider, "m", ["English"])
    assert list(p.stream("hello world.")) == ["Hel", "lo ", "world."]
    provider.stream_cleanup.assert_called_once()
    assert provider.stream_cleanup.call_args.args[1] == "m"


def test_cleanup_fallback_retains_model_and_language_hints():
    primary, fallback = _provider(), _provider("Recovered.")
    primary.cleanup.side_effect = RuntimeError("primary unavailable")
    processor = CleanupProcessor(
        primary, "primary-model", ["English", "Portuguese"],
        fallback_provider=fallback, fallback_model="fallback-model",
    )
    assert processor.process("Do this.") == "Recovered."
    fallback.cleanup.assert_called_once()
    text, model, prompt = fallback.cleanup.call_args.args
    assert text == "Do this."
    assert model == "fallback-model"
    assert "Portuguese" in prompt and "English" in prompt
