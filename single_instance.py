"""Named Windows mutex prevents two app processes from registering the shortcut."""
from __future__ import annotations

import ctypes
import sys

ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    def __init__(self) -> None:
        self._kernel = None
        self._handle = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        if sys.platform != "win32":
            return True
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
        kernel.CloseHandle.restype = ctypes.c_int
        handle = kernel.CreateMutexW(None, False, "Local\\not-wisprflow")
        if not handle:
            raise OSError(ctypes.get_last_error(), "Cannot create app mutex")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel.CloseHandle(handle)
            return False
        self._kernel, self._handle = kernel, handle
        return True

    def close(self) -> None:
        if self._handle is not None:
            self._kernel.CloseHandle(self._handle)
            self._handle = None
