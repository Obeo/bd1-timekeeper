# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

"""Observations built from the macOS power management log, without any live listener.

The display is turned on when the user is there. The display turned off, or
an idle, lid or software sleep, means the user left. Maintenance wakes and
sleeps happen while the user is away and are ignored.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from bd1.asl import read_asl_messages
from bd1.models import Observation, ObservationType

DEFAULT_POWER_LOG_DIR = Path("/private/var/log/powermanagement")
METADATA = {"source": "power_log"}

PRESENT = ("Display is turned on",)
AWAY = (
    "Display is turned off",
    "Entering Sleep state due to 'Idle Sleep'",
    "Entering Sleep state due to 'Clamshell Sleep'",
    "Entering Sleep state due to 'Software Sleep'",
)


def power_log_observations(directory: Path = DEFAULT_POWER_LOG_DIR) -> list[Observation]:
    observations = []
    for path in sorted(directory.glob("*.asl")):
        for observed_at, message in read_asl_messages(path):
            if message.startswith(PRESENT):
                observations.append(_observation(observed_at, ObservationType.ACTIVITY_RESUMED))
            elif message.startswith(AWAY):
                observations.append(_observation(observed_at, ObservationType.SHUTDOWN))
    return observations


def _observation(observed_at: datetime, observation_type: ObservationType) -> Observation:
    return Observation(observed_at=observed_at, type=observation_type, metadata=METADATA)
