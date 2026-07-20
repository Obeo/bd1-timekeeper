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

from bd1.models import DailyReport, TimeBlock, WeeklyReport


class WeeklyDeclarationTest(unittest.TestCase):
    def test_week_under_target_keeps_estimated_blocks_and_reports_remaining_time(self) -> None:
        report = WeeklyReport("2026-07-06", (_day("2026-07-06", 7),))

        declaration = report.declaration

        self.assertEqual(37 * 3600, declaration.target_seconds)
        self.assertEqual(30 * 3600, declaration.remaining_seconds)
        self.assertEqual(0, declaration.excess_seconds)
        self.assertEqual(report.days, declaration.proposed_days)

    def test_week_at_target_keeps_estimated_blocks(self) -> None:
        report = WeeklyReport(
            "2026-07-06",
            tuple(
                _day(f"2026-07-{day:02d}", duration)
                for day, duration in zip(range(6, 11), (7, 7, 7, 7, 9), strict=True)
            ),
        )

        declaration = report.declaration

        self.assertEqual(0, declaration.remaining_seconds)
        self.assertEqual(0, declaration.excess_seconds)
        self.assertEqual(37 * 3600, declaration.proposed_seconds)

    def test_week_above_target_reduces_each_worked_day(self) -> None:
        report = WeeklyReport(
            "2026-07-06",
            tuple(_day(f"2026-07-{day:02d}", 8) for day in range(6, 11)),
        )

        declaration = report.declaration

        self.assertEqual(3 * 3600, declaration.excess_seconds)
        self.assertEqual(37 * 3600, declaration.proposed_seconds)
        self.assertEqual(
            [7 * 3600 + 24 * 60] * 5,
            [day.worked_seconds for day in declaration.proposed_days],
        )
        self.assertEqual(
            ["16:24"] * 5,
            [day.work_blocks[-1].end.strftime("%H:%M") for day in declaration.proposed_days],
        )

    def test_non_working_days_are_excluded_from_declaration(self) -> None:
        report = WeeklyReport(
            "2026-07-06",
            (
                _day("2026-07-06", 8),
                _day("2026-07-07", 8),
                _day("2026-07-08", 8),
                _day("2026-07-09", 8),
                _day("2026-07-10", 8),
                _day("2026-07-11", 8),
                _day("2026-07-12", 8),
            ),
        )

        declaration = report.declaration

        self.assertEqual(40 * 3600, declaration.estimated_seconds)
        self.assertEqual(37 * 3600, declaration.proposed_seconds)
        self.assertEqual(
            ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"],
            [day.date for day in declaration.proposed_days],
        )


def _day(day: str, hours: int) -> DailyReport:
    start = datetime.fromisoformat(f"{day}T09:00:00+02:00")
    return DailyReport(
        date=day,
        observations=(),
        work_blocks=(TimeBlock("work", start, start + timedelta(hours=hours)),),
        break_blocks=(),
        anomalies=(),
    )


if __name__ == "__main__":
    unittest.main()
