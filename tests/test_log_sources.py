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
from datetime import datetime, timedelta
from pathlib import Path

from asl_builder import build_asl

from bd1.log_sources import observations_from_logs, without_short_absences
from bd1.models import Observation, ObservationType

THRESHOLD = timedelta(minutes=15)


def at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 9, 15, hour, minute, second).astimezone()


def present(hour: int, minute: int, second: int = 0) -> Observation:
    return Observation(at(hour, minute, second), ObservationType.ACTIVITY_RESUMED)


def away(hour: int, minute: int, second: int = 0) -> Observation:
    return Observation(at(hour, minute, second), ObservationType.SHUTDOWN)


class WithoutShortAbsencesTest(unittest.TestCase):
    def test_absence_shorter_than_threshold_keeps_work_continuous(self) -> None:
        kept = without_short_absences(
            [present(9, 4), away(11, 23), present(11, 32), away(12, 10), present(13, 21)],
            THRESHOLD,
        )

        self.assertEqual(kept, [present(9, 4), away(12, 10), present(13, 21)])

    def test_flicker_within_seconds_disappears(self) -> None:
        kept = without_short_absences(
            [present(9, 4, 10), away(9, 4, 14), present(9, 4, 16), away(9, 4, 40)],
            THRESHOLD,
        )

        self.assertEqual(kept, [present(9, 4, 10), away(9, 4, 40)])

    def test_consecutive_absence_events_keep_the_first(self) -> None:
        kept = without_short_absences(
            [present(9, 0), away(17, 38), away(17, 40), present(18, 37)],
            THRESHOLD,
        )

        self.assertEqual(kept, [present(9, 0), away(17, 38), present(18, 37)])

    def test_short_absence_before_the_first_presence_keeps_the_presence(self) -> None:
        kept = without_short_absences([away(8, 50), present(8, 55)], THRESHOLD)

        self.assertEqual(kept, [present(8, 55)])


class ObservationsFromLogsTest(unittest.TestCase):
    def test_concatenates_the_available_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            power_log_dir = Path(directory) / "powermanagement"
            power_log_dir.mkdir()
            (power_log_dir / "2026.09.15.asl").write_bytes(
                build_asl(
                    [(at(9, 4), "Display is turned on"), (at(12, 10), "Display is turned off")]
                )
            )
            mattermost_log = Path(directory) / "main.log"
            mattermost_log.write_text(
                "[2026-09-15 10:15:00.000] [info]  [MainWindow] showing main window\n",
                encoding="utf-8",
            )

            observations = observations_from_logs(THRESHOLD, power_log_dir, mattermost_log)
            with self.assertRaises(FileNotFoundError):
                observations_from_logs(THRESHOLD, Path(directory) / "absent", Path("/absent"))

        self.assertEqual(
            [(item.observed_at, item.metadata["source"]) for item in observations],
            [(at(9, 4), "power_log"), (at(10, 15), "mattermost_log"), (at(12, 10), "power_log")],
        )


if __name__ == "__main__":
    unittest.main()
