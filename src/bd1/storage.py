from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from bd1.models import Observation, ObservationType
from bd1.paths import database_path


class ObservationStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def add(
        self,
        observation_type: ObservationType,
        observed_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Observation:
        observed_at = observed_at or datetime.now().astimezone()
        with self._connection:
            cursor = self._connection.execute(
                """
                INSERT INTO observations (observed_at, type, metadata_json)
                VALUES (?, ?, ?)
                """,
                (
                    observed_at.isoformat(),
                    observation_type.value,
                    json.dumps(metadata or {}, sort_keys=True),
                ),
            )
        return Observation(
            id=int(cursor.lastrowid),
            observed_at=observed_at,
            type=observation_type,
            metadata=metadata or {},
        )

    def list_between(self, start: datetime, end: datetime) -> tuple[Observation, ...]:
        rows = self._connection.execute(
            """
            SELECT id, observed_at, type, metadata_json
            FROM observations
            WHERE observed_at >= ? AND observed_at < ?
            ORDER BY observed_at ASC, id ASC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return tuple(self._row_to_observation(row) for row in rows)

    def list_for_day(self, day: date) -> tuple[Observation, ...]:
        start = datetime.combine(day, time.min).astimezone()
        return self.list_between(start, start + timedelta(days=1))

    def list_for_week(self, any_day: date) -> tuple[Observation, ...]:
        week_start = any_day - timedelta(days=any_day.weekday())
        start = datetime.combine(week_start, time.min).astimezone()
        return self.list_between(start, start + timedelta(days=7))

    def add_many(self, observations: Iterable[Observation]) -> None:
        with self._connection:
            self._connection.executemany(
                """
                INSERT INTO observations (observed_at, type, metadata_json)
                VALUES (?, ?, ?)
                """,
                [
                    (
                        observation.observed_at.isoformat(),
                        observation.type.value,
                        json.dumps(observation.metadata or {}, sort_keys=True),
                    )
                    for observation in observations
                ],
            )

    def _migrate(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    observed_at TEXT NOT NULL,
                    type TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_observations_observed_at
                ON observations (observed_at)
                """
            )

    @staticmethod
    def _row_to_observation(row: sqlite3.Row) -> Observation:
        metadata = json.loads(row["metadata_json"] or "{}")
        return Observation(
            id=int(row["id"]),
            observed_at=datetime.fromisoformat(row["observed_at"]),
            type=ObservationType(row["type"]),
            metadata=metadata,
        )
