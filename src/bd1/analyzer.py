# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta

from bd1.calendar import is_working_day
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
WORK_BLOCK_MERGE_GAP_SECONDS = 2 * 60
HEARTBEAT_GAP_OFFLINE_SECONDS = 20 * 60
LUNCH_AUTOMATIC_RESUME_GRACE_SECONDS = 5 * 60
LUNCH_START = time(12, 0)
LUNCH_END = time(14, 0)
DEFAULT_LUNCH_AUTOMATIC_WORK_RESUME = time(13, 58)


class ReportAnalyzer:
    def __init__(
        self,
        now_provider: Callable[[], datetime] | None = None,
        lunch_automatic_work_resume: time = DEFAULT_LUNCH_AUTOMATIC_WORK_RESUME,
    ) -> None:
        self._now_provider = now_provider or (lambda: datetime.now().astimezone())
        self.lunch_automatic_work_resume = self._normalize_lunch_automatic_work_resume(
            lunch_automatic_work_resume
        )

    def build_daily(self, day: date, observations: Iterable[Observation]) -> DailyReport:
        ordered = tuple(sorted(observations, key=lambda item: (item.observed_at, item.id or 0)))
        interpreted = self._with_boot_as_work_start_when_app_started_late(
            self._with_offline_markers_for_heartbeat_gaps(ordered)
        )
        work_blocks: list[TimeBlock] = []
        break_blocks: list[TimeBlock] = []
        anomalies: list[str] = []

        current_label: str | None = None
        current_start: datetime | None = None
        pending_lunch_work_start: datetime | None = None

        for index, observation in enumerate(interpreted):
            if observation.type == ObservationType.APP_STOPPED:
                if current_label is not None and current_start is not None:
                    self._append_block(
                        current_label,
                        current_start,
                        observation.observed_at,
                        work_blocks,
                        break_blocks,
                    )
                current_label = None
                current_start = None
                pending_lunch_work_start = None
                if index == len(interpreted) - 1:
                    anomalies.append(
                        "Application stopped before a system shutdown was observed; "
                        "using it as the estimated day end."
                    )
                continue

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
            now = self._now_provider()
            if day < now.date():
                effective_end = self._last_known_end_for_closed_day(
                    interpreted,
                    pending_lunch_work_start,
                )
                anomalies.append(
                    "No shutdown observation after the last active segment; "
                    "stopping the past-day estimate at the last known observation."
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
            work_blocks=self._merge_close_work_blocks(work_blocks, break_blocks),
            break_blocks=tuple(break_blocks),
            anomalies=tuple(anomalies),
        )

    def build_weekly(self, any_day: date, observations: Iterable[Observation]) -> WeeklyReport:
        week_start = any_day - timedelta(days=any_day.weekday())
        observations_by_day: dict[date, list[Observation]] = {
            week_start + timedelta(days=offset): []
            for offset in range(7)
            if is_working_day(week_start + timedelta(days=offset))
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
    def _merge_close_work_blocks(
        work_blocks: list[TimeBlock],
        break_blocks: list[TimeBlock],
    ) -> tuple[TimeBlock, ...]:
        if not work_blocks:
            return ()

        merged = [work_blocks[0]]
        for block in work_blocks[1:]:
            previous = merged[-1]
            gap_seconds = (block.start - previous.end).total_seconds()
            has_break_between = any(
                break_block.start < block.start and break_block.end > previous.end
                for break_block in break_blocks
            )
            if 0 <= gap_seconds < WORK_BLOCK_MERGE_GAP_SECONDS and not has_break_between:
                merged[-1] = TimeBlock(
                    label="work",
                    start=previous.start,
                    end=max(previous.end, block.end),
                )
            else:
                merged.append(block)
        return tuple(merged)

    def _is_protected_lunch_resume(self, observed_at: datetime) -> bool:
        if not LUNCH_START <= observed_at.time() < self.lunch_automatic_work_resume:
            return False
        automatic_resume_at = self._lunch_automatic_work_resume_at(observed_at)
        seconds_before_resume = (automatic_resume_at - observed_at).total_seconds()
        return seconds_before_resume > LUNCH_AUTOMATIC_RESUME_GRACE_SECONDS

    @staticmethod
    def _normalize_lunch_automatic_work_resume(value: time) -> time:
        if LUNCH_START < value <= LUNCH_END:
            return value
        return DEFAULT_LUNCH_AUTOMATIC_WORK_RESUME

    def _lunch_automatic_work_resume_at(self, observed_at: datetime) -> datetime:
        return observed_at.replace(
            hour=self.lunch_automatic_work_resume.hour,
            minute=self.lunch_automatic_work_resume.minute,
            second=0,
            microsecond=0,
        )

    @staticmethod
    def _last_known_end_for_closed_day(
        observations: tuple[Observation, ...],
        pending_lunch_work_start: datetime | None,
    ) -> datetime:
        known_end = observations[-1].observed_at
        if pending_lunch_work_start is not None and pending_lunch_work_start > known_end:
            return pending_lunch_work_start
        return known_end

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

        if ReportAnalyzer._should_insert_default_lunch_break(boot, app_started, observations):
            return tuple(
                sorted(
                    (
                        *observations,
                        Observation(
                            observed_at=boot.observed_at.replace(
                                hour=LUNCH_START.hour,
                                minute=LUNCH_START.minute,
                                second=0,
                                microsecond=0,
                            ),
                            type=ObservationType.USER_BREAK,
                            metadata={"source": "inferred_late_app_start_lunch"},
                        ),
                        Observation(
                            observed_at=boot.observed_at.replace(
                                hour=LUNCH_END.hour,
                                minute=LUNCH_END.minute,
                                second=0,
                                microsecond=0,
                            ),
                            type=ObservationType.ACTIVITY_RESUMED,
                            metadata={"source": "inferred_late_app_start_lunch"},
                        ),
                    ),
                    key=lambda item: (item.observed_at, item.id or 0),
                )
            )

        return observations

    @staticmethod
    def _with_offline_markers_for_heartbeat_gaps(
        observations: tuple[Observation, ...],
    ) -> tuple[Observation, ...]:
        adjusted: list[Observation] = []
        previous: Observation | None = None
        current_label: str | None = None
        for observation in observations:
            if previous is not None and previous.type == ObservationType.APP_HEARTBEAT:
                gap_seconds = int((observation.observed_at - previous.observed_at).total_seconds())
                if gap_seconds > HEARTBEAT_GAP_OFFLINE_SECONDS and current_label == "work":
                    adjusted.append(
                        Observation(
                            observed_at=previous.observed_at,
                            type=ObservationType.APP_STOPPED,
                            metadata={
                                "source": "inferred_heartbeat_gap",
                                "gap_seconds": gap_seconds,
                            },
                        )
                    )
            adjusted.append(observation)
            next_label = ReportAnalyzer._label_for(observation.type)
            if observation.type == ObservationType.APP_STOPPED:
                current_label = None
            elif next_label is not None:
                current_label = None if observation.type in DAY_END_EVENTS else next_label
            previous = observation

        return tuple(sorted(adjusted, key=lambda item: (item.observed_at, item.id or 0)))

    @staticmethod
    def _should_insert_default_lunch_break(
        boot: Observation,
        app_started: Observation,
        observations: tuple[Observation, ...],
    ) -> bool:
        lunch_start = boot.observed_at.replace(
            hour=LUNCH_START.hour,
            minute=LUNCH_START.minute,
            second=0,
            microsecond=0,
        )
        lunch_end = boot.observed_at.replace(
            hour=LUNCH_END.hour,
            minute=LUNCH_END.minute,
            second=0,
            microsecond=0,
        )

        if not (boot.observed_at < lunch_start and app_started.observed_at >= lunch_end):
            return False

        return not any(
            observation.type not in {ObservationType.BOOT, ObservationType.APP_STARTED}
            and lunch_start <= observation.observed_at < lunch_end
            for observation in observations
        )
