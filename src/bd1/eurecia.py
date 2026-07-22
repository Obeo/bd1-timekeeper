# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import http.cookies
import json
import os
import re
import secrets
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from bd1.calendar import is_working_day
from bd1.formatting import format_duration
from bd1.models import ObservationType, WeeklyReport
from bd1.network import REMOTE, work_location
from bd1.settings import DEFAULT_VPN_INTERFACE_PATTERNS, DEFAULT_WEEKLY_CAP_HOURS

_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_WEEK_PATTERN = re.compile(
    r"\b(?P<year>20\d{2})\s*(?:semaine|sem\.?|s|week)\s*(?P<week>\d{1,2})\b",
    re.IGNORECASE,
)
_STATUS_PATTERN = re.compile(
    r"\b(nouvelle|new|à valider|a valider|soumise|validée|validee|refusée|refusee)\b",
    re.IGNORECASE,
)
_ONCLICK_URL_PATTERN = re.compile(
    r"(?:window\.)?location(?:\.href)?\s*=\s*['\"](?P<url>[^'\"]+)['\"]",
    re.IGNORECASE,
)
_FRENCH_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
_FRENCH_WEEKDAYS = (
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
)
_STANDARD_SEGMENTS = (("09:00", "12:00"), ("14:00", "18:00"))
_EURECIA_IDP_HOST = "plateforme-idp.eurecia.com"
_KEYRING_SERVICE = "BD-1 Eurecia"
REMOTE_COMMENT = "Télétravail/Remote"


class EureciaError(RuntimeError):
    """Raised when the private Eurecia web interface cannot be used safely."""


class EureciaAuthenticationError(EureciaError):
    """Raised when Eurecia rejects credentials."""


class EureciaConnectionError(EureciaError):
    """Raised when Eurecia or its identity provider cannot be reached."""


class EureciaCredentialError(EureciaError):
    """Raised when the operating-system credential store is unavailable."""


def get_saved_password(base_url: str, email: str) -> str | None:
    try:
        return keyring.get_password(_KEYRING_SERVICE, _credential_account(base_url, email))
    except KeyringError as error:
        raise EureciaCredentialError(f"Credential store unavailable: {error}") from error


def store_password(base_url: str, email: str, password: str) -> None:
    try:
        keyring.set_password(
            _KEYRING_SERVICE,
            _credential_account(base_url, email),
            password,
        )
    except KeyringError as error:
        raise EureciaCredentialError(f"Could not store Eurecia password: {error}") from error


def delete_password(base_url: str, email: str) -> None:
    account = _credential_account(base_url, email)
    try:
        if keyring.get_password(_KEYRING_SERVICE, account) is not None:
            keyring.delete_password(_KEYRING_SERVICE, account)
    except PasswordDeleteError:
        return
    except KeyringError as error:
        raise EureciaCredentialError(f"Could not remove Eurecia password: {error}") from error


def login_interactively(
    client: EureciaHttpClient,
    email: str,
    *,
    remember_password: bool = False,
) -> None:
    password = os.environ.get("BD1_EURECIA_PASSWORD") or None
    saved_password = False
    if password is None:
        try:
            password = get_saved_password(client.base_url, email) or None
        except EureciaCredentialError as error:
            print(f"Warning: {error}", file=sys.stderr)
        saved_password = password is not None
    if password is None:
        password = getpass.getpass("Eurecia / SSO password: ")

    try:
        client.login(email, password)
    except EureciaAuthenticationError:
        if not saved_password:
            raise
        password = getpass.getpass("Stored password rejected; new Eurecia / SSO password: ")
        client.login(email, password)
        remember_password = True
        saved_password = False

    if remember_password and not saved_password:
        try:
            store_password(client.base_url, email, password)
        except EureciaCredentialError as error:
            print(f"Warning: {error}", file=sys.stderr)


def _credential_account(base_url: str, email: str) -> str:
    return json.dumps(
        (base_url.strip().rstrip("/") + "/", email.strip().casefold()),
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True)
class EureciaSegment:
    start: str
    end: str

    def __post_init__(self) -> None:
        if not _TIME_PATTERN.fullmatch(self.start) or not _TIME_PATTERN.fullmatch(self.end):
            raise ValueError(f"Invalid Eurecia segment: {self.start!r} -> {self.end!r}")
        if _minutes(self.end) <= _minutes(self.start):
            raise ValueError(
                f"Eurecia segment must end after it starts: {self.start} -> {self.end}"
            )

    @property
    def seconds(self) -> int:
        return (_minutes(self.end) - _minutes(self.start)) * 60


@dataclass(frozen=True, slots=True)
class EureciaDay:
    date: date
    segments: tuple[EureciaSegment, ...]
    comment: str = ""

    @property
    def worked_seconds(self) -> int:
        return sum(segment.seconds for segment in self.segments)


@dataclass(frozen=True, slots=True)
class EureciaTimesheetSummary:
    year: int
    week: int
    label: str
    href: str
    status: str | None = None


@dataclass(frozen=True, slots=True)
class EureciaTimesheet:
    summary: EureciaTimesheetSummary
    days: tuple[EureciaDay, ...]

    @property
    def worked_seconds(self) -> int:
        return sum(day.worked_seconds for day in self.days)


@dataclass(frozen=True, slots=True)
class EureciaWrite:
    method: str
    path: str
    status: int
    requests: int = 1


@dataclass(slots=True)
class _Anchor:
    attrs: dict[str, str]
    row_key: tuple[int, int] | None
    text_parts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return _collapse(self.text_parts)


@dataclass(slots=True)
class _Control:
    index: int
    tag: str
    attrs: dict[str, str]
    row_key: tuple[int, int] | None
    cell_key: tuple[int, int, int] | None
    text_parts: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.attrs.get("name", "")

    @property
    def type(self) -> str:
        default = "submit" if self.tag == "button" else "text"
        return self.attrs.get("type", default).casefold()

    @property
    def value(self) -> str:
        if self.values:
            return self.values[0]
        if self.tag == "textarea":
            return "".join(self.text_parts)
        return self.attrs.get("value", "")

    @property
    def label(self) -> str:
        return _collapse([*self.text_parts, self.attrs.get("value", "")])


@dataclass(slots=True)
class _Form:
    attrs: dict[str, str]
    controls: list[_Control] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _HttpResponse:
    url: str
    status: int
    headers: Any
    body: bytes

    def text(self) -> str:
        content_type = self.headers.get_content_charset() or "utf-8"
        return self.body.decode(content_type, "replace")


