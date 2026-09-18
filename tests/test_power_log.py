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
from datetime import datetime
from pathlib import Path

from asl_builder import build_asl

from bd1.models import ObservationType
from bd1.power_log import power_log_observations


def at(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 9, day, hour, minute).astimezone()


class PowerLogTest(unittest.TestCase):
    def test_presence_and_absence_events_across_daily_files(self) -> None:
        self.write(
            "2026.09.16.asl",
            [
                (at(16, 0, 9), "Entering Sleep state due to 'Sleep Service Back to Sleep'"),
                (at(16, 0, 28), "DarkWake from Deep Idle [CDNP] : due to NUB.SPMI0.SW3"),
                (at(16, 9, 11), "Display is turned on"),
                (at(16, 18, 15), "Entering Sleep state due to 'Clamshell Sleep':TCPKeepAlive"),
            ],
        )
        self.write(
            "2026.09.17.asl",
            [
                (at(17, 9, 11), "Display is turned on"),
                (at(17, 12, 22), "Display is turned off"),
            ],
        )
        (self.directory / "StoreData").write_bytes(b"\0" * 8)

        observations = power_log_observations(self.directory)

        self.assertEqual(
            [(item.observed_at, item.type) for item in observations],
            [
                (at(16, 9, 11), ObservationType.ACTIVITY_RESUMED),
                (at(16, 18, 15), ObservationType.SHUTDOWN),
                (at(17, 9, 11), ObservationType.ACTIVITY_RESUMED),
                (at(17, 12, 22), ObservationType.SHUTDOWN),
            ],
        )
        self.assertEqual(observations[0].metadata, {"source": "power_log"})

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def write(self, name: str, entries: list[tuple[datetime, str]]) -> None:
        (self.directory / name).write_bytes(build_asl(entries))


if __name__ == "__main__":
    unittest.main()
