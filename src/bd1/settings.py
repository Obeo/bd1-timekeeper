# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import time
from pathlib import Path

from bd1.paths import settings_path

DEFAULT_LUNCH_AUTOMATIC_WORK_RESUME_TIME = "13:58"
LUNCH_AUTOMATIC_WORK_RESUME_TIME_MIN = "12:00"
LUNCH_AUTOMATIC_WORK_RESUME_TIME_MAX = "14:00"
DEFAULT_WEEKLY_CAP_HOURS = 37


@dataclass(frozen=True, slots=True)
class Settings:
    idle_threshold_minutes: int = 16
    autostart_enabled: bool = False
    notifications_enabled: bool = True
    icon_theme: str = "head-small"
    activity_poll_seconds: float = 10.0
    heartbeat_interval_seconds: float = 300.0
    idle_ignored_process_names: tuple[str, ...] = ("aomhost64.exe", "cpthost")
    lunch_automatic_work_resume_time: str = DEFAULT_LUNCH_AUTOMATIC_WORK_RESUME_TIME
    weekly_37h_cap_enabled: bool = False
    weekly_cap_hours: int = DEFAULT_WEEKLY_CAP_HOURS

    @property
    def idle_threshold_seconds(self) -> int:
        return self.idle_threshold_minutes * 60

    @property
    def lunch_automatic_work_resume(self) -> time:
        return parse_lunch_automatic_work_resume_time(
            self.lunch_automatic_work_resume_time,
            DEFAULT_LUNCH_AUTOMATIC_WORK_RESUME_TIME,
        )


def load_settings(path: Path | None = None) -> Settings:
    target = path or settings_path()
    if not target.exists():
        save_settings(Settings(), target)
        return Settings()

    with target.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    allowed = {field.name for field in Settings.__dataclass_fields__.values()}
    data = {key: value for key, value in raw.items() if key in allowed}
    if "idle_ignored_process_names" in data:
        names = data["idle_ignored_process_names"]
        if isinstance(names, str):
            names = (names,)
        elif not isinstance(names, (list, tuple)):
            names = ()
        data["idle_ignored_process_names"] = tuple(str(name) for name in names if str(name))
    if "lunch_automatic_work_resume_time" in data:
        data["lunch_automatic_work_resume_time"] = normalize_lunch_automatic_work_resume_time(
            data["lunch_automatic_work_resume_time"],
            DEFAULT_LUNCH_AUTOMATIC_WORK_RESUME_TIME,
        )
    if "weekly_cap_hours" in data:
        data["weekly_cap_hours"] = normalize_weekly_cap_hours(
            data["weekly_cap_hours"],
            DEFAULT_WEEKLY_CAP_HOURS,
        )
    return Settings(**data)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(asdict(settings), file, indent=2, sort_keys=True)
        file.write("\n")


def normalize_lunch_automatic_work_resume_time(value: object, default: str) -> str:
    if not isinstance(value, str):
        return default
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        return default
    minimum = time.fromisoformat(LUNCH_AUTOMATIC_WORK_RESUME_TIME_MIN)
    maximum = time.fromisoformat(LUNCH_AUTOMATIC_WORK_RESUME_TIME_MAX)
    if not minimum < parsed <= maximum:
        return default
    return parsed.strftime("%H:%M")


def parse_lunch_automatic_work_resume_time(value: object, default: str) -> time:
    return time.fromisoformat(normalize_lunch_automatic_work_resume_time(value, default))


def normalize_weekly_cap_hours(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return default
    return value
