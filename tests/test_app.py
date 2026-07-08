from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from bd1.app import BD1Application
from bd1.models import ObservationType
from bd1.settings import Settings
from bd1.storage import ObservationStore


class BD1ApplicationTest(unittest.TestCase):
    def test_records_system_boot_once_for_same_boot_timestamp(self) -> None:
        boot_time = datetime.fromisoformat("2026-07-08T07:12:00+02:00")

        with tempfile.TemporaryDirectory() as tmp:
            store = ObservationStore(Path(tmp) / "bd1.db")
            try:
                app = BD1Application(
                    Settings(),
                    store,
                    activity_monitor_enabled=False,
                    boot_time_provider=lambda: boot_time,
                )

                app._record_system_boot()
                app._record_system_boot()

                observations = store.list_for_day(boot_time.date())
            finally:
                store.close()

        boots = [
            observation for observation in observations if observation.type == ObservationType.BOOT
        ]
        self.assertEqual(1, len(boots))
        self.assertEqual({"source": "system_boot"}, boots[0].metadata)


if __name__ == "__main__":
    unittest.main()