class _LegacyPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[_Anchor] = []
        self.forms: list[_Form] = []
        self.row_text: dict[tuple[int, int], list[str]] = {}
        self.cell_text: dict[tuple[int, int, int], list[str]] = {}
        self._table_stack: list[int] = []
        self._table_count = 0
        self._row_count: dict[int, int] = {}
        self._row_stack: list[tuple[int, int]] = []
        self._cell_stack: list[tuple[int, int, int]] = []
        self._cell_count: dict[tuple[int, int], int] = {}
        self._form_stack: list[_Form] = []
        self._anchor_stack: list[_Anchor] = []
        self._text_control_stack: list[_Control] = []
        self._select_stack: list[_Control] = []
        self._option: tuple[dict[str, str], list[str]] | None = None
        self._control_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if tag == "table":
            table = self._table_count
            self._table_count += 1
            self._table_stack.append(table)
        elif tag == "tr" and self._table_stack:
            table = self._table_stack[-1]
            row = self._row_count.get(table, 0)
            self._row_count[table] = row + 1
            row_key = (table, row)
            self._row_stack.append(row_key)
            self.row_text.setdefault(row_key, [])
        elif tag in {"td", "th"} and self._row_stack:
            row_key = self._row_stack[-1]
            cell = self._cell_count.get(row_key, 0)
            self._cell_count[row_key] = cell + 1
            cell_key = (*row_key, cell)
            self._cell_stack.append(cell_key)
            self.cell_text.setdefault(cell_key, [])
        elif tag == "form":
            form = _Form(attributes)
            self.forms.append(form)
            self._form_stack.append(form)
        elif tag == "a":
            anchor = _Anchor(attributes, self._row_stack[-1] if self._row_stack else None)
            self._anchor_stack.append(anchor)
        elif tag in {"input", "select", "textarea", "button"} and self._form_stack:
            control = _Control(
                index=self._control_count,
                tag=tag,
                attrs=attributes,
                row_key=self._row_stack[-1] if self._row_stack else None,
                cell_key=self._cell_stack[-1] if self._cell_stack else None,
            )
            self._control_count += 1
            self._form_stack[-1].controls.append(control)
            if tag in {"textarea", "button"}:
                self._text_control_stack.append(control)
            elif tag == "select":
                self._select_stack.append(control)
        elif tag == "option" and self._select_stack:
            self._option = (attributes, [])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._table_stack:
            self._table_stack.pop()
        elif tag == "tr" and self._row_stack:
            self._row_stack.pop()
        elif tag in {"td", "th"} and self._cell_stack:
            self._cell_stack.pop()
        elif tag == "form" and self._form_stack:
            self._form_stack.pop()
        elif tag == "a" and self._anchor_stack:
            self.anchors.append(self._anchor_stack.pop())
        elif tag in {"textarea", "button"} and self._text_control_stack:
            self._text_control_stack.pop()
        elif tag == "option" and self._option is not None and self._select_stack:
            attrs, text_parts = self._option
            value = attrs.get("value", _collapse(text_parts))
            selected = "selected" in attrs
            select = self._select_stack[-1]
            if selected or not select.values:
                if not selected:
                    select.values = [value]
                else:
                    if "multiple" not in select.attrs:
                        select.values.clear()
                    select.values.append(value)
            self._option = None
        elif tag == "select" and self._select_stack:
            self._select_stack.pop()

    def handle_data(self, data: str) -> None:
        for row_key in self._row_stack:
            self.row_text[row_key].append(data)
        for cell_key in self._cell_stack:
            self.cell_text[cell_key].append(data)
        if self._anchor_stack:
            self._anchor_stack[-1].text_parts.append(data)
        if self._text_control_stack:
            self._text_control_stack[-1].text_parts.append(data)
        if self._option is not None:
            self._option[1].append(data)


def iso_week_dates(year: int, week: int) -> tuple[date, ...]:
    try:
        monday = date.fromisocalendar(year, week, 1)
    except ValueError as error:
        raise EureciaError(f"Invalid ISO week: {year}-W{week:02d}") from error
    return tuple(monday + timedelta(days=offset) for offset in range(7))


def standard_week(year: int, week: int) -> tuple[EureciaDay, ...]:
    segments = tuple(EureciaSegment(start, end) for start, end in _STANDARD_SEGMENTS)
    return tuple(EureciaDay(day, segments) for day in iso_week_dates(year, week)[:5])


def eurecia_days_from_report(
    report: WeeklyReport,
    *,
    apply_weekly_cap: bool = False,
    weekly_cap_hours: int = DEFAULT_WEEKLY_CAP_HOURS,
    vpn_interface_patterns: tuple[str, ...] = DEFAULT_VPN_INTERFACE_PATTERNS,
) -> tuple[EureciaDay, ...]:
    report_days = (
        report.declaration_for(weekly_cap_hours).proposed_days if apply_weekly_cap else report.days
    )
    result: list[EureciaDay] = []
    for day in report_days:
        day_date = date.fromisoformat(day.date)
        if not is_working_day(day_date):
            continue
        segments = tuple(
            EureciaSegment(block.start.strftime("%H:%M"), block.end.strftime("%H:%M"))
            for block in sorted(day.work_blocks, key=lambda item: item.start)
        )
        remote = segments and any(
            observation.type == ObservationType.APP_STARTED
            and isinstance(observation.metadata, dict)
            and "intranet_resolved" in observation.metadata
            and work_location(observation.metadata, vpn_interface_patterns) == REMOTE
            for observation in day.observations
        )
        result.append(EureciaDay(day_date, segments, REMOTE_COMMENT if remote else ""))
    return tuple(result)


def format_timesheet(timesheet: EureciaTimesheet) -> str:
    status = f" [{timesheet.summary.status}]" if timesheet.summary.status else ""
    lines = [f"Eurecia timesheet - {timesheet.summary.label}{status}", ""]
    for day in timesheet.days:
        lines.append(f"{day.date.isoformat()}: {format_duration(day.worked_seconds)} worked")
        if not day.segments:
            lines.append("  - No segments")
            lines.append("")
            continue
        for index, segment in enumerate(day.segments):
            if index:
                previous = day.segments[index - 1]
                seconds = max(0, (_minutes(segment.start) - _minutes(previous.end)) * 60)
                if seconds:
                    lines.append(
                        f"  - Break: {previous.end} -> {segment.start} ({format_duration(seconds)})"
                    )
            lines.append(
                f"  - Work: {segment.start} -> {segment.end} ({format_duration(segment.seconds)})"
            )
        lines.append("")
    lines.append(f"Weekly total: {format_duration(timesheet.worked_seconds)}")
    return "\n".join(lines)


