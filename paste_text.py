"""Paste into whichever field is active when processing finishes."""
import time
from typing import Iterable
import keyboard
import pyperclip


def paste(text: str) -> None:
    if not text:
        return
    pyperclip.copy(text)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            if pyperclip.paste() == text:
                break
        except Exception:
            pass
        time.sleep(0.005)
    keyboard.press_and_release("ctrl+v")


def paste_stream(deltas: Iterable[str]) -> str:
    """Compatibility helper for consumers that want typed deltas."""
    iterator = iter(deltas)
    written: list[str] = []
    while True:
        try:
            delta = next(iterator)
        except StopIteration:
            break
        except Exception:
            if not written:
                raise
            print("[not-wisprflow] Streaming cleanup truncated mid-output.")
            break
        if delta:
            keyboard.write(delta)
            written.append(delta)
    return "".join(written)
