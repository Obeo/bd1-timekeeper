# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest
from unittest.mock import patch

from bd1.mattermost import MattermostError
from bd1.mattermost_window import (
    _parse_vpn_patterns,
    configure_mattermost,
    disable_mattermost,
)
from bd1.settings import DEFAULT_VPN_INTERFACE_PATTERNS, Settings


class MattermostWindowConfigurationTest(unittest.TestCase):
    def test_configures_url_token_and_vpn_patterns(self) -> None:
        settings = Settings(mattermost_url="https://old.example.com")

        with (
            patch("bd1.mattermost_window.verify_token") as verify,
            patch("bd1.mattermost_window.store_token") as store,
            patch("bd1.mattermost_window.delete_token") as delete,
            patch("bd1.mattermost_window.save_settings") as save,
        ):
            updated = configure_mattermost(
                settings,
                " https://mattermost.example.com/ ",
                " secret ",
                "tun*, OpenVPN*, tun*",
            )

        self.assertEqual("https://mattermost.example.com", updated.mattermost_url)
        self.assertEqual(("tun*", "OpenVPN*"), updated.vpn_interface_patterns)
        verify.assert_called_once_with("https://mattermost.example.com", "secret")
        store.assert_called_once_with("https://mattermost.example.com", "secret")
        delete.assert_called_once_with("https://old.example.com")
        save.assert_called_once_with(updated)

    def test_blank_token_keeps_the_stored_token(self) -> None:
        settings = Settings(mattermost_url="https://mattermost.example.com")

        with (
            patch("bd1.mattermost_window.get_token", return_value="stored") as get,
            patch("bd1.mattermost_window.verify_token") as verify,
            patch("bd1.mattermost_window.store_token") as store,
            patch("bd1.mattermost_window.save_settings"),
        ):
            configure_mattermost(settings, settings.mattermost_url, "", "")

        get.assert_called_once_with(settings.mattermost_url)
        verify.assert_called_once_with(settings.mattermost_url, "stored")
        store.assert_not_called()

    def test_empty_vpn_patterns_restore_cross_platform_defaults(self) -> None:
        self.assertEqual(DEFAULT_VPN_INTERFACE_PATTERNS, _parse_vpn_patterns(" , \n"))

    def test_disables_even_if_remote_status_cleanup_fails(self) -> None:
        settings = Settings(mattermost_url="https://mattermost.example.com")

        with (
            patch("bd1.mattermost_window.get_token", return_value="stored"),
            patch(
                "bd1.mattermost_window.remove_bd1_status",
                side_effect=MattermostError("offline"),
            ),
            patch("bd1.mattermost_window.delete_token") as delete,
            patch("bd1.mattermost_window.save_settings") as save,
        ):
            updated, warnings = disable_mattermost(settings)

        self.assertEqual("", updated.mattermost_url)
        self.assertEqual(("offline",), warnings)
        delete.assert_called_once_with(settings.mattermost_url)
        save.assert_called_once_with(updated)


if __name__ == "__main__":
    unittest.main()
