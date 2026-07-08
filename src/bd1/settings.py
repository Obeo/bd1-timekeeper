from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from bd1.paths import settings_path


@dataclass(frozen=True, slots=True)
class Settings:
    idle_threshold_minutes: int = 30
    autostart_enabled: bool = False
    notifications_enabled: bool = True
    icon_theme: str = "hd"
    activity_poll_seconds: float = 1.0

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
    return Settings(**data)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(asdict(settings), file, indent=2, sort_keys=True)
        file.write("\n")
