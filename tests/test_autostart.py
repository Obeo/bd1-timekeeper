# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bd1.autostart import AutostartManager


class AutostartManagerTest(unittest.TestCase):
    def test_linux_enable_status_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            manager = AutostartManager(["/opt/bd1/bd1", "--no-activity-monitor"], "linux")

            self.assertFalse(manager.status().enabled)
            enabled = manager.enable()
            self.assertTrue(enabled.enabled)
            self.assertTrue(manager.status().enabled)

            content = enabled.location.read_text(encoding="utf-8")
            self.assertIn("Type=Application", content)
            self.assertIn("Exec=/opt/bd1/bd1 --no-activity-monitor", content)

            disabled = manager.disable()
            self.assertFalse(disabled.enabled)
            self.assertFalse(manager.status().enabled)

    def test_unsupported_platform_reports_status(self) -> None:
        status = AutostartManager(["bd1"], "plan9").status()

        self.assertFalse(status.supported)
        self.assertFalse(status.enabled)
        self.assertIn("Unsupported platform", status.detail)

    def test_windows_refresh_replaces_an_existing_command(self) -> None:
        registry = _FakeRegistry({"BD-1": '"C:\\old location\\BD-1.exe"'})
        winreg = SimpleNamespace(
            HKEY_CURRENT_USER="current-user",
            KEY_SET_VALUE=2,
            REG_SZ=1,
            OpenKey=registry.open_key,
            CreateKey=registry.create_key,
            QueryValueEx=registry.query_value,
            SetValueEx=registry.set_value,
            DeleteValue=registry.delete_value,
        )

        with patch.dict(sys.modules, {"winreg": winreg}):
            status = AutostartManager([r"D:\\BD-1\\BD-1.exe"], "windows").refresh_if_enabled()

        self.assertTrue(status.enabled)
        self.assertEqual(registry.values["BD-1"], r"D:\\BD-1\\BD-1.exe")


class _FakeRegistry:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def open_key(self, *_: object) -> _FakeRegistry:
        return self

    def create_key(self, *_: object) -> _FakeRegistry:
        return self

    def query_value(self, _: object, name: str) -> tuple[str, int]:
        return self.values[name], 1

    def set_value(self, _: object, name: str, __: int, ___: int, value: str) -> None:
        self.values[name] = value

    def delete_value(self, _: object, name: str) -> None:
        del self.values[name]

    def __enter__(self) -> _FakeRegistry:
        return self

    def __exit__(self, *_: object) -> None:
        return None


if __name__ == "__main__":
    unittest.main()
