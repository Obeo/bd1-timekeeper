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

from bd1.models import DailyReport, Observation, ObservationType, WeeklyReport
from bd1.report_window import (
    ReportView,
    _daily_status,
    _is_latest,
    _normalize_date,
    _scope_title,
    _weekly_status,
)


class ReportWindowHelpersTest(unittest.TestCase):
    def test_week_view_normalizes_to_monday(self) -> None:
        self.assertEqual(
            date(2026, 7, 6),
            _normalize_date(ReportView.WEEK, date(2026, 7, 8)),
        )

    def test_scope_title_describes_day_and_week(self) -> None:
        current = date(2026, 7, 10)
        week_start = _normalize_date(ReportView.WEEK, current)

        self.assertEqual("vendredi 10 juillet 2026", _scope_title(ReportView.DAY, current))
        self.assertEqual(
            "Semaine du lundi 6 juillet 2026 au dimanche 12 juillet 2026",
            _scope_title(ReportView.WEEK, week_start),
        )

    def test_next_navigation_stops_at_current_scope(self) -> None:
        self.assertTrue(_is_latest(ReportView.DAY, date.today()))
        self.assertTrue(_is_latest(ReportView.WEEK, date.today()))
        self.assertFalse(_is_latest(ReportView.DAY, date.today() - timedelta(days=1)))

    def test_daily_status_distinguishes_missing_and_partial_data(self) -> None:
        empty = DailyReport("2026-07-10", (), (), (), ())
        partial = DailyReport(
            "2026-07-10",
            (
                Observation(
                    datetime.fromisoformat("2026-07-10T09:00:00+02:00"),
                    ObservationType.FIRST_ACTIVITY,
                ),
            ),
            (),
            (),
            ("No shutdown observation after the last active segment.",),
        )

        self.assertEqual("Aucune information", _daily_status(empty))
        self.assertEqual("Données partielles", _daily_status(partial))

    def test_weekly_status_mentions_missing_days(self) -> None:
        empty = DailyReport("2026-07-10", (), (), (), ())
        partial = DailyReport(
            "2026-07-10",
            (
                Observation(
                    datetime.fromisoformat("2026-07-10T09:00:00+02:00"),
                    ObservationType.FIRST_ACTIVITY,
                ),
            ),
            (),
            (),
            (),
        )

        self.assertEqual(
            "Aucune information",
            _weekly_status(WeeklyReport("2026-07-06", (empty,) * 7)),
        )
        self.assertEqual(
            "Données partielles",
            _weekly_status(WeeklyReport("2026-07-06", (partial,) + (empty,) * 6)),
        )


if __name__ == "__main__":
    unittest.main()
