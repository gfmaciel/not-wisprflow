from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Iterable, Optional, Protocol


@dataclass(frozen=True)
class FocusIdentity:
    """Privacy-safe identity for a focused UI Automation element.

    Runtime IDs are intentionally combined with the owning process ID. We do
    not capture the element name, value, text, URL, or other user content.
    Window identity alone is never considered a safe match because multiple
    browser tabs and editors can share one top-level window.
    """

    runtime_id: tuple[int, ...]
    process_id: int
    top_level_runtime_id: tuple[int, ...] = ()
    top_level_handle: int = 0
    control_type: str = ""
    class_name: str = ""
    automation_id: str = ""
    framework_id: str = ""

    def matches(self, other: Optional[FocusIdentity]) -> bool:
        return bool(
            other
            and self.runtime_id
            and other.runtime_id
            and self.process_id == other.process_id
            and self.runtime_id == other.runtime_id
        )


class FocusProvider(Protocol):
    def capture(self) -> Optional[FocusIdentity]: ...


class WindowsUIAFocusProvider:
    """Capture focused controls using Windows UI Automation.

    `uiautomation` is imported lazily so the core guard remains importable and
    unit-testable on non-Windows systems. Every capture initializes UI
    Automation in the calling thread because paste operations can run from the
    mono executor or the collector thread.
    """

    def __init__(self, auto_module=None) -> None:
        self._auto_module = auto_module

    def _auto(self):
        if self._auto_module is None:
            import uiautomation as auto  # type: ignore[import-not-found]

            self._auto_module = auto
        return self._auto_module

    def capture(self) -> Optional[FocusIdentity]:
        try:
            auto = self._auto()
            with auto.UIAutomationInitializerInThread():
                control = auto.GetFocusedControl()
                if control is None or not control.HasKeyboardFocus:
                    return None
                if bool(control.IsPassword):
                    return None

                runtime_id = tuple(int(value) for value in (control.GetRuntimeId() or ()))
                if not runtime_id:
                    return None

                top_runtime_id: tuple[int, ...] = ()
                top_handle = 0
                try:
                    top = control.GetTopLevelControl()
                    if top is not None:
                        top_runtime_id = tuple(
                            int(value) for value in (top.GetRuntimeId() or ())
                        )
                        top_handle = int(top.NativeWindowHandle or 0)
                except Exception:
                    # Top-level metadata is diagnostic only; never weaken the
                    # strong focused-element match if it is unavailable.
                    pass

                return FocusIdentity(
                    runtime_id=runtime_id,
                    process_id=int(control.ProcessId or 0),
                    top_level_runtime_id=top_runtime_id,
                    top_level_handle=top_handle,
                    control_type=str(control.ControlTypeName or ""),
                    class_name=str(control.ClassName or ""),
                    automation_id=str(control.AutomationId or ""),
                    framework_id=str(control.FrameworkId or ""),
                )
        except Exception:
            # Safety rule: inability to prove the destination is the target is
            # equivalent to a mismatch. The caller buffers instead of typing.
            return None


class PasteTargetGuard:
    """Route text only to the focused element captured at session start.

    The guard is deliberately fail-closed:
    - strong target match -> paste/type now;
    - mismatch or UI Automation uncertainty -> buffer;
    - finish while away -> copy only the unpasted buffer to the clipboard and
      send no keystrokes.

    The class is thread-safe because recording starts, mono processing, and
    final collection can happen on different threads.
    """

    def __init__(
        self,
        focus_provider: FocusProvider,
        paste_fn: Callable[[str], None],
        type_fn: Callable[[str], None],
        clipboard_fn: Callable[[str], None],
        *,
        on_recovery: Optional[Callable[[], None]] = None,
    ) -> None:
        self._focus_provider = focus_provider
        self._paste_fn = paste_fn
        self._type_fn = type_fn
        self._clipboard_fn = clipboard_fn
        self._on_recovery = on_recovery or (lambda: None)
        self._lock = threading.RLock()
        self._target: Optional[FocusIdentity] = None
        self._buffer = ""
        self._active = False

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def buffered_text(self) -> str:
        with self._lock:
            return self._buffer

    @property
    def target(self) -> Optional[FocusIdentity]:
        with self._lock:
            return self._target

    def begin(self) -> bool:
        """Start a guarded paste session and capture the current target."""
        with self._lock:
            self._buffer = ""
            self._target = self._safe_capture()
            self._active = True
            return self._target is not None

    def cancel(self) -> None:
        """Reset guard state without emitting text."""
        with self._lock:
            self._buffer = ""
            self._target = None
            self._active = False

    def _safe_capture(self) -> Optional[FocusIdentity]:
        try:
            return self._focus_provider.capture()
        except Exception:
            return None

    def _target_is_focused(self) -> bool:
        target = self._target
        if target is None:
            return False
        return target.matches(self._safe_capture())

    def submit(self, text: str) -> bool:
        """Paste a complete text fragment now or buffer it for the target.

        Returns True only when the fragment (and any older buffered text) was
        sent to the captured target during this call.
        """
        if not text:
            return False

        with self._lock:
            if not self._active:
                self._paste_fn(text)
                return True

            if not self._target_is_focused():
                self._buffer += text
                return False

            combined = self._buffer + text
            self._buffer = ""
            try:
                self._paste_fn(combined)
                return True
            except Exception:
                self._buffer = combined + self._buffer
                return False

    def stream(self, deltas: Iterable[str]) -> str:
        """Safely route streaming deltas while preserving legacy semantics.

        A stream error before any delta propagates so the caller can fall back.
        Once any output has been handled (typed or buffered), later stream
        errors are swallowed to prevent duplicate fallback text.
        """
        iterator = iter(deltas)
        handled: list[str] = []
        while True:
            try:
                delta = next(iterator)
            except StopIteration:
                break
            except Exception:
                if not handled:
                    raise
                print("[not-wisprflow] Streaming cleanup truncated mid-output.")
                break

            if not delta:
                continue

            with self._lock:
                if not self._active:
                    self._type_fn(delta)
                elif not self._target_is_focused():
                    self._buffer += delta
                elif self._buffer:
                    combined = self._buffer + delta
                    self._buffer = ""
                    try:
                        self._paste_fn(combined)
                    except Exception:
                        self._buffer = combined + self._buffer
                else:
                    try:
                        self._type_fn(delta)
                    except Exception:
                        self._buffer += delta

            handled.append(delta)

        return "".join(handled)

    def finish(self) -> bool:
        """Finish the session, safely delivering or recovering pending text.

        Returns True when buffered text was pasted into the original target.
        If the target is not strongly focused, pending text is copied to the
        clipboard without any keyboard input and False is returned.
        """
        with self._lock:
            if not self._active:
                return False

            pending = self._buffer
            self._buffer = ""
            pasted = False
            try:
                if not pending:
                    return False

                if self._target_is_focused():
                    try:
                        self._paste_fn(pending)
                        pasted = True
                        return True
                    except Exception:
                        pass

                self._clipboard_fn(pending)
                self._on_recovery()
                return False
            finally:
                self._target = None
                self._active = False
                if pasted:
                    self._buffer = ""
