from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from bd1.models import DailyReport, Observation, ObservationType, TimeBlock, WeeklyReport

WORK_START_EVENTS = {
    ObservationType.FIRST_ACTIVITY,
    ObservationType.ACTIVITY_RESUMED,
    ObservationType.USER_WORKING,
}
AUTOMATIC_WORK_START_EVENTS = {
    ObservationType.FIRST_ACTIVITY,
    ObservationType.ACTIVITY_RESUMED,
}
BREAK_START_EVENTS = {
    ObservationType.IDLE_STARTED,
    ObservationType.USER_BREAK,
}
DAY_END_EVENTS = {ObservationType.SHUTDOWN}
LATE_APP_START_AFTER_BOOT_SECONDS = 60 * 60
SHORT_AUTOMATIC_RESUME_SECONDS = 5 * 60
LUNCH_START = time(12, 0)
LUNCH_AUTOMATIC_WORK_RESUME = time(13, 58)


class ReportAnalyzer:
    def build_daily(self, day: date, observations: Iterable[Observation]) -> DailyReport:
        ordered = tuple(sorted(observations, key=lambda item: (item.observed_at, item.id or 0)))
        interpreted = self._with_boot_as_work_start_when_app_started_late(ordered)
        work_blocks: list[TimeBlock] = []
        break_blocks: list[TimeBlock] = []
        anomalies: list[str] = []

        current_label: str | None = None
        current_start: datetime | None = None
        pending_lunch_work_start: datetime | None = None

        for index, observation in enumerate(interpreted):
            if (
                pending_lunch_work_start is not None
                and observation.observed_at >= pending_lunch_work_start
                and current_label == "break"
                and current_start is not None
            ):
                self._append_block(
                    current_label,
                    current_start,
                    pending_lunch_work_start,
                    work_blocks,
                    break_blocks,
                )
                current_label = "work"
                current_start = pending_lunch_work_start
                pending_lunch_work_start = None

            next_label = self._label_for(observation.type)
            if next_label is None:
                continue

            if (
                current_label == "break"
                and observation.type in AUTOMATIC_WORK_START_EVENTS
                and self._is_short_automatic_resume(interpreted, index)
            ):
                continue

            if (
                current_label == "break"
                and observation.type in AUTOMATIC_WORK_START_EVENTS
                and self._is_protected_lunch_resume(observation.observed_at)
            ):
                pending_lunch_work_start = self._lunch_automatic_work_resume_at(
                    observation.observed_at
                )
                continue

            if observation.type == ObservationType.USER_BREAK:
                pending_lunch_work_start = None

            if next_label == current_label:
                continue

            pending_lunch_work_start = None

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
            app_stopped_at = self._last_app_stopped_at(ordered)
            if app_stopped_at is not None and app_stopped_at > current_start:
                effective_end = min(end_of_day, app_stopped_at)
                anomalies.append(
                    "Application stopped before a system shutdown was observed; "
                    "using it as the estimated day end."
                )
            else:
                effective_end = min(end_of_day, now)
                anomalies.append("No shutdown observation after the last active segment.")

            if (
                pending_lunch_work_start is not None
                and current_label == "break"
                and pending_lunch_work_start < effective_end
            ):
                self._append_block(
                    current_label,
                    current_start,
                    pending_lunch_work_start,
                    work_blocks,
                    break_blocks,
                )
                current_label = "work"
                current_start = pending_lunch_work_start
            self._append_block(
                current_label,
                current_start,
                effective_end,
                work_blocks,
                break_blocks,
            )

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
        if observation_type == ObservationType.BOOT:
            return "work"
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

    @staticmethod
    def _is_protected_lunch_resume(observed_at: datetime) -> bool:
        return LUNCH_START <= observed_at.time() < LUNCH_AUTOMATIC_WORK_RESUME

    @staticmethod
    def _lunch_automatic_work_resume_at(observed_at: datetime) -> datetime:
        return observed_at.replace(
            hour=LUNCH_AUTOMATIC_WORK_RESUME.hour,
            minute=LUNCH_AUTOMATIC_WORK_RESUME.minute,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def _last_app_stopped_at(observations: tuple[Observation, ...]) -> datetime | None:
        if not observations or observations[-1].type != ObservationType.APP_STOPPED:
            return None
        return observations[-1].observed_at

    @staticmethod
    def _is_short_automatic_resume(
        observations: tuple[Observation, ...],
        index: int,
    ) -> bool:
        observation = observations[index]
        next_break = next(
            (
                candidate
                for candidate in observations[index + 1 :]
                if candidate.type in BREAK_START_EVENTS
            ),
            None,
        )
        if next_break is None:
            return False

        resume_seconds = int((next_break.observed_at - observation.observed_at).total_seconds())
        return 0 <= resume_seconds <= SHORT_AUTOMATIC_RESUME_SECONDS

    @staticmethod
    def _with_boot_as_work_start_when_app_started_late(
        observations: tuple[Observation, ...],
    ) -> tuple[Observation, ...]:
        boot = next(
            (
                observation
                for observation in observations
                if observation.type == ObservationType.BOOT
            ),
            None,
        )
        app_started = next(
            (
                observation
                for observation in observations
                if observation.type == ObservationType.APP_STARTED
            ),
            None,
        )
        if boot is None or app_started is None:
            return tuple(
                observation
                for observation in observations
                if observation.type != ObservationType.BOOT
            )

        if app_started.observed_at <= boot.observed_at:
            return tuple(
                observation
                for observation in observations
                if observation.type != ObservationType.BOOT
            )

        gap_seconds = int((app_started.observed_at - boot.observed_at).total_seconds())
        if gap_seconds < LATE_APP_START_AFTER_BOOT_SECONDS:
            return tuple(
                observation
                for observation in observations
                if observation.type != ObservationType.BOOT
            )

        has_work_signal_after_app_start = any(
            observation.type in WORK_START_EVENTS
            and observation.observed_at >= app_started.observed_at
            for observation in observations
        )
        if not has_work_signal_after_app_start:
            return tuple(
                observation
                for observation in observations
                if observation.type != ObservationType.BOOT
            )

        return observations
