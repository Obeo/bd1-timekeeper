# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import importlib
import sys
import unittest
from queue import Empty
from types import ModuleType
from unittest.mock import patch

from bd1.models import ObservationType


def _activity_monitor_type() -> type:
    pynput = ModuleType("pynput")
    pynput.keyboard = ModuleType("pynput.keyboard")
    pynput.mouse = ModuleType("pynput.mouse")
    with patch.dict(
        sys.modules,
        {
            "pynput": pynput,
            "pynput.keyboard": pynput.keyboard,
            "pynput.mouse": pynput.mouse,
        },
    ):
        module = importlib.import_module("bd1.activity")
    return module.ActivityMonitor


class ActivityMonitorMeetingTest(unittest.TestCase):
    def test_desktop_idle_provider_records_activity_and_idle(self) -> None:
        ActivityMonitor = _activity_monitor_type()
        idle_values = iter((0.0, 90.0))
        monitor = ActivityMonitor(
            idle_threshold_seconds=60,
            callback=lambda observation_type, observed_at, metadata: None,
            idle_seconds_provider=lambda: next(idle_values),
        )

        monitor._watch_desktop_idle()
        monitor._watch_desktop_idle()
        events = (monitor._events.get_nowait(), monitor._events.get_nowait())

        self.assertEqual(ObservationType.FIRST_ACTIVITY, events[0].observation_type)
        self.assertEqual(ObservationType.IDLE_STARTED, events[1].observation_type)
        self.assertEqual(90, events[1].metadata["observed_idle_seconds"])
        self.assertIn("threshold_crossed_at", events[1].metadata)
        with self.assertRaises(Empty):
            monitor._events.get_nowait()

    def test_meeting_microphone_activity_is_detected_when_enabled(self) -> None:
        ActivityMonitor = _activity_monitor_type()
        monitor = ActivityMonitor.__new__(ActivityMonitor)
        monitor.meeting_activity_detection_enabled = True
        monitor.meeting_process_names = ("zoom",)
        monitor.microphone_activity_checker = lambda names: names == ("zoom",)

        self.assertTrue(monitor._has_meeting_microphone_activity())

    def test_meeting_microphone_activity_is_ignored_when_disabled(self) -> None:
        ActivityMonitor = _activity_monitor_type()
        monitor = ActivityMonitor.__new__(ActivityMonitor)
        monitor.meeting_activity_detection_enabled = False
        monitor.meeting_process_names = ("zoom",)
        monitor.microphone_activity_checker = lambda _names: True

        self.assertFalse(monitor._has_meeting_microphone_activity())

    def test_desktop_idle_provider_does_not_mark_idle_during_meeting_activity(self) -> None:
        ActivityMonitor = _activity_monitor_type()
        monitor = ActivityMonitor(
            idle_threshold_seconds=60,
            callback=lambda observation_type, observed_at, metadata: None,
            idle_seconds_provider=lambda: 90.0,
            meeting_activity_detection_enabled=True,
            meeting_process_names=("zoom",),
            microphone_activity_checker=lambda names: names == ("zoom",),
        )
        monitor._seen_activity = True

        monitor._watch_desktop_idle()

        with self.assertRaises(Empty):
            monitor._events.get_nowait()


if __name__ == "__main__":
    unittest.main()
