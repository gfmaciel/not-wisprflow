import time
import pyperclip
import keyboard


def paste(text: str) -> None:
    """Write text to clipboard and paste it at the active cursor."""
    pyperclip.copy(text)
    time.sleep(0.05)  # brief wait for clipboard to settle
    keyboard.send("ctrl+v")
