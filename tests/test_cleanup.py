from unittest.mock import MagicMock
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


def _groq(text):
    c = MagicMock()
    c.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=text))]
    )
    return c


def test_incomplete_held():
    p = CleanupProcessor(MagicMock(), "m", ["English"])
    assert p.process("hello world") is None


def test_complete_triggers_llm():
    client = _groq("Hello world.")
    p = CleanupProcessor(client, "m", ["English"])
    assert p.process("hello world.") == "Hello world."
    client.chat.completions.create.assert_called_once()


def test_fragment_prepended():
    client = _groq("In the morning I went.")
    p = CleanupProcessor(client, "m", ["English"])
    p.process("in the morning")
    p.process("I went.")
    msg = client.chat.completions.create.call_args[1]["messages"][1]["content"]
    assert "in the morning" in msg and "I went." in msg


def test_flush_emits_held():
    client = _groq("Hello world")
    p = CleanupProcessor(client, "m", ["English"])
    p.process("hello world")
    assert p.flush() == "Hello world"


def test_languages_in_system_prompt():
    client = _groq("Ola.")
    p = CleanupProcessor(client, "m", ["Portuguese", "English"])
    p.process("ola.")
    sys_msg = client.chat.completions.create.call_args[1]["messages"][0]["content"]
    assert "Portuguese" in sys_msg and "English" in sys_msg


# ── Fallback tests ────────────────────────────────────────────────────────────

def test_fallback_used_on_primary_failure(capsys):
    primary = MagicMock()
    primary.chat.completions.create.side_effect = RuntimeError("overloaded")
    fallback = _groq("Clean text.")

    p = CleanupProcessor(primary, "model-primary", ["English"],
                         fallback_client=fallback, fallback_model="gpt-4o-mini")
    result = p.process("clean text.")

    assert result == "Clean text."
    fallback.chat.completions.create.assert_called_once()
    captured = capsys.readouterr()
    assert "fallback" in captured.out.lower()


def test_no_fallback_raises_on_primary_failure():
    primary = MagicMock()
    primary.chat.completions.create.side_effect = RuntimeError("err")
    p = CleanupProcessor(primary, "model", ["English"])
    import pytest
    with pytest.raises(RuntimeError, match="err"):
        p.process("done.")


def test_fallback_uses_fallback_model():
    primary = MagicMock()
    primary.chat.completions.create.side_effect = RuntimeError("err")
    fallback = _groq("ok.")

    p = CleanupProcessor(primary, "primary-model", ["English"],
                         fallback_client=fallback, fallback_model="gpt-4o-mini")
    p.process("ok.")

    call_kwargs = fallback.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "gpt-4o-mini"


def test_backward_compat_constructor():
    """Original 3-arg positional call still works (no fallback params)."""
    p = CleanupProcessor(MagicMock(), "m", ["English"])
    assert p._fallback_client is None
