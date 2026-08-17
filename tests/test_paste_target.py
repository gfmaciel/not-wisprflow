from __future__ import annotations

from contextlib import nullcontext

import pytest

from paste_target import FocusIdentity, PasteTargetGuard, WindowsUIAFocusProvider


A = FocusIdentity(
    runtime_id=(42, 1),
    process_id=100,
    top_level_runtime_id=(7,),
    top_level_handle=900,
)
B_SAME_BROWSER_WINDOW = FocusIdentity(
    runtime_id=(42, 2),
    process_id=100,
    top_level_runtime_id=(7,),
    top_level_handle=900,
)
C_OTHER_APP = FocusIdentity(
    runtime_id=(55, 1),
    process_id=200,
    top_level_runtime_id=(8,),
    top_level_handle=901,
)


class FakeFocusProvider:
    def __init__(self, current=A):
        self.current = current
        self.raise_error = False

    def capture(self):
        if self.raise_error:
            raise RuntimeError("UIA unavailable")
        return self.current


def make_guard(provider=None):
    provider = provider or FakeFocusProvider()
    pasted: list[str] = []
    typed: list[str] = []
    clipboard: list[str] = []
    recovery: list[bool] = []
    guard = PasteTargetGuard(
        provider,
        pasted.append,
        typed.append,
        clipboard.append,
        on_recovery=lambda: recovery.append(True),
    )
    return guard, provider, pasted, typed, clipboard, recovery


def test_focus_match_requires_same_runtime_id_not_just_same_window():
    assert A.matches(A)
    assert not A.matches(B_SAME_BROWSER_WINDOW)
    assert not A.matches(C_OTHER_APP)
    assert not A.matches(None)


def test_matching_target_pastes_immediately():
    guard, _, pasted, _, clipboard, _ = make_guard()
    assert guard.begin()

    assert guard.submit("hello ") is True

    assert pasted == ["hello "]
    assert clipboard == []
    assert guard.buffered_text == ""


def test_other_control_in_same_browser_window_buffers_instead_of_pasting():
    guard, provider, pasted, _, _, _ = make_guard()
    assert guard.begin()
    provider.current = B_SAME_BROWSER_WINDOW

    assert guard.submit("do not mispaste ") is False

    assert pasted == []
    assert guard.buffered_text == "do not mispaste "


def test_returning_to_original_target_flushes_buffer_in_order():
    guard, provider, pasted, _, _, _ = make_guard()
    guard.begin()
    provider.current = C_OTHER_APP
    guard.submit("first ")
    guard.submit("second ")

    provider.current = A
    assert guard.submit("third ") is True

    assert pasted == ["first second third "]
    assert guard.buffered_text == ""


def test_finish_while_away_copies_only_pending_text_without_keystrokes():
    guard, provider, pasted, typed, clipboard, recovery = make_guard()
    guard.begin()
    provider.current = C_OTHER_APP
    guard.submit("pending text")

    assert guard.finish() is False

    assert pasted == []
    assert typed == []
    assert clipboard == ["pending text"]
    assert recovery == [True]
    assert not guard.active


def test_finish_after_return_pastes_pending_text():
    guard, provider, pasted, _, clipboard, _ = make_guard()
    guard.begin()
    provider.current = C_OTHER_APP
    guard.submit("pending")
    provider.current = A

    assert guard.finish() is True

    assert pasted == ["pending"]
    assert clipboard == []
    assert not guard.active


def test_capture_failure_is_fail_closed_and_recovers_to_clipboard():
    provider = FakeFocusProvider(None)
    guard, _, pasted, typed, clipboard, _ = make_guard(provider)

    assert guard.begin() is False
    guard.submit("safe")
    guard.finish()

    assert pasted == []
    assert typed == []
    assert clipboard == ["safe"]


def test_runtime_focus_error_is_fail_closed():
    guard, provider, pasted, _, clipboard, _ = make_guard()
    guard.begin()
    provider.raise_error = True

    guard.submit("safe")
    guard.finish()

    assert pasted == []
    assert clipboard == ["safe"]


def test_stream_types_while_focused_then_buffers_after_focus_change():
    guard, provider, pasted, typed, clipboard, _ = make_guard()
    guard.begin()

    def deltas():
        provider.current = A
        yield "hello "
        provider.current = C_OTHER_APP
        yield "world"

    handled = guard.stream(deltas())
    guard.finish()

    assert handled == "hello world"
    assert typed == ["hello "]
    assert pasted == []
    assert clipboard == ["world"]


def test_stream_flushes_away_buffer_when_original_target_returns():
    guard, provider, pasted, typed, clipboard, _ = make_guard()
    guard.begin()

    def deltas():
        provider.current = C_OTHER_APP
        yield "buffered "
        provider.current = A
        yield "returned"
        yield "!"

    handled = guard.stream(deltas())
    guard.finish()

    assert handled == "buffered returned!"
    assert pasted == ["buffered returned"]
    assert typed == ["!"]
    assert clipboard == []


def test_stream_propagates_error_before_any_output():
    guard, _, _, _, _, _ = make_guard()
    guard.begin()

    def broken():
        raise RuntimeError("network down")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="network down"):
        guard.stream(broken())


def test_stream_swallows_error_after_handled_output(capsys):
    guard, _, _, typed, _, _ = make_guard()
    guard.begin()

    def partial():
        yield "hello"
        raise RuntimeError("connection reset")

    assert guard.stream(partial()) == "hello"
    assert typed == ["hello"]
    assert "truncated" in capsys.readouterr().out.lower()


class FakeControl:
    HasKeyboardFocus = True
    IsPassword = False
    ProcessId = 321
    ControlTypeName = "EditControl"
    ClassName = "Chrome_RenderWidgetHostHWND"
    AutomationId = "editor"
    FrameworkId = "Chrome"
    NativeWindowHandle = 0

    def __init__(self, runtime_id=(9, 8, 7), top=None):
        self._runtime_id = runtime_id
        self._top = top

    def GetRuntimeId(self):
        return self._runtime_id

    def GetTopLevelControl(self):
        return self._top


class FakeAuto:
    def __init__(self, control):
        self.control = control
        self.initialized = 0

    def UIAutomationInitializerInThread(self):
        parent = self

        class Initializer:
            def __enter__(self):
                parent.initialized += 1
                return self

            def __exit__(self, exc_type, exc, tb):
                parent.initialized -= 1

        return Initializer()

    def GetFocusedControl(self):
        return self.control


def test_windows_provider_uses_thread_initializer_and_returns_identity():
    top = FakeControl(runtime_id=(1, 2))
    top.NativeWindowHandle = 1234
    control = FakeControl(top=top)
    auto = FakeAuto(control)
    provider = WindowsUIAFocusProvider(auto)

    identity = provider.capture()

    assert identity is not None
    assert identity.runtime_id == (9, 8, 7)
    assert identity.process_id == 321
    assert identity.top_level_runtime_id == (1, 2)
    assert identity.top_level_handle == 1234
    assert auto.initialized == 0


def test_windows_provider_rejects_password_field():
    control = FakeControl()
    control.IsPassword = True
    provider = WindowsUIAFocusProvider(FakeAuto(control))

    assert provider.capture() is None
