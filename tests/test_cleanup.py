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
