# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import os
import unittest
from datetime import date
from email.message import Message
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from keyring.errors import KeyringError

from bd1.eurecia import (
    EureciaAuthenticationError,
    EureciaConnectionError,
    EureciaCredentialError,
    EureciaDay,
    EureciaError,
    EureciaHttpClient,
    EureciaSegment,
    EureciaTimesheet,
    EureciaTimesheetSummary,
    _days_from_controls,
    _days_from_page,
    _encode_form_payload,
    _find_save_control,
    _find_timesheet_form,
    _form_payload,
    _HttpResponse,
    _legacy_load_time_payload,
    _legacy_row_segment,
    _legacy_rows_by_day,
    _legacy_save_fields,
    _legacy_target_overrides,
    _managed_comment,
    _parse_page,
    _summaries_from_page,
    _validated_target_days,
    _write_private_capture,
    delete_password,
    format_timesheet,
    get_saved_password,
    iso_week_dates,
    login_interactively,
    standard_week,
    store_password,
)

_TIMESHEET_HTML = """
<html><body>
<form method="post" action="/eurecia/timesheet/Open.do">
  <input type="hidden" name="action" value="Save">
  <table>
    <tr><th>Date</th><th>Début</th><th>Fin</th><th>Début</th><th>Fin</th></tr>
    <tr>
      <td>01/06/2026</td>
      <td><input name="mon_start_1" value="08:30"></td>
      <td><input name="mon_end_1" value="12:30"></td>
      <td><input name="mon_start_2" value="13:30"></td>
      <td><input name="mon_end_2" value="17:30"></td>
      <td><input type="checkbox" name="mon_standard" value="true" checked></td>
    </tr>
    <tr>
      <td>02/06/2026</td>
      <td><input name="tue_start_1" value="08:30"></td>
      <td><input name="tue_end_1" value="12:30"></td>
      <td><input name="tue_start_2" value="13:30"></td>
      <td><input name="tue_end_2" value="17:30"></td>
    </tr>
  </table>
  <button type="submit" name="save" value="true">Enregistrer</button>
</form>
</body></html>
"""

_STANDARD_TIMESHEET_HTML = """
<form method="post" action="/eurecia/timesheet/Open.do">
  <input type="hidden" id="standardValueSelectedRow" name="standardValueSelectedRow"
         value="false">
  <input type="hidden" id="infoSelectedRow" name="infoSelectedRow" value="">
  <input type="hidden" id="validate" name="validate" value="">
  <table>
    <tr>
      <td>01/06/2026 (07:10)</td>
      <td><input id="standard_0" value="true"
        name="ctrlvcol%3Dstandard%3Bctrl%3Dtimes%3Brow%3Drow_0%3Btype%3Dtxt"></td>
      <td><input type="hidden" value="true"
        name="ctrlvcol%3Dstandard%3Bctrl%3Dtimes%3Brow%3Drow_0%3Btype%3Dtxt">
        <input type="checkbox" checked value="true"
        name="ctrlvcol%3Dstandard%3Bctrl%3Dtimes%3Brow%3Drow_0%3Btype%3Dtxt"
        onclick='document.getElementById("infoSelectedRow").value="Lundi:01/06/2026:0";'>
      </td>
      <td><table><tr><td>09 : 00</td></tr></table></td>
      <td><table><tr><td>12 : 35</td></tr></table></td>
      <td>03:35</td>
    </tr>
    <tr>
      <td><input id="standard_1" value="true"
        name="ctrlvcol%3Dstandard%3Bctrl%3Dtimes%3Brow%3Drow_1%3Btype%3Dtxt"></td>
      <td><table><tr><td>14 : 00</td></tr></table></td>
      <td><table><tr><td>17 : 35</td></tr></table></td>
      <td>03:35</td>
    </tr>
  </table>
</form>
"""


def _response(
    content_type: str,
    body: bytes,
    *,
    url: str = "https://tenant.example/eurecia/test",
) -> _HttpResponse:
    headers = Message()
    headers["Content-Type"] = content_type
    return _HttpResponse(
        url=url,
        status=200,
        headers=headers,
        body=body,
    )