class EureciaHttpClient:
    """Small HTTP client for Eurecia's private legacy timesheet forms."""

    def __init__(self, base_url: str) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise EureciaError("Eurecia base URL must be an absolute HTTPS URL")
        self.base_url = base_url.rstrip("/") + "/"
        self._cookies = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookies)
        )

    def login(self, email: str, password: str) -> None:
        if not email or not password:
            raise EureciaError("Eurecia email and password are required")
        self._cookies.clear()
        self._request("GET", "login.do", accept="text/html")
        preflight = self._request(
            "GET",
            "login.do?" + urllib.parse.urlencode({"ajax": "false", "email": email}),
            accept="application/json, text/plain, */*",
        )
        redirect: str | None = None
        if "application/json" in preflight.headers.get("content-type", ""):
            try:
                redirect = json.loads(preflight.text()).get("redirectUrl")
            except (AttributeError, json.JSONDecodeError):
                redirect = None

        if redirect:
            self._login_sso(redirect, password)
        else:
            self._login_legacy(email, password)
        try:
            self._init_data()
        except EureciaConnectionError:
            raise
        except EureciaError as error:
            if redirect:
                raise EureciaAuthenticationError(
                    "The Eurecia SSO password form did not establish a session. The account "
                    "may require MFA or another interactive identity-provider step."
                ) from error
            raise EureciaAuthenticationError(
                "Eurecia login failed or the credentials were rejected."
            ) from error

    def _login_legacy(self, email: str, password: str) -> None:
        payload = urllib.parse.urlencode(
            {
                "requestedURL": "",
                "requestParams": "",
                "email": email,
                "password": password,
            }
        ).encode()
        self._request(
            "POST",
            "login.do",
            data=payload,
            content_type="application/x-www-form-urlencoded",
            accept="text/html,application/xhtml+xml",
        )

    def _login_sso(self, redirect: str, password: str) -> None:
        login_page = self._request_identity_provider("GET", redirect)
        parser = _parse_page(login_page.text())
        candidates: list[tuple[_Form, _Control]] = []
        for form in parser.forms:
            passwords = [
                control
                for control in form.controls
                if control.tag == "input" and control.type == "password" and control.name
            ]
            if len(passwords) == 1:
                candidates.append((form, passwords[0]))
        if len(candidates) != 1:
            raise EureciaError(
                "Expected exactly one password form on the Eurecia identity provider, "
                f"found {len(candidates)}"
            )
        form, password_control = candidates[0]
        submit_controls = [
            control
            for control in form.controls
            if control.tag in {"button", "input"} and control.type == "submit"
        ]
        if len(submit_controls) != 1:
            raise EureciaError(
                "Expected exactly one submit button on the Eurecia identity provider, "
                f"found {len(submit_controls)}"
            )
        submit = submit_controls[0]
        method = form.attrs.get("method", "GET").upper()
        if method != "POST":
            raise EureciaError(f"Expected the Eurecia SSO form to use POST, found {method}")
        action = urljoin(login_page.url, form.attrs.get("action", "") or login_page.url)
        payload = urllib.parse.urlencode(
            _form_payload(form, submit, {password_control.index: password}),
            doseq=True,
        ).encode()
        self._request_identity_provider(
            "POST",
            action,
            data=payload,
            content_type="application/x-www-form-urlencoded",
            referer=login_page.url,
        )

    def login_with_cookie(self, cookie_header: str) -> None:
        """Import an authenticated browser Cookie header into the in-memory jar."""
        value = cookie_header.strip()
        if value.casefold().startswith("cookie:"):
            value = value.split(":", 1)[1].strip()
        if not value or "\n" in value or "\r" in value:
            raise EureciaError("A single non-empty browser Cookie header is required")
        parsed = http.cookies.SimpleCookie()
        try:
            parsed.load(value)
        except http.cookies.CookieError as error:
            raise EureciaError("The browser Cookie header is invalid") from error
        if not parsed:
            raise EureciaError("No cookie was found in the browser Cookie header")

        host = urlsplit(self.base_url).hostname
        if host is None:
            raise EureciaError("The Eurecia tenant URL has no hostname")
        for name, morsel in parsed.items():
            self._cookies.set_cookie(
                http.cookiejar.Cookie(
                    version=0,
                    name=name,
                    value=morsel.value,
                    port=None,
                    port_specified=False,
                    domain=host,
                    domain_specified=False,
                    domain_initial_dot=False,
                    path="/",
                    path_specified=True,
                    secure=True,
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False,
                )
            )
        try:
            self._init_data()
        except EureciaError as error:
            self._cookies.clear()
            raise EureciaError(
                "The imported browser cookies did not establish an Eurecia session; "
                "copy the Cookie request header from a fresh authenticated initData request."
            ) from error

    def is_authenticated(self) -> bool:
        try:
            self._init_data()
        except EureciaError:
            return False
        return True

    def list_timesheets(self) -> tuple[EureciaTimesheetSummary, ...]:
        browse_link = _find_browse_link(self._init_data())
        response = self._request("GET", browse_link, accept="text/html")
        parser = _parse_page(response.text())
        summaries = list(_summaries_from_page(parser))
        current = self._current_timesheet_summary()
        if current is not None and not any(
            item.year == current.year and item.week == current.week for item in summaries
        ):
            summaries.append(current)
        summaries.sort(key=lambda item: (item.year, item.week), reverse=True)
        return tuple(summaries)

    def show_timesheet(self, year: int, week: int) -> EureciaTimesheet:
        summary = self._find_timesheet(year, week)
        return self._read_timesheet(summary)

    def capture_timesheet_html(
        self, year: int, week: int
    ) -> tuple[EureciaTimesheetSummary, _HttpResponse]:
        """Fetch an Open.do response without attempting to interpret its private HTML."""
        summary = self._find_timesheet(year, week)
        response = self._request("GET", summary.href, accept="text/html")
        return summary, response

    def set_standard_week(
        self,
        year: int,
        week: int,
        *,
        apply: bool = False,
    ) -> tuple[EureciaTimesheet, EureciaTimesheet, EureciaWrite | None]:
        target_days = standard_week(year, week)
        if apply:
            return self.replace_timesheet(year, week, target_days)
        summary = self._find_timesheet(year, week)
        _response, parser, form, controls = self._open_timesheet(summary)
        current = EureciaTimesheet(
            summary,
            _days_from_page(parser, form, iso_week_dates(year, week), controls),
        )
        return current, EureciaTimesheet(summary, target_days), None

    def replace_timesheet(
        self,
        year: int,
        week: int,
        target_days: tuple[EureciaDay, ...],
        progress: Callable[[str], None] | None = None,
    ) -> tuple[EureciaTimesheet, EureciaTimesheet, EureciaWrite]:
        days = iso_week_dates(year, week)
        targets = _validated_target_days(days, target_days)
        emit = progress or (lambda _message: None)

        emit(f"Recherche de la feuille Eurecia {year}-W{week:02d}.")
        summary = self._find_timesheet(year, week)
        if _normalize(summary.status or "") not in {"nouvelle", "new"}:
            status = repr(summary.status) if summary.status else "unknown"
            raise EureciaError(
                f"Timesheet {summary.label} has status {status}; refusing to edit it"
            )

        response, parser, form, controls = self._open_timesheet(summary)
        _find_save_control(form)
        current = EureciaTimesheet(
            summary,
            _days_from_page(parser, form, days, controls),
        )
        target = EureciaTimesheet(summary, targets)
        emit(f"Feuille trouvée avec le statut {summary.status}.")

        post_count = 0
        for target_day in targets:
            day = target_day.date
            emit(f"{day.isoformat()} : préparation de {len(target_day.segments)} segment(s).")
            rows = _legacy_rows_by_day(parser, form, days).get(day, ())
            if not rows:
                raise EureciaError(f"No Eurecia rows were found for {day.isoformat()}")
            if any(_legacy_row_is_standard(form, row) for row in rows):
                response = self._post_load_time(response, parser, form, day, rows[0])
                post_count += 1
                parser, form, controls = _parse_timesheet_response(response, days)
                rows = _legacy_rows_by_day(parser, form, days).get(day, ())
                if not rows or any(_legacy_row_is_standard(form, row) for row in rows):
                    raise EureciaError(
                        f"Eurecia did not expose editable rows for {day.isoformat()}"
                    )
                emit(f"{day.isoformat()} : mode Standard désactivé.")

            editable_rows = tuple(row for row in rows if _legacy_row_is_editable(form, row))
            locked_rows = tuple(row for row in rows if row not in editable_rows)
            expected_rows = len(target_day.segments) or (0 if locked_rows else 1)
            while len(editable_rows) < expected_rows:
                previous_count = len(editable_rows)
                response = self._post_legacy_action(
                    response,
                    form,
                    f"times=Copy=row_{editable_rows[-1] if editable_rows else rows[-1]}",
                )
                post_count += 1
                parser, form, controls = _parse_timesheet_response(response, days)
                rows = _legacy_rows_by_day(parser, form, days).get(day, ())
                editable_rows = tuple(row for row in rows if _legacy_row_is_editable(form, row))
                if len(editable_rows) != previous_count + 1:
                    raise EureciaError(f"Eurecia did not add a row for {day.isoformat()}")
                emit(f"{day.isoformat()} : ligne ajoutée.")
            while len(editable_rows) > expected_rows:
                previous_count = len(editable_rows)
                response = self._post_legacy_action(
                    response,
                    form,
                    f"times=Delete=row_{editable_rows[-1]}",
                )
                post_count += 1
                parser, form, controls = _parse_timesheet_response(response, days)
                rows = _legacy_rows_by_day(parser, form, days).get(day, ())
                editable_rows = tuple(row for row in rows if _legacy_row_is_editable(form, row))
                if len(editable_rows) != previous_count - 1:
                    raise EureciaError(f"Eurecia did not delete a row for {day.isoformat()}")
                emit(f"{day.isoformat()} : ligne supprimée.")

        overrides = _legacy_target_overrides(parser, form, days, targets)
        save_fields = _legacy_save_fields(form, overrides)
        payload, content_type = _encode_form_payload(form, save_fields)
        method, action = _post_form_target(response, form)
        emit("Sauvegarde de la feuille Eurecia.")
        saved = self._request(
            method,
            action,
            data=payload,
            content_type=content_type,
            accept="text/html,application/xhtml+xml",
            referer=response.url,
        )
        emit("Relecture et vérification des segments sauvegardés.")
        verified = self._read_timesheet(summary)
        _verify_target_days(verified, target)
        emit("Feuille Eurecia sauvegardée et vérifiée.")
        return (
            current,
            verified,
            EureciaWrite("POST", urlsplit(action).path, saved.status, post_count + 1),
        )

    def _post_load_time(
        self,
        response: _HttpResponse,
        parser: _LegacyPageParser,
        form: _Form,
        day: date,
        row: int,
    ) -> _HttpResponse:
        payload, content_type = _encode_form_payload(
            form,
            _legacy_load_time_payload(parser, form, day, row),
        )
        method, action = _post_form_target(response, form)
        return self._request(
            method,
            action,
            data=payload,
            content_type=content_type,
            accept="text/html,application/xhtml+xml",
            referer=response.url,
        )

    def _post_legacy_action(
        self,
        response: _HttpResponse,
        form: _Form,
        action_value: str,
    ) -> _HttpResponse:
        fields = _form_payload(form, None, {})
        fields.append(("ctrla", action_value))
        payload, content_type = _encode_form_payload(form, fields)
        method, action = _post_form_target(response, form)
        return self._request(
            method,
            action,
            data=payload,
            content_type=content_type,
            accept="text/html,application/xhtml+xml",
            referer=response.url,
        )

    def _init_data(self) -> dict[str, Any]:
        response = self._request("GET", "api/v3/users/me/initData", accept="application/json")
        if "application/json" not in response.headers.get("content-type", ""):
            raise EureciaError("Eurecia login failed or the session is not authenticated")
        try:
            data = json.loads(response.text())
        except json.JSONDecodeError as error:
            raise EureciaError("Eurecia returned invalid initData JSON") from error
        if not isinstance(data, dict) or not isinstance(data.get("user"), dict):
            raise EureciaError("Eurecia login failed or initData changed")
        return data

    def _current_timesheet_summary(self) -> EureciaTimesheetSummary | None:
        response = self._request(
            "GET", "api/v1/whatconcernsme/timesheet", accept="application/json"
        )
        try:
            data = json.loads(response.text())
        except json.JSONDecodeError:
            return None
        details = data.get("legacyDetails") if isinstance(data, dict) else None
        if not isinstance(details, dict):
            return None
        label = str(details.get("label", ""))
        match = _WEEK_PATTERN.search(label)
        href = str(details.get("actionLink", ""))
        if match is None or not href:
            return None
        return EureciaTimesheetSummary(
            year=int(match.group("year")),
            week=int(match.group("week")),
            label=label,
            href=href,
        )

    def _find_timesheet(self, year: int, week: int) -> EureciaTimesheetSummary:
        iso_week_dates(year, week)
        for summary in self.list_timesheets():
            if summary.year == year and summary.week == week:
                return summary
        raise EureciaError(
            f"Timesheet {year} week {week} was not found on the first Eurecia browse page"
        )

    def _read_timesheet(self, summary: EureciaTimesheetSummary) -> EureciaTimesheet:
        _response, parser, form, controls = self._open_timesheet(summary)
        return EureciaTimesheet(
            summary,
            _days_from_page(
                parser,
                form,
                iso_week_dates(summary.year, summary.week),
                controls,
            ),
        )

    def _open_timesheet(
        self, summary: EureciaTimesheetSummary
    ) -> tuple[_HttpResponse, _LegacyPageParser, _Form, dict[date, tuple[_Control, ...]]]:
        response = self._request("GET", summary.href, accept="text/html")
        parser = _parse_page(response.text())
        days = iso_week_dates(summary.year, summary.week)
        form, controls = _find_timesheet_form(parser, days)
        return response, parser, form, controls

    def _request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        content_type: str | None = None,
        accept: str = "*/*",
        referer: str | None = None,
    ) -> _HttpResponse:
        absolute = urljoin(self.base_url, url)
        base = urlsplit(self.base_url)
        target = urlsplit(absolute)
        if (target.scheme, target.netloc) != (base.scheme, base.netloc):
            raise EureciaError("Refusing to send an Eurecia request outside the configured tenant")
        headers = {
            "Accept": accept,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 bd1-eurecia/0.1"
            ),
        }
        if content_type:
            headers["Content-Type"] = content_type
        if referer:
            headers["Referer"] = referer
            headers["Origin"] = (
                f"{urlsplit(self.base_url).scheme}://{urlsplit(self.base_url).netloc}"
            )
        request = urllib.request.Request(absolute, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=30) as response:
                return _HttpResponse(
                    url=response.url,
                    status=response.status,
                    headers=response.headers,
                    body=response.read(),
                )
        except urllib.error.HTTPError as error:
            path = urlsplit(absolute).path
            raise EureciaConnectionError(
                f"Eurecia returned HTTP {error.code} for {method} {path}"
            ) from error
        except urllib.error.URLError as error:
            raise EureciaConnectionError(f"Cannot reach Eurecia: {error.reason}") from error

    def _request_identity_provider(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        content_type: str | None = None,
        referer: str | None = None,
    ) -> _HttpResponse:
        target = urlsplit(url)
        if target.scheme != "https" or target.hostname != _EURECIA_IDP_HOST:
            raise EureciaError("Refusing to send credentials outside the Eurecia identity provider")
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 bd1-eurecia/0.1"
            ),
        }
        if content_type:
            headers["Content-Type"] = content_type
        if referer:
            headers["Referer"] = referer
            headers["Origin"] = f"{target.scheme}://{target.netloc}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=30) as response:
                return _HttpResponse(
                    url=response.url,
                    status=response.status,
                    headers=response.headers,
                    body=response.read(),
                )
        except urllib.error.HTTPError as error:
            raise EureciaConnectionError(
                f"Eurecia identity provider returned HTTP {error.code}"
            ) from error
        except urllib.error.URLError as error:
            raise EureciaConnectionError(
                f"Cannot reach the Eurecia identity provider: {error.reason}"
            ) from error


