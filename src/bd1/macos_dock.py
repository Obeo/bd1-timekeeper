# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import sys
from typing import Any, Protocol


class DockController(Protocol):
    def show(self) -> None: ...

    def hide(self) -> None: ...


class NoOpDockController:
    def show(self) -> None:
        return

    def hide(self) -> None:
        return


class MacOSDockController:
    """Switch the current macOS process between accessory and regular modes."""

    def __init__(self, application: Any | None = None) -> None:
        self._application = application
        self._regular_policy: int | None = None
        self._accessory_policy: int | None = None

    def show(self) -> None:
        application = self._load_application()
        application.setActivationPolicy_(self._regular_policy)
        application.activateIgnoringOtherApps_(True)

    def hide(self) -> None:
        application = self._load_application()
        application.setActivationPolicy_(self._accessory_policy)

    def _load_application(self) -> Any:
        if self._application is None:
            from AppKit import (
                NSApplication,
                NSApplicationActivationPolicyAccessory,
                NSApplicationActivationPolicyRegular,
            )

            self._application = NSApplication.sharedApplication()
            self._regular_policy = NSApplicationActivationPolicyRegular
            self._accessory_policy = NSApplicationActivationPolicyAccessory
        elif self._regular_policy is None or self._accessory_policy is None:
            # AppKit's activation policy values are stable API constants. Keeping
            # them here makes injecting a fake NSApplication straightforward.
            self._regular_policy = 0
            self._accessory_policy = 1
        return self._application


def create_dock_controller(platform_name: str | None = None) -> DockController:
    if (platform_name or sys.platform) == "darwin":
        return MacOSDockController()
    return NoOpDockController()
