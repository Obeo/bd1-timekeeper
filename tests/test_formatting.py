from __future__ import annotations

import unittest
from datetime import datetime

from bd1.formatting import format_daily_report, format_weekly_report
from bd1.models import DailyReport, Observation, ObservationType, TimeBlock, WeeklyReport


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


if __name__ == "__main__":
    unittest.main()
