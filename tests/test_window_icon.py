# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bd1.window_icon import WINDOW_ICON_PATH, apply_window_icon


class WindowIconTest(unittest.TestCase):
    def test_applies_active_icon_and_keeps_reference(self) -> None:
        root = Mock()
        icon = Mock()
        photo_image = Mock(return_value=icon)
        tkinter = SimpleNamespace(PhotoImage=photo_image, TclError=Exception)

        with (
            patch("bd1.window_icon.sys.platform", "win32"),
            patch.dict("sys.modules", {"tkinter": tkinter}),
        ):
            apply_window_icon(root)

        photo_image.assert_called_once_with(file=str(WINDOW_ICON_PATH))
        root.iconphoto.assert_called_once_with(True, icon)
        self.assertIs(icon, root._bd1_window_icon)

    def test_does_not_apply_icon_outside_windows(self) -> None:
        root = Mock()
        photo_image = Mock()
        tkinter = SimpleNamespace(PhotoImage=photo_image, TclError=Exception)

        with (
            patch("bd1.window_icon.sys.platform", "linux"),
            patch.dict("sys.modules", {"tkinter": tkinter}),
        ):
            apply_window_icon(root)

        photo_image.assert_not_called()
        root.iconphoto.assert_not_called()


if __name__ == "__main__":
    unittest.main()
