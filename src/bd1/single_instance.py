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
import os
import sys
from ctypes import wintypes
from pathlib import Path

if sys.platform != "win32":
    import fcntl

MUTEX_NAME = "Local\\BD1TimekeeperSingleInstance"
ERROR_ALREADY_EXISTS = 183
LOGGER = logging.getLogger(__name__)


class SingleInstanceLock:
    def __init__(self, name: str = MUTEX_NAME, lock_path: Path | None = None) -> None:
        self.name = name
        self.lock_path = lock_path or Path.home() / ".cache" / "bd1" / f"{name}.lock"
        self._handle: int | None = None
        self._file: object | None = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return self._acquire_file_lock()
        if self._handle is not None:
            return True

        kernel32 = ctypes.windll.kernel32
        _configure_kernel32(kernel32)
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            LOGGER.error(
                "Failed to create single-instance mutex %r; GetLastError=%s",
                self.name,
                kernel32.GetLastError(),
            )
            return False

        self._handle = handle
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            self.release()
            return False
        return True

    def release(self) -> None:
        if self._file is not None:
            try:
                fcntl.flock(self._file, fcntl.LOCK_UN)
            finally:
                self._file.close()
                self._file = None
        if self._handle is None:
            return
        ctypes.windll.kernel32.CloseHandle(self._handle)
        self._handle = None

    def _acquire_file_lock(self) -> bool:
        if self._file is not None:
            return True
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.lock_path.open("w", encoding="utf-8")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            return False
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        self._file = lock_file
        return True


def _configure_kernel32(kernel32: ctypes.WinDLL) -> None:
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
