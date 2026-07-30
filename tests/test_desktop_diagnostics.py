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
from unittest.mock import patch

from bd1 import __main__


class DesktopDiagnosticsTest(unittest.TestCase):
    def test_appindicator_backend_accepts_appindicator_namespace(self) -> None:
        gi = SimpleNamespace(require_version=lambda namespace, version: None)

        with (
            patch("bd1.__main__.find_spec", return_value=True),
            patch.dict("sys.modules", {"gi": gi}),
            patch("bd1.__main__.importlib.import_module", return_value=object()),
        ):
            self.assertEqual("AppIndicator3", __main__._appindicator_backend_name())

    def test_appindicator_backend_falls_back_to_ayatana_namespace(self) -> None:
        def require_version(namespace: str, version: str) -> None:
            if namespace == "AppIndicator3":
                raise ValueError("missing")

        gi = SimpleNamespace(require_version=require_version)

        with (
            patch("bd1.__main__.find_spec", return_value=True),
            patch.dict("sys.modules", {"gi": gi}),
            patch("bd1.__main__.importlib.import_module", return_value=object()),
        ):
            self.assertEqual("AyatanaAppIndicator3", __main__._appindicator_backend_name())

    def test_gnome_extension_status_detects_enabled_appindicator(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="appindicatorsupport@rgcjonas.gmail.com\n")

        with (
            patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "GNOME"}),
            patch("bd1.__main__.shutil.which", return_value="/usr/bin/gnome-extensions"),
            patch("bd1.__main__.subprocess.run", return_value=completed),
        ):
            self.assertEqual("enabled", __main__._gnome_appindicator_extension_status())

    def test_gnome_extension_status_detects_missing_extension(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="background-logo@fedorahosted.org\n")

        with (
            patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "GNOME"}),
            patch("bd1.__main__.shutil.which", return_value="/usr/bin/gnome-extensions"),
            patch("bd1.__main__.subprocess.run", return_value=completed),
        ):
            self.assertEqual("missing-or-disabled", __main__._gnome_appindicator_extension_status())


if __name__ == "__main__":
    unittest.main()
