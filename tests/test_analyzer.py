# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bd1.analyzer import ReportAnalyzer
from bd1.models import Observation, ObservationType

PARIS = ZoneInfo("Europe/Paris")


class ReportAnalyzerTest(unittest.TestCase):
    def test_weekly_report_contains_workdays_only(self) -> None:
        week_start = date(2026, 7, 6)
        weekend_observation = obs("2026-07-11T09:00:00+02:00", ObservationType.USER_WORKING)

        report = ReportAnalyzer().build_weekly(week_start, [weekend_observation])

        self.assertEqual(
            tuple((week_start + timedelta(days=offset)).isoformat() for offset in range(5)),
            tuple(day.date for day in report.days),
        )
        self.assertEqual(0, report.worked_seconds)

    def test_weekly_report_excludes_french_holidays(self) -> None:
        report = ReportAnalyzer().build_weekly(date(2026, 7, 13), [])

        self.assertEqual(
            ("2026-07-13", "2026-07-15", "2026-07-16", "2026-07-17"),
            tuple(day.date for day in report.days),
        )

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
        self.assertEqual(7 * 3600 + 43 * 60, report.worked_seconds)
        self.assertEqual(110 * 60, report.break_seconds)
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

    def test_automatic_lunch_resume_before_1358_keeps_break_until_1358(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:08:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T13:20:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T18:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual("12:08", report.break_blocks[0].start.strftime("%H:%M"))
        self.assertEqual("13:58", report.break_blocks[0].end.strftime("%H:%M"))
        self.assertEqual("13:58", report.work_blocks[1].start.strftime("%H:%M"))

    def test_explicit_lunch_working_mark_starts_work_immediately(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:08:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T13:20:00+02:00", ObservationType.USER_WORKING),
            obs("2026-07-08T18:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual("13:20", report.break_blocks[0].end.strftime("%H:%M"))
        self.assertEqual("13:20", report.work_blocks[1].start.strftime("%H:%M"))

    def test_automatic_lunch_resume_at_1358_starts_work(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:08:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T13:58:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T18:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual("13:58", report.break_blocks[0].end.strftime("%H:%M"))
        self.assertEqual("13:58", report.work_blocks[1].start.strftime("%H:%M"))

    def test_short_automatic_resume_keeps_break_continuous(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:00:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T14:05:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T14:08:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T15:00:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T17:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(2, len(report.work_blocks))
        self.assertEqual(1, len(report.break_blocks))
        self.assertEqual("12:00", report.break_blocks[0].start.strftime("%H:%M"))
        self.assertEqual("15:00", report.break_blocks[0].end.strftime("%H:%M"))

    def test_explicit_working_mark_keeps_short_resume_as_work(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:00:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T14:05:00+02:00", ObservationType.USER_WORKING),
            obs("2026-07-08T14:08:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T15:00:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T17:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual("14:05", report.work_blocks[1].start.strftime("%H:%M"))
        self.assertEqual("14:08", report.work_blocks[1].end.strftime("%H:%M"))

    def test_long_automatic_resume_splits_break(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:00:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T14:05:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T14:12:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T15:00:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T17:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual("14:05", report.work_blocks[1].start.strftime("%H:%M"))
        self.assertEqual("14:12", report.work_blocks[1].end.strftime("%H:%M"))

    def test_app_started_does_not_affect_work_time(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T08:00:00+02:00", ObservationType.APP_STARTED),
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T17:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(8 * 3600, report.worked_seconds)
        self.assertEqual(0, report.break_seconds)

    def test_last_app_stopped_closes_open_work_block_qualitatively(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T18:03:00+02:00", ObservationType.APP_STOPPED),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(1, len(report.work_blocks))
        self.assertEqual("18:03", report.work_blocks[0].end.strftime("%H:%M"))
        self.assertEqual(9 * 3600 + 3 * 60, report.worked_seconds)
        self.assertIn(
            "Application stopped before a system shutdown was observed; "
            "using it as the estimated day end.",
            report.anomalies,
        )
        self.assertNotIn("No shutdown observation after the last active segment.", report.anomalies)

    def test_past_day_without_shutdown_stops_at_last_known_observation(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:07:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:23:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T13:51:00+02:00", ObservationType.ACTIVITY_RESUMED),
        ]

        report = ReportAnalyzer(
            now_provider=lambda: datetime.fromisoformat("2026-07-09T09:00:00+02:00")
        ).build_daily(day, observations)

        self.assertEqual(1, len(report.work_blocks))
        self.assertEqual(1, len(report.break_blocks))
        self.assertEqual("09:07", report.work_blocks[0].start.strftime("%H:%M"))
        self.assertEqual("12:23", report.work_blocks[0].end.strftime("%H:%M"))
        self.assertEqual("12:23", report.break_blocks[0].start.strftime("%H:%M"))
        self.assertEqual("13:58", report.break_blocks[0].end.strftime("%H:%M"))
        self.assertEqual(3 * 3600 + 16 * 60, report.worked_seconds)
        self.assertIn(
            "No shutdown observation after the last active segment; "
            "stopping the past-day estimate at the last known observation.",
            report.anomalies,
        )

    def test_past_day_without_shutdown_uses_last_heartbeat_as_estimated_end(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:07:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:23:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-08T13:51:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-08T18:05:00+02:00", ObservationType.APP_HEARTBEAT),
        ]

        report = ReportAnalyzer(
            now_provider=lambda: datetime.fromisoformat("2026-07-09T09:00:00+02:00")
        ).build_daily(day, observations)

        self.assertEqual(2, len(report.work_blocks))
        self.assertEqual("13:58", report.work_blocks[1].start.strftime("%H:%M"))
        self.assertEqual("18:05", report.work_blocks[1].end.strftime("%H:%M"))

    def test_app_stopped_closes_a_session_before_a_later_session(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T09:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T12:00:00+02:00", ObservationType.APP_STOPPED),
            obs("2026-07-08T17:00:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T18:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(2, len(report.work_blocks))
        self.assertEqual("12:00", report.work_blocks[0].end.strftime("%H:%M"))
        self.assertEqual("17:00", report.work_blocks[1].start.strftime("%H:%M"))

    def test_reboot_after_workday_does_not_extend_the_previous_session(self) -> None:
        day = date(2026, 7, 10)
        observations = [
            obs("2026-07-10T08:36:00+02:00", ObservationType.BOOT),
            obs("2026-07-10T08:36:00+02:00", ObservationType.APP_STARTED),
            obs("2026-07-10T08:36:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-10T09:38:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-10T09:58:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-10T12:26:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-10T14:31:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-10T15:02:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-10T15:21:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-10T17:37:00+02:00", ObservationType.IDLE_STARTED),
            obs("2026-07-10T17:55:00+02:00", ObservationType.ACTIVITY_RESUMED),
            obs("2026-07-10T18:31:00+02:00", ObservationType.APP_STOPPED),
            obs("2026-07-10T21:37:00+02:00", ObservationType.BOOT),
            obs("2026-07-10T21:38:00+02:00", ObservationType.APP_STARTED),
            obs("2026-07-10T21:38:00+02:00", ObservationType.FIRST_ACTIVITY),
        ]

        report = ReportAnalyzer(
            now_provider=lambda: datetime.fromisoformat("2026-07-10T21:47:00+02:00")
        ).build_daily(day, observations)

        self.assertEqual(6, len(report.work_blocks))
        self.assertEqual("18:31", report.work_blocks[4].end.strftime("%H:%M"))
        self.assertEqual("21:38", report.work_blocks[5].start.strftime("%H:%M"))
        self.assertEqual("21:47", report.work_blocks[5].end.strftime("%H:%M"))

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

    def test_late_afternoon_app_start_infers_default_lunch_break(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T08:00:00+02:00", ObservationType.BOOT),
            obs("2026-07-08T15:00:00+02:00", ObservationType.APP_STARTED),
            obs("2026-07-08T15:02:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T18:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(8 * 3600, report.worked_seconds)
        self.assertEqual(2 * 3600, report.break_seconds)
        self.assertEqual("08:00", report.work_blocks[0].start.strftime("%H:%M"))
        self.assertEqual("12:00", report.work_blocks[0].end.strftime("%H:%M"))
        self.assertEqual("12:00", report.break_blocks[0].start.strftime("%H:%M"))
        self.assertEqual("14:00", report.break_blocks[0].end.strftime("%H:%M"))
        self.assertEqual("14:00", report.work_blocks[1].start.strftime("%H:%M"))

    def test_late_app_start_keeps_real_lunch_information(self) -> None:
        day = date(2026, 7, 8)
        observations = [
            obs("2026-07-08T08:00:00+02:00", ObservationType.BOOT),
            obs("2026-07-08T12:30:00+02:00", ObservationType.USER_BREAK),
            obs("2026-07-08T15:00:00+02:00", ObservationType.APP_STARTED),
            obs("2026-07-08T15:02:00+02:00", ObservationType.FIRST_ACTIVITY),
            obs("2026-07-08T18:00:00+02:00", ObservationType.SHUTDOWN),
        ]

        report = ReportAnalyzer().build_daily(day, observations)

        self.assertEqual(1, len(report.break_blocks))
        self.assertEqual("12:30", report.break_blocks[0].start.strftime("%H:%M"))
        self.assertEqual("15:02", report.break_blocks[0].end.strftime("%H:%M"))

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
