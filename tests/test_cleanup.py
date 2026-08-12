from unittest.mock import MagicMock
import pytest
from cleanup import ends_with_sentence, CleanupProcessor


def test_period():
    assert ends_with_sentence("Hello.") is True


def test_question():
    assert ends_with_sentence("How?") is True


def test_exclamation():
    assert ends_with_sentence("Yes!") is True


def test_incomplete():
    assert ends_with_sentence("hello world") is False


def test_empty():
    assert ends_with_sentence("") is False


def test_trailing_space():
    assert ends_with_sentence("Done.   ") is True


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


def test_fallback_used_on_primary_failure(capsys):
    primary = _provider()
    primary.cleanup.side_effect = RuntimeError("overloaded")
    fallback = _provider("Clean text.")

    p = CleanupProcessor(
        primary,
        "model-primary",
        ["English"],
        fallback_provider=fallback,
        fallback_model="gpt-4o-mini",
    )
    result = p.process("clean text.")

    assert result == "Clean text."
    fallback.cleanup.assert_called_once()
    captured = capsys.readouterr()
    assert "fallback" in captured.out.lower()


def test_no_fallback_raises_on_primary_failure():
    primary = _provider()
    primary.cleanup.side_effect = RuntimeError("err")
    p = CleanupProcessor(primary, "model", ["English"])
    with pytest.raises(RuntimeError, match="err"):
        p.process("done.")


def test_fallback_uses_fallback_model():
    primary = _provider()
    primary.cleanup.side_effect = RuntimeError("err")
    fallback = _provider("ok.")

    p = CleanupProcessor(
        primary,
        "primary-model",
        ["English"],
        fallback_provider=fallback,
        fallback_model="gpt-4o-mini",
    )
    p.process("ok.")

    assert fallback.cleanup.call_args.args[1] == "gpt-4o-mini"


def test_stream_yields_deltas():
    provider = _provider(deltas=["Hel", "lo ", "world."])
    p = CleanupProcessor(provider, "m", ["English"])
    assert list(p.stream("hello world.")) == ["Hel", "lo ", "world."]
    provider.stream_cleanup.assert_called_once()
    assert provider.stream_cleanup.call_args.args[1] == "m"


def test_stream_uses_system_prompt_with_languages():
    provider = _provider(deltas=["x"])
    p = CleanupProcessor(provider, "m", ["Portuguese", "English"])
    list(p.stream("test."))
    system_prompt = provider.stream_cleanup.call_args.args[2]
    assert "Portuguese" in system_prompt and "English" in system_prompt
