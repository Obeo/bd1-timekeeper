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
from datetime import time
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

        self.assertEqual(
            ("aomhost64.exe", "cpthost"),
            settings.idle_ignored_process_names,
        )

    def test_round_trips_lunch_automatic_work_resume_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            settings = Settings(lunch_automatic_work_resume_time="13:45")

            save_settings(settings, path)
            loaded = load_settings(path)

        self.assertEqual("13:45", loaded.lunch_automatic_work_resume_time)
        self.assertEqual(time(13, 45), loaded.lunch_automatic_work_resume)

    def test_invalid_lunch_automatic_work_resume_time_keeps_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(
                json.dumps({"lunch_automatic_work_resume_time": "not-a-time"}),
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual("13:58", settings.lunch_automatic_work_resume_time)
        self.assertEqual(time(13, 58), settings.lunch_automatic_work_resume)

    def test_lunch_automatic_work_resume_time_before_lunch_keeps_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(
                json.dumps({"lunch_automatic_work_resume_time": "11:00"}),
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual("13:58", settings.lunch_automatic_work_resume_time)
        self.assertEqual(time(13, 58), settings.lunch_automatic_work_resume)

    def test_lunch_automatic_work_resume_time_after_lunch_keeps_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(
                json.dumps({"lunch_automatic_work_resume_time": "15:00"}),
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual("13:58", settings.lunch_automatic_work_resume_time)
        self.assertEqual(time(13, 58), settings.lunch_automatic_work_resume)

    def test_lunch_automatic_work_resume_time_accepts_lunch_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(
                json.dumps({"lunch_automatic_work_resume_time": "14:00"}),
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual("14:00", settings.lunch_automatic_work_resume_time)
        self.assertEqual(time(14, 0), settings.lunch_automatic_work_resume)


if __name__ == "__main__":
    unittest.main()