def _editable_week_html(
    segments: tuple[tuple[str, str], ...] = (("08:30", "12:30"), ("13:30", "17:30")),
    *,
    include_standard_markers: bool = True,
) -> str:
    rows: list[str] = []
    for day_offset, day in enumerate(iso_week_dates(2026, 23)[:5]):
        for segment_offset, (start, end) in enumerate(segments):
            row = day_offset * len(segments) + segment_offset
            date_cell = day.strftime("%d/%m/%Y") if segment_offset == 0 else ""
            fields = []
            for field_name, value in (
                ("startHour_Hours", start[:2]),
                ("startHour_Minutes", start[3:]),
                ("endHour_Hours", end[:2]),
                ("endHour_Minutes", end[3:]),
            ):
                fields.append(
                    f'<select id="{field_name}_{row}" '
                    f'name="ctrlvcol%3D{field_name}%3Bctrl%3Dtimes%3Brow%3Drow_{row}'
                    f'%3Btype%3Dtxt"><option selected value="{value}">{value}</option></select>'
                )
            rows.append(
                f"""
                <tr><td>{date_cell}</td>
                  <td>{
                    f'<input id="standard_{row}" value="false" '
                    f'name="ctrlvcol%3Dstandard%3Bctrl%3Dtimes%3Brow%3Drow_{row}%3Btype%3Dtxt">'
                    if include_standard_markers
                    else ""
                }</td>
                  <td><input id="generatedItem_{row}" value="true"
                    name="ctrlvcol%3DgeneratedItem%3Bctrl%3Dtimes%3Brow%3Drow_{row}%3Btype%3Dtxt">
                    <input id="duplicatedItem_{row}" value="true"
                    name="ctrlvcol%3DduplicatedItem%3Bctrl%3Dtimes%3Brow%3Drow_{row}%3Btype%3Dtxt">
                  </td><td>{"".join(fields)}
                    <textarea id="comment_{row}"
                      name="ctrlvcol%3Dcomment%3Bctrl%3Dtimes%3Brow%3Drow_{row}%3Btype%3Dtxt"
                    >Commentaire existant</textarea>
                  </td>
                </tr>
                """
            )
    return (
        '<form method="post" action="/eurecia/timesheet/Open.do">'
        '<input type="hidden" id="validate" name="validate" value="">'
        '<input type="submit" id="btnApply" value="Enregistrer">'
        f"<table>{''.join(rows)}</table></form>"
    )


def _legacy_field(field_name: str, row: int) -> str:
    return f"ctrlvcol%3D{field_name}%3Bctrl%3Dtimes%3Brow%3Drow_{row}%3Btype%3Dtxt"


def _editable_row_selects(row: int, start: str, end: str) -> str:
    return "".join(
        f'<select id="{field}_{row}" name="{_legacy_field(field, row)}">'
        f'<option selected value="{value}">{value}</option></select>'
        for field, value in (
            ("startHour_Hours", start[:2]),
            ("startHour_Minutes", start[3:]),
            ("endHour_Hours", end[:2]),
            ("endHour_Minutes", end[3:]),
        )
    )


