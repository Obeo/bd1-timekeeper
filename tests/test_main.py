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
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from bd1.__main__ import _push_week_to_eurecia, main
from bd1.models import DailyReport, TimeBlock, WeeklyReport
from bd1.settings import Settings


class MainTest(unittest.TestCase):
    def test_cli_report_and_push_use_the_configured_top_up_target(self) -> None:
        start = datetime.fromisoformat("2026-09-14T09:00:00+02:00")
        report = WeeklyReport(
            "2026-09-14",
            (
                DailyReport(
                    "2026-09-14",
                    (),
                    (TimeBlock("work", start, start + timedelta(hours=6)),),
                    (),
                    (),
                ),
            ),
        )
        for arguments, enabled in (
            (["--report", "week", "--date", "2026-09-14"], True),
            (["--push-eurecia", "38", "--year", "2026", "--weekly-target"], False),
        ):
            with self.subTest(arguments=arguments):
                settings = Settings(
                    weekly_37h_cap_enabled=enabled,
                    weekly_top_up_enabled=enabled,
                    weekly_top_up_hours=36,
                    eurecia_base_url="https://tenant.example/eurecia/",
                    eurecia_email="user@example.com",
                )
                output = StringIO()
                with (
                    patch("sys.argv", ["bd1", *arguments]),
                    patch("bd1.__main__.ObservationStore"),
                    patch("bd1.__main__.ReportService") as reports,
                    patch("bd1.__main__.load_settings", return_value=settings),
                    patch("builtins.input", return_value="o"),
                    patch("bd1.__main__.EureciaHttpClient") as client,
                    patch("bd1.__main__.login_interactively"),
                    redirect_stdout(output),
                ):
                    reports.return_value.weekly.return_value = report

                    main()

                self.assertIn("Weekly total: 7 h 12", output.getvalue())
                if "--push-eurecia" in arguments:
                    days = client.return_value.replace_timesheet.call_args.args[2]
                    self.assertEqual("16:12", days[0].segments[-1].end)

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
