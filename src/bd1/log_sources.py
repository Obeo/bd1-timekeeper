# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

"""Observations gathered from logs the system and applications already write.

Every available source is read and the events are concatenated in time order.
A source reports when the user is present (ACTIVITY_RESUMED) and when the user
left (SHUTDOWN), so reports only show work time. An absence shorter than the
idle threshold is not a break: the live activity monitor would not have
reported it either.

The sources implemented so far exist on macOS only.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from bd1.mattermost_log import DEFAULT_MATTERMOST_LOG, mattermost_log_observations
from bd1.models import Observation, ObservationType
from bd1.power_log import DEFAULT_POWER_LOG_DIR, power_log_observations


def observations_from_logs(
    idle_threshold: timedelta,
    power_log_dir: Path = DEFAULT_POWER_LOG_DIR,
    mattermost_log: Path = DEFAULT_MATTERMOST_LOG,
) -> list[Observation]:
    observations = []
    if power_log_dir.is_dir():
        observations += power_log_observations(power_log_dir)
    if mattermost_log.is_file():
        observations += mattermost_log_observations(mattermost_log)
    if not observations:
        raise FileNotFoundError(f"No log source found: {power_log_dir}, {mattermost_log}")
    observations.sort(key=lambda item: item.observed_at)
    return without_short_absences(observations, idle_threshold)


def without_short_absences(
    observations: list[Observation],
    idle_threshold: timedelta,
) -> list[Observation]:
    kept: list[Observation] = []
    for observation in observations:
        previous = kept[-1] if kept else None
        left = previous is not None and previous.type == ObservationType.SHUTDOWN
        if left and observation.type == ObservationType.SHUTDOWN:
            continue
        if left and observation.observed_at - previous.observed_at < idle_threshold:
            kept.pop()
            if kept:
                continue
        kept.append(observation)
    return kept
