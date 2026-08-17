import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows UI Automation smoke test")
def test_uiautomation_thread_initializer_context_manager():
    import uiautomation as auto

    assert callable(auto.GetFocusedControl)
    assert callable(auto.UIAutomationInitializerInThread)

    # UI Automation must be initialized in every thread that uses it. Exercise
    # the real package/context manager on the Windows runner without depending
    # on an interactive desktop or a specific focused control.
    with auto.UIAutomationInitializerInThread():
        pass
