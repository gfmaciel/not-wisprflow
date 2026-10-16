"""Non-suppressing scan-code hotkey for use across foreground applications."""
from __future__ import annotations

import threading
import time
from typing import Callable

import keyboard


class GlobalHotkey:
    """Use one low-level hook rather than an async hotkey + unrelated release hook."""

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[float], None],
        *,
        keyboard_module=None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._keyboard = keyboard_module if keyboard_module is not None else keyboard
        steps = self._keyboard.parse_hotkey_combinations(hotkey)
        if len(steps) != 1 or not steps[0]:
            raise ValueError("HOTKEY must be a single combination, e.g. alt+\\")
        self._combinations = [frozenset(c) for c in steps[0]]
        trigger = hotkey.rsplit("+", 1)[-1]
        self._trigger_codes = set(self._keyboard.key_to_scan_codes(trigger))
        if not self._trigger_codes:
            raise ValueError(f"Unknown HOTKEY trigger: {trigger!r}")
        self._on_press, self._on_release = on_press, on_release
        self._clock = clock
        self._lock = threading.RLock()
        self._pressed: set[int] = set()
        self._armed: int | None = None
        self._press_at = 0.0
        self._hook = None

    def start(self) -> None:
        with self._lock:
            if self._hook is None:
                self._hook = self._keyboard.hook(self._handle_event, suppress=False)

    def stop(self) -> None:
        with self._lock:
            if self._hook is not None:
                self._keyboard.unhook(self._hook)
                self._hook = None
            self._pressed.clear()
            self._armed = None

    def _handle_event(self, event) -> None:
        action = None
        duration = 0.0
        with self._lock:
            code = event.scan_code
            if event.event_type == "down":
                fresh = code not in self._pressed
                self._pressed.add(code)
                if (
                    fresh
                    and self._armed is None
                    and code in self._trigger_codes
                    and any(combo <= self._pressed for combo in self._combinations)
                ):
                    self._armed = code
                    self._press_at = self._clock()
                    action = self._on_press
            elif event.event_type == "up":
                if self._armed == code:
                    duration = max(0.0, self._clock() - self._press_at)
                    self._armed = None
                    action = self._on_release
                self._pressed.discard(code)
        if action is self._on_release:
            action(duration)
        elif action is not None:
            action()
