# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable

IdleSecondsProvider = Callable[[], float]


def default_idle_seconds_provider() -> IdleSecondsProvider | None:
    if not _is_gnome_wayland():
        return None
    return gnome_idle_seconds


def gnome_idle_seconds() -> float:
    completed = subprocess.run(
        (
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.gnome.Mutter.IdleMonitor",
            "--object-path",
            "/org/gnome/Mutter/IdleMonitor/Core",
            "--method",
            "org.gnome.Mutter.IdleMonitor.GetIdletime",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=2,
    )
    match = re.search(r"\b(\d+)\b(?=,?\))", completed.stdout)
    if match is None:
        raise RuntimeError("GNOME idle monitor did not return an idle duration")
    return int(match.group(0)) / 1000


def _is_gnome_wayland() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" and "gnome" in desktop
