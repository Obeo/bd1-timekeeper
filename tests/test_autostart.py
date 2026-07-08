from __future__ import annotations

import os
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
