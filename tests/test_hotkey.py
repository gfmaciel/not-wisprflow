from types import SimpleNamespace

import pytest

from hotkey import GlobalHotkey


class FakeKeyboard:
    def __init__(self):
        self.callback = None
        self.installs = []
        self.removals = []

    def parse_hotkey_combinations(self, shortcut):
        if shortcut == "alt+\\":
            return (((56, 43), (3640, 43)),)
        return ((), ())

    def key_to_scan_codes(self, key):
        return (43,) if key == "\\" else ()

    def hook(self, callback, suppress=False):
        self.callback = callback
        self.installs.append(suppress)
        return callback

    def unhook(self, handle):
        self.removals.append(handle)

    def send(self, code, kind="down", app="other-window"):
        # The callback is application-independent: the active target is irrelevant.
        self.callback(SimpleNamespace(scan_code=code, event_type=kind, app=app))


def test_hotkey_works_while_typing_elsewhere_and_never_suppresses_keys():
    keyboard = FakeKeyboard()
    clock = [10.0]
    events = []
    listener = GlobalHotkey(
        "alt+\\", lambda: events.append("start"),
        lambda duration: events.append(("end", duration)),
        keyboard_module=keyboard, clock=lambda: clock[0],
    )
    listener.start()
    listener.start()
    assert keyboard.installs == [False]  # no duplicate listeners, no key suppression
    keyboard.send(30)  # ordinary typing
    keyboard.send(30, "up")
    keyboard.send(43)  # backslash by itself is NOT the hotkey
    keyboard.send(43, "up")
    assert events == []
    keyboard.send(56)  # alt in a different application
    keyboard.send(43)  # backslash while alt is held
    keyboard.send(43)  # auto-repeat must not trigger twice
    assert events == ["start"]
    keyboard.send(56, "up")  # modifier released before trigger
    clock[0] = 10.7
    keyboard.send(43, "up")
    assert events[1][0] == "end"
    assert events[1][1] == pytest.approx(0.7)
    listener.stop()
    assert keyboard.removals == [keyboard.callback]


def test_hotkey_can_rearm_after_release_without_extra_listeners():
    keyboard = FakeKeyboard()
    calls = []
    listener = GlobalHotkey(
        "alt+\\", lambda: calls.append("press"),
        lambda _: calls.append("release"), keyboard_module=keyboard,
    )
    listener.start()
    for _ in range(2):
        keyboard.send(56)
        keyboard.send(43)
        keyboard.send(43, "up")
        keyboard.send(56, "up")
    assert calls == ["press", "release", "press", "release"]
    listener.stop()
    listener.stop()
    assert len(keyboard.removals) == 1


def test_invalid_multistep_hotkey_fails_before_installing_hook():
    with pytest.raises(ValueError, match="single combination"):
        GlobalHotkey("alt+\\, a", lambda: None, lambda _: None,
                     keyboard_module=FakeKeyboard())
