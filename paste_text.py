import time
from typing import Iterable
import pyperclip
import keyboard

from paste_target import PasteTargetGuard, WindowsUIAFocusProvider


def _paste_hotkey() -> None:
    keyboard.press_and_release("ctrl+v")


def _paste_now(text: str) -> None:
    """Legacy unguarded active-cursor paste used when safety is disabled."""
    pyperclip.copy(text)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            if pyperclip.paste() == text:
                break
        except Exception:
            pass
        time.sleep(0.005)

    _paste_hotkey()


def _type_now(text: str) -> None:
    keyboard.write(text)


def _recovery_notice() -> None:
    print(
        "[not-wisprflow] Paste target changed or could not be verified; "
        "pending text was copied to the clipboard without sending keystrokes."
    )


_guard = PasteTargetGuard(
    WindowsUIAFocusProvider(),
    clipboard_fn=pyperclip.copy,
    paste_hotkey_fn=_paste_hotkey,
    type_fn=_type_now,
    on_recovery=_recovery_notice,
)


def start_paste_session(*, enabled: bool = True) -> bool:
    """Capture the focused field as the destination for this recording.

    Returns True when a strong UI Automation target was captured. When the
    feature is disabled, the legacy active-cursor behavior is retained.
    """
    if not enabled:
        _guard.cancel()
        return False
    return _guard.begin()


def finish_paste_session() -> bool:
    """Safely finish a guarded session and recover any pending text."""
    try:
        return _guard.finish()
    except Exception as exc:
        # Do not let clipboard/UI Automation cleanup wedge the pipeline state.
        print(f"[not-wisprflow] Safe paste recovery failed: {exc}")
        _guard.cancel()
        return False


def paste(text: str) -> None:
    """Paste text, guarded to the recording's original target when active."""
    if _guard.active:
        _guard.submit(text)
    else:
        _paste_now(text)


def _paste_stream_now(deltas: Iterable[str]) -> str:
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
        _type_now(delta)
        written.append(delta)
    return "".join(written)


def paste_stream(deltas: Iterable[str]) -> str:
    """Route streaming deltas to the original recording target when guarded.

    The legacy behavior is preserved when no guarded recording session is
    active. During a guarded session, focus changes cause future deltas to be
    buffered instead of typed into the newly focused application.
    """
    if _guard.active:
        return _guard.stream(deltas)
    return _paste_stream_now(deltas)
