# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from bd1.__main__ import _push_week_to_eurecia
from bd1.models import DailyReport, WeeklyReport
from bd1.settings import Settings


class MainTest(unittest.TestCase):
    def test_eurecia_push_prints_preview_and_requires_confirmation(self) -> None:
        report = WeeklyReport(
            "2026-07-13",
            (DailyReport("2026-07-13", (), (), (), ()),),
        )
        output = StringIO()

        with (
            patch("builtins.input", return_value="n"),
            patch("bd1.__main__.EureciaHttpClient") as client,
            redirect_stdout(output),
        ):
            _push_week_to_eurecia(report, Settings())

        self.assertIn("BD-1 weekly report - week of 2026-07-13", output.getvalue())
        self.assertIn("Envoi annulé.", output.getvalue())
        client.assert_not_called()

    def test_eurecia_push_forwards_password_storage_consent(self) -> None:
        report = WeeklyReport(
            "2026-07-13",
            (DailyReport("2026-07-13", (), (), (), ()),),
        )
        settings = Settings(
            eurecia_base_url="https://tenant.example/eurecia/",
            eurecia_email="user@example.com",
        )

        with (
            patch("builtins.input", return_value="o"),
            patch("bd1.__main__.EureciaHttpClient") as client_type,
            patch("bd1.__main__.login_interactively") as login,
            redirect_stdout(StringIO()),
        ):
            _push_week_to_eurecia(report, settings, remember_password=True)

        login.assert_called_once_with(
            client_type.return_value,
            "user@example.com",
            remember_password=True,
        )


if __name__ == "__main__":
    unittest.main()
