from __future__ import annotations

import tempfile
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


if __name__ == "__main__":
    unittest.main()