def _parse_page(html: str) -> _LegacyPageParser:
    parser = _LegacyPageParser()
    parser.feed(html)
    parser.close()
    return parser


def _parse_timesheet_response(
    response: _HttpResponse,
    days: tuple[date, ...],
) -> tuple[_LegacyPageParser, _Form, dict[date, tuple[_Control, ...]]]:
    parser = _parse_page(response.text())
    form, controls = _find_timesheet_form(parser, days)
    return parser, form, controls


def _validated_target_days(
    week_days: tuple[date, ...],
    target_days: tuple[EureciaDay, ...],
) -> tuple[EureciaDay, ...]:
    expected = set(week_days)
    seen: set[date] = set()
    for target_day in target_days:
        if target_day.date not in expected:
            raise EureciaError(
                f"Target day {target_day.date.isoformat()} is outside the requested ISO week"
            )
        if target_day.date in seen:
            raise EureciaError(f"Duplicate target day: {target_day.date.isoformat()}")
        seen.add(target_day.date)
        previous: EureciaSegment | None = None
        for segment in target_day.segments:
            if previous is not None and _minutes(segment.start) < _minutes(previous.end):
                raise EureciaError(
                    f"Overlapping segments on {target_day.date.isoformat()}: "
                    f"{previous.start}-{previous.end} and {segment.start}-{segment.end}"
                )
            previous = segment
    return tuple(sorted(target_days, key=lambda item: item.date))


