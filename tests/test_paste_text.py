import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _stub_keyboard_and_pyperclip(monkeypatch):
    """Stub out OS-touching modules so tests don't move the user's clipboard
    or fire real key events."""
    fake_keyboard = types.SimpleNamespace(
        write=MagicMock(),
        press_and_release=MagicMock(),
    )
    fake_pyperclip = types.SimpleNamespace(
        copy=MagicMock(),
        paste=MagicMock(return_value=""),
    )
    monkeypatch.setitem(sys.modules, "keyboard", fake_keyboard)
    monkeypatch.setitem(sys.modules, "pyperclip", fake_pyperclip)
    if "paste_text" in sys.modules:
        del sys.modules["paste_text"]
    yield fake_keyboard, fake_pyperclip


def test_paste_stream_types_each_delta(_stub_keyboard_and_pyperclip):
    fake_keyboard, _ = _stub_keyboard_and_pyperclip
    from paste_text import paste_stream

    typed = paste_stream(iter(["Hel", "lo ", "world."]))

    assert typed == "Hello world."
    assert fake_keyboard.write.call_count == 3
    fake_keyboard.write.assert_any_call("Hel")
    fake_keyboard.write.assert_any_call("lo ")
    fake_keyboard.write.assert_any_call("world.")


def test_paste_stream_skips_empty(_stub_keyboard_and_pyperclip):
    fake_keyboard, _ = _stub_keyboard_and_pyperclip
    from paste_text import paste_stream

    typed = paste_stream(iter(["Hi", "", "!"]))

    assert typed == "Hi!"
    assert fake_keyboard.write.call_count == 2


def test_paste_stream_propagates_when_empty(_stub_keyboard_and_pyperclip):
    fake_keyboard, _ = _stub_keyboard_and_pyperclip
    from paste_text import paste_stream

    def boom():
        raise RuntimeError("network down")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="network down"):
        paste_stream(boom())

    fake_keyboard.write.assert_not_called()


def test_paste_stream_swallows_after_partial(_stub_keyboard_and_pyperclip, capsys):
    fake_keyboard, _ = _stub_keyboard_and_pyperclip
    from paste_text import paste_stream

    def partial():
        yield "Hello "
        yield "wor"
        raise RuntimeError("connection reset")

    typed = paste_stream(partial())

    assert typed == "Hello wor"
    assert fake_keyboard.write.call_count == 2
    assert "truncated" in capsys.readouterr().out.lower()


def test_paste_writes_clipboard_and_ctrl_v(_stub_keyboard_and_pyperclip):
    fake_keyboard, fake_pyperclip = _stub_keyboard_and_pyperclip
    fake_pyperclip.paste.return_value = "hello"
    from paste_text import paste

    paste("hello")

    fake_pyperclip.copy.assert_called_once_with("hello")
    fake_keyboard.press_and_release.assert_called_once_with("ctrl+v")
