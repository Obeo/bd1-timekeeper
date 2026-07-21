# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest

from bd1.activity import ActivityMonitor


class ActivityMonitorMeetingTest(unittest.TestCase):
    def test_meeting_microphone_activity_is_detected_when_enabled(self) -> None:
        monitor = ActivityMonitor.__new__(ActivityMonitor)
        monitor.meeting_activity_detection_enabled = True
        monitor.meeting_process_names = ("zoom",)
        monitor.microphone_activity_checker = lambda names: names == ("zoom",)

        self.assertTrue(monitor._has_meeting_microphone_activity())

    def test_meeting_microphone_activity_is_ignored_when_disabled(self) -> None:
        monitor = ActivityMonitor.__new__(ActivityMonitor)
        monitor.meeting_activity_detection_enabled = False
        monitor.meeting_process_names = ("zoom",)
        monitor.microphone_activity_checker = lambda _names: True

        self.assertFalse(monitor._has_meeting_microphone_activity())


if __name__ == "__main__":
    unittest.main()
