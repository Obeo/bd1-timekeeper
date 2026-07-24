# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import json
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from bd1.mattermost import (
    MattermostError,
    normalize_server_url,
    sync_custom_status,
    verify_token,
)
from bd1.network import OFFICE, REMOTE


class MattermostTest(unittest.TestCase):
    def test_normalizes_only_safe_https_server_urls(self) -> None:
        self.assertEqual(
            "https://mattermost.example.com/team",
            normalize_server_url(" https://mattermost.example.com/team/ "),
        )
        for value in (
            "http://mattermost.example.com",
            "https://token@mattermost.example.com",
            "https://mattermost.example.com?next=elsewhere",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_server_url(value)

    def test_sets_office_status_until_next_local_midnight(self) -> None:
        now = datetime.fromisoformat("2026-07-24T10:00:00+02:00")
        with patch(
            "bd1.mattermost._request",
            side_effect=[{"props": {}}, None],
        ) as request:
            result = sync_custom_status(
                "https://mattermost.example.com",
                "secret",
                OFFICE,
                now,
            )

        self.assertEqual("updated", result)
        self.assertEqual(
            {
                "emoji": "office",
                "text": "In the office",
                "duration": "today",
                "expires_at": "2026-07-25T00:00:00+02:00",
            },
            request.call_args_list[1].kwargs["payload"],
        )

    def test_preserves_manual_status(self) -> None:
        manual = json.dumps(
            {
                "emoji": "calendar",
                "text": "In a meeting",
                "expires_at": "2026-07-24T12:00:00+02:00",
            }
        )
        with patch(
            "bd1.mattermost._request",
            return_value={"props": {"customStatus": manual}},
        ) as request:
            result = sync_custom_status(
                "https://mattermost.example.com",
                "secret",
                REMOTE,
                datetime.fromisoformat("2026-07-24T10:00:00+02:00"),
            )

        self.assertEqual("manual", result)
        request.assert_called_once()

    def test_rejects_invalid_mattermost_user_response(self) -> None:
        with (
            patch("bd1.mattermost._request", return_value={}),
            self.assertRaises(MattermostError),
        ):
            verify_token("https://mattermost.example.com", "secret")

    def test_sends_token_only_in_authorization_header(self) -> None:
        response = Mock()
        response.read.return_value = b'{"id": "user-id"}'
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        opener = Mock()
        opener.open.return_value = response

        with patch("bd1.mattermost.build_opener", return_value=opener):
            verify_token("https://mattermost.example.com", "secret")

        request = opener.open.call_args.args[0]
        self.assertEqual(
            "https://mattermost.example.com/api/v4/users/me",
            request.full_url,
        )
        self.assertEqual("Bearer secret", request.get_header("Authorization"))
        self.assertNotIn("secret", request.full_url)
        self.assertEqual(10, opener.open.call_args.kwargs["timeout"])


if __name__ == "__main__":
    unittest.main()
