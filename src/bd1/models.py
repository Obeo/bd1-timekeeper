# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


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


@dataclass(frozen=True, slots=True)
class WeeklyReport:
    week_start: str
    days: tuple[DailyReport, ...]

    @property
    def worked_seconds(self) -> int:
        return sum(day.worked_seconds for day in self.days)