class EureciaTest(unittest.TestCase):
    def test_password_uses_the_system_credential_store_per_account(self) -> None:
        with (
            patch("bd1.eurecia.keyring.get_password", return_value="secret") as get,
            patch("bd1.eurecia.keyring.set_password") as set_password,
            patch("bd1.eurecia.keyring.delete_password") as delete,
        ):
            self.assertEqual(
                "secret",
                get_saved_password(
                    "https://tenant.example/eurecia",
                    "User@Example.com",
                ),
            )
            store_password(
                "https://tenant.example/eurecia/",
                "user@example.com",
                "new-secret",
            )
            delete_password(
                "https://tenant.example/eurecia/",
                "user@example.com",
            )

        service, account = get.call_args.args
        self.assertEqual("BD-1 Eurecia", service)
        self.assertIn("https://tenant.example/eurecia/", account)
        self.assertIn("user@example.com", account)
        set_password.assert_called_once_with(service, account, "new-secret")
        delete.assert_called_once_with(service, account)

    def test_saved_password_is_replaced_only_after_successful_login(self) -> None:
        client = Mock(base_url="https://tenant.example/eurecia/")
        client.login.side_effect = (EureciaAuthenticationError("rejected"), None)

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("bd1.eurecia.get_saved_password", return_value="old-secret"),
            patch("bd1.eurecia.getpass.getpass", return_value="new-secret") as prompt,
            patch("bd1.eurecia.store_password") as store,
        ):
            login_interactively(client, "user@example.com")

        self.assertEqual(
            [
                unittest.mock.call("user@example.com", "old-secret"),
                unittest.mock.call("user@example.com", "new-secret"),
            ],
            client.login.call_args_list,
        )
        prompt.assert_called_once()
        store.assert_called_once_with(
            "https://tenant.example/eurecia/",
            "user@example.com",
            "new-secret",
        )

    def test_credential_store_errors_are_reported_without_exposing_the_secret(self) -> None:
        with (
            patch(
                "bd1.eurecia.keyring.set_password",
                side_effect=KeyringError("locked"),
            ),
            self.assertRaisesRegex(EureciaCredentialError, "Could not store"),
        ):
            store_password(
                "https://tenant.example/eurecia/",
                "user@example.com",
                "secret",
            )

    def test_prompted_password_is_saved_only_with_explicit_consent(self) -> None:
        client = Mock(base_url="https://tenant.example/eurecia/")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("bd1.eurecia.get_saved_password", return_value=None),
            patch("bd1.eurecia.getpass.getpass", return_value="secret"),
            patch("bd1.eurecia.store_password") as store,
        ):
            login_interactively(client, "user@example.com")
            store.assert_not_called()
            login_interactively(client, "user@example.com", remember_password=True)

        store.assert_called_once_with(
            "https://tenant.example/eurecia/",
            "user@example.com",
            "secret",
        )

    def test_environment_password_is_not_stored_without_explicit_consent(self) -> None:
        client = Mock(base_url="https://tenant.example/eurecia/")

        with (
            patch.dict(os.environ, {"BD1_EURECIA_PASSWORD": "from-env"}, clear=True),
            patch("bd1.eurecia.get_saved_password") as get_saved,
            patch("bd1.eurecia.getpass.getpass") as prompt,
            patch("bd1.eurecia.store_password") as store,
        ):
            login_interactively(client, "user@example.com")

        client.login.assert_called_once_with("user@example.com", "from-env")
        get_saved.assert_not_called()
        prompt.assert_not_called()
        store.assert_not_called()

    def test_client_rejects_non_https_base_url(self) -> None:
        with self.assertRaisesRegex(EureciaError, "absolute HTTPS"):
            EureciaHttpClient("http://tenant.example/eurecia/")

    def test_login_distinguishes_rejected_credentials_from_connection_errors(self) -> None:
        client = EureciaHttpClient("https://tenant.example/eurecia/")
        client._request = Mock(  # type: ignore[method-assign]
            side_effect=(
                _response("text/html", b"login"),
                _response("text/html", b"legacy"),
            )
        )
        client._login_legacy = Mock()  # type: ignore[method-assign]
        client._init_data = Mock(side_effect=EureciaError("not authenticated"))  # type: ignore[method-assign]

        with self.assertRaises(EureciaAuthenticationError):
            client.login("user@example.com", "wrong")

        client._request = Mock(  # type: ignore[method-assign]
            side_effect=(
                _response("text/html", b"login"),
                _response("text/html", b"legacy"),
            )
        )
        client._init_data = Mock(side_effect=EureciaConnectionError("offline"))  # type: ignore[method-assign]

        with self.assertRaises(EureciaConnectionError):
            client.login("user@example.com", "secret")

    def test_client_does_not_follow_an_external_application_link(self) -> None:
        client = EureciaHttpClient("https://tenant.example/eurecia/")

        with self.assertRaisesRegex(EureciaError, "outside the configured tenant"):
            client._request("GET", "https://attacker.example/collect")

    def test_login_uses_identity_provider_when_preflight_advertises_sso(self) -> None:
        client = EureciaHttpClient("https://tenant.example/eurecia/")
        tenant_requests: list[tuple[str, str, bytes | None]] = []
        tenant_responses = iter(
            (
                _response("text/html", b"<form></form>"),
                _response(
                    "application/json",
                    b'{"redirectUrl":"https://plateforme-idp.eurecia.com/authorize"}',
                ),
                _response("application/json", b'{"user":{}}'),
            )
        )
        idp_requests: list[tuple[str, str, bytes | None]] = []
        idp_responses = iter(
            (
                _response(
                    "text/html",
                    b"""
                    <form method="post"
                          action="https://plateforme-idp.eurecia.com/login-actions/authenticate">
                      <input type="password" name="password">
                      <input type="hidden" name="credentialId" value="">
                      <input type="submit" name="login" value="Sign In">
                    </form>
                    """,
                    url="https://plateforme-idp.eurecia.com/authorize",
                ),
                _response("text/html", b"authenticated"),
            )
        )

        def request(method: str, url: str, **kwargs: object) -> _HttpResponse:
            data = kwargs.get("data")
            tenant_requests.append((method, url, data if isinstance(data, bytes) else None))
            return next(tenant_responses)

        def idp_request(method: str, url: str, **kwargs: object) -> _HttpResponse:
            data = kwargs.get("data")
            idp_requests.append((method, url, data if isinstance(data, bytes) else None))
            return next(idp_responses)

        client._request = request  # type: ignore[method-assign]
        client._request_identity_provider = idp_request  # type: ignore[method-assign]

        client.login("user@example.com", "secret")

        self.assertEqual(["GET", "GET", "GET"], [item[0] for item in tenant_requests])
        method, url, payload = idp_requests[1]
        self.assertEqual("POST", method)
        self.assertEqual(
            "https://plateforme-idp.eurecia.com/login-actions/authenticate",
            url,
        )
        self.assertIn(b"password=secret", payload or b"")

    def test_client_does_not_send_credentials_to_an_untrusted_idp(self) -> None:
        client = EureciaHttpClient("https://tenant.example/eurecia/")

        with self.assertRaisesRegex(EureciaError, "outside the Eurecia identity provider"):
            client._request_identity_provider("POST", "https://attacker.example/login")

    def test_login_can_import_browser_cookie_header(self) -> None:
        client = EureciaHttpClient("https://tenant.example/eurecia/")
        client._init_data = lambda: {"user": {}}  # type: ignore[method-assign]

        client.login_with_cookie("Cookie: JSESSIONID=session; route=main")

        cookies = {cookie.name: cookie.value for cookie in client._cookies}
        self.assertEqual({"JSESSIONID": "session", "route": "main"}, cookies)

    def test_browser_cookie_import_rejects_an_empty_header(self) -> None:
        client = EureciaHttpClient("https://tenant.example/eurecia/")

        with self.assertRaisesRegex(EureciaError, "non-empty"):
            client.login_with_cookie("")

    def test_diagnostic_capture_is_private_and_never_overwritten(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "open.html"

            _write_private_capture(output, b"private html")

            self.assertEqual(b"private html", output.read_bytes())
            if os.name == "posix":
                self.assertEqual(0o600, output.stat().st_mode & 0o777)
            with self.assertRaisesRegex(EureciaError, "Refusing to overwrite"):
                _write_private_capture(output, b"replacement")

    def test_iso_week_23_of_2026_starts_on_june_1(self) -> None:
        days = iso_week_dates(2026, 23)

        self.assertEqual(date(2026, 6, 1), days[0])
        self.assertEqual(date(2026, 6, 7), days[-1])

    def test_standard_week_contains_two_segments_on_each_workday(self) -> None:
        days = standard_week(2026, 23)

        self.assertEqual(5, len(days))
        self.assertEqual(35 * 3600, sum(day.worked_seconds for day in days))

    def test_format_timesheet_looks_like_the_bd1_weekly_report(self) -> None:
        summary = EureciaTimesheetSummary(
            year=2026,
            week=23,
            label="2026 Semaine 23",
            href="timesheet/Open.do?id=opaque",
            status="Nouvelle",
        )

        rendered = format_timesheet(EureciaTimesheet(summary, standard_week(2026, 23)))

        self.assertIn("2026-06-01: 7 h 00 worked", rendered)
        self.assertIn("  - Work: 09:00 -> 12:00 (3 h 00)", rendered)
        self.assertIn("  - Break: 12:00 -> 14:00 (2 h 00)", rendered)
        self.assertIn("Weekly total: 35 h 00", rendered)

    def test_parser_extracts_editable_segments(self) -> None:
        parser = _parse_page(_TIMESHEET_HTML)
        days = iso_week_dates(2026, 23)

        _form, controls = _find_timesheet_form(parser, days)
        reports = _days_from_controls(days, controls)

        self.assertEqual(
            [("08:30", "12:30"), ("13:30", "17:30")],
            [(segment.start, segment.end) for segment in reports[0].segments],
        )

    def test_parser_extracts_segments_rendered_as_standard_text(self) -> None:
        parser = _parse_page(_STANDARD_TIMESHEET_HTML)
        days = iso_week_dates(2026, 23)

        form, controls = _find_timesheet_form(parser, days)
        reports = _days_from_page(parser, form, days, controls)

        self.assertEqual(
            [("09:00", "12:35"), ("14:00", "17:35")],
            [(segment.start, segment.end) for segment in reports[0].segments],
        )

    def test_parser_treats_a_blank_legacy_row_as_no_segment(self) -> None:
        self.assertIsNone(_legacy_row_segment(0, "Lundi 13 juillet 2026", []))
        self.assertIsNone(_legacy_row_segment(0, "00:00", []))
        self.assertIsNone(
            _legacy_row_segment(
                0,
                "Lundi (00:00) 00:00 00:00 Congés payés 09:00:00 - 17:35:00",
                [],
            )
        )

    def test_locked_vacation_row_is_preserved_beside_editable_work(self) -> None:
        html = f"""
        <form method="post" action="/eurecia/timesheet/Open.do">
          <input id="validate" name="validate" value="">
          <table>
            <tr><td>13/07/2026 Congés payés 09:00 - 17:35</td>
              <td><input id="standard_0" value="false"
                name="{_legacy_field("standard", 0)}"></td>
              <td><textarea name="{_legacy_field("comment", 0)}">
                Congés payés 13/07/2026 09:00:00 - 17:35:00
              </textarea></td>
            </tr>
            <tr><td><input id="standard_1" value="false"
              name="{_legacy_field("standard", 1)}"></td>
              <td>{_editable_row_selects(1, "08:30", "17:30")}</td>
            </tr>
          </table>
          <input type="submit" id="btnApply" value="Enregistrer">
        </form>
        """
        parser = _parse_page(html)
        days = iso_week_dates(2026, 29)
        form, controls = _find_timesheet_form(parser, days)
        target = (EureciaDay(days[0], (EureciaSegment("08:50", "09:18"),)),)

        current = _days_from_page(parser, form, days, controls)
        overrides = _legacy_target_overrides(parser, form, days, target)
        payload = dict(_legacy_save_fields(form, overrides))

        self.assertEqual(
            (("08:30", "17:30"),),
            tuple((segment.start, segment.end) for segment in current[0].segments),
        )
        self.assertIn("Congés payés", payload[_legacy_field("comment", 0)])
        self.assertEqual("08", payload[_legacy_field("startHour_Hours", 1)])
        self.assertEqual("50", payload[_legacy_field("startHour_Minutes", 1)])
        self.assertEqual("09", payload[_legacy_field("endHour_Hours", 1)])
        self.assertEqual("18", payload[_legacy_field("endHour_Minutes", 1)])

    def test_standard_toggle_payload_uses_observed_load_time_action(self) -> None:
        parser = _parse_page(_STANDARD_TIMESHEET_HTML)
        days = iso_week_dates(2026, 23)
        form, _controls = _find_timesheet_form(parser, days)
        monday_row = _legacy_rows_by_day(parser, form, days)[days[0]][0]

        payload = _legacy_load_time_payload(parser, form, days[0], monday_row)

        self.assertIn(("ctrla", "timeSheetOpenForm=LoadTime"), payload)
        self.assertIn(("standardValueSelectedRow", "false"), payload)
        self.assertIn(("infoSelectedRow", "Lundi:01/06/2026:0"), payload)

    def test_legacy_save_payload_sets_target_hours_and_validate_mode(self) -> None:
        parser = _parse_page(_editable_week_html())
        days = iso_week_dates(2026, 23)
        form, _controls = _find_timesheet_form(parser, days)

        overrides = _legacy_target_overrides(parser, form, days, standard_week(2026, 23))
        payload = dict(_legacy_save_fields(form, overrides))

        self.assertEqual("09", payload[_legacy_field("startHour_Hours", 0)])
        self.assertEqual("12", payload[_legacy_field("endHour_Hours", 0)])
        self.assertEqual("14", payload[_legacy_field("startHour_Hours", 1)])
        self.assertEqual("18", payload[_legacy_field("endHour_Hours", 1)])
        self.assertEqual("false", payload[_legacy_field("generatedItem", 0)])
        self.assertEqual("false", payload[_legacy_field("duplicatedItem", 1)])
        self.assertEqual("2", payload["validate"])
        self.assertEqual("clicked", payload["btnApply"])

    def test_remote_comment_is_managed_on_the_first_row_only(self) -> None:
        parser = _parse_page(_editable_week_html())
        days = iso_week_dates(2026, 23)
        form, _controls = _find_timesheet_form(parser, days)
        target = (
            EureciaDay(
                days[0],
                (
                    EureciaSegment("09:00", "12:00"),
                    EureciaSegment("14:00", "18:00"),
                ),
                "Télétravail/Remote",
            ),
        )

        payload = dict(
            _legacy_save_fields(
                form,
                _legacy_target_overrides(parser, form, days, target),
            )
        )

        self.assertEqual(
            "Commentaire existant\nTélétravail/Remote",
            payload[_legacy_field("comment", 0)],
        )
        self.assertEqual("Commentaire existant", payload[_legacy_field("comment", 1)])
        self.assertEqual(
            "Commentaire existant",
            _managed_comment("Commentaire existant\nTélétravail/Remote", ""),
        )

    def test_editable_rows_do_not_require_standard_markers(self) -> None:
        parser = _parse_page(_editable_week_html(include_standard_markers=False))
        days = iso_week_dates(2026, 23)
        form, controls = _find_timesheet_form(parser, days)

        current = _days_from_page(parser, form, days, controls)
        overrides = _legacy_target_overrides(parser, form, days, standard_week(2026, 23))

        self.assertEqual(
            ("08:30", "12:30"),
            (
                current[0].segments[0].start,
                current[0].segments[0].end,
            ),
        )
        self.assertEqual(
            "09", dict(_legacy_save_fields(form, overrides))[_legacy_field("startHour_Hours", 0)]
        )

    def test_legacy_save_payload_clears_a_day_with_one_empty_row(self) -> None:
        parser = _parse_page(_editable_week_html((("08:30", "17:30"),)))
        days = iso_week_dates(2026, 23)
        form, _controls = _find_timesheet_form(parser, days)

        overrides = _legacy_target_overrides(
            parser,
            form,
            days,
            (EureciaDay(days[0], ()),),
        )
        payload = dict(_legacy_save_fields(form, overrides))

        self.assertEqual("00", payload[_legacy_field("startHour_Hours", 0)])
        self.assertEqual("00", payload[_legacy_field("startHour_Minutes", 0)])
        self.assertEqual("00", payload[_legacy_field("endHour_Hours", 0)])
        self.assertEqual("00", payload[_legacy_field("endHour_Minutes", 0)])

    def test_target_days_reject_overlapping_segments(self) -> None:
        days = iso_week_dates(2026, 23)
        target = EureciaDay(
            days[0],
            (
                EureciaSegment("09:00", "12:00"),
                EureciaSegment("11:45", "14:00"),
            ),
        )

        with self.assertRaisesRegex(EureciaError, "Overlapping segments"):
            _validated_target_days(days, (target,))

    def test_legacy_multipart_form_uses_its_declared_encoding(self) -> None:
        parser = _parse_page('<form method="post" enctype="multipart/form-data"></form>')

        body, content_type = _encode_form_payload(
            parser.forms[0],
            [("validate", "2"), (_legacy_field("endHour_Hours", 1), "18")],
        )

        self.assertRegex(
            content_type,
            r"^multipart/form-data; boundary=----bd1-eurecia-[0-9a-f]{32}$",
        )
        boundary = content_type.partition("boundary=")[2].encode()
        self.assertTrue(body.startswith(b"--" + boundary + b"\r\n"))
        self.assertTrue(body.endswith(b"--" + boundary + b"--\r\n"))
        self.assertIn(b'name="validate"\r\n\r\n2\r\n', body)
        self.assertIn(b'name="ctrlvcol%3DendHour_Hours', body)

    def test_form_payload_can_replace_times_and_uncheck_standard(self) -> None:
        parser = _parse_page(_TIMESHEET_HTML)
        days = iso_week_dates(2026, 23)
        form, controls = _find_timesheet_form(parser, days)
        save = _find_save_control(form)
        monday = controls[days[0]]
        times = [control for control in monday if control.value.count(":") == 1]
        standard = next(control for control in monday if control.type == "checkbox")
        overrides = {
            times[0].index: "09:00",
            times[1].index: "12:00",
            times[2].index: "14:00",
            times[3].index: "18:00",
            standard.index: None,
        }

        payload = _form_payload(form, save, overrides)

        self.assertIn(("mon_start_1", "09:00"), payload)
        self.assertIn(("mon_end_2", "18:00"), payload)
        self.assertIn(("save", "true"), payload)
        self.assertNotIn(("mon_standard", "true"), payload)

    def test_parser_extracts_week_status_and_edit_link(self) -> None:
        parser = _parse_page(
            """
            <table><tr><td>2026 Semaine 23</td><td>Nouvelle</td>
            <td><a href="timesheet/Browse.do?ctrl=list&amp;action=Edit&amp;param=x">
            Ouvrir</a></td></tr></table>
            """
        )

        summaries = _summaries_from_page(parser)

        self.assertEqual(1, len(summaries))
        self.assertEqual(
            (2026, 23, "Nouvelle"),
            (
                summaries[0].year,
                summaries[0].week,
                summaries[0].status,
            ),
        )

    def test_parser_rejects_ambiguous_timesheet_forms(self) -> None:
        html = f"""
        <form><input id="standard_0" value="false"
          name="{_legacy_field("standard", 0)}"></form>
        <form><input id="standard_1" value="false"
          name="{_legacy_field("standard", 1)}"></form>
        """

        with self.assertRaisesRegex(EureciaError, "Ambiguous"):
            _find_timesheet_form(_parse_page(html), iso_week_dates(2026, 23))

    def test_parser_rejects_time_fields_without_a_date(self) -> None:
        html = """
        <form>
          <table><tr><td>01/06/2026</td>
            <td><input name="start" value="09:00"></td>
          </tr></table>
          <input name="orphan" value="10:00">
        </form>
        """

        with self.assertRaisesRegex(EureciaError, "associate"):
            _find_timesheet_form(_parse_page(html), iso_week_dates(2026, 23))

    def test_save_payload_requires_an_unambiguous_save_control(self) -> None:
        parser = _parse_page(_editable_week_html())
        form, _controls = _find_timesheet_form(parser, iso_week_dates(2026, 23))
        form.controls = [
            control
            for control in form.controls
            if control.attrs.get("id") not in {"btnApply", "validate"}
        ]

        with self.assertRaisesRegex(EureciaError, "Enregistrer control"):
            _legacy_save_fields(form, {})

    def test_save_control_can_be_the_observed_hidden_btn_apply_field(self) -> None:
        form = _parse_page('<form><input type="hidden" id="btnApply"></form>').forms[0]

        self.assertEqual("btnApply", _find_save_control(form).attrs["id"])

    def test_btn_apply_takes_priority_over_the_visible_save_button(self) -> None:
        form = _parse_page(
            '<form><input type="hidden" id="btnApply">'
            '<button type="submit">Enregistrer</button></form>'
        ).forms[0]

        self.assertEqual("btnApply", _find_save_control(form).attrs["id"])

    def test_save_control_handles_eurecias_duplicate_btn_apply_id(self) -> None:
        form = _parse_page(
            '<form><button id="btnApply" type="submit">Valider</button>'
            '<button id="btnApply" type="submit">Enregistrer</button></form>'
        ).forms[0]

        self.assertEqual("Enregistrer", _find_save_control(form).label)
        self.assertEqual("clicked", dict(_legacy_save_fields(form, {}))["btnApply"])

    def test_workflow_buttons_use_the_observed_validate_save_contract(self) -> None:
        form = _parse_page(
            '<form><input type="hidden" id="validate">'
            '<button id="btnApply" type="submit">Soumettre à validation</button>'
            '<button id="btnApply" type="submit">Transférer la validation</button></form>'
        ).forms[0]

        self.assertEqual("btnApply", _find_save_control(form).attrs["id"])
        self.assertEqual("clicked", dict(_legacy_save_fields(form, {}))["btnApply"])

    def test_save_control_uses_legacy_validate_contract_without_a_button(self) -> None:
        form = _parse_page('<form><input type="hidden" id="validate"></form>').forms[0]

        self.assertEqual("btnApply", _find_save_control(form).attrs["id"])
        self.assertEqual("clicked", dict(_legacy_save_fields(form, {}))["btnApply"])


if __name__ == "__main__":
    unittest.main()
