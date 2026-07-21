# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import date, datetime
from pathlib import Path

from bd1.models import ObservationType
from bd1.storage import ObservationStore


class ObservationStoreTest(unittest.TestCase):
    def test_persists_and_lists_observations_for_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-07-08T08:31:00+02:00"),
                    {"source": "test"},
                )
                store.add(
                    ObservationType.SHUTDOWN,
                    datetime.fromisoformat("2026-07-09T18:04:00+02:00"),
                )

                observations = store.list_for_day(date(2026, 7, 8))
            finally:
                store.close()

        self.assertEqual(1, len(observations))
        self.assertEqual(ObservationType.FIRST_ACTIVITY, observations[0].type)
        self.assertEqual({"source": "test"}, observations[0].metadata)

    def test_accepts_observations_from_multiple_threads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                threads = [
                    threading.Thread(
                        target=store.add,
                        args=(ObservationType.FIRST_ACTIVITY,),
                    )
                    for _ in range(5)
                ]

                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                observations = store.list_for_day(date.today())
            finally:
                store.close()

        self.assertEqual(5, len(observations))

    def test_checks_observation_existence_at_exact_time(self) -> None:
        observed_at = datetime.fromisoformat("2026-07-08T08:31:00+02:00")
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                self.assertFalse(store.exists_at(ObservationType.BOOT, observed_at))
                store.add(ObservationType.BOOT, observed_at, {"source": "system_boot"})
                self.assertTrue(store.exists_at(ObservationType.BOOT, observed_at))
                self.assertFalse(store.exists_at(ObservationType.SHUTDOWN, observed_at))
            finally:
                store.close()

    def test_lists_all_observations_in_time_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                store.add(
                    ObservationType.SHUTDOWN,
                    datetime.fromisoformat("2026-07-08T18:00:00+02:00"),
                )
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-07-08T09:00:00+02:00"),
                )
                observations = store.list_all()
            finally:
                store.close()

        self.assertEqual(ObservationType.FIRST_ACTIVITY, observations[0].type)
        self.assertEqual(ObservationType.SHUTDOWN, observations[1].type)

    def test_deletes_observations_for_one_day_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-07-08T09:00:00+02:00"),
                )
                store.add(
                    ObservationType.FIRST_ACTIVITY,
                    datetime.fromisoformat("2026-07-09T09:00:00+02:00"),
                )
                store.add(
                    ObservationType.SHUTDOWN,
                    datetime.fromisoformat("2026-07-09T18:00:00+02:00"),
                )

                deleted_count = store.delete_for_day(date(2026, 7, 9))
                remaining_observations = store.list_all()
            finally:
                store.close()

        self.assertEqual(2, deleted_count)
        self.assertEqual(1, len(remaining_observations))
        self.assertEqual(date(2026, 7, 8), remaining_observations[0].observed_at.date())


if __name__ == "__main__":
    unittest.main()
