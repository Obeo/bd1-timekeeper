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

from bd1.settings import (
    DEFAULT_VPN_INTERFACE_PATTERNS,
    DEFAULT_WEEKLY_CAP_HOURS,
    Settings,
    load_settings,
    save_settings,
)


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

    def test_weekly_37h_cap_is_disabled_by_default(self) -> None:
        self.assertFalse(Settings().weekly_37h_cap_enabled)

    def test_round_trips_weekly_37h_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_settings(Settings(weekly_37h_cap_enabled=True), path)
            loaded = load_settings(path)

        self.assertTrue(loaded.weekly_37h_cap_enabled)

    def test_weekly_cap_hours_defaults_to_37(self) -> None:
        self.assertEqual(DEFAULT_WEEKLY_CAP_HOURS, Settings().weekly_cap_hours)

    def test_round_trips_weekly_cap_hours(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_settings(Settings(weekly_cap_hours=20), path)
            loaded = load_settings(path)

        self.assertEqual(20, loaded.weekly_cap_hours)

    def test_round_trips_eurecia_connection_without_a_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_settings(
                Settings(
                    eurecia_base_url="https://tenant.example/eurecia/",
                    eurecia_email="user@example.com",
                ),
                path,
            )

            loaded = load_settings(path)
            raw = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual("https://tenant.example/eurecia/", loaded.eurecia_base_url)
        self.assertEqual("user@example.com", loaded.eurecia_email)
        self.assertNotIn("password", raw)

    def test_invalid_weekly_cap_hours_keeps_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"weekly_cap_hours": 0}), encoding="utf-8")

            settings = load_settings(path)

        self.assertEqual(DEFAULT_WEEKLY_CAP_HOURS, settings.weekly_cap_hours)

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

    def test_round_trips_mattermost_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_settings(
                Settings(
                    mattermost_url="https://mattermost.example.com",
                    vpn_interface_patterns=("tun*", "Corporate VPN"),
                ),
                path,
            )

            settings = load_settings(path)

        self.assertEqual("https://mattermost.example.com", settings.mattermost_url)
        self.assertEqual(("tun*", "Corporate VPN"), settings.vpn_interface_patterns)

    def test_invalid_mattermost_settings_keep_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(
                json.dumps({"mattermost_url": 42, "vpn_interface_patterns": 42}),
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual("", settings.mattermost_url)
        self.assertEqual(DEFAULT_VPN_INTERFACE_PATTERNS, settings.vpn_interface_patterns)
        self.assertEqual(DEFAULT_VPN_INTERFACE_PATTERNS, Settings().vpn_interface_patterns)

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
