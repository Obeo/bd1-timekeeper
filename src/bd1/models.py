# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Any

from bd1.calendar import is_working_day


class ObservationType(StrEnum):
    BOOT = "BOOT"
    SHUTDOWN = "SHUTDOWN"
    APP_STARTED = "APP_STARTED"
    APP_STOPPED = "APP_STOPPED"
    APP_HEARTBEAT = "APP_HEARTBEAT"
    FIRST_ACTIVITY = "FIRST_ACTIVITY"
    IDLE_STARTED = "IDLE_STARTED"
    ACTIVITY_RESUMED = "ACTIVITY_RESUMED"
    USER_WORKING = "USER_WORKING"
    USER_BREAK = "USER_BREAK"


class RuntimeState(StrEnum):
    OFFLINE = "OFFLINE"
    PC_ON = "PC_ON"
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"


@dataclass(frozen=True, slots=True)
class Observation:
    observed_at: datetime
    type: ObservationType
    metadata: dict[str, Any] | None = None
    id: int | None = None


@dataclass(frozen=True, slots=True)
class TimeBlock:
    label: str
    start: datetime
    end: datetime

    @property
    def seconds(self) -> int:
        return max(0, int((self.end - self.start).total_seconds()))


@dataclass(frozen=True, slots=True)
class DailyReport:
    date: str
    observations: tuple[Observation, ...]
    work_blocks: tuple[TimeBlock, ...]
    break_blocks: tuple[TimeBlock, ...]
    anomalies: tuple[str, ...]

    @property
    def worked_seconds(self) -> int:
        return sum(block.seconds for block in self.work_blocks)

    @property
    def break_seconds(self) -> int:
        return sum(block.seconds for block in self.break_blocks)


WEEKLY_DECLARATION_TARGET_SECONDS = 37 * 3600


@dataclass(frozen=True, slots=True)
class WeeklyDeclaration:
    target_seconds: int
    estimated_seconds: int
    proposed_days: tuple[DailyReport, ...]

    @property
    def proposed_seconds(self) -> int:
        return sum(day.worked_seconds for day in self.proposed_days)

    @property
    def remaining_seconds(self) -> int:
        return max(0, self.target_seconds - self.estimated_seconds)

    @property
    def excess_seconds(self) -> int:
        return max(0, self.estimated_seconds - self.target_seconds)


@dataclass(frozen=True, slots=True)
class WeeklyReport:
    week_start: str
    days: tuple[DailyReport, ...]

    @property
    def worked_seconds(self) -> int:
        return sum(day.worked_seconds for day in self._workdays)

    @property
    def break_seconds(self) -> int:
        return sum(day.break_seconds for day in self._workdays)

    @property
    def declaration(self) -> WeeklyDeclaration:
        return WeeklyDeclaration(
            target_seconds=WEEKLY_DECLARATION_TARGET_SECONDS,
            estimated_seconds=self.worked_seconds,
            proposed_days=_weekly_declaration_days(
                self._workdays,
                WEEKLY_DECLARATION_TARGET_SECONDS,
            ),
        )

    @property
    def _workdays(self) -> tuple[DailyReport, ...]:
        return tuple(day for day in self.days if is_working_day(date.fromisoformat(day.date)))


def _weekly_declaration_days(
    days: tuple[DailyReport, ...],
    target_seconds: int,
) -> tuple[DailyReport, ...]:
    estimated_seconds = sum(day.worked_seconds for day in days)
    if estimated_seconds <= target_seconds:
        return days

    worked_days = tuple(day for day in days if day.worked_seconds > 0)
    reductions = _distributed_reductions(
        tuple(day.worked_seconds for day in worked_days),
        estimated_seconds - target_seconds,
    )
    reductions_by_date = dict(zip((day.date for day in worked_days), reductions, strict=True))
    return tuple(_reduce_daily_work(day, reductions_by_date.get(day.date, 0)) for day in days)


def _distributed_reductions(durations: tuple[int, ...], total_reduction: int) -> tuple[int, ...]:
    if not durations or total_reduction <= 0:
        return tuple(0 for _duration in durations)

    total_duration = sum(durations)
    reductions = [total_reduction * duration // total_duration for duration in durations]
    remainder = total_reduction - sum(reductions)
    order = sorted(
        range(len(durations)),
        key=lambda index: (total_reduction * durations[index]) % total_duration,
        reverse=True,
    )
    for index in order[:remainder]:
        reductions[index] += 1
    return tuple(reductions)


def _reduce_daily_work(day: DailyReport, reduction_seconds: int) -> DailyReport:
    if reduction_seconds <= 0 or day.worked_seconds == 0:
        return day

    remaining_reduction = reduction_seconds
    reduced_blocks: list[TimeBlock] = []
    for block in reversed(day.work_blocks):
        if remaining_reduction <= 0:
            reduced_blocks.append(block)
            continue
        if remaining_reduction >= block.seconds:
            remaining_reduction -= block.seconds
            continue
        reduced_blocks.append(
            TimeBlock(
                label=block.label,
                start=block.start,
                end=block.end - timedelta(seconds=remaining_reduction),
            )
        )
        remaining_reduction = 0

    return DailyReport(
        date=day.date,
        observations=day.observations,
        work_blocks=tuple(reversed(reduced_blocks)),
        break_blocks=day.break_blocks,
        anomalies=day.anomalies,
    )
