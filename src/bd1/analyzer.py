from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from bd1.models import DailyReport, Observation, ObservationType, TimeBlock, WeeklyReport

WORK_START_EVENTS = {
    ObservationType.FIRST_ACTIVITY,
    ObservationType.ACTIVITY_RESUMED,
    ObservationType.USER_WORKING,
}
BREAK_START_EVENTS = {
    ObservationType.IDLE_STARTED,
    ObservationType.USER_BREAK,
}
DAY_END_EVENTS = {ObservationType.SHUTDOWN}


class ReportAnalyzer:
    def build_daily(self, day: date, observations: Iterable[Observation]) -> DailyReport:
        ordered = tuple(sorted(observations, key=lambda item: (item.observed_at, item.id or 0)))
        work_blocks: list[TimeBlock] = []
        break_blocks: list[TimeBlock] = []
        anomalies: list[str] = []

        current_label: str | None = None
        current_start: datetime | None = None

        for observation in ordered:
            next_label = self._label_for(observation.type)
            if next_label is None:
                continue

            if current_label is not None and current_start is not None:
                self._append_block(
                    current_label, current_start, observation.observed_at, work_blocks, break_blocks
                )

            if observation.type in DAY_END_EVENTS:
                current_label = None
                current_start = None
            else:
                current_label = next_label
                current_start = observation.observed_at

        if current_label is not None and current_start is not None:
            end_of_day = datetime.combine(day + timedelta(days=1), time.min).astimezone()
            now = datetime.now().astimezone()
            self._append_block(
                current_label, current_start, min(end_of_day, now), work_blocks, break_blocks
            )
            anomalies.append("No shutdown observation after the last active segment.")

        if not any(observation.type in WORK_START_EVENTS for observation in ordered):
            anomalies.append("No user activity detected for this day.")

        return DailyReport(
            date=day.isoformat(),
            observations=ordered,
            work_blocks=tuple(work_blocks),
            break_blocks=tuple(break_blocks),
            anomalies=tuple(anomalies),
        )

    def build_weekly(self, any_day: date, observations: Iterable[Observation]) -> WeeklyReport:
        week_start = any_day - timedelta(days=any_day.weekday())
        observations_by_day: dict[date, list[Observation]] = {
            week_start + timedelta(days=offset): [] for offset in range(7)
        }
        for observation in observations:
            observation_day = observation.observed_at.date()
            if observation_day in observations_by_day:
                observations_by_day[observation_day].append(observation)

        days = tuple(
            self.build_daily(day, observations_by_day[day]) for day in sorted(observations_by_day)
        )
        return WeeklyReport(week_start=week_start.isoformat(), days=days)

    @staticmethod
    def _label_for(observation_type: ObservationType) -> str | None:
        if observation_type in WORK_START_EVENTS:
            return "work"
        if observation_type in BREAK_START_EVENTS:
            return "break"
        if observation_type in DAY_END_EVENTS:
            return "offline"
        return None

    @staticmethod
    def _append_block(
        label: str,
        start: datetime,
        end: datetime,
        work_blocks: list[TimeBlock],
        break_blocks: list[TimeBlock],
    ) -> None:
        if end <= start:
            return
        block = TimeBlock(label=label, start=start, end=end)
        if label == "work":
            work_blocks.append(block)
        elif label == "break":
            break_blocks.append(block)
