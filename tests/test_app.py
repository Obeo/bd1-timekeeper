# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from bd1.app import BD1Application
from bd1.autostart import AutostartStatus
from bd1.models import ObservationType
from bd1.settings import Settings
from bd1.storage import ObservationStore


class BD1ApplicationTest(unittest.TestCase):
    def test_records_system_boot_once_for_same_boot_timestamp(self) -> None:
        boot_time = datetime.fromisoformat("2026-07-08T07:12:00+02:00")

        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                app = BD1Application(
                    Settings(),
                    store,
                    activity_monitor_enabled=False,
                    boot_time_provider=lambda: boot_time,
                )

                app._record_system_boot()
                app._record_system_boot()

                observations = store.list_for_day(boot_time.date())
            finally:
                store.close()

        boots = [
            observation for observation in observations if observation.type == ObservationType.BOOT
        ]
        self.assertEqual(1, len(boots))
        self.assertEqual({"source": "system_boot"}, boots[0].metadata)

    def test_toggle_autostart_updates_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                manager = FakeAutostartManager()
                app = BD1Application(
                    Settings(),
                    store,
                    activity_monitor_enabled=False,
                    autostart_manager=manager,
                )

                with patch("bd1.app.save_settings"):
                    self.assertTrue(app.toggle_autostart())
                    self.assertTrue(app.settings.autostart_enabled)
                    self.assertFalse(app.toggle_autostart())
                    self.assertFalse(app.settings.autostart_enabled)
            finally:
                store.close()

    def test_records_periodic_app_heartbeats(self) -> None:
        now = datetime.now().astimezone()
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                app = BD1Application(
                    Settings(heartbeat_interval_seconds=1.0),
                    store,
                    activity_monitor_enabled=False,
                )

                app._start_heartbeat()
                time.sleep(1.2)
                app._stop_heartbeat()

                observations = store.list_for_day(now.date())
            finally:
                store.close()

        self.assertTrue(
            any(observation.type == ObservationType.APP_HEARTBEAT for observation in observations)
        )


class FakeAutostartManager:
    def __init__(self) -> None:
        self.enabled = False

    def is_enabled(self) -> bool:
        return self.enabled

    def set_enabled(self, enabled: bool) -> AutostartStatus:
        self.enabled = enabled
        return AutostartStatus(True, enabled, "fake")

    def refresh_if_enabled(self) -> AutostartStatus:
        return AutostartStatus(True, self.enabled, "fake")


if __name__ == "__main__":
    unittest.main()
