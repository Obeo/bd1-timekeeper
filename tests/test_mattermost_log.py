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
from datetime import datetime
from pathlib import Path

from bd1.mattermost_log import mattermost_log_observations
from bd1.models import ObservationType

LOG_LINES = """\
[2026-09-17 15:50:53.101] [info]  [MainWindow] showing main window
[2026-09-17 15:50:53.102] [warn]  [WebContentsEventM...] [renderer] Polling websocket
[2026-09-17 15:51:10.500] [info]  [UpdateNotifier] Checking for updates { manually: false }
[2026-09-17 16:10:22.010] [info]  [MainWindow] showing main window
"""


class MattermostLogTest(unittest.TestCase):
    def test_only_window_shown_lines_become_observations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.log"
            path.write_text(LOG_LINES, encoding="utf-8")

            observations = mattermost_log_observations(path)

        self.assertEqual(
            [(item.observed_at, item.type) for item in observations],
            [
                (datetime(2026, 9, 17, 15, 50, 53).astimezone(), ObservationType.ACTIVITY_RESUMED),
                (datetime(2026, 9, 17, 16, 10, 22).astimezone(), ObservationType.ACTIVITY_RESUMED),
            ],
        )
        self.assertEqual(observations[0].metadata, {"source": "mattermost_log"})


if __name__ == "__main__":
    unittest.main()
