# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest
from argparse import Namespace
from unittest.mock import patch

from bd1.__main__ import _handle_mattermost_command
from bd1.settings import Settings


class MattermostCliTest(unittest.TestCase):
    def test_configures_url_and_stores_hidden_token(self) -> None:
        args = Namespace(configure_mattermost=True, disable_mattermost=False)
        with (
            patch("bd1.__main__.load_settings", return_value=Settings()),
            patch("bd1.__main__.save_settings") as save,
            patch("builtins.input", return_value="https://mattermost.example.com/"),
            patch("bd1.__main__.getpass", return_value="secret"),
            patch("bd1.mattermost.verify_token") as verify,
            patch("bd1.mattermost.store_token") as store,
        ):
            result = _handle_mattermost_command(args)

        verify.assert_called_once_with("https://mattermost.example.com", "secret")
        store.assert_called_once_with("https://mattermost.example.com", "secret")
        self.assertEqual(
            "https://mattermost.example.com",
            save.call_args.args[0].mattermost_url,
        )
        self.assertNotIn("secret", result)

    def test_disables_integration_and_removes_token(self) -> None:
        args = Namespace(configure_mattermost=False, disable_mattermost=True)
        settings = Settings(mattermost_url="https://mattermost.example.com")
        with (
            patch("bd1.__main__.load_settings", return_value=settings),
            patch("bd1.__main__.save_settings") as save,
            patch("bd1.mattermost.get_token", return_value="secret"),
            patch("bd1.mattermost.remove_bd1_status", return_value=True),
            patch("bd1.mattermost.delete_token") as delete,
        ):
            result = _handle_mattermost_command(args)

        delete.assert_called_once_with("https://mattermost.example.com")
        self.assertEqual("", save.call_args.args[0].mattermost_url)
        self.assertIn("custom status cleared", result)


if __name__ == "__main__":
    unittest.main()
