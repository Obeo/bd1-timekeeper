# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bd1.report_window import ReportView
from bd1.tray import TrayApp


class TrayAppReportWindowTest(unittest.TestCase):
    def test_repeated_report_action_focuses_existing_window(self) -> None:
        tray = _tray_without_platform_icon()

        with patch("bd1.tray.ReportWindow") as report_window_type:
            report_window = report_window_type.return_value
            report_window.is_alive.return_value = True

            tray._show_report_window(ReportView.DAY)
            tray._show_report_window(ReportView.DAY)

        report_window_type.assert_called_once()
        report_window.start.assert_called_once_with()
        report_window.focus.assert_called_once_with()

    def test_only_current_report_window_can_clear_reference(self) -> None:
        tray = _tray_without_platform_icon()
        current_window = Mock()
        tray._report_window = current_window

        tray._report_window_closed(Mock())
        self.assertIs(current_window, tray._report_window)

        tray._report_window_closed(current_window)
        self.assertIsNone(tray._report_window)


def _tray_without_platform_icon() -> TrayApp:
    tray = TrayApp.__new__(TrayApp)
    tray.store = SimpleNamespace(path=Path("bd1.db"))
    tray._report_window = None
    tray._report_window_lock = threading.Lock()
    return tray


if __name__ == "__main__":
    unittest.main()
