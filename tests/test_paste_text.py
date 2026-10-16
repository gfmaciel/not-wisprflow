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


def test_paste_writes_clipboard_and_ctrl_v(_stub_keyboard_and_pyperclip):
    fake_keyboard, fake_pyperclip = _stub_keyboard_and_pyperclip
    fake_pyperclip.paste.return_value = "hello"
    from paste_text import paste

    paste("hello")

    fake_pyperclip.copy.assert_called_once_with("hello")
    fake_keyboard.press_and_release.assert_called_once_with("ctrl+v")
