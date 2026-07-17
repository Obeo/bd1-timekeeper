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
from pathlib import Path

from bd1.paths import settings_path


@dataclass(frozen=True, slots=True)
class Settings:
    idle_threshold_minutes: int = 16
    autostart_enabled: bool = False
    notifications_enabled: bool = True
    icon_theme: str = "head-small"
    activity_poll_seconds: float = 10.0
    heartbeat_interval_seconds: float = 300.0
    idle_ignored_process_names: tuple[str, ...] = ("aomhost64.exe", "cpthost")

    @property
    def idle_threshold_seconds(self) -> int:
        return self.idle_threshold_minutes * 60


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
    return Settings(**data)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(asdict(settings), file, indent=2, sort_keys=True)
        file.write("\n")
