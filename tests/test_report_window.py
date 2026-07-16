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
    _is_latest,
    _normalize_date,
    _render_daily,
    _render_weekly,
    _scope_title,
)


class TextBuffer:
    def __init__(self) -> None:
        self.values: list[str] = []

    def configure(self, **_kwargs: object) -> None:
        return

    def delete(self, _start: str, _end: str) -> None:
        self.values.clear()

    def insert(self, _index: str, value: str, _tags: tuple[str, ...] = ()) -> None:
        self.values.append(value)

    def tag_configure(self, _tag: str, **_kwargs: object) -> None:
        return

    def rendered(self) -> str:
        return "".join(self.values)


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

    def test_report_views_hide_routine_anomalies(self) -> None:
        observation = Observation(
            observed_at=datetime.fromisoformat("2026-07-10T09:00:00+02:00"),
            type=ObservationType.FIRST_ACTIVITY,
        )
        day = DailyReport(
            date="2026-07-10",
            observations=(observation,),
            work_blocks=(),
            break_blocks=(),
            anomalies=(
                "Application stopped before a system shutdown was observed; "
                "using it as the estimated day end.",
                "No shutdown observation after the last active segment.",
            ),
        )

        daily_text = TextBuffer()
        _render_daily(daily_text, day)
        weekly_text = TextBuffer()
        _render_weekly(weekly_text, WeeklyReport("2026-07-06", (day,)))

        for rendered in (daily_text.rendered(), weekly_text.rendered()):
            self.assertNotIn("État des données", rendered)
            self.assertNotIn("Qualité des données", rendered)
            self.assertNotIn("Application stopped before", rendered)
            self.assertNotIn("No shutdown observation", rendered)


if __name__ == "__main__":
    unittest.main()
