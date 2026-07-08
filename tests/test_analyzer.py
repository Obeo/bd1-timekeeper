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

    def test_consecutive_work_signals_are_merged_into_one_block(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T09:03:00+02:00", ObservationType.USER_WORKING),
            obs("2026-07-08T09:06:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T12:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(1, len(report.work_blocks))
        self.assertEqual(3 * 3600, report.worked_seconds)
        self.assertEqual("09:00", report.work_blocks[0].start.strftime("%H:%M"))
        self.assertEqual("12:00", report.work_blocks[0].end.strftime("%H:%M"))

    def test_app_lifecycle_events_do_not_affect_work_time(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T08:00:00+02:00", ObservationType.APP_STARTED),
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:00:00+02:00", ObservationType.APP_STOPPED),
            obs("2026-07-08T17:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(8 * 3600, report.worked_seconds)
        self.assertEqual(0, report.break_seconds)

    def test_late_app_start_interprets_boot_as_work_start(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T08:00:00+02:00", ObservationType.BOOT),
            obs("2026-07-08T09:00:00+02:00", ObservationType.APP_STARTED),
            obs("2026-07-08T09:05:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T17:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(9 * 3600, report.worked_seconds)
        self.assertEqual("08:00", report.work_blocks[0].start.strftime("%H:%M"))

    def test_near_app_start_does_not_interpret_boot_as_work_start(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T08:00:00+02:00", ObservationType.BOOT),
            obs("2026-07-08T08:10:00+02:00", ObservationType.APP_STARTED),
            obs("2026-07-08T08:12:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T17:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(8 * 3600 + 48 * 60, report.worked_seconds)
        self.assertEqual("08:12", report.work_blocks[0].start.strftime("%H:%M"))

    def test_late_app_start_without_activity_does_not_interpret_boot_as_work_start(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T08:00:00+02:00", ObservationType.BOOT),
            obs("2026-07-08T10:00:00+02:00", ObservationType.APP_STARTED),
            obs("2026-07-08T10:05:00+02:00", ObservationType.APP_STOPPED),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(0, report.worked_seconds)
        self.assertEqual((), report.work_blocks)


def obs(value: str, observation_type: ObservationType) -> Observation:
    return Observation(
        observed_at=datetime.fromisoformat(value).astimezone(PARIS),
        type=observation_type,
    )


if __name__ == "__main__":
    unittest.main()
