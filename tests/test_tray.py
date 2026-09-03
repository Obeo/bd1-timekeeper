# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bd1.report_window import ReportView
from bd1.storage import ObservationStore
from bd1.tray import TrayApp
from bd1.updates import AvailableUpdate


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


class TrayAppTest(unittest.TestCase):
    def test_exposes_mattermost_configuration_menu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                tray = TrayApp(
                    store,
                    lambda *_: None,
                    lambda: False,
                    lambda: False,
                    lambda: None,
                    lambda: None,
                )
                configure = next(item for item in tray.icon.menu.items if item.text == "Configurer")
            finally:
                store.close()

        self.assertIsNotNone(configure.submenu)
        self.assertEqual(
            ["Intégration Mattermost"],
            [item.text for item in configure.submenu.items],
        )

    def test_exposes_current_version_and_manual_update_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                tray = TrayApp(
                    store,
                    lambda *_: None,
                    lambda: False,
                    lambda: False,
                    lambda: None,
                    lambda: None,
                )
                menu = tray.icon.menu
            finally:
                store.close()

        labels = [item.text for item in menu.items]
        self.assertIn("Version : BD-1 v0.2.0", labels)
        self.assertIn("Rechercher les mises à jour", labels)

    def test_exposes_available_update_and_opens_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                tray = TrayApp(
                    store,
                    lambda *_: None,
                    lambda: False,
                    lambda: False,
                    lambda: None,
                    lambda: None,
                )
                tray.available_update = AvailableUpdate(
                    "0.2.0",
                    "https://github.com/Obeo/bd1-timekeeper/releases/download/v0.2.0/bd1-linux-x86_64.tar.gz",
                )

                menu = tray._menu()
                with patch("bd1.tray.webbrowser.open") as open_browser:
                    tray._download_update()
            finally:
                store.close()

        self.assertIn("Télécharger BD-1 v0.2.0", [item.text for item in menu.items])
        open_browser.assert_called_once_with(tray.available_update.download_url)

    @patch("bd1.tray.find_update")
    def test_update_check_refreshes_menu_and_notifies(self, find_update) -> None:
        find_update.return_value = AvailableUpdate(
            "0.2.0",
            "https://github.com/Obeo/bd1-timekeeper/releases/download/v0.2.0/bd1-linux-x86_64.tar.gz",
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                tray = TrayApp(
                    store,
                    lambda *_: None,
                    lambda: False,
                    lambda: False,
                    lambda: None,
                    lambda: None,
                )
                icon = Mock(HAS_NOTIFICATION=True)

                tray._check_updates(icon)
            finally:
                store.close()

        self.assertEqual("0.2.0", tray.available_update.version)
        icon.update_menu.assert_called_once_with()
        icon.notify.assert_called_once()

    @patch("bd1.tray.find_update", return_value=None)
    def test_manual_update_check_notifies_when_no_update_is_found(self, _find_update) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                tray = TrayApp(
                    store,
                    lambda *_: None,
                    lambda: False,
                    lambda: False,
                    lambda: None,
                    lambda: None,
                )
                tray.icon.HAS_NOTIFICATION = True
                with patch.object(tray.icon, "notify") as notify:
                    tray._check_updates_now_worker()
            finally:
                store.close()

        notify.assert_called_once_with(
            "Aucune nouvelle version détectée.",
            "Mise à jour de BD-1",
        )


if __name__ == "__main__":
    unittest.main()
