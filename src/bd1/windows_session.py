# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes

LOGGER = logging.getLogger(__name__)

WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_DESTROY = 0x0002


SessionEndCallback = Callable[[str], None]
WNDPROC = ctypes.WINFUNCTYPE(
    wintypes.LPARAM,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class WindowsSessionEndListener:
    def __init__(self, callback: SessionEndCallback) -> None:
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._notified = threading.Event()
        self._hwnd: int | None = None
        self._wndproc: WNDPROC | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="bd1-windows-session", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)

    def stop(self) -> None:
        if self._hwnd is not None:
            ctypes.windll.user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        _configure_win32_api(user32, kernel32)
        hinstance = kernel32.GetModuleHandleW(None)
        class_name = f"BD1WindowsSessionEndListener{threading.get_ident()}"

        self._wndproc = WNDPROC(self._window_proc)

        window_class = WNDCLASS()
        window_class.lpfnWndProc = self._wndproc
        window_class.hInstance = hinstance
        window_class.lpszClassName = class_name

        atom = user32.RegisterClassW(ctypes.byref(window_class))
        if atom == 0:
            LOGGER.warning("Could not register Windows session listener window class")
            self._ready.set()
            return

        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            class_name,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            hinstance,
            None,
        )
        if hwnd == 0:
            LOGGER.warning("Could not create Windows session listener window")
            self._ready.set()
            return

        self._hwnd = hwnd
        self._ready.set()
        LOGGER.info("Windows session listener started")

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

        self._hwnd = None
        self._stopped.set()
        LOGGER.info("Windows session listener stopped")

    def _window_proc(
        self,
        hwnd: wintypes.HWND,
        message: int,
        wparam: wintypes.WPARAM,
        lparam: wintypes.LPARAM,
    ) -> int:
        user32 = ctypes.windll.user32
        if message == WM_QUERYENDSESSION:
            self._notify_once("query_end_session")
            return 1
        if message == WM_ENDSESSION:
            if bool(wparam):
                self._notify_once("end_session")
            return 0
        if message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _notify_once(self, phase: str) -> None:
        if self._notified.is_set():
            return
        self._notified.set()
        try:
            LOGGER.info("Windows session ending: phase=%s", phase)
            self.callback(phase)
        except Exception:
            LOGGER.exception("Windows session end callback failed")


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


def _configure_win32_api(user32: ctypes.WinDLL, kernel32: ctypes.WinDLL) -> None:
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
    user32.RegisterClassW.restype = wintypes.ATOM

    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND

    user32.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.DefWindowProcW.restype = wintypes.LPARAM

    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL

    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.PostMessageW.restype = wintypes.BOOL

    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None

    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = wintypes.BOOL

    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL

    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = wintypes.LPARAM
