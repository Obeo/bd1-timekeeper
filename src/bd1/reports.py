# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date, time

from bd1.analyzer import DEFAULT_LUNCH_AUTOMATIC_WORK_RESUME, WORK_START_EVENTS, ReportAnalyzer
from bd1.calendar import is_working_day
from bd1.models import DailyReport, WeeklyReport
from bd1.storage import ObservationStore

DAILY_TARGET_SECONDS = int(7.4 * 60 * 60)
MINIMUM_CORRECTION_WORK_SECONDS = 2 * 60 * 60


class ReportService:
    def __init__(
        self,
        store: ObservationStore,
        analyzer: ReportAnalyzer | None = None,
        today_provider: Callable[[], date] | None = None,
        lunch_automatic_work_resume: time | None = None,
    ) -> None:
        self.store = store
        if analyzer is None:
            analyzer = ReportAnalyzer(
                lunch_automatic_work_resume=lunch_automatic_work_resume
                or DEFAULT_LUNCH_AUTOMATIC_WORK_RESUME
            )
        self.analyzer = analyzer
        self._today_provider = today_provider or date.today

    def daily(self, day: date | None = None) -> DailyReport:
        target_day = day or date.today()
        return self.analyzer.build_daily(target_day, self.store.list_for_day(target_day))

    def weekly(self, day: date | None = None) -> WeeklyReport:
        target_day = day or date.today()
        return self.analyzer.build_weekly(target_day, self.store.list_for_week(target_day))

    def delete_day(self, day: date) -> int:
        return self.store.delete_for_day(day)

    def all_time_correction_seconds(self) -> int:
        today = self._today_provider()
        period_start = correction_period_start(today)
        observations_by_day = defaultdict(list)
        for observation in self.store.list_all():
            observation_day = observation.observed_at.date()
            if period_start <= observation_day < today and is_working_day(observation_day):
                observations_by_day[observation_day].append(observation)

        correction_seconds = 0
        for day, observations in sorted(observations_by_day.items()):
            if not any(observation.type in WORK_START_EVENTS for observation in observations):
                continue
            daily_report = self.analyzer.build_daily(day, observations)
            if daily_report.worked_seconds < MINIMUM_CORRECTION_WORK_SECONDS:
                continue
            correction_seconds += daily_report.worked_seconds - DAILY_TARGET_SECONDS
        return correction_seconds


def correction_period_start(today: date) -> date:
    current_year_start = date(today.year, 6, 1)
    if today >= current_year_start:
        return current_year_start
    return date(today.year - 1, 6, 1)
