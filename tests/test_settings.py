# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bd1.settings import Settings, load_settings, save_settings


class SettingsTest(unittest.TestCase):
    def test_round_trips_idle_ignored_process_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            settings = Settings(idle_ignored_process_names=("aomhost64.exe", "Teams.exe"))

            save_settings(settings, path)
            loaded = load_settings(path)

        self.assertEqual(("aomhost64.exe", "Teams.exe"), loaded.idle_ignored_process_names)

    def test_missing_idle_ignored_process_names_keeps_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"idle_threshold_minutes": 12}), encoding="utf-8")

            settings = load_settings(path)

        self.assertEqual(("aomhost64.exe",), settings.idle_ignored_process_names)


if __name__ == "__main__":
    unittest.main()
