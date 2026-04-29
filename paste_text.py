import time
from typing import Iterable
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
        time.sleep(0.005)

    keyboard.press_and_release("ctrl+v")


def paste_stream(deltas: Iterable[str]) -> str:
    """Type deltas at the active cursor as they arrive.

    Returns the full text typed. If the underlying stream raises **before**
    any delta is yielded, the exception propagates so the caller can cleanly
    fall back to clipboard paste. If it raises **after** partial output, the
    error is swallowed (logged) and the partial text is returned — the
    caller must not then re-paste, or the user would see duplicate text.
    """
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
        if not delta:
            continue
        keyboard.write(delta)
        written.append(delta)
    return "".join(written)
