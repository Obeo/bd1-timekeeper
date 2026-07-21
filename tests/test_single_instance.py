# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bd1.single_instance import SingleInstanceLock


class SingleInstanceLockTest(unittest.TestCase):
    def test_file_lock_prevents_duplicate_non_windows_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bd1.lock"
            first = SingleInstanceLock(lock_path=path)
            second = SingleInstanceLock(lock_path=path)

            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
            finally:
                first.release()
                second.release()

    def test_windows_mutex_creation_failure_fails_closed(self) -> None:
        kernel32 = Mock()
        kernel32.CreateMutexW.return_value = 0
        kernel32.GetLastError.return_value = 5

        with (
            patch("bd1.single_instance.sys.platform", "win32"),
            patch(
                "bd1.single_instance.ctypes.windll",
                SimpleNamespace(kernel32=kernel32),
                create=True,
            ),
            patch("bd1.single_instance._configure_kernel32"),
            self.assertLogs("bd1.single_instance", level="ERROR") as logs,
        ):
            acquired = SingleInstanceLock().acquire()

        self.assertFalse(acquired)
        self.assertIn("Failed to create single-instance mutex", logs.output[0])
        self.assertIn("GetLastError=5", logs.output[0])
        kernel32.CloseHandle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
