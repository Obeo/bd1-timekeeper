# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest

from bd1.macos_dock import (
    MacOSDockController,
    NoOpDockController,
    create_dock_controller,
)


class MacOSDockControllerTest(unittest.TestCase):
    def test_show_activates_regular_application_and_hide_restores_accessory_mode(self) -> None:
        application = FakeApplication()
        controller = MacOSDockController(application)

        controller.show()
        controller.hide()

        self.assertEqual([0, 1], application.policies)
        self.assertEqual([True], application.activations)

    def test_factory_uses_no_op_controller_outside_macos(self) -> None:
        self.assertIsInstance(create_dock_controller("linux"), NoOpDockController)
        self.assertIsInstance(create_dock_controller("win32"), NoOpDockController)

    def test_factory_uses_macos_controller_on_darwin(self) -> None:
        self.assertIsInstance(create_dock_controller("darwin"), MacOSDockController)


class FakeApplication:
    def __init__(self) -> None:
        self.policies: list[int] = []
        self.activations: list[bool] = []

    def setActivationPolicy_(self, policy: int) -> None:
        self.policies.append(policy)

    def activateIgnoringOtherApps_(self, activate: bool) -> None:
        self.activations.append(activate)


if __name__ == "__main__":
    unittest.main()
