"""Narrow native adapters for content-free local input-idle duration."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys

from time_tracker.application.idle import IdleDetector


def create_idle_detector() -> IdleDetector | None:
    """Return the supported adapter for this interactive platform session."""
    try:
        if sys.platform == "darwin":
            return MacOSIdleDetector()
        if sys.platform == "win32":
            return WindowsIdleDetector()
        if sys.platform.startswith("linux") and os.environ.get("DISPLAY"):
            return X11IdleDetector()
    except AttributeError, OSError:
        return None
    return None


class MacOSIdleDetector:
    """Read aggregate input-idle duration from Core Graphics."""

    def __init__(self) -> None:
        library = ctypes.CDLL(
            "/System/Library/Frameworks/ApplicationServices.framework/"
            "ApplicationServices"
        )
        function = library.CGEventSourceSecondsSinceLastEventType
        function.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        function.restype = ctypes.c_double
        self._library = library
        self._function = function

    def idle_seconds(self) -> float:
        """Return seconds since any combined-session input event."""
        return float(self._function(0, 0xFFFFFFFF))


class WindowsIdleDetector:
    """Read aggregate input-idle duration from Win32 GetLastInputInfo."""

    class _LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint32), ("dwTime", ctypes.c_uint32)]

    def __init__(self) -> None:
        win_dll = getattr(ctypes, "WinDLL", None)
        if win_dll is None:
            raise OSError("Win32 libraries are unavailable")
        self._user32 = win_dll("user32", use_last_error=True)
        self._kernel32 = win_dll("kernel32", use_last_error=True)
        self._user32.GetLastInputInfo.argtypes = [ctypes.POINTER(self._LastInputInfo)]
        self._user32.GetLastInputInfo.restype = ctypes.c_bool
        self._kernel32.GetTickCount.argtypes = []
        self._kernel32.GetTickCount.restype = ctypes.c_uint32

    def idle_seconds(self) -> float:
        """Return seconds since input, handling the 32-bit tick counter wrap."""
        info = self._LastInputInfo(ctypes.sizeof(self._LastInputInfo), 0)
        if not self._user32.GetLastInputInfo(ctypes.byref(info)):
            raise OSError("GetLastInputInfo failed")
        now = int(self._kernel32.GetTickCount())
        milliseconds = (now - int(info.dwTime)) & 0xFFFFFFFF
        return milliseconds / 1000.0


class _XScreenSaverInfo(ctypes.Structure):
    _fields_ = [
        ("window", ctypes.c_ulong),
        ("state", ctypes.c_int),
        ("kind", ctypes.c_int),
        ("til_or_since", ctypes.c_ulong),
        ("idle", ctypes.c_ulong),
        ("event_mask", ctypes.c_ulong),
    ]


class X11IdleDetector:
    """Read aggregate input-idle duration from the XScreenSaver extension."""

    def __init__(self) -> None:
        x11_name = ctypes.util.find_library("X11")
        xss_name = ctypes.util.find_library("Xss")
        if x11_name is None or xss_name is None:
            raise OSError("X11 idle-detection libraries are unavailable")
        self._x11 = ctypes.CDLL(x11_name)
        self._xss = ctypes.CDLL(xss_name)
        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self._x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self._x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self._x11.XCloseDisplay.restype = ctypes.c_int
        self._xss.XScreenSaverQueryInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(_XScreenSaverInfo),
        ]
        self._xss.XScreenSaverQueryInfo.restype = ctypes.c_int
        # Probe once so a display without the screen-saver extension, such as
        # WSLg's, reports detection as unavailable instead of appearing available
        # until its first failing poll.
        self.idle_seconds()

    def idle_seconds(self) -> float:
        """Return seconds since input for the current X11 display."""
        display = self._x11.XOpenDisplay(None)
        if not display:
            raise OSError("the X11 display is unavailable")
        try:
            root = self._x11.XDefaultRootWindow(display)
            info = _XScreenSaverInfo()
            if not self._xss.XScreenSaverQueryInfo(display, root, ctypes.byref(info)):
                raise OSError("XScreenSaverQueryInfo failed")
            return int(info.idle) / 1000.0
        finally:
            self._x11.XCloseDisplay(display)
