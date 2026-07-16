# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest
from unittest.mock import patch

from bd1.processes import is_any_process_running


class ProcessDetectionTest(unittest.TestCase):
    def test_detects_running_process_by_name_case_insensitively(self) -> None:
        processes = [
            FakeProcess("explorer.exe"),
            FakeProcess("AomHost64.exe"),
        ]

        with patch("bd1.processes.psutil.process_iter", return_value=processes):
            running = is_any_process_running(("aomhost64.exe",))

        self.assertTrue(running)

    def test_returns_false_when_no_process_name_matches(self) -> None:
        with patch("bd1.processes.psutil.process_iter", return_value=[FakeProcess("Zoom.exe")]):
            running = is_any_process_running(("aomhost64.exe",))

        self.assertFalse(running)


class FakeProcess:
    def __init__(self, name: str) -> None:
        self.info = {"name": name}


if __name__ == "__main__":
    unittest.main()
