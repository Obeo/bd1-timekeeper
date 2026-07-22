# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from bd1.idle import default_idle_seconds_provider, gnome_idle_seconds


class IdleTest(unittest.TestCase):
    def test_uses_gnome_idle_provider_on_gnome_wayland(self) -> None:
        with patch.dict(
            "os.environ",
            {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"},
        ):
            self.assertIs(gnome_idle_seconds, default_idle_seconds_provider())

    def test_does_not_use_gnome_idle_provider_on_x11(self) -> None:
        with patch.dict(
            "os.environ",
            {"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "GNOME"},
        ):
            self.assertIsNone(default_idle_seconds_provider())

    def test_parses_gnome_idle_time_as_seconds(self) -> None:
        completed = Mock(stdout="(uint64 12345,)")
        with patch("bd1.idle.subprocess.run", return_value=completed):
            self.assertEqual(12.345, gnome_idle_seconds())


if __name__ == "__main__":
    unittest.main()