def _summaries_from_page(parser: _LegacyPageParser) -> tuple[EureciaTimesheetSummary, ...]:
    summaries: dict[tuple[int, int], EureciaTimesheetSummary] = {}
    for anchor in parser.anchors:
        row_text = _collapse(parser.row_text.get(anchor.row_key, [])) if anchor.row_key else ""
        text = f"{row_text} {anchor.text}".strip()
        match = _WEEK_PATTERN.search(text)
        if match is None:
            continue
        href = anchor.attrs.get("href", "")
        if not _is_timesheet_link(href):
            onclick = _ONCLICK_URL_PATTERN.search(anchor.attrs.get("onclick", ""))
            href = onclick.group("url") if onclick else ""
        if not _is_timesheet_link(href):
            continue
        year, week = int(match.group("year")), int(match.group("week"))
        status = _STATUS_PATTERN.search(text)
        summaries[(year, week)] = EureciaTimesheetSummary(
            year=year,
            week=week,
            label=match.group(0),
            href=href,
            status=status.group(0) if status else None,
        )
    return tuple(summaries[key] for key in sorted(summaries, reverse=True))


def _find_browse_link(init_data: dict[str, Any]) -> str:
    candidates: list[tuple[int, str]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            link = value.get("link")
            if isinstance(link, str) and "timesheet/Browse.do" in link:
                label = _normalize(str(value.get("label", "")))
                candidates.append((2 if "mes feuilles" in label else 1, link))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(init_data.get("userLeftMenu", []))
    if not candidates:
        raise EureciaError("The authenticated user has no personal timesheet menu entry")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _find_timesheet_form(
    parser: _LegacyPageParser,
    days: tuple[date, ...],
) -> tuple[_Form, dict[date, tuple[_Control, ...]]]:
    candidates: list[tuple[int, _Form, dict[date, tuple[_Control, ...]]]] = []
    for form in parser.forms:
        controls = _controls_by_day(parser, form, days)
        score = sum(
            _is_time_control(control) or _logical_row(control) is not None
            for control in form.controls
        )
        if score:
            candidates.append((score, form, controls))
    if not candidates:
        raise EureciaError(
            "No server-rendered timesheet form was found. Save a HAR with the Open.do body "
            "to update the lightweight adapter."
        )
    best_score = max(candidate[0] for candidate in candidates)
    best = [candidate for candidate in candidates if candidate[0] == best_score]
    if len(best) != 1:
        raise EureciaError("Ambiguous Eurecia page: multiple timesheet forms have the same score")
    _score, form, controls = best[0]
    mapped = {control.index for values in controls.values() for control in values}
    unmapped = [
        control
        for control in form.controls
        if _is_time_control(control) and control.index not in mapped
    ]
    if unmapped:
        raise EureciaError(f"Could not associate {len(unmapped)} Eurecia time field(s) with a date")
    return form, controls


def _controls_by_day(
    parser: _LegacyPageParser,
    form: _Form,
    days: tuple[date, ...],
) -> dict[date, tuple[_Control, ...]]:
    row_dates: dict[tuple[int, int], date] = {}
    column_dates: dict[tuple[int, int], date] = {}
    rows_by_table: dict[int, list[int]] = {}
    for row_key, parts in parser.row_text.items():
        rows_by_table.setdefault(row_key[0], []).append(row_key[1])
        matched = _match_date(_collapse(parts), days)
        if matched:
            row_dates[row_key] = matched
    for cell_key, parts in parser.cell_text.items():
        matched = _match_date(_collapse(parts), days)
        if matched:
            column_dates[(cell_key[0], cell_key[2])] = matched

    propagated: dict[tuple[int, int], date] = {}
    for table, rows in rows_by_table.items():
        active: date | None = None
        for row in sorted(rows):
            active = row_dates.get((table, row), active)
            if active:
                propagated[(table, row)] = active

    grouped: dict[date, list[_Control]] = {day: [] for day in days}
    for control in form.controls:
        context = _control_context(parser, control)
        matched = _match_date(context, days)
        if matched is None and control.cell_key:
            matched = column_dates.get((control.cell_key[0], control.cell_key[2]))
        if matched is None and control.row_key:
            matched = row_dates.get(control.row_key) or propagated.get(control.row_key)
        if matched:
            grouped[matched].append(control)
    return {day: tuple(values) for day, values in grouped.items()}


def _control_context(parser: _LegacyPageParser, control: _Control) -> str:
    values = list(control.attrs.values())
    if control.row_key:
        values.extend(parser.row_text.get(control.row_key, []))
    if control.cell_key:
        values.extend(parser.cell_text.get(control.cell_key, []))
    return " ".join(values)


def _days_from_controls(
    days: tuple[date, ...],
    controls: dict[date, tuple[_Control, ...]],
) -> tuple[EureciaDay, ...]:
    result: list[EureciaDay] = []
    for day in days:
        values = [control.value for control in controls.get(day, ()) if _is_time_control(control)]
        if len(values) % 2:
            raise EureciaError(
                f"Found an odd number of time fields on {day.isoformat()}: {len(values)}"
            )
        segments: list[EureciaSegment] = []
        for index in range(0, len(values), 2):
            start, end = values[index : index + 2]
            if not start and not end:
                continue
            if not _TIME_PATTERN.fullmatch(start) or not _TIME_PATTERN.fullmatch(end):
                raise EureciaError(f"Incomplete segment on {day.isoformat()}: {start!r} -> {end!r}")
            segments.append(EureciaSegment(start, end))
        result.append(EureciaDay(day, tuple(segments)))
    return tuple(result)


def _days_from_page(
    parser: _LegacyPageParser,
    form: _Form,
    days: tuple[date, ...],
    controls: dict[date, tuple[_Control, ...]],
) -> tuple[EureciaDay, ...]:
    legacy = _legacy_days(parser, form, days)
    if legacy is not None:
        return legacy
    return _days_from_controls(days, controls)


def _legacy_days(
    parser: _LegacyPageParser,
    form: _Form,
    days: tuple[date, ...],
) -> tuple[EureciaDay, ...] | None:
    controls_by_row = _legacy_controls_by_row(form)
    if not any(
        _legacy_row_is_editable(form, row) or _legacy_row_is_standard(form, row)
        for row in controls_by_row
    ):
        return None

    rows_by_day: dict[date, list[EureciaSegment]] = {day: [] for day in days}
    active_day: date | None = None
    for row, controls in sorted(controls_by_row.items()):
        row_text = _collapse(parser.row_text.get(controls[0].row_key, []))
        active_day = _match_date(row_text, days) or active_day
        if active_day is None:
            raise EureciaError(f"Cannot associate Eurecia row_{row} with a date")
        if not _legacy_row_is_editable(form, row) and not _legacy_row_is_standard(form, row):
            continue
        segment = _legacy_row_segment(row, row_text, controls)
        if segment is not None:
            rows_by_day[active_day].append(segment)
    return tuple(EureciaDay(day, tuple(rows_by_day[day])) for day in days)


def _legacy_rows_by_day(
    parser: _LegacyPageParser,
    form: _Form,
    days: tuple[date, ...],
) -> dict[date, tuple[int, ...]]:
    controls_by_row = _legacy_controls_by_row(form)
    if not controls_by_row:
        raise EureciaError("The Eurecia form has no legacy timesheet rows")

    grouped: dict[date, list[int]] = {day: [] for day in days}
    active_day: date | None = None
    for row, controls in sorted(controls_by_row.items()):
        row_text = _collapse(parser.row_text.get(controls[0].row_key, []))
        active_day = _match_date(row_text, days) or active_day
        if active_day is None:
            raise EureciaError(f"Cannot associate Eurecia row_{row} with a date")
        grouped[active_day].append(row)
    return {day: tuple(rows) for day, rows in grouped.items()}


def _legacy_controls_by_row(form: _Form) -> dict[int, list[_Control]]:
    grouped: dict[int, list[_Control]] = {}
    for control in form.controls:
        row = _logical_row(control)
        if row is not None and control.row_key is not None:
            grouped.setdefault(row, []).append(control)
    return grouped


def _legacy_row_is_standard(form: _Form, row: int) -> bool:
    controls = [
        control for control in form.controls if control.attrs.get("id") == f"standard_{row}"
    ]
    if not controls:
        return False
    if len(controls) != 1:
        raise EureciaError(
            f"Expected exactly one standard marker for Eurecia row_{row}, found {len(controls)}"
        )
    return controls[0].value.casefold() == "true"


def _legacy_row_is_editable(form: _Form, row: int) -> bool:
    expected = {
        f"startHour_Hours_{row}",
        f"startHour_Minutes_{row}",
        f"endHour_Hours_{row}",
        f"endHour_Minutes_{row}",
    }
    return expected <= {control.attrs.get("id", "") for control in form.controls}


def _legacy_load_time_payload(
    parser: _LegacyPageParser,
    form: _Form,
    day: date,
    row: int,
) -> list[tuple[str, str]]:
    checkboxes = [
        control
        for control in form.controls
        if _logical_row(control) == row
        and control.type == "checkbox"
        and _is_standard_checkbox(control)
    ]
    if len(checkboxes) != 1:
        raise EureciaError(
            f"Expected one Standard checkbox for Eurecia row_{row}, found {len(checkboxes)}"
        )
    checkbox = checkboxes[0]
    info_match = re.search(
        r"infoSelectedRow[^;]*\.value\s*=\s*['\"](?P<value>[^'\"]+)['\"]",
        checkbox.attrs.get("onclick", ""),
    )
    if info_match is None or day.strftime("%d/%m/%Y") not in info_match.group("value"):
        raise EureciaError(f"Cannot recover the LoadTime context for {day.isoformat()}")

    overrides: dict[int, str | None] = {}
    for control in form.controls:
        identifier = control.attrs.get("id", "")
        decoded_name = urllib.parse.unquote(control.name)
        if _logical_row(control) == row and "vcol=standard" in decoded_name:
            overrides[control.index] = None if control.type == "checkbox" else "false"
        elif identifier == "standardValueSelectedRow":
            overrides[control.index] = "false"
        elif identifier == "infoSelectedRow":
            overrides[control.index] = info_match.group("value")
    payload = _form_payload(form, None, overrides)
    payload.append(("ctrla", "timeSheetOpenForm=LoadTime"))
    return payload


def _legacy_target_overrides(
    parser: _LegacyPageParser,
    form: _Form,
    days: tuple[date, ...],
    target_days: tuple[EureciaDay, ...],
) -> dict[int, str | None]:
    rows_by_day = _legacy_rows_by_day(parser, form, days)
    target_by_day = {day.date: day for day in target_days}
    overrides: dict[int, str | None] = {}
    for day, target_day in target_by_day.items():
        segments = target_day.segments
        all_rows = rows_by_day.get(day, ())
        rows = tuple(row for row in all_rows if _legacy_row_is_editable(form, row))
        locked_rows = tuple(row for row in all_rows if row not in rows)
        expected_rows = len(segments) or (0 if locked_rows else 1)
        if len(rows) != expected_rows:
            raise EureciaError(
                f"Expected {expected_rows} editable rows for {day.isoformat()}, found {len(rows)}"
            )
        for index, row in enumerate(rows):
            segment = segments[index] if index < len(segments) else None
            values = {
                f"startHour_Hours_{row}": segment.start[:2] if segment else "00",
                f"startHour_Minutes_{row}": segment.start[3:] if segment else "00",
                f"endHour_Hours_{row}": segment.end[:2] if segment else "00",
                f"endHour_Minutes_{row}": segment.end[3:] if segment else "00",
            }
            found: set[str] = set()
            for control in form.controls:
                identifier = control.attrs.get("id", "")
                if identifier in values:
                    overrides[control.index] = values[identifier]
                    found.add(identifier)
                elif identifier in {f"generatedItem_{row}", f"duplicatedItem_{row}"}:
                    overrides[control.index] = "false"
                elif identifier == f"comment_{row}":
                    overrides[control.index] = _managed_comment(
                        control.value,
                        target_day.comment if index == 0 else "",
                    )
                elif _logical_row(control) == row and "vcol=standard" in urllib.parse.unquote(
                    control.name
                ):
                    overrides[control.index] = None if control.type == "checkbox" else "false"
            if found != set(values):
                missing = ", ".join(sorted(set(values) - found))
                raise EureciaError(
                    f"Missing editable time selectors for Eurecia row_{row}: {missing}"
                )

    validate_controls = [
        control for control in form.controls if control.attrs.get("id") == "validate"
    ]
    if len(validate_controls) != 1:
        raise EureciaError(
            f"Expected exactly one Eurecia validate field, found {len(validate_controls)}"
        )
    overrides[validate_controls[0].index] = "2"
    return overrides


def _managed_comment(current: str, managed: str) -> str:
    lines = [line for line in current.splitlines() if line.strip() != REMOTE_COMMENT]
    if managed:
        lines.append(managed)
    return "\n".join(lines)


def _post_form_target(response: _HttpResponse, form: _Form) -> tuple[str, str]:
    method = form.attrs.get("method", "GET").upper()
    if method != "POST":
        raise EureciaError(f"Expected the Eurecia form to use POST, found {method}")
    action = urljoin(response.url, form.attrs.get("action", "") or response.url)
    return method, action


def _encode_form_payload(
    form: _Form,
    fields: list[tuple[str, str]],
) -> tuple[bytes, str]:
    enctype = form.attrs.get("enctype", "application/x-www-form-urlencoded").casefold()
    if enctype == "application/x-www-form-urlencoded":
        return urllib.parse.urlencode(fields, doseq=True).encode(), enctype
    if enctype != "multipart/form-data":
        raise EureciaError(f"Unsupported Eurecia form encoding: {enctype}")

    boundary = f"----bd1-eurecia-{secrets.token_hex(16)}"
    chunks: list[bytes] = []
    for name, value in fields:
        if any(character in name for character in '\r\n"'):
            raise EureciaError("Unsafe field name in the Eurecia multipart form")
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            )
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _legacy_save_fields(
    form: _Form,
    overrides: dict[int, str | None],
) -> list[tuple[str, str]]:
    save_control = _find_save_control(form)
    save_field = save_control.attrs.get("id") or save_control.name
    if not save_field:
        raise EureciaError("The Eurecia Enregistrer control has no field name or id")
    fields = _form_payload(form, None, overrides)
    fields.append((save_field, "clicked"))
    return fields


