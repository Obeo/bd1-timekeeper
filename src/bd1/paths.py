# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir

APP_AUTHOR = "BD-1"
APP_NAME = "BD-1"


def data_dir() -> Path:
    path = Path(user_data_dir(APP_NAME, APP_AUTHOR))
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "bd1.db"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def icon_dir() -> Path:
    return Path(__file__).resolve().parent / "assets" / "icons" / "head-small"
