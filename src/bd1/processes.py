# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from collections.abc import Iterable

import psutil


def is_any_process_running(process_names: Iterable[str]) -> bool:
    expected = {name.lower() for name in process_names if name}
    if not expected:
        return False

    for process in psutil.process_iter(["name"]):
        try:
            name = process.info.get("name")
        except (psutil.Error, OSError):
            continue
        if isinstance(name, str) and name.lower() in expected:
            return True

    return False