def _legacy_row_segment(
    row: int,
    row_text: str,
    controls: list[_Control],
) -> EureciaSegment | None:
    selected: dict[str, str] = {}
    for control in controls:
        identifier = control.attrs.get("id", "")
        for field_name in (
            "startHour_Hours",
            "startHour_Minutes",
            "endHour_Hours",
            "endHour_Minutes",
        ):
            if identifier == f"{field_name}_{row}":
                selected[field_name] = control.value
    if selected:
        expected = {
            "startHour_Hours",
            "startHour_Minutes",
            "endHour_Hours",
            "endHour_Minutes",
        }
        if set(selected) != expected:
            raise EureciaError(f"Incomplete time selectors for Eurecia row_{row}")
        start = f"{selected['startHour_Hours']}:{selected['startHour_Minutes']}"
        end = f"{selected['endHour_Hours']}:{selected['endHour_Minutes']}"
        if start == end == "00:00":
            return None
        return EureciaSegment(start, end)

    values = [
        re.sub(r"\s+", "", value)
        for value in re.findall(r"\b(?:[01]\d|2[0-3])\s*:\s*[0-5]\d\b", row_text)
    ]
    if (
        not values
        or all(value == "00:00" for value in values)
        or values[:3] == ["00:00", "00:00", "00:00"]
    ):
        return None
    candidates: list[EureciaSegment] = []
    for start, end, duration in zip(values, values[1:], values[2:], strict=False):
        if _minutes(end) <= _minutes(start):
            continue
        if _minutes(end) - _minutes(start) != _minutes(duration):
            continue
        candidates.append(EureciaSegment(start, end))
    if len(candidates) != 1:
        raise EureciaError(
            f"Expected one displayed segment in Eurecia row_{row}, found {len(candidates)}"
        )
    return candidates[0]


