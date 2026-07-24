# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import socket
from fnmatch import fnmatchcase

import psutil

from bd1.settings import DEFAULT_VPN_INTERFACE_PATTERNS

INTRANET_HOSTNAME = "intranet.obeo.fr"
INTRANET_PORT = 443
OFFICE = "office"
REMOTE = "remote"


def network_status(hostname: str = INTRANET_HOSTNAME) -> dict[str, object]:
    status: dict[str, object] = {
        "intranet_hostname": hostname,
        "intranet_resolved": False,
    }
    try:
        addresses = socket.getaddrinfo(hostname, INTRANET_PORT, type=socket.SOCK_STREAM)
    except OSError:
        return status

    if not addresses:
        return status

    status["intranet_resolved"] = True
    for family, _, _, _, remote_address in addresses:
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as connection:
                connection.connect(remote_address)
                local_address = connection.getsockname()[0]
        except OSError:
            continue

        status["local_address"] = local_address
        interface = _interface_for(local_address)
        if interface is not None:
            status["network_interface"] = interface
        break
    return status


def _interface_for(local_address: str) -> str | None:
    address = local_address.split("%", 1)[0]
    try:
        interfaces = psutil.net_if_addrs()
    except psutil.Error:
        return None

    for name, addresses in interfaces.items():
        if any(
            entry.family in (socket.AF_INET, socket.AF_INET6)
            and entry.address.split("%", 1)[0] == address
            for entry in addresses
        ):
            return name
    return None


def work_location(
    status: dict[str, object],
    vpn_interface_patterns: tuple[str, ...] = DEFAULT_VPN_INTERFACE_PATTERNS,
) -> str:
    if not status.get("intranet_resolved"):
        return REMOTE

    interface = status.get("network_interface")
    if not isinstance(interface, str) or not interface:
        return REMOTE

    name = interface.casefold()
    # ponytail: interface names are heuristic; use native adapter types if renamed VPNs appear.
    if any(fnmatchcase(name, pattern.casefold()) for pattern in vpn_interface_patterns):
        return REMOTE
    return OFFICE
