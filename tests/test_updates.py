# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import io
import json
import unittest
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from bd1.updates import AvailableUpdate, find_update, installed_version


class UpdateCheckTest(unittest.TestCase):
    @patch("bd1.updates.version", return_value="0.2.0")
    def test_reads_the_installed_version(self, _version) -> None:
        self.assertEqual("0.2.0", installed_version())

    @patch("bd1.updates.version", side_effect=PackageNotFoundError)
    def test_uses_dev_when_the_package_is_not_installed(self, _version) -> None:
        self.assertEqual("dev", installed_version())

    @patch("bd1.updates.urllib.request.urlopen")
    def test_returns_platform_asset_for_newer_release(self, urlopen) -> None:
        urlopen.return_value = _response(
            {
                "tag_name": "v0.2.0",
                "assets": [
                    {
                        "name": "bd1-windows-x86_64.exe",
                        "browser_download_url": "https://github.com/Obeo/bd1-timekeeper/releases/download/v0.2.0/bd1-windows-x86_64.exe",
                    }
                ],
            }
        )

        update = find_update("0.1.0", "win32")

        self.assertEqual(
            AvailableUpdate(
                "0.2.0",
                "https://github.com/Obeo/bd1-timekeeper/releases/download/v0.2.0/bd1-windows-x86_64.exe",
            ),
            update,
        )

    @patch("bd1.updates.urllib.request.urlopen")
    def test_ignores_same_or_older_release(self, urlopen) -> None:
        urlopen.return_value = _response({"tag_name": "v0.1.0", "assets": []})

        self.assertIsNone(find_update("0.1.0", "linux"))

    @patch("bd1.updates.urllib.request.urlopen", side_effect=OSError("offline"))
    def test_network_failure_does_not_escape(self, _urlopen) -> None:
        self.assertIsNone(find_update("0.1.0", "darwin"))

    @patch("bd1.updates.urllib.request.urlopen")
    def test_rejects_untrusted_download_url(self, urlopen) -> None:
        urlopen.return_value = _response(
            {
                "tag_name": "v0.2.0",
                "assets": [
                    {
                        "name": "bd1-linux-x86_64.tar.gz",
                        "browser_download_url": "https://example.com/bd1-linux-x86_64.tar.gz",
                    }
                ],
            }
        )

        self.assertIsNone(find_update("0.1.0", "linux"))


def _response(payload: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(payload).encode())


if __name__ == "__main__":
    unittest.main()