def _logical_row(control: _Control) -> int | None:
    metadata = urllib.parse.unquote(" ".join((control.name, control.attrs.get("id", ""))))
    match = re.search(r"(?:row=row_|_(?=\d+\b))(?P<row>\d+)", metadata)
    return int(match.group("row")) if match else None


def _find_save_control(form: _Form) -> _Control:
    def is_save(control: _Control) -> bool:
        return bool(
            {
                _normalize(" ".join(control.text_parts)),
                _normalize(control.attrs.get("value", "")),
            }
            & {"enregistrer", "save"}
        )

    apply_controls = [control for control in form.controls if control.attrs.get("id") == "btnApply"]
    save_controls = [control for control in apply_controls if is_save(control)]
    if len(save_controls) == 1:
        return save_controls[0]
    if len(save_controls) > 1:
        raise EureciaError(
            f"Expected exactly one Enregistrer control in the form, found {len(save_controls)}"
        )
    if len(apply_controls) == 1:
        return apply_controls[0]

    controls = [
        control
        for control in form.controls
        if control.tag in {"button", "input"}
        and control.type in {"submit", "button"}
        and is_save(control)
    ]
    if len(controls) == 1:
        return controls[0]
    if len(controls) > 1:
        raise EureciaError(
            f"Expected exactly one Enregistrer control in the form, found {len(controls)}"
        )

    validate_fields = [
        control for control in form.controls if control.attrs.get("id") == "validate"
    ]
    if len(validate_fields) == 1:
        return _Control(
            index=-1,
            tag="input",
            attrs={"id": "btnApply"},
            row_key=None,
            cell_key=None,
        )
    raise EureciaError("The Eurecia form has no unambiguous Enregistrer control")


