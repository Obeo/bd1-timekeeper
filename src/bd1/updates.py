# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urlsplit

LOGGER = logging.getLogger(__name__)
LATEST_RELEASE_URL = "https://api.github.com/repos/Obeo/bd1-timekeeper/releases/latest"
ASSET_NAMES = {
    "win32": "bd1-windows-x86_64.exe",
    "linux": "bd1-linux-x86_64.tar.gz",
    "darwin": "bd1-macos-arm64.zip",
}


@dataclass(frozen=True, slots=True)
class AvailableUpdate:
    version: str
    download_url: str


def installed_version() -> str:
    try:
        return version("bd1")
    except PackageNotFoundError:
        return "dev"


def find_update(
    current_version: str | None = None,
    platform_name: str | None = None,
) -> AvailableUpdate | None:
    asset_name = ASSET_NAMES.get(platform_name or sys.platform)
    if asset_name is None:
        return None

    try:
        installed = _semantic_version(current_version or installed_version())
        request = urllib.request.Request(
            LATEST_RELEASE_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"BD-1/{'.'.join(map(str, installed))}",
            },
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            release = json.load(response)
        tag_name = release["tag_name"]
        if not tag_name.startswith("v"):
            raise ValueError(f"Invalid release tag: {tag_name}")
        available = _semantic_version(tag_name[1:])
        assets = release["assets"]
    except (OSError, PackageNotFoundError, AttributeError, TypeError, ValueError, KeyError):
        LOGGER.info("Could not check for a BD-1 update", exc_info=True)
        return None

    if available <= installed or not isinstance(assets, list):
        return None

    for asset in assets:
        if not isinstance(asset, dict) or asset.get("name") != asset_name:
            continue
        download_url = asset.get("browser_download_url")
        if _is_release_download(download_url):
            return AvailableUpdate(".".join(map(str, available)), download_url)
    return None


def _semantic_version(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"Invalid release version: {value}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _is_release_download(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.path.startswith("/Obeo/bd1-timekeeper/releases/download/")
    )
