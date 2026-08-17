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
        if (
            other is None
            or not self.runtime_id
            or not other.runtime_id
            or self.process_id <= 0
            or other.process_id <= 0
            or self.process_id != other.process_id
            or self.runtime_id != other.runtime_id
        ):
            return False
        if (
            self.top_level_runtime_id
            and other.top_level_runtime_id
            and self.top_level_runtime_id != other.top_level_runtime_id
        ):
            return False
        if (
            self.top_level_handle
            and other.top_level_handle
            and self.top_level_handle != other.top_level_handle
        ):
            return False
        return True


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
                process_id = int(control.ProcessId or 0)
                if not runtime_id or process_id <= 0:
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
                    # Top-level metadata is additional evidence only. Missing
                    # metadata never permits a weaker window-only match.
                    pass

                return FocusIdentity(
                    runtime_id=runtime_id,
                    process_id=process_id,
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
    """Route output only to the UI element captured at recording start.

    The guard is fail-closed and thread-safe. Clipboard paste is split into
    prepare + hotkey phases so focus can be checked a second time after the
    clipboard is ready, immediately before Ctrl+V is emitted.
    """

    def __init__(
        self,
        focus_provider: FocusProvider,
        *,
        clipboard_fn: Callable[[str], None],
        paste_hotkey_fn: Callable[[], None],
        type_fn: Callable[[str], None],
        on_recovery: Optional[Callable[[], None]] = None,
    ) -> None:
        self._focus_provider = focus_provider
        self._clipboard_fn = clipboard_fn
        self._paste_hotkey_fn = paste_hotkey_fn
        self._type_fn = type_fn
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
        """Start a guarded session and capture the current focused element."""
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

    def _paste_to_verified_target(self, text: str) -> bool:
        """Paste only if focus matches both before and after clipboard prep."""
        if not self._target_is_focused():
            return False
        try:
            self._clipboard_fn(text)
        except Exception:
            return False
        # Clipboard preparation is not atomic with Ctrl+V. Recheck focus after
        # it so an Alt+Tab during that gap never intentionally receives a paste.
        if not self._target_is_focused():
            return False
        try:
            self._paste_hotkey_fn()
            return True
        except Exception:
            return False

    def _type_to_verified_target(self, text: str) -> bool:
        if not self._target_is_focused():
            return False
        try:
            self._type_fn(text)
            return True
        except Exception:
            return False

    def submit(self, text: str) -> bool:
        """Paste a complete fragment now, or buffer it on any uncertainty."""
        if not text:
            return False

        with self._lock:
            if not self._active:
                try:
                    self._clipboard_fn(text)
                    self._paste_hotkey_fn()
                    return True
                except Exception:
                    return False

            combined = self._buffer + text
            if self._paste_to_verified_target(combined):
                self._buffer = ""
                return True

            self._buffer = combined
            return False

    def stream(self, deltas: Iterable[str]) -> str:
        """Safely route streaming deltas while preserving fallback semantics.

        A stream error before any delta propagates so the caller can fall back.
        Once any output has been handled (typed or buffered), later errors are
        swallowed to avoid duplicate fallback output.
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
                    try:
                        self._type_fn(delta)
                    except Exception:
                        pass
                elif self._buffer:
                    combined = self._buffer + delta
                    if self._paste_to_verified_target(combined):
                        self._buffer = ""
                    else:
                        self._buffer = combined
                elif not self._type_to_verified_target(delta):
                    self._buffer += delta

            handled.append(delta)

        return "".join(handled)

    def finish(self) -> bool:
        """Deliver pending text to the target or recover it to clipboard only."""
        with self._lock:
            if not self._active:
                return False

            pending = self._buffer
            try:
                if not pending:
                    return False

                if self._paste_to_verified_target(pending):
                    self._buffer = ""
                    return True

                # `_paste_to_verified_target` may already have prepared the
                # clipboard before detecting a focus change. Copy once more so
                # recovery is deterministic, but never emit a key here.
                self._clipboard_fn(pending)
                self._on_recovery()
                return False
            finally:
                self._target = None
                self._buffer = ""
                self._active = False
