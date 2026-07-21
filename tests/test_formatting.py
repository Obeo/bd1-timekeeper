# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from bd1.formatting import format_daily_report, format_duration, format_weekly_report
from bd1.models import (
    WEEKLY_DECLARATION_TARGET_SECONDS,
    DailyReport,
    Observation,
    ObservationType,
    TimeBlock,
    WeeklyReport,
)


class FormattingTest(unittest.TestCase):
    def test_daily_report_puts_observed_timeline_after_interpretation(self) -> None:
        report = DailyReport(
            date="2026-07-08",
            observations=(
                Observation(
                    datetime.fromisoformat("2026-07-08T09:07:00+02:00"),
                    ObservationType.FIRST_ACTIVITY,
                ),
            ),
            work_blocks=(
                TimeBlock(
                    "work",
                    datetime.fromisoformat("2026-07-08T09:07:00+02:00"),
                    datetime.fromisoformat("2026-07-08T12:23:00+02:00"),
                ),
            ),
            break_blocks=(),
            anomalies=("Example anomaly",),
        )

        rendered = format_daily_report(report)

        self.assertLess(
            rendered.index("Suggested interpretation:"),
            rendered.index("Observed timeline:"),
        )
        self.assertLess(rendered.index("Anomalies:"), rendered.index("Observed timeline:"))

    def test_weekly_report_includes_daily_work_and_break_ranges(self) -> None:
        day = DailyReport(
            date="2026-07-08",
            observations=(
                Observation(
                    datetime.fromisoformat("2026-07-08T09:07:00+02:00"),
                    ObservationType.FIRST_ACTIVITY,
                ),
            ),
            work_blocks=(
                TimeBlock(
                    "work",
                    datetime.fromisoformat("2026-07-08T09:07:00+02:00"),
                    datetime.fromisoformat("2026-07-08T12:23:00+02:00"),
                ),
                TimeBlock(
                    "work",
                    datetime.fromisoformat("2026-07-08T13:51:00+02:00"),
                    datetime.fromisoformat("2026-07-08T18:00:00+02:00"),
                ),
            ),
            break_blocks=(
                TimeBlock(
                    "break",
                    datetime.fromisoformat("2026-07-08T12:23:00+02:00"),
                    datetime.fromisoformat("2026-07-08T13:51:00+02:00"),
                ),
            ),
            anomalies=(),
        )

        rendered = format_weekly_report(WeeklyReport("2026-07-06", (day,)))

        self.assertNotIn("Suggested interpretation:", rendered)
        self.assertIn("  - Work: 09:07 -> 12:23 (3 h 16)", rendered)
        self.assertIn("  - Break: 12:23 -> 13:51 (1 h 28)", rendered)
        self.assertIn("  - Work: 13:51 -> 18:00 (4 h 09)", rendered)
        self.assertLess(
            rendered.index("  - Work: 09:07 -> 12:23"),
            rendered.index("  - Break: 12:23 -> 13:51"),
        )
        self.assertLess(
            rendered.index("  - Break: 12:23 -> 13:51"),
            rendered.index("  - Work: 13:51 -> 18:00"),
        )
        self.assertIn("Weekly total: 7 h 25", rendered)

    def test_weekly_declaration_is_opt_in(self) -> None:
        days = tuple(
            DailyReport(
                date=f"2026-07-{day:02d}",
                observations=(
                    Observation(
                        datetime.fromisoformat(f"2026-07-{day:02d}T09:00:00+02:00"),
                        ObservationType.FIRST_ACTIVITY,
                    ),
                ),
                work_blocks=(
                    TimeBlock(
                        "work",
                        datetime.fromisoformat(f"2026-07-{day:02d}T09:00:00+02:00"),
                        datetime.fromisoformat(f"2026-07-{day:02d}T17:00:00+02:00"),
                    ),
                ),
                break_blocks=(),
                anomalies=(),
            )
            for day in range(6, 11)
        )
        report = WeeklyReport("2026-07-06", days)
        capped_daily_seconds = WEEKLY_DECLARATION_TARGET_SECONDS // 5
        capped_end = (
            datetime.fromisoformat("2026-07-06T09:00:00+02:00")
            + timedelta(seconds=capped_daily_seconds)
        ).strftime("%H:%M")

        uncapped = format_weekly_report(report)
        capped = format_weekly_report(report, apply_weekly_cap=True)

        self.assertIn("2026-07-06: 8 h 00 worked", uncapped)
        self.assertIn("Weekly total: 40 h 00", uncapped)
        self.assertIn(
            f"2026-07-06: {format_duration(capped_daily_seconds)} worked",
            capped,
        )
        self.assertIn(f"09:00 -> {capped_end}", capped)
        self.assertIn(f"Weekly total: {format_duration(WEEKLY_DECLARATION_TARGET_SECONDS)}", capped)
        self.assertNotIn("Suggested declaration:", capped)

    def test_daily_report_orders_interpreted_blocks_chronologically(self) -> None:
        report = DailyReport(
            date="2026-07-08",
            observations=(),
            work_blocks=(
                TimeBlock(
                    "work",
                    datetime.fromisoformat("2026-07-08T09:07:00+02:00"),
                    datetime.fromisoformat("2026-07-08T12:23:00+02:00"),
                ),
                TimeBlock(
                    "work",
                    datetime.fromisoformat("2026-07-08T13:51:00+02:00"),
                    datetime.fromisoformat("2026-07-08T18:00:00+02:00"),
                ),
            ),
            break_blocks=(
                TimeBlock(
                    "break",
                    datetime.fromisoformat("2026-07-08T12:23:00+02:00"),
                    datetime.fromisoformat("2026-07-08T13:51:00+02:00"),
                ),
            ),
            anomalies=(),
        )

        rendered = format_daily_report(report)

        self.assertLess(
            rendered.index("- Work: 09:07 -> 12:23"),
            rendered.index("- Break: 12:23 -> 13:51"),
        )
        self.assertLess(
            rendered.index("- Break: 12:23 -> 13:51"),
            rendered.index("- Work: 13:51 -> 18:00"),
        )

    def test_daily_report_hides_heartbeat_observations(self) -> None:
        report = DailyReport(
            date="2026-07-08",
            observations=(
                Observation(
                    datetime.fromisoformat("2026-07-08T09:07:00+02:00"),
                    ObservationType.FIRST_ACTIVITY,
                ),
                Observation(
                    datetime.fromisoformat("2026-07-08T18:05:00+02:00"),
                    ObservationType.APP_HEARTBEAT,
                ),
            ),
            work_blocks=(),
            break_blocks=(),
            anomalies=(),
        )

        rendered = format_daily_report(report)

        self.assertIn("- 09:07 FIRST_ACTIVITY", rendered)
        self.assertNotIn("APP_HEARTBEAT", rendered)

    def test_weekly_report_says_when_day_has_no_observations(self) -> None:
        day = DailyReport(
            date="2026-07-08",
            observations=(),
            work_blocks=(),
            break_blocks=(),
            anomalies=("No user activity detected for this day.",),
        )

        rendered = format_weekly_report(WeeklyReport("2026-07-06", (day,)))

        self.assertIn("2026-07-08: no observations", rendered)
        self.assertNotIn("No user activity detected for this day.", rendered)

    def test_weekly_report_hides_weekend_days(self) -> None:
        day = DailyReport(
            date="2026-07-11",
            observations=(),
            work_blocks=(),
            break_blocks=(),
            anomalies=(),
        )

        rendered = format_weekly_report(WeeklyReport("2026-07-06", (day,)))

        self.assertNotIn("2026-07-11", rendered)


if __name__ == "__main__":
    unittest.main()
