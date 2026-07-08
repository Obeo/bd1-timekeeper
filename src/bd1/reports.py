from __future__ import annotations

from datetime import date

from bd1.analyzer import ReportAnalyzer
from bd1.models import DailyReport, WeeklyReport
from bd1.storage import ObservationStore


class ReportService:
    def __init__(self, store: ObservationStore, analyzer: ReportAnalyzer | None = None) -> None:
        self.store = store
        self.analyzer = analyzer or ReportAnalyzer()

    def daily(self, day: date | None = None) -> DailyReport:
        target_day = day or date.today()
        return self.analyzer.build_daily(target_day, self.store.list_for_day(target_day))

    def weekly(self, day: date | None = None) -> WeeklyReport:
        target_day = day or date.today()
        return self.analyzer.build_weekly(target_day, self.store.list_for_week(target_day))
