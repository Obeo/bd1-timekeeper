from __future__ import annotations

import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from bd1.analyzer import ReportAnalyzer
from bd1.models import Observation, ObservationType

PARIS = ZoneInfo("Europe/Paris")


class ReportAnalyzerTest(unittest.TestCase):
    def test_builds_work_and_break_blocks_from_observations(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T08:31:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:08:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T13:37:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T18:04:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(2, len(report.work_blocks))
        self.assertEqual(1, len(report.break_blocks))
        self.assertEqual(8 * 3600 + 4 * 60, report.worked_seconds)
        self.assertEqual(89 * 60, report.break_seconds)
        self.assertEqual((), report.anomalies)

    def test_manual_marks_are_strong_signals(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.USER_WORKING),
            obs("2026-07-08T12:00:00+02:00", ObservationType.USER_BREAK),
            obs("2026-07-08T13:00:00+02:00", ObservationType.USER_WORKING),
            obs("2026-07-08T17:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(7 * 3600, report.worked_seconds)
        self.assertEqual(3600, report.break_seconds)


def obs(value: str, observation_type: ObservationType) -> Observation:
    return Observation(
        observed_at=datetime.fromisoformat(value).astimezone(PARIS),
        type=observation_type,
    )


if __name__ == "__main__":
    unittest.main()
