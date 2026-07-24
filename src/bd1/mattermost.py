# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from bd1.network import OFFICE, REMOTE

KEYRING_SERVICE = "BD-1 Mattermost"
HTTP_TIMEOUT_SECONDS = 10
STATUSES = {
    OFFICE: {"emoji": "office", "text": "In the office"},
    REMOTE: {"emoji": "house", "text": "Working remotely"},
}


class MattermostError(RuntimeError):
    pass


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        return None


def normalize_server_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Mattermost URL must be an HTTPS URL without credentials or a query.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def get_token(server_url: str) -> str | None:
    try:
        return keyring.get_password(KEYRING_SERVICE, server_url)
    except KeyringError as error:
        raise MattermostError(f"Credential store unavailable: {error}") from error


def store_token(server_url: str, token: str) -> None:
    try:
        keyring.set_password(KEYRING_SERVICE, server_url, token)
    except KeyringError as error:
        raise MattermostError(f"Could not store Mattermost token: {error}") from error


def delete_token(server_url: str) -> None:
    try:
        if keyring.get_password(KEYRING_SERVICE, server_url) is not None:
            keyring.delete_password(KEYRING_SERVICE, server_url)
    except PasswordDeleteError:
        return
    except KeyringError as error:
        raise MattermostError(f"Could not remove Mattermost token: {error}") from error


def verify_token(server_url: str, token: str) -> None:
    user = _request(server_url, token, "/api/v4/users/me")
    if not isinstance(user, dict) or not user.get("id"):
        raise MattermostError("Mattermost returned an invalid user response.")


def sync_custom_status(
    server_url: str,
    token: str,
    location: str,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now().astimezone()
    current = _current_custom_status(server_url, token, now)
    desired = STATUSES[location]
    if current is not None and not _is_bd1_status(current):
        return "manual"
    if current is not None and all(current.get(key) == value for key, value in desired.items()):
        return "unchanged"

    expires_at = datetime.combine(
        now.date() + timedelta(days=1),
        time.min,
        tzinfo=now.tzinfo,
    )
    _request(
        server_url,
        token,
        "/api/v4/users/me/status/custom",
        method="PUT",
        payload={**desired, "duration": "today", "expires_at": expires_at.isoformat()},
    )
    return "updated"


def remove_bd1_status(server_url: str, token: str) -> bool:
    current = _current_custom_status(server_url, token, datetime.now().astimezone())
    if current is None or not _is_bd1_status(current):
        return False
    _request(server_url, token, "/api/v4/users/me/status/custom", method="DELETE")
    return True


def _current_custom_status(
    server_url: str,
    token: str,
    now: datetime,
) -> dict[str, object] | None:
    user = _request(server_url, token, "/api/v4/users/me")
    if not isinstance(user, dict):
        raise MattermostError("Mattermost returned an invalid user response.")

    props = user.get("props")
    raw = props.get("customStatus") if isinstance(props, dict) else None
    if not raw:
        return None
    try:
        status = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as error:
        raise MattermostError("Mattermost returned an invalid custom status.") from error
    if not isinstance(status, dict):
        raise MattermostError("Mattermost returned an invalid custom status.")

    expires_at = status.get("expires_at")
    if isinstance(expires_at, str):
        try:
            if datetime.fromisoformat(expires_at) <= now:
                return None
        except (TypeError, ValueError) as error:
            raise MattermostError("Mattermost returned an invalid custom status expiry.") from error
    return status


def _is_bd1_status(status: dict[str, object]) -> bool:
    return any(
        all(status.get(key) == value for key, value in item.items()) for item in STATUSES.values()
    )


def _request(
    server_url: str,
    token: str,
    path: str,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> object:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{server_url}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with build_opener(_NoRedirects).open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read()
    except HTTPError as error:
        raise MattermostError(f"Mattermost request failed with HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        detail = error.reason if isinstance(error, URLError) else error
        raise MattermostError(f"Mattermost request failed: {detail}") from error

    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError as error:
        raise MattermostError("Mattermost returned invalid JSON.") from error
