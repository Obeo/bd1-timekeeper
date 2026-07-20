# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from bd1.models import ObservationType
from bd1.reports import (
    DAILY_TARGET_SECONDS,
    MINIMUM_CORRECTION_WORK_SECONDS,
    ReportService,
    correction_period_start,
)
from bd1.storage import ObservationStore


class ReportServiceTest(unittest.TestCase):
    def test_correction_period_starts_on_latest_june_first(self) -> None:
        self.assertEqual(date(2026, 6, 1), correction_period_start(date(2026, 7, 20)))
        self.assertEqual(date(2025, 6, 1), correction_period_start(date(2026, 5, 31)))

    def test_all_time_correction_ignores_weekends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-07-06T09:00:00+02:00"),
                )
                store.add(
                    ObservationType.SHUTDOWN,
                    datetime.fromisoformat("2026-07-06T16:24:00+02:00"),
                )
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-07-11T09:00:00+02:00"),
                )
                store.add(
                    ObservationType.SHUTDOWN,
                    datetime.fromisoformat("2026-07-11T18:00:00+02:00"),
                )
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-07-14T09:00:00+02:00"),
                )
                store.add(
                    ObservationType.SHUTDOWN,
                    datetime.fromisoformat("2026-07-14T16:24:00+02:00"),
                )
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-05-29T09:00:00+02:00"),
                )
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-07-07T09:00:00+02:00"),
                )
                store.add(
                    ObservationType.SHUTDOWN,
                    datetime.fromisoformat("2026-07-07T10:00:00+02:00"),
                )
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-07-20T09:00:00+02:00"),
                )
                store.add(
                    ObservationType.SHUTDOWN,
                    datetime.fromisoformat("2026-07-20T18:00:00+02:00"),
                )

                correction = ReportService(
                    store,
                    today_provider=lambda: date(2026, 7, 20),
                ).all_time_correction_seconds()
            finally:
                store.close()

        self.assertEqual(0, correction)
        self.assertEqual(7 * 3600 + 24 * 60, DAILY_TARGET_SECONDS)
        self.assertEqual(2 * 3600, MINIMUM_CORRECTION_WORK_SECONDS)


if __name__ == "__main__":
    unittest.main()
