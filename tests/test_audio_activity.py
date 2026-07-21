# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from bd1.audio_activity import is_microphone_used_by


class AudioActivityTest(unittest.TestCase):
    def test_detects_matching_source_output(self) -> None:
        output = """
Source Output #42
    Properties:
        application.name = "Google Chrome"
        application.process.binary = "chrome"
"""

        with (
            patch("bd1.audio_activity.shutil.which", return_value="/usr/bin/pactl"),
            patch(
                "bd1.audio_activity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, output, ""),
            ),
        ):
            self.assertTrue(is_microphone_used_by(("chrome",)))

    def test_returns_false_when_pactl_is_missing(self) -> None:
        with patch("bd1.audio_activity.shutil.which", return_value=None):
            self.assertFalse(is_microphone_used_by(("chrome",)))


if __name__ == "__main__":
    unittest.main()
