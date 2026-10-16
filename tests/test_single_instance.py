from unittest.mock import Mock, patch

from single_instance import SingleInstance


class FakeFunction:
    def __init__(self, result):
        self.result = result
        self.argtypes = None
        self.restype = None
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class FakeKernel:
    def __init__(self):
        self.CreateMutexW = FakeFunction(12345)
        self.CloseHandle = FakeFunction(True)


def test_windows_mutex_refuses_second_process_and_closes_duplicate_handle():
    kernel = FakeKernel()
    with (
        patch("single_instance.sys.platform", "win32"),
        patch("single_instance.ctypes.WinDLL", return_value=kernel, create=True),
        patch("single_instance.ctypes.get_last_error", return_value=183, create=True),
    ):
        guard = SingleInstance()
        assert guard.acquire() is False
        assert len(kernel.CloseHandle.calls) == 1
        assert kernel.CloseHandle.calls[0] == (12345,)
        assert kernel.CloseHandle.argtypes is not None


def test_windows_mutex_keeps_one_handle_and_releases_on_close():
    kernel = FakeKernel()
    with (
        patch("single_instance.sys.platform", "win32"),
        patch("single_instance.ctypes.WinDLL", return_value=kernel, create=True),
        patch("single_instance.ctypes.get_last_error", return_value=0, create=True),
    ):
        guard = SingleInstance()
        assert guard.acquire() is True
        assert guard.acquire() is True
        assert len(kernel.CreateMutexW.calls) == 1
        guard.close()
        guard.close()
        assert kernel.CloseHandle.calls == [(12345,)]
