# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import ClassVar
from unittest.mock import patch

from bd1.models import ObservationType
from bd1.observer import HeadlessObserver
from bd1.settings import Settings
from bd1.storage import ObservationStore


class HeadlessObserverTest(unittest.TestCase):
    def test_run_records_lifecycle_without_tray(self) -> None:
        boot_time = datetime.fromisoformat("2026-07-20T08:00:00+02:00")
        messages: list[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                observer = HeadlessObserver(
                    Settings(heartbeat_interval_seconds=60.0),
                    store,
                    printer=messages.append,
                    boot_time_provider=lambda: boot_time,
                )
                observer._stop_event.set()

                with patch.dict(sys.modules, {"bd1.activity": _activity_module()}):
                    observer.run()

                observations = store.list_for_day(boot_time.date())
            finally:
                store.close()

        self.assertEqual(
            [
                ObservationType.BOOT,
                ObservationType.APP_STARTED,
                ObservationType.APP_STOPPED,
            ],
            [observation.type for observation in observations],
        )
        self.assertTrue(any("BD-1 observe l'activité" in message for message in messages))

    def test_activity_monitor_receives_settings(self) -> None:
        fake_monitor = FakeActivityMonitor
        activity_module = ModuleType("bd1.activity")
        activity_module.ActivityMonitor = fake_monitor

        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                observer = HeadlessObserver(
                    Settings(
                        idle_threshold_minutes=12,
                        activity_poll_seconds=3.0,
                        idle_ignored_process_names=("Zoom.exe",),
                    ),
                    store,
                    printer=lambda _: None,
                )

                with patch.dict(sys.modules, {"bd1.activity": activity_module}):
                    observer._start_activity_monitor()
                    observer._stop_activity_monitor()
            finally:
                store.close()

        self.assertEqual(12 * 60, fake_monitor.last_kwargs["idle_threshold_seconds"])
        self.assertEqual(3.0, fake_monitor.last_kwargs["poll_seconds"])
        self.assertEqual(("Zoom.exe",), fake_monitor.last_kwargs["idle_ignored_process_names"])


def _activity_module() -> ModuleType:
    activity_module = ModuleType("bd1.activity")
    activity_module.ActivityMonitor = FakeActivityMonitor
    return activity_module


class FakeActivityMonitor:
    last_kwargs: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs: object) -> None:
        type(self).last_kwargs = kwargs
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


if __name__ == "__main__":
    unittest.main()
