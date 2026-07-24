# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

WINDOW_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icons" / "head_16" / "active.png"


def apply_window_icon(root: Any) -> None:
    if sys.platform != "win32":
        return

    import tkinter as tk

    with suppress(tk.TclError, OSError):
        icon = tk.PhotoImage(file=str(WINDOW_ICON_PATH))
        root.iconphoto(True, icon)
        root._bd1_window_icon = icon
