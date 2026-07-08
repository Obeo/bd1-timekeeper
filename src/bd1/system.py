from __future__ import annotations

from datetime import datetime

import psutil


def system_boot_time() -> datetime:
    return datetime.fromtimestamp(int(psutil.boot_time())).astimezone()
