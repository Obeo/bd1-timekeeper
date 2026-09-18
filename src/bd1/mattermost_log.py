# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

"""Observations built from the Mattermost desktop application log.

Only the lines recording the main window being shown are user actions.
Connection, polling and update lines also happen while the machine wakes on
its own and are ignored. The default path is the macOS one.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from bd1.models import Observation, ObservationType

DEFAULT_MATTERMOST_LOG = Path.home() / "Library" / "Logs" / "Mattermost" / "main.log"
METADATA = {"source": "mattermost_log"}

WINDOW_SHOWN = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+\] \[info\]\s+\[MainWindow\] showing main window"
)


def mattermost_log_observations(path: Path = DEFAULT_MATTERMOST_LOG) -> list[Observation]:
    observations = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = WINDOW_SHOWN.match(line)
        if match:
            observed_at = datetime.strptime(match[1], "%Y-%m-%d %H:%M:%S").astimezone()
            observations.append(
                Observation(
                    observed_at=observed_at,
                    type=ObservationType.ACTIVITY_RESUMED,
                    metadata=METADATA,
                )
            )
    return observations
