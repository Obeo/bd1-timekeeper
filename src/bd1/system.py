# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from datetime import datetime

import psutil


def system_boot_time() -> datetime:
    return datetime.fromtimestamp(int(psutil.boot_time())).astimezone()
