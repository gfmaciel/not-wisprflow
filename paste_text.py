import time
import pyperclip
import keyboard


def paste(text: str) -> None:
    """Write text to clipboard and paste it at the active cursor."""
    pyperclip.copy(text)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            if pyperclip.paste() == text:
                break
        except Exception:
            pass
        time.sleep(0.01)

    time.sleep(0.05)
    keyboard.press_and_release("ctrl+v")