def _form_payload(
    form: _Form,
    save_control: _Control | None,
    overrides: dict[int, str | None],
) -> list[tuple[str, str]]:
    payload: list[tuple[str, str]] = []
    for control in form.controls:
        if not control.name:
            continue
        override_present = control.index in overrides
        override = overrides.get(control.index)
        if override_present and override is None:
            continue
        if "disabled" in control.attrs and not override_present:
            continue
        if control.type in {"reset", "file"}:
            continue
        if control.type in {"submit", "button", "image"} and control is not save_control:
            continue
        if control.type in {"checkbox", "radio"} and "checked" not in control.attrs:
            continue
        values = [override] if override_present else control.values or [control.value]
        payload.extend((control.name, value) for value in values if value is not None)
    return payload


def _is_time_control(control: _Control) -> bool:
    if control.tag != "input" or control.type not in {"text", "time", "tel"}:
        return False
    if not _TIME_PATTERN.fullmatch(control.value):
        return False
    metadata = _normalize(" ".join(control.attrs.values()))
    return not re.search(r"\b(total|duree|duration|quantity|quantite|synthese)\b", metadata)


def _is_standard_checkbox(control: _Control) -> bool:
    return control.type == "checkbox" and "standard" in _normalize(" ".join(control.attrs.values()))


def _verify_target_days(actual: EureciaTimesheet, target: EureciaTimesheet) -> None:
    actual_days = {day.date: day.segments for day in actual.days}
    mismatches = [
        day.date.isoformat() for day in target.days if actual_days.get(day.date) != day.segments
    ]
    if mismatches:
        raise EureciaError(
            "The page was saved but verification failed for: " + ", ".join(mismatches)
        )


def _match_date(value: str, days: tuple[date, ...]) -> date | None:
    normalized = _normalize(value)
    for day in days:
        if any(pattern in normalized for pattern in _date_patterns(day)):
            return day
    return None


def _date_patterns(day: date) -> tuple[str, ...]:
    month = _FRENCH_MONTHS[day.month - 1]
    weekday = _FRENCH_WEEKDAYS[day.weekday()]
    return tuple(
        _normalize(value)
        for value in (
            day.isoformat(),
            day.strftime("%d/%m/%Y"),
            day.strftime("%d/%m/%y"),
            day.strftime("%d/%m"),
            f"{day.day} {month} {day.year}",
            f"{day.day:02d} {month} {day.year}",
            f"{weekday} {day.day} {month}",
            f"{weekday} {day.day:02d} {month}",
        )
    )


def _is_timesheet_link(href: str) -> bool:
    lowered = href.casefold()
    return "timesheet/" in lowered and ("action=edit" in lowered or "open.do" in lowered)


def _minutes(value: str) -> int:
    hours, minutes = value.split(":", 1)
    return int(hours) * 60 + int(minutes)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().split())


def _collapse(parts: Iterable[str]) -> str:
    return " ".join(" ".join(parts).split())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Use Eurecia's private HTTP forms without browser automation."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BD1_EURECIA_BASE_URL"),
        help="Tenant base URL, or set BD1_EURECIA_BASE_URL.",
    )
    parser.add_argument(
        "--email",
        default=os.environ.get("BD1_EURECIA_EMAIL"),
        help="Eurecia email, or set BD1_EURECIA_EMAIL.",
    )
    parser.add_argument(
        "--browser-session",
        action="store_true",
        help="Import an authenticated browser Cookie header instead of using a password.",
    )
    parser.add_argument(
        "--remember-password",
        action="store_true",
        help="Store a successfully authenticated password in the system credential store.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List timesheets visible on the first browse page.")
    show = commands.add_parser("show", help="Display a timesheet with BD-1-like segments.")
    _add_week_arguments(show)
    capture = commands.add_parser(
        "capture-html",
        help="Save an Open.do response locally for adapter diagnostics.",
    )
    _add_week_arguments(capture)
    capture.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New private output file; existing files are never overwritten.",
    )
    set_week = commands.add_parser(
        "set-standard-week",
        help="Set Monday-Friday to 09:00-12:00 and 14:00-18:00.",
    )
    _add_week_arguments(set_week)
    set_week.add_argument(
        "--apply",
        action="store_true",
        help="POST Enregistrer and verify. Without this flag, only preview.",
    )
    return parser


def _add_week_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--year", type=int, required=True, help="ISO week year.")
    parser.add_argument("--week", type=int, required=True, help="ISO week number.")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.base_url:
        parser.error("--base-url or BD1_EURECIA_BASE_URL is required")
    if args.browser_session and args.remember_password:
        parser.error("--remember-password cannot be used with --browser-session")
    try:
        client = EureciaHttpClient(args.base_url)
        if args.browser_session:
            cookie_header = getpass.getpass("Authenticated browser Cookie header: ")
            client.login_with_cookie(cookie_header)
        else:
            email = args.email or input("Eurecia email: ").strip()
            login_interactively(
                client,
                email,
                remember_password=args.remember_password,
            )
        if args.command == "list":
            summaries = client.list_timesheets()
            if not summaries:
                print("No timesheets found.")
            for summary in summaries:
                status = summary.status or "unknown status"
                print(f"{summary.year}-W{summary.week:02d}  {status:14}  {summary.label}")
        elif args.command == "show":
            print(format_timesheet(client.show_timesheet(args.year, args.week)))
        elif args.command == "capture-html":
            summary, response = client.capture_timesheet_html(args.year, args.week)
            output = _write_private_capture(args.output, response.body)
            print(
                f"Captured {summary.label}: {len(response.body)} bytes from "
                f"{urlsplit(response.url).path} into {output} (mode 0600)."
            )
        else:
            current, result, write = client.set_standard_week(
                args.year,
                args.week,
                apply=args.apply,
            )
            print("Current Eurecia value:\n")
            print(format_timesheet(current))
            print("\nTarget value:\n" if not args.apply else "\nSaved and verified value:\n")
            print(format_timesheet(result))
            if write:
                print(
                    f"\nObserved write sequence: {write.requests} {write.method} requests; "
                    f"final {write.path} -> {write.status}"
                )
            else:
                print("\nPreview only. Re-run with --apply to save.")
    except EureciaError as error:
        parser.exit(2, f"bd1-eurecia: {error}\n")


def _write_private_capture(path: Path, body: bytes) -> Path:
    output = path.expanduser().resolve()
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise EureciaError(f"Refusing to overwrite existing capture: {output}") from error
    except OSError as error:
        raise EureciaError(f"Cannot create capture {output}: {error.strerror}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
    except OSError as error:
        with suppress(OSError):
            output.unlink()
        raise EureciaError(f"Cannot write capture {output}: {error.strerror}") from error
    return output


if __name__ == "__main__":
    main()
